#
#    Copyright (c) 2026 Manuel Hilgert
#
#    See the file LICENSE.txt for your rights.
#
"""The sun and the moon, against an independent calculation.

The reference values come from the sky page of wetter.hilman.eu, which computes them in
PHP, not with pyephem, for the same station (Kirchdorf an der Amper, 48.459 N,
11.654 E, 440 m) on 3 November 2026. A comparison with pyephem itself would only show
that pyephem agrees with itself.
"""

import datetime
import time

import pytest

ephem = pytest.importorskip('ephem')

from user.display import Sky, local_midnight  # noqa: E402

KIRCHDORF = (48.459, 11.654, 440.0)

# The moment of the reference, 15:07 local time. The page showed the sun at 13.7
# degrees then, which test_the_sun_stands_where_the_reference_saw_it checks.
REFERENCE = (2026, 11, 3, 15, 7, 0, 0, 0, -1)


def clock(ts):
    return time.strftime('%H:%M', time.localtime(ts))


def minutes_apart(ts, hhmm):
    """How many minutes a time lies from a wall clock reading on the same day."""
    day = datetime.date.fromtimestamp(ts)
    hour, minute = map(int, hhmm.split(':'))
    wanted = time.mktime((day.year, day.month, day.day, hour, minute, 0, 0, 0, -1))
    return abs(ts - wanted) / 60.0


@pytest.fixture
def sun(berlin):
    return Sky(*KIRCHDORF).sun(int(time.mktime(REFERENCE)), 10)


@pytest.fixture
def moon(berlin):
    return Sky(*KIRCHDORF).moon(int(time.mktime(REFERENCE)))


def test_the_sun_stands_where_the_reference_saw_it(sun):
    assert sun['altitude'] == pytest.approx(13.7, abs=0.1)


@pytest.mark.parametrize('field,expected', [
    ('rise', '07:02'), ('set', '16:50'), ('dawn', '06:29'), ('dusk', '17:23'),
    ('tomorrow_rise', '07:03'), ('tomorrow_set', '16:49'),
])
def test_the_sun_rises_and_sets_when_the_reference_says(sun, field, expected):
    # One minute covers the rounding of the reference to whole minutes.
    assert minutes_apart(sun[field], expected) <= 1.0, clock(sun[field])


def test_the_day_is_as_long_as_the_reference_says(sun):
    assert round(sun['length'] / 3600.0, 1) == 9.8
    assert round(sun['length_change'] / 60.0, 1) == pytest.approx(-3.1, abs=0.1)


def test_the_sun_climbs_as_high_as_the_reference_says(sun):
    assert sun['transit_altitude'] == pytest.approx(26.4, abs=0.1)


def test_the_distance_and_light_time_match_the_reference(sun):
    assert round(sun['distance'] / 1e6, 1) == 148.4
    assert divmod(sun['light_time'], 60) == (8, 15)


def test_the_moon_is_lit_as_the_reference_says(moon):
    assert round(moon['illumination']) == 31
    assert moon['waxing'] is False
    assert moon['phase'] == 'last_quarter'


def test_each_curve_covers_the_whole_day(sun):
    for name in ('curve_today', 'curve_june', 'curve_december'):
        assert len(sun[name]) == 24 * 6 + 1


def test_the_june_curve_is_the_high_one_north_of_the_equator(sun):
    assert max(sun['curve_june']) > max(sun['curve_today']) > max(sun['curve_december'])


def test_the_december_curve_is_the_high_one_south_of_the_equator(berlin):
    now = int(time.mktime((2026, 11, 3, 14, 30, 0, 0, 0, -1)))
    sun = Sky(-33.87, 151.21, 0.0).sun(now, 10)
    assert max(sun['curve_december']) > max(sun['curve_june'])


def test_a_day_without_sunset_has_no_times(berlin):
    # Midsummer north of the arctic circle: the sun neither rises nor sets that day.
    now = int(time.mktime((2026, 6, 21, 12, 0, 0, 0, 0, -1)))
    sun = Sky(78.22, 15.65, 0.0).sun(now, 10)
    assert sun['rise'] is None and sun['set'] is None and sun['length'] is None
    assert min(sun['curve_today']) > 0


@pytest.mark.parametrize('days,phase', [
    (0.2, 'new'), (7.4, 'first_quarter'), (14.8, 'full'), (22.1, 'last_quarter'),
    (3.7, 'waxing_crescent'), (26.0, 'waning_crescent'),
])
def test_the_phase_follows_the_age_of_the_moon(berlin, days, phase):
    new_moon = ephem.previous_new_moon('2026/11/03')
    when = ephem.Date(new_moon + days)
    ts = int(round((float(when) - float(ephem.Date('1970/1/1'))) * 86400))
    assert Sky(*KIRCHDORF).moon(ts)['phase'] == phase


def test_local_midnight_is_on_the_wall_clock_across_summer_time(berlin):
    # 25 October 2026 has 25 hours: summer time ends at 03:00.
    noon = int(time.mktime((2026, 10, 25, 12, 0, 0, 0, 0, -1)))
    assert local_midnight(noon, 1) - local_midnight(noon) == 25 * 3600
    assert clock(local_midnight(noon, 1)) == '00:00'
