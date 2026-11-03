#
#    Copyright (c) 2026 Manuel Hilgert
#
#    See the file LICENSE.txt for your rights.
#
"""The live readings, the forecast and the time zone."""

import json
import os
import pathlib
import time

import configobj
import pytest

import weewx
from user.display import DisplayLive, posix_timezone, theme_of, to_forecast

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Engine(object):
    """Just enough of weewx.engine.StdEngine for a service to bind to it."""

    def __init__(self):
        self.bindings = {}

    def bind(self, event_type, callback):
        self.bindings[event_type] = callback


class Event(object):
    def __init__(self, packet):
        self.packet = packet


def config(tmp_path, units='METRIC', **display):
    return configobj.ConfigObj({
        'WEEWX_ROOT': str(tmp_path),
        'StdReport': {
            'SKIN_ROOT': str(ROOT / 'skins'),
            'HTML_ROOT': 'public_html',
            'Defaults': {'unit_system': units},
            'DisplayReport': {'skin': 'Display', 'HTML_ROOT': 'public_html/display'},
        },
        'Display': display,
    })


def test_live_readings_are_in_the_units_of_the_report(tmp_path):
    engine = Engine()
    DisplayLive(engine, config(tmp_path, live_interval='0'))
    engine.bindings[weewx.NEW_LOOP_PACKET](Event({
        'dateTime': 1793714100, 'usUnits': weewx.US, 'outTemp': 50.0, 'windSpeed': 10.0,
        'barometer': 30.0,
    }))
    live = json.loads((tmp_path / 'public_html' / 'display' / 'live.json').read_text())

    assert live['time'] == 1793714100
    assert live['values']['outTemp'] == pytest.approx(10.0)
    assert live['values']['windSpeed'] == pytest.approx(16.093, abs=0.001)
    assert live['values']['barometer'] == pytest.approx(1015.917, abs=0.01)


def test_a_reading_from_an_earlier_packet_stays_until_it_is_too_old(tmp_path, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(time, 'time', lambda: clock[0])
    engine = Engine()
    DisplayLive(engine, config(tmp_path, live_interval='0', live_max_age='60'))
    loop = engine.bindings[weewx.NEW_LOOP_PACKET]
    path = tmp_path / 'public_html' / 'display' / 'live.json'

    loop(Event({'dateTime': 1000, 'usUnits': weewx.METRIC, 'outTemp': 5.0}))
    clock[0] = 1030.0
    loop(Event({'dateTime': 1030, 'usUnits': weewx.METRIC, 'windSpeed': 3.0}))
    assert set(json.loads(path.read_text())['values']) == {'outTemp', 'windSpeed'}

    clock[0] = 1070.0
    loop(Event({'dateTime': 1070, 'usUnits': weewx.METRIC, 'windSpeed': 4.0}))
    assert set(json.loads(path.read_text())['values']) == {'windSpeed'}


def test_live_json_goes_where_live_path_says(tmp_path):
    target = tmp_path / 'run' / 'live.json'
    engine = Engine()
    DisplayLive(engine, config(tmp_path, live_interval='0', live_path=str(target)))
    engine.bindings[weewx.NEW_LOOP_PACKET](Event({'dateTime': 1, 'usUnits': weewx.METRIC,
                                                  'outTemp': 1.0}))
    assert target.exists()
    assert os.stat(str(target)).st_mode & 0o777 == 0o644


def test_without_the_report_no_live_json_is_written(tmp_path):
    engine = Engine()
    settings = config(tmp_path)
    del settings['StdReport']['DisplayReport']
    DisplayLive(engine, settings)
    assert weewx.NEW_LOOP_PACKET not in engine.bindings


OPEN_METEO = {
    'daily': {
        'time': [1793660400, 1793746800],
        'weather_code': [3, 61],
        'temperature_2m_max': [8.1, 6.4],
        'temperature_2m_min': [1.2, 2.0],
        'precipitation_probability_max': [10, 80],
        'precipitation_sum': [0.0, 4.2],
        'wind_speed_10m_max': [12.0, 20.5],
        'wind_gusts_10m_max': [25.0, 41.0],
        'wind_direction_10m_dominant': [220, 250],
        'sunshine_duration': [10800.4, 0.0],
        'uv_index_max': [1.2, 0.4],
    },
    'hourly': {
        'time': [1793710800, 1793714400, 1793718000, 1793721600],
        'weather_code': [3, 3, 2, 61],
        'temperature_2m': [6.0, 5.5, 5.0, 4.6],
        'precipitation_probability': [0, 5, 10, 60],
        'precipitation': [0.0, 0.0, 0.0, 0.6],
        'wind_speed_10m': [8.0, 7.5, 7.0, 9.0],
        'wind_direction_10m': [210, 215, 220, 230],
        'is_day': [1, 1, 0, 0],
    },
}


def test_the_forecast_keeps_the_hour_in_progress_and_drops_the_ones_before():
    # 14:40 local in the hour that began at 1793714400.
    forecast = to_forecast(OPEN_METEO, 1793714400 + 40 * 60, 48)
    assert [hour['time'] for hour in forecast['hours']] == [1793714400, 1793718000, 1793721600]


def test_the_forecast_keeps_as_many_hours_as_asked():
    assert len(to_forecast(OPEN_METEO, 0, 2)['hours']) == 2


def test_the_forecast_names_its_units_as_weewx_does():
    forecast = to_forecast(OPEN_METEO, 0, 48)
    assert forecast['units'] == {'temperature': 'degree_C', 'speed': 'km_per_hour',
                                 'rain': 'mm', 'direction': 'degree_compass'}
    assert forecast['days'][1] == {
        'time': 1793746800, 'code': 61, 'high': 6.4, 'low': 2.0, 'rain_chance': 80,
        'rain': 4.2, 'wind': 20.5, 'gust': 41.0, 'dir': 250, 'sun': 0, 'uv': 0.4,
    }
    assert forecast['hours'][2]['day'] is False


def test_an_answer_with_a_missing_column_gives_nulls_not_an_error():
    said = {'daily': {'time': [1793660400], 'weather_code': [3]}, 'hourly': {}}
    day = to_forecast(said, 0, 48)['days'][0]
    assert day['code'] == 3 and day['high'] is None and day['sun'] is None


def test_the_theme_passes_colors_and_white_balance_on():
    # configobj hands a list over as strings.
    theme = theme_of({'tile': '#1A1A1A', 'white_balance': ['1.0', '1.0', '0.9']})
    assert theme == {'tile': '#1A1A1A', 'white_balance': [1.0, 1.0, 0.9]}


@pytest.mark.parametrize('section', [
    {'tile': '1A1A1A'}, {'tile': '#1A1A1'}, {'tile': '#GGGGGG'},
    {'white_balance': ['1.0', '0.9']}, {'white_balance': ['1.0', 'blue', '0.9']},
])
def test_a_theme_value_that_is_wrong_is_left_out(section):
    assert theme_of(section) == {}


def tzif(path, version, footer):
    path.write_bytes(b'TZif' + version + b'\0' * 39 + b'\n' + footer + b'\n')
    return str(path)


def test_the_time_zone_comes_from_the_footer_of_the_tzif_file(tmp_path):
    path = tzif(tmp_path / 'localtime', b'2', b'CET-1CEST,M3.5.0,M10.5.0/3')
    assert posix_timezone(path) == 'CET-1CEST,M3.5.0,M10.5.0/3'


@pytest.mark.parametrize('content', [b'', b'not a tzif file\n'])
def test_a_file_that_is_not_tzif_gives_no_time_zone(tmp_path, content):
    path = tmp_path / 'localtime'
    path.write_bytes(content)
    assert posix_timezone(str(path)) is None


def test_a_tzif_file_of_version_1_has_no_footer(tmp_path):
    path = tmp_path / 'localtime'
    path.write_bytes(b'TZif\0' + b'\0' * 39)
    assert posix_timezone(str(path)) is None


def test_a_missing_file_gives_no_time_zone(tmp_path):
    assert posix_timezone(str(tmp_path / 'missing')) is None
