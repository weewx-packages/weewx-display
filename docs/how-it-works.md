# How it works

This page describes the files the extension writes and how they are made. It is
for anyone who writes a display, a dashboard or a page that reads them. To
install and configure the extension, see the [README](../README.md).

## Who writes what

| File | Written by | How often |
|---|---|---|
| `station.json` | template `station.json.tmpl` | every report |
| `summary.json` | template `summary.json.tmpl` | every report |
| `sky.json` | template `sky.json.tmpl`, with `user.display.DisplaySky` | every report |
| `data/` | `user.jsongenerator.JSONGenerator` | every report, only what changed |
| `forecast.json` | service `user.display.DisplayForecast` | every `forecast_interval` |
| `live.json` | service `user.display.DisplayLive` | every `live_interval` |

All files are in the `HTML_ROOT` of the report. `live.json` can be elsewhere,
see [`live_path`](../README.md#live_path).

A client reads `station.json` first. Every other file holds bare numbers, and
`station.json` says what they mean.

## Conventions of every file

* Numbers are in the units of the report. `station.json` names the unit of each
  observation type. The forecast is the exception; see
  [forecast.json](#forecastjson).
* Times are Unix epoch seconds. Durations are seconds.
* A value that is not known is `null` or absent, never `0`. A type the station
  does not record is absent.
* `version` is the version of the format of the file, as `"<major>.<minor>"`.
  The minor number grows when a key is added. The major number grows when a key
  changes its meaning or goes away. A client refuses a major version it does not
  know. All files are at `1.0`.
* Every file is replaced in one step. A client never reads half a file.

## station.json

What a client needs once, and again when the file changes.

``` json
{
  "version": "1.0",
  "location": "Kirchdorf",
  "latitude": 48.459, "longitude": 11.654, "altitude": 440.0,
  "tz": "CET-1CEST,M3.5.0,M10.5.0/3",
  "types": {"outTemp": {"unit": "degree_C", "label": "Außentemperatur"}},
  "report_units": {"group_temperature": "degree_C"},
  "units": {"degree_C": {"label": "°C", "format": "%.1f"}},
  "charts": [{"name": "temp", "type": "line"}, {"name": "rain", "type": "bar"}],
  "directions": ["N", "NNO", "NO"],
  "theme": {"tile": "#161616", "white_balance": [1.0, 1.0, 0.9]},
  "texts": {"decimal_separator": ",", "tab_now": "Jetzt"}
}
```

* `altitude` is in meters, `latitude` and `longitude` in degrees north and east.
* `tz` is the time zone of the machine that runs WeeWX, as a POSIX TZ string,
  taken from `/etc/localtime`. A microcontroller can keep local time with it,
  summer time included. `[DisplayOptions] tz` in `skin.conf` overrides it.
* `types` holds each type of `observations`, `extremes` and `sums` in
  `skin.conf`: its unit and its label in the language of the report.
* `report_units` maps each unit group to the unit of the report.
* `units` holds how to write each unit: `label` to put after the number, and
  `format`, a printf format for the number. Write the number with `format`, then
  replace `.` with `texts.decimal_separator`.
* `charts` lists the plot groups of the history page in their order, each drawn
  as a `line` or as `bar`s.
* `directions` holds the 16 compass points, north first, in steps of 22.5°.
* `theme` holds the colors set under `[DisplayOptions] [[Theme]]`. A key that is
  absent means the client's own color.
* `texts` holds every entry of `[Texts]` of the language file. Lists, such as
  `weekdays`, are JSON arrays. `day_format` writes a date: `{w}` is the weekday,
  `{d}` the day, `{m}` the month.

## summary.json

The archive record, the trends, and the extremes and totals of each period.

``` json
{
  "version": "1.0",
  "time": 1793715300,
  "interval": 5,
  "current": {"outTemp": 5.278, "barometer": 1034.019},
  "trends": {"barometer": {"change": -0.058, "over": 10800}},
  "periods": {
    "day": {
      "start": 1793660400, "end": 1793746800,
      "outTemp": {"min": 5.278, "min_t": 1793698589, "max": 5.722, "max_t": 1793707277},
      "rain": {"sum": 0.0}
    }
  }
}
```

* `time` is the time of the archive record, `interval` its archive interval in
  minutes.
* `current` holds the types of `observations`.
* `trends` holds the change of each type of `trends` over `over` seconds, as
  WeeWX's tag `$trend` gives it.
* `periods` holds each period of `periods`, by the name of its Cheetah tag:
  `day`, `yesterday`, `week`, `month`, `year`, `rainyear`, `alltime`. Each has
  its `start` and `end`, the lowest and highest value of each type of
  `extremes` with the time of each, and the `sum` of each type of `sums`.

## sky.json

The sun and the moon, for the time of the report.

``` json
{
  "version": "1.0",
  "time": 1793715300,
  "sun": {
    "rise": 1793685737, "set": 1793721057, "transit": 1793703416,
    "transit_altitude": 26.4, "dawn": 1793683757, "dusk": 1793723036,
    "length": 35320, "length_change": -188,
    "tomorrow_rise": 1793772231, "tomorrow_set": 1793807365,
    "altitude": 12.7, "azimuth": 228.8, "distance": 148404902, "light_time": 495,
    "curve_step": 10, "curve_today": [-60.1], "curve_june": [-17.9], "curve_december": [-64.9]
  },
  "moon": {
    "illumination": 31.2, "waxing": false, "age": 23.93,
    "phase": "last_quarter", "phase_text": "Letztes Viertel",
    "rise": 1793661066, "set": 1793712324,
    "next_full": 1795532009, "next_new": 1794207723,
    "altitude": -8.5, "azimuth": 294.1, "distance": 379505
  }
}
```

* Rise and set are of the upper limb at a horizon of −0.57°, the standard that
  includes the refraction at the horizon. `dawn` and `dusk` are civil twilight,
  the center of the sun 6° below the horizon.
* A time is `null` when the event does not happen that day: the sun in a polar
  summer, or the moon on the day it rises after midnight.
* `length` is from rise to set, `length_change` the difference to yesterday.
* `distance` is in kilometers, `light_time` in seconds.
* The curves hold the altitude of the sun in degrees, from 00:00 to 24:00 on the
  wall clock, one value every `curve_step` minutes: 145 values for 10 minutes.
  Below the horizon they are negative. `curve_june` and `curve_december` are the
  21st of those months: the highest and the lowest course of the year, swapped
  south of the equator.
* `age` is the time since new moon, in days. `phase` is one of `new`,
  `waxing_crescent`, `first_quarter`, `waxing_gibbous`, `full`,
  `waning_gibbous`, `last_quarter`, `waning_crescent`: the eighth of the lunation
  the age falls into, centered on the four principal phases. `phase_text` is its
  name in the language of the report.
* Without pyephem, the file has only `version` and `time`.

## forecast.json

The forecast of [Open-Meteo](https://open-meteo.com/) for the station's
coordinates.

``` json
{
  "version": "1.0",
  "source": "open-meteo",
  "fetched": 1793714400,
  "units": {"temperature": "degree_C", "speed": "km_per_hour", "rain": "mm",
            "direction": "degree_compass"},
  "days": [{"time": 1793660400, "code": 3, "high": 8.1, "low": 1.2,
            "rain_chance": 10, "rain": 0.0, "wind": 12.0, "gust": 25.0,
            "dir": 220, "sun": 10800, "uv": 1.2}],
  "hours": [{"time": 1793714400, "code": 3, "temp": 5.5, "rain_chance": 5,
             "rain": 0.0, "wind": 7.5, "dir": 215, "day": true}]
}
```

* The numbers are in the units of `units`, not in those of the report, named as
  WeeWX names them. `data/meta.json` has the factors to convert them.
* `days` starts with today. Each `time` is local midnight. `rain_chance` is a
  percentage, `rain` the total of the day, `wind` and `gust` the highest of the
  day, `dir` the dominant direction, `sun` the seconds of sunshine.
* `hours` starts with the hour in progress, each `time` at its start. `day` is
  false at night, to pick a night icon.
* `code` is a WMO 4677 weather code as Open-Meteo uses it. `texts.wmo_<code>`
  in `station.json` is its name.
* `fetched` tells a stale forecast from a current one. When a request fails,
  the previous file stays.

## live.json

The latest readings, collected across LOOP packets.

``` json
{"version": "1.0", "time": 1793715677,
 "values": {"outTemp": 5.278, "windSpeed": 1.386, "windDir": 206.0}}
```

* `time` is the time of the last LOOP packet.
* `values` holds every numeric reading of the LOOP packets, converted into the
  units of the report. A packet often carries only some types, so each type
  keeps its last value until `live_max_age` passes without a new one.
* A client checks `time`: a file that stops changing keeps its last readings.

## data/

The history, written by the JSON generator of WeeWX
[pull request 1139](https://github.com/weewx/weewx/pull/1139). Its
[file formats](https://github.com/weewx/weewx/blob/horizon-rework-v2/docs_src/reference/json-files.md)
are documented there: `meta.json` with the conversion factors of the units,
`archive/index.json` with the files that exist, and one file per plot group and
day, month or year.

`skin.conf` sets the resolutions for a screen 800 pixels wide: the last two
days at the archive interval, the last two months at one hour, and every year
at one day. A day of a year file carries the lowest and highest value of the
types in `extremes` of `[[Archive]]`, so a year chart can draw the band between
them.
