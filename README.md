# weewx-display

Writes the data a wall display needs, as small JSON files beside your WeeWX
pages: the current readings every few seconds, the extremes and totals of
today, the week, the month, the year and all time, the history for charts, a
seven-day forecast, and the course of the sun and the phase of the moon.

The display reads these files and draws everything itself. WeeWX keeps doing
what it does well: units, formats, translations and statistics. A display needs
no knowledge of your station, and a change to a template needs no new firmware.

The files are documented, so any program can use them: a wall display, a
dashboard, or a page of your own.

## Requirements

* WeeWX 5.5 or later.
* A web server that serves the `HTML_ROOT` of your reports.
* [pyephem](https://pypi.org/project/ephem/) for the sun and the moon. Without
  it, everything else works and `sky.json` stays empty.
* An outgoing HTTPS connection to `api.open-meteo.com` for the forecast.

## Installation

Install `display` from the [WeeWX packages catalog](https://github.com/weewx-packages/catalog/blob/main/packages/display.md).
The catalog page lists the current release, its WeeWX and Python requirements,
and the install, update and removal commands.

The installer adds the report `DisplayReport`, the two services that write the
live readings and fetch the forecast, and the section `[Display]` in
`weewx.conf`. The report writes into the directory `display` below the
`HTML_ROOT` of `[StdReport]`, for example `/var/www/html/weewx/display` on a
package install.

Restart WeeWX. After the next report, these files are there:

```
http://your-station/display/station.json
http://your-station/display/summary.json
http://your-station/display/sky.json
http://your-station/display/forecast.json
http://your-station/display/live.json
http://your-station/display/data/
```

`live.json` appears with the first LOOP packet, `forecast.json` within a minute.
The first report builds the history from your whole database, a part at a time,
so the files under `data/` may take a few reports to cover all of it.

## Configuration

Nothing needs to be set. The report takes the units and the language of your
other reports.

### Showing the display in another language

The display takes all its words from the report. Set the language of the
report in `weewx.conf`:

``` ini
[StdReport]
    [[DisplayReport]]
        lang = de
```

The skin brings English and German. Another language is a copy of
`skins/Display/lang/en.conf` with the words translated.

### Showing other units

The report uses the units of `[StdReport] [[Defaults]]`. To give the display
other units than your web pages, set them for this report alone:

``` ini
[StdReport]
    [[DisplayReport]]
        [[[Units]]]
            [[[[Groups]]]]
                group_speed = km_per_hour
                group_pressure = hPa
```

### Changing the colors

The colors are in `skins/Display/skin.conf`, under `[DisplayOptions] [[Theme]]`.
Each one that is set there replaces the display's built-in dark theme. The
display picks the change up with the next `station.json`, without a restart.

If the panel of your display has a color cast, `white_balance` corrects it:

``` ini
[DisplayOptions]
    [[Theme]]
        white_balance = 1.0, 1.0, 0.9
```

### Choosing what the display shows

`skins/Display/skin.conf` lists the readings, the extremes, the totals, the
periods and the charts, each with a line saying what it does. A type your
station does not record is left out of the files, so the defaults work for any
station.

### Keeping live.json off the SD card

`live.json` is written every two seconds. On a Raspberry Pi, you can keep it in
memory instead of on the SD card:

``` ini
[Display]
    live_path = /run/weewx/live.json
```

and serve it from there. For nginx:

```
location = /display/live.json {
    alias /run/weewx/live.json;
}
```

### Options

These options go under `[Display]` in `weewx.conf`.

#### report

The report whose units and `HTML_ROOT` the services use. Default is
`DisplayReport`.

#### live_path

Where `live.json` is written. Default is `live.json` in the `HTML_ROOT` of the
report.

#### live_interval

Seconds between two writes of `live.json`. Default is `2`.

#### live_max_age

Seconds after which a reading that has not arrived again is left out of
`live.json`. Default is `600`.

#### forecast_interval

Seconds between two requests to Open-Meteo. Default is `3600`. `0` turns the
forecast off.

#### forecast_days

Days of the forecast, today included. Default is `7`.

#### forecast_hours

Hours of the hourly forecast, from the current one. Default is `48`.

#### forecast_timeout

Seconds to wait for Open-Meteo. Default is `20`.

### Further reading

* [How it works](docs/how-it-works.md): the files and their formats.

## Limitations

* The forecast comes from [Open-Meteo](https://open-meteo.com/), which is free
  for non-commercial use. Its data are licensed under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); a display that
  shows them names the source.
* The history comes from the JSON generator of WeeWX
  [pull request 1139](https://github.com/weewx/weewx/pull/1139), which is not
  part of a WeeWX release yet. The extension brings a copy, as
  `user.jsongenerator`.
* The times of the sun and the moon are in the time zone of the machine that
  runs WeeWX.

## Development

Run the tests in Docker, from the repository root:

```sh
docker compose -f tests/docker/compose.yml run --rm tests
```

Or with WeeWX, pyephem and pytest installed, `just fast`.

[PUBLISHING.md](PUBLISHING.md) describes the release steps.

## License

Copyright 2026 Manuel Hilgert. [GNU GPLv3](LICENSE.txt).
