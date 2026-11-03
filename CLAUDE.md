# weewx-display

WeeWX extension that writes the data of a wall display as JSON files: station,
summary, sky, forecast, live readings and the history of the JSON generator.

## Structure

* `install.py` registers files, services, the report and configuration
  defaults. `configure()` derives the report's `HTML_ROOT` from `[StdReport]`.
* `bin/user/display.py` holds the services `DisplayLive` and `DisplayForecast`
  and the search list extension `DisplaySky`.
* `bin/user/jsongenerator.py` is a verbatim copy from WeeWX PR 1139. Do not
  edit it here; see PUBLISHING.md.
* `skins/Display/` holds the templates, `skin.conf` and the language files.
  `[Texts]` of the language files is the whole vocabulary of the display.
* `docs/how-it-works.md` is the one place that documents the file formats.
  Templates and code point there instead of repeating them.
* `tests/` covers the installer, the services and the sky calculations.

## Conventions

Python follows WeeWX's style, with types in Google docstrings and no runtime
annotations. The files are a contract with clients: a new key is a minor
version, a changed or removed key a major version, in `FORMAT_VERSION` of
`display.py` and in the templates.

The extension is generic. Nothing in it may assume one station, unit system,
language, hemisphere or web server.

## Tests

Run them in Docker from the repository root:

    docker compose -f tests/docker/compose.yml run --rm tests

The sky tests compare against values of an independent calculation. Do not
replace those values with pyephem's own output.

## Documentation

README follows the weewx-packages schema and names no versions or archive URLs;
installation links to the catalog page.
