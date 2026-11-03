#
#    Copyright (c) 2026 Manuel Hilgert
#
#    See the file LICENSE.txt for your full rights.
#
"""The server side of the wall display: what the templates of the skin cannot do.

The display reads everything from the web server, from files that the report of the
skin Display writes. Most of them come from its templates and from the JSON generator.
This module adds the three parts that need code:

  DisplayLive      A service. It writes the latest readings, in the units of the report,
                   every few seconds to a file in memory. The web server hands it out
                   as live.json.
  DisplayForecast  A service. It asks Open-Meteo for a forecast, once an hour, in a
                   thread of its own, and writes forecast.json into the HTML_ROOT of the
                   report.
  DisplaySky       A search list extension. It gives the templates $sky, the course of
                   the sun and the phase of the moon, and $display, the tables that
                   station.json needs and that no tag of WeeWX offers.

The options are in the section [Display] of weewx.conf. install.py writes them, and the
README of the repository explains them.
"""

import datetime
import json
import logging
import math
import os
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import weeutil.weeutil
import weewx
import weewx.cheetahgenerator
import weewx.engine
import weewx.reportengine
import weewx.units
from weeutil.weeutil import to_float, to_int

log = logging.getLogger(__name__)

# The version of the format of live.json, forecast.json and sky.json, as
# "<major>.<minor>". The display refuses a file whose major number it does not know.
FORMAT_VERSION = '1.0'

DEFAULT_REPORT = 'DisplayReport'

# One astronomical unit and the speed of light, in km and km/s.
AU_KM = 149597870.7
LIGHT_KM_S = 299792.458

# The mean length of a lunation, in days.
SYNODIC_MONTH = 29.530588


def report_skin_dict(config_dict, report_name):
    """Build the skin dictionary of a report, as the report engine builds it.

    Args:
        config_dict (dict): The configuration of WeeWX.
        report_name (str): The name of the report under [StdReport], e.g.,
            'DisplayReport'.

    Returns:
        configobj.ConfigObj|None: The skin dictionary, with the units and the language
            of the report merged in. None if [StdReport] has no such report.
    """
    if report_name not in config_dict.get('StdReport', {}):
        return None
    return weewx.reportengine.build_skin_dict(config_dict, report_name)


def write_json(payload, path):
    """Write payload to path as JSON, replacing the file in one step.

    The display may fetch the file at any moment. It gets the old file or the new one,
    never one half written.

    Args:
        payload (dict): What to write.
        path (str): The file to write.
    """
    folder = os.path.dirname(os.path.abspath(path))
    handle, temporary = tempfile.mkstemp(dir=folder, suffix='.tmp')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(',', ':'))
        # mkstemp() creates the file readable by its owner only. The web server runs as
        # another user.
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


# ===============================================================================
#                              The live readings
# ===============================================================================

class DisplayLive(weewx.engine.StdService):
    """Write the latest readings to live.json, a few seconds apart.

    The readings are numbers in the units of the report, the same units as in every other
    file of the report. station.json names the unit of each type.

    By default, live.json goes into the HTML_ROOT of the report, where the web server
    finds it without further setup. On a machine with an SD card, option 'live_path' can
    put it into memory instead, e.g., /run/weewx/live.json, with a line in the
    configuration of the web server that serves it from there.
    """

    def __init__(self, engine, config_dict):
        super().__init__(engine, config_dict)
        options = config_dict.get('Display', {})
        self.interval = to_float(options.get('live_interval', 2.0))
        # A sensor that stops sending must not keep its last reading forever. After
        # 'live_max_age' seconds without a new one, its type is left out of live.json.
        self.max_age = to_float(options.get('live_max_age', 600))
        report_name = options.get('report', DEFAULT_REPORT)
        skin_dict = report_skin_dict(config_dict, report_name)
        if skin_dict is None:
            log.error("No report '%s' under [StdReport]. live.json is not written.",
                      report_name)
            return
        self.path = options.get('live_path') or os.path.join(
            config_dict['WEEWX_ROOT'], skin_dict['HTML_ROOT'], 'live.json')
        self.converter = weewx.units.Converter.fromSkinDict(skin_dict)
        # Ecowitt and Davis packets each carry only some of the observation types. The
        # display needs all of them, so they are collected across packets: name ->
        # (value, unit system, time received).
        self.readings = {}
        self.written = 0
        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)

    def new_loop_packet(self, event):
        packet = event.packet
        now = time.time()
        for name, value in packet.items():
            if name in ('dateTime', 'usUnits') or not isinstance(value, (int, float)):
                continue
            self.readings[name] = (value, packet['usUnits'], now)
        if now - self.written < self.interval:
            return
        self.written = now
        values = {}
        for name, (value, unit_system, received) in list(self.readings.items()):
            if now - received > self.max_age:
                del self.readings[name]
                continue
            converted = self.converter.convert(weewx.units.as_value_tuple(
                {name: value, 'usUnits': unit_system}, name)).value
            if converted is not None:
                values[name] = round(converted, 3)
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            write_json({'version': FORMAT_VERSION, 'time': packet['dateTime'],
                        'values': values}, self.path)
        except OSError as error:
            log.debug("Cannot write %s: %s", self.path, error)


# ===============================================================================
#                                The forecast
# ===============================================================================

OPEN_METEO = 'https://api.open-meteo.com/v1/forecast'

# The fields asked of Open-Meteo. to_forecast() reads them by these names.
DAILY_FIELDS = ('weather_code', 'temperature_2m_max', 'temperature_2m_min',
                'precipitation_probability_max', 'precipitation_sum',
                'wind_speed_10m_max', 'wind_gusts_10m_max',
                'wind_direction_10m_dominant', 'sunshine_duration', 'uv_index_max')
HOURLY_FIELDS = ('weather_code', 'temperature_2m', 'precipitation_probability',
                 'precipitation', 'wind_speed_10m', 'wind_direction_10m', 'is_day')


def fetch_forecast(lat, lon, days, timeout):
    """Ask Open-Meteo for a forecast.

    Args:
        lat (float): The latitude of the station, in degrees north.
        lon (float): The longitude of the station, in degrees east.
        days (int): How many days to ask for, today included.
        timeout (float): How long to wait for the answer, in seconds.

    Returns:
        dict: Open-Meteo's answer, decoded from JSON.

    Raises:
        OSError: If the request fails or times out. urllib.error.URLError is an
            OSError.
        ValueError: If the answer is not JSON.
    """
    query = urllib.parse.urlencode({
        'latitude': lat,
        'longitude': lon,
        'daily': ','.join(DAILY_FIELDS),
        'hourly': ','.join(HOURLY_FIELDS),
        'timezone': 'auto',
        'timeformat': 'unixtime',
        'forecast_days': days,
    })
    request = urllib.request.Request('%s?%s' % (OPEN_METEO, query),
                                     headers={'User-Agent': 'weewx-display/1.0'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def to_forecast(said, now, hours):
    """Convert Open-Meteo's answer into the format of forecast.json.

    The format, in full:

        {"version": "1.0",
         "source":  "open-meteo",
         "fetched": int,              when the answer came, epoch seconds
         "units":   {"temperature": "degree_C", "speed": "km_per_hour",
                     "rain": "mm", "direction": "degree_compass"},
         "days":    [{"time": int,    local midnight of the day, epoch seconds
                      "code": int,    WMO 4677 weather code
                      "high": float, "low": float,
                      "rain_chance": int|null,  per cent
                      "rain": float|null,       total of the day
                      "wind": float|null, "gust": float|null, "dir": int|null,
                      "sun": int|null,          seconds of sunshine
                      "uv": float|null}],
         "hours":   [{"time": int, "code": int, "temp": float,
                      "rain_chance": int|null, "rain": float|null,
                      "wind": float|null, "dir": int|null, "day": bool}]}

    The units are names of WeeWX units. The display converts them into the units of the
    report with the table in meta.json.

    Args:
        said (dict): Open-Meteo's answer, as fetch_forecast() returns it.
        now (int): The time of the answer, in epoch seconds. The hours before the
            current one are left out.
        hours (int): How many hours to keep, counting from the current one.

    Returns:
        dict: The forecast, in the format above.
    """
    daily = said.get('daily') or {}
    hourly = said.get('hourly') or {}

    def column(source, name, index):
        values = source.get(name) or []
        return values[index] if index < len(values) else None

    days = [{
        'time': when,
        'code': column(daily, 'weather_code', i),
        'high': column(daily, 'temperature_2m_max', i),
        'low': column(daily, 'temperature_2m_min', i),
        'rain_chance': column(daily, 'precipitation_probability_max', i),
        'rain': column(daily, 'precipitation_sum', i),
        'wind': column(daily, 'wind_speed_10m_max', i),
        'gust': column(daily, 'wind_gusts_10m_max', i),
        'dir': column(daily, 'wind_direction_10m_dominant', i),
        'sun': to_int(column(daily, 'sunshine_duration', i)),
        'uv': column(daily, 'uv_index_max', i),
    } for i, when in enumerate(daily.get('time') or [])]

    # An hour stays in the file while it is in progress: the hour that began at 14:00
    # is still the current one at 14:59.
    hour_entries = [{
        'time': when,
        'code': column(hourly, 'weather_code', i),
        'temp': column(hourly, 'temperature_2m', i),
        'rain_chance': column(hourly, 'precipitation_probability', i),
        'rain': column(hourly, 'precipitation', i),
        'wind': column(hourly, 'wind_speed_10m', i),
        'dir': column(hourly, 'wind_direction_10m', i),
        'day': bool(column(hourly, 'is_day', i)),
    } for i, when in enumerate(hourly.get('time') or []) if when + 3600 > now]

    return {
        'version': FORMAT_VERSION,
        'source': 'open-meteo',
        'fetched': int(now),
        'units': {'temperature': 'degree_C', 'speed': 'km_per_hour', 'rain': 'mm',
                  'direction': 'degree_compass'},
        'days': days,
        'hours': hour_entries[:hours],
    }


class DisplayForecast(weewx.engine.StdService):
    """Fetch the forecast once an hour, in a thread of its own.

    The thread keeps the request out of the main loop and out of the report cycle: a slow
    answer from Open-Meteo delays neither the readings nor the reports.
    """

    def __init__(self, engine, config_dict):
        super().__init__(engine, config_dict)
        options = config_dict.get('Display', {})
        self.interval = to_int(options.get('forecast_interval', 3600))
        self.days = to_int(options.get('forecast_days', 7))
        # Seven days of hours, so that the display can show the hours of every day of
        # the forecast, not only of the next two.
        self.hours = to_int(options.get('forecast_hours', 168))
        self.timeout = to_float(options.get('forecast_timeout', 20))
        self.stop = threading.Event()
        self.thread = None
        if not self.interval:
            log.info("forecast_interval is 0. No forecast is fetched.")
            return
        report_name = options.get('report', DEFAULT_REPORT)
        skin_dict = report_skin_dict(config_dict, report_name)
        if skin_dict is None:
            log.error("No report '%s' under [StdReport]. No forecast is fetched.",
                      report_name)
            return
        self.path = os.path.join(config_dict['WEEWX_ROOT'], skin_dict['HTML_ROOT'],
                                 'forecast.json')
        station = config_dict['Station']
        self.lat = to_float(station['latitude'])
        self.lon = to_float(station['longitude'])
        self.thread = threading.Thread(target=self.run, name='DisplayForecast',
                                       daemon=True)
        self.thread.start()

    def run(self):
        # A restart of WeeWX must not ask Open-Meteo again while the file on disk is
        # still fresh. Restarts are frequent while a station is being set up.
        try:
            age = time.time() - os.path.getmtime(self.path)
        except OSError:
            age = self.interval
        wait = max(0.0, self.interval - age)
        while not self.stop.wait(wait):
            wait = self.interval
            try:
                said = fetch_forecast(self.lat, self.lon, self.days, self.timeout)
                payload = to_forecast(said, int(time.time()), self.hours)
                if not payload['days']:
                    raise ValueError("no days in the answer")
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                write_json(payload, self.path)
                log.debug("Wrote %s", self.path)
            except (OSError, ValueError) as error:
                # The old file stays, because an old forecast is better than none. The
                # display shows its age. Try again in ten minutes, not in an hour.
                log.error("Cannot fetch the forecast: %s", error)
                wait = min(self.interval, 600)

    def shutDown(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(5)


# ===============================================================================
#                               The sun and the moon
# ===============================================================================

def posix_timezone(path='/etc/localtime'):
    """Return the time zone of this machine as a POSIX TZ string.

    The display keeps its clock with SNTP and needs the rule for summer time, which only
    a POSIX string carries for a microcontroller. A TZif file of version 2 or later ends
    with that string, between two newlines.

    Args:
        path (str): The TZif file. Default is '/etc/localtime'.

    Returns:
        str|None: E.g., 'CET-1CEST,M3.5.0,M10.5.0/3'. None if the file has no such
            footer.
    """
    try:
        with open(path, 'rb') as stream:
            content = stream.read()
    except OSError:
        return None
    if not content.startswith(b'TZif') or content[4:5] < b'2' or not content.endswith(b'\n'):
        return None
    footer = content[content.rfind(b'\n', 0, len(content) - 1) + 1:-1]
    return footer.decode('ascii', 'replace') or None


def local_midnight(ts, days=0):
    """Return the local midnight of the day of ts, moved by a number of days.

    Args:
        ts (int|float): A time, in epoch seconds.
        days (int): How many days to move, e.g., -1 for the day before. Default is 0.

    Returns:
        int: The midnight, in epoch seconds.
    """
    day = datetime.date.fromtimestamp(ts) + datetime.timedelta(days=days)
    return int(time.mktime((day.year, day.month, day.day, 0, 0, 0, 0, 0, -1)))


def local_time(day, minute):
    """Return the time of a wall clock reading on a given day.

    Args:
        day (datetime.date): The day.
        minute (int): Minutes since midnight on the wall clock.

    Returns:
        int: The time, in epoch seconds.
    """
    return int(time.mktime((day.year, day.month, day.day, minute // 60, minute % 60, 0,
                            0, 0, -1)))


class Sky(object):
    """The sun and the moon, as seen from one place."""

    # ephem counts days from 1899-12-31 12:00 UTC. This is the Unix epoch on that scale.
    EPOCH = None

    def __init__(self, lat, lon, elevation):
        """Set up the place.

        Args:
            lat (float): Degrees north.
            lon (float): Degrees east.
            elevation (float): Meters above sea level.
        """
        # pyephem is optional for WeeWX. Import it here, so that a station without it
        # still loads this module, and only $sky is missing.
        import ephem
        self.ephem = ephem
        if Sky.EPOCH is None:
            Sky.EPOCH = float(ephem.Date('1970/01/01 00:00:00'))
        self.lat = lat
        self.lon = lon
        self.elevation = elevation

    def observer(self, ts, horizon='0'):
        """Return an observer at the station, at a time.

        The pressure is 0, which turns off ephem's own refraction. Rise and set then use
        the standard horizon of -0:34, which includes the refraction at the horizon.

        Args:
            ts (int|float): The time, in epoch seconds.
            horizon (str): The altitude of the horizon, in degrees as text.
                Default is '0'.

        Returns:
            ephem.Observer: The observer.
        """
        observer = self.ephem.Observer()
        observer.lat = str(self.lat)
        observer.lon = str(self.lon)
        observer.elevation = self.elevation
        observer.pressure = 0
        observer.horizon = horizon
        observer.date = self.to_ephem(ts)
        return observer

    def to_ephem(self, ts):
        return self.ephem.Date(ts / 86400.0 + Sky.EPOCH)

    def to_epoch(self, date):
        return int(round((float(date) - Sky.EPOCH) * 86400.0))

    def event(self, which, body, start, stop, horizon='-0:34', use_center=False):
        """Return the time of the next rise, set or transit of a body within a span.

        Args:
            which (str): 'next_rising', 'next_setting' or 'next_transit'.
            body (ephem.Body): The sun or the moon.
            start (int): The span begins, in epoch seconds.
            stop (int): The span ends, in epoch seconds.
            horizon (str): The altitude of the horizon, in degrees as text. Default is
                '-0:34'.
            use_center (bool): True to take the center of the body, False its upper
                limb. Default is False.

        Returns:
            int|None: The time, in epoch seconds. None if it does not happen within the
                span, e.g., the moon on the day it rises after midnight.
        """
        observer = self.observer(start, horizon)
        try:
            if which == 'next_transit':
                found = observer.next_transit(body)
            else:
                found = getattr(observer, which)(body, use_center=use_center)
        except self.ephem.CircumpolarError:
            return None
        ts = self.to_epoch(found)
        return ts if start <= ts < stop else None

    def sun_altitude(self, ts):
        sun = self.ephem.Sun(self.observer(ts))
        return math.degrees(sun.alt)

    def curve(self, day, step):
        """Return the altitude of the sun over one day, in steps of the wall clock.

        Args:
            day (datetime.date): The day.
            step (int): Minutes between two points.

        Returns:
            list[float]: The altitude in degrees, from 00:00 to 24:00 inclusive, one
                point every 'step' minutes. Below the horizon it is negative. The display
                cuts the curve off there.
        """
        return [round(self.sun_altitude(local_time(day, minute)), 1)
                for minute in range(0, 1441, step)]

    def sun(self, now, step):
        """Return the sun's times, distance and curves for the day of now.

        Args:
            now (int): The time, in epoch seconds.
            step (int): The minutes between two points of the curves.

        Returns:
            dict: The fields of 'sun' in sky.json. See the template sky.json.tmpl.
        """
        ephem = self.ephem
        midnight = local_midnight(now)
        tomorrow = local_midnight(now, 1)
        day_after = local_midnight(now, 2)
        yesterday = local_midnight(now, -1)
        body = ephem.Sun()

        def day_of(start, stop):
            rise = self.event('next_rising', body, start, stop)
            set_ = self.event('next_setting', body, start, stop)
            return rise, set_

        rise, set_ = day_of(midnight, tomorrow)
        rise_yesterday, set_yesterday = day_of(yesterday, midnight)
        rise_tomorrow, set_tomorrow = day_of(tomorrow, day_after)
        transit = self.event('next_transit', body, midnight, tomorrow)

        length = set_ - rise if rise is not None and set_ is not None else None
        length_yesterday = (set_yesterday - rise_yesterday
                            if rise_yesterday is not None and set_yesterday is not None
                            else None)

        sun_now = ephem.Sun(self.observer(now))
        distance = sun_now.earth_distance * AU_KM
        today = datetime.date.fromtimestamp(now)
        return {
            'rise': rise,
            'set': set_,
            'transit': transit,
            'transit_altitude': (round(self.sun_altitude(transit), 1)
                                 if transit is not None else None),
            # Civil twilight: the center of the sun 6 degrees below the horizon. Until
            # then one can read outside without a lamp.
            'dawn': self.event('next_rising', body, midnight, tomorrow, '-6', True),
            'dusk': self.event('next_setting', body, midnight, tomorrow, '-6', True),
            'length': length,
            'length_change': (length - length_yesterday
                              if length is not None and length_yesterday is not None
                              else None),
            'tomorrow_rise': rise_tomorrow,
            'tomorrow_set': set_tomorrow,
            'altitude': round(math.degrees(sun_now.alt), 1),
            'azimuth': round(math.degrees(sun_now.az), 1),
            'distance': round(distance),
            'light_time': round(distance / LIGHT_KM_S),
            # The curves of today and of the two solstices. The area between the
            # solstices is every course the sun can take here in a year, and today's
            # curve lies within it. They are named by their month, not by summer and
            # winter, because south of the equator the June curve is the low one.
            'curve_step': step,
            'curve_today': self.curve(today, step),
            'curve_june': self.curve(datetime.date(today.year, 6, 21), step),
            'curve_december': self.curve(datetime.date(today.year, 12, 21), step),
        }

    def moon(self, now):
        """Return the moon's phase, times and distance for the day of now.

        Args:
            now (int): The time, in epoch seconds.

        Returns:
            dict: The fields of 'moon' in sky.json. See the template sky.json.tmpl.
        """
        ephem = self.ephem
        midnight = local_midnight(now)
        tomorrow = local_midnight(now, 1)
        body = ephem.Moon()
        moon_now = ephem.Moon(self.observer(now))
        date = self.to_ephem(now)
        previous_new = self.to_epoch(ephem.previous_new_moon(date))
        next_new = self.to_epoch(ephem.next_new_moon(date))
        next_full = self.to_epoch(ephem.next_full_moon(date))
        age = (now - previous_new) / 86400.0
        # The phase in eighths of a lunation, centered on the four principal phases, so
        # that 'first_quarter' covers the day and a half either side of it.
        names = ('new', 'waxing_crescent', 'first_quarter', 'waxing_gibbous', 'full',
                 'waning_gibbous', 'last_quarter', 'waning_crescent')
        eighth = int(age / SYNODIC_MONTH * 8 + 0.5) % 8
        return {
            'illumination': round(moon_now.moon_phase * 100, 1),
            'waxing': next_full < next_new,
            'age': round(age, 2),
            'phase': names[eighth],
            'rise': self.event('next_rising', body, midnight, tomorrow),
            'set': self.event('next_setting', body, midnight, tomorrow),
            'next_full': next_full,
            'next_new': next_new,
            'altitude': round(math.degrees(moon_now.alt), 1),
            'azimuth': round(math.degrees(moon_now.az), 1),
            'distance': round(moon_now.earth_distance * AU_KM),
        }


def theme_of(section):
    """Return the theme of the display from [DisplayOptions][[Theme]].

    Args:
        section (dict): The section [[Theme]], or {}.

    Returns:
        dict: Each color as skin.conf gives it, e.g., '#161616', and 'white_balance' as
            a list of three floats. A value that is not a color, and a white balance
            that is not three numbers, are left out: the display keeps its own.
    """
    theme = {}
    for key, value in section.items():
        if key == 'white_balance':
            try:
                factors = [float(f) for f in weeutil.weeutil.option_as_list(value)]
            except (TypeError, ValueError):
                continue
            if len(factors) == 3:
                theme[key] = factors
        elif isinstance(value, str) and len(value) == 7 and value.startswith('#'):
            try:
                int(value[1:], 16)
            except ValueError:
                continue
            theme[key] = value
    return theme


class DisplaySky(weewx.cheetahgenerator.SearchList):
    """Give the templates $sky and $display.

    $sky is a dict with the keys 'sun' and 'moon', computed for the end of the report's
    timespan. It is None where pyephem is not installed.

    $display holds what station.json needs and no tag of WeeWX offers:
      'latitude', 'longitude'  Degrees north and east, as numbers.
      'altitude'    Meters above sea level, as a number.
      'tz'          The POSIX time zone of the station. See posix_timezone().
      'directions'  The names of the compass points in the language of the report,
                    north first, in 16 steps.
      'texts'       Every entry of [Texts] in the language file. The display takes its
                    words from here, so that a new language needs no new firmware.
      'theme'       The colors of [DisplayOptions][[Theme]]. See theme_of().
    """

    def __init__(self, generator):
        super().__init__(generator)
        options = generator.skin_dict.get('DisplayOptions', {})
        self.step = to_int(options.get('sun_curve_step', 10))
        stn_info = generator.stn_info
        altitude = weewx.units.convert(stn_info.altitude_vt, 'meter').value
        try:
            self.sky = Sky(stn_info.latitude_f, stn_info.longitude_f, altitude)
        except ImportError:
            log.info("pyephem is not installed. sky.json has no sun and no moon.")
            self.sky = None
        directions = weeutil.weeutil.option_as_list(
            generator.skin_dict.get('Units', {}).get('Ordinates', {}).get('directions'))
        texts = generator.skin_dict.get('Texts', {})
        self.display = {
            'latitude': stn_info.latitude_f,
            'longitude': stn_info.longitude_f,
            'altitude': altitude,
            # A machine without a TZif file, or one whose clock runs in another zone
            # than the station's, sets the zone in [DisplayOptions].
            'tz': options.get('tz') or posix_timezone(),
            # The last ordinate of WeeWX is the text for no direction, e.g., 'N/A'.
            'directions': list(directions[:16]) if directions else None,
            # Subsections of [Texts], such as [[Geographical]] in the languages of WeeWX,
            # are not words of the display.
            'texts': {key: texts[key] for key in texts.scalars},
            'theme': theme_of(options.get('Theme', {})),
        }

    def get_extension_list(self, timespan, db_lookup):
        sky = None
        if self.sky is not None:
            now = int(timespan.stop)
            sky = {'sun': self.sky.sun(now, self.step), 'moon': self.sky.moon(now)}
        return [{'sky': sky, 'display': self.display}]
