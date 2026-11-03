# Publishing a release

The [shared package catalog](https://github.com/weewx-packages/catalog) lists
this extension. Publish the archive before adding its metadata to that catalog.
Keep old release assets and hashes unchanged so stations can reproduce an
installed version.

Replace `VERSION` below with the new version, for example `1.2.3`.

1. Update `version` in `install.py`. Run the tests described in
   [README.md](README.md#development).
2. Commit the payload changes and tag that commit as `vVERSION`.
3. Build the archive from the tag:

   ``` sh
   git archive --format=zip --prefix=weewx-display-VERSION/ \
       --output=/tmp/weewx-display-VERSION.zip vVERSION \
       install.py bin skins LICENSE.txt README.md
   sha256sum /tmp/weewx-display-VERSION.zip
   ```

4. Create the GitHub release for the tag and upload that ZIP. Download the
   published asset and compare its digest with the local archive.
5. Update the `display` entry in the shared catalog. Follow its
   [contribution guide](https://github.com/weewx-packages/catalog/blob/main/CONTRIBUTING.md)
   to supply the release metadata and validate the index. The catalog page
   [`packages/display.md`](https://github.com/weewx-packages/catalog/blob/main/packages/display.md)
   is generated from that entry. The README names no version or archive URL and
   needs no change for a release.
6. On a test station running stock WeeWX, install the exact published URL:

   ```sh
   weectl extension install https://github.com/weewx-packages/weewx-display/releases/download/vVERSION/weewx-display-VERSION.zip
   ```

   Restart WeeWX and run the report with `weectl report run DisplayReport`.
   Check that `station.json`, `summary.json`, `sky.json` and `data/` appear in
   the report's `HTML_ROOT`, `live.json` within seconds and `forecast.json`
   within a minute.

The catalog owns the repository identity. Keep the package ID and installer
name `display` stable when adding releases.

`bin/user/jsongenerator.py` is a copy of `src/weewx/jsongenerator.py` from WeeWX
pull request 1139. `install.py` names the commit it was taken from. Replace it
from the same pull request only, and update that commit.
