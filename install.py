#
#    Copyright (c) 2026 Manuel Hilgert
#
#    See the file LICENSE.txt for your full rights.
#
"""Installer of the extension 'display', the server side of the wall display.

    weectl extension install weewx-display.zip

bin/user/jsongenerator.py is the JSON generator of WeeWX pull request 1139, unchanged,
at commit a5c09b186447e25f11326a77bc21c2ef828b6f08. It ships here until a release of
WeeWX includes it as weewx.jsongenerator.
"""

from weecfg.extension import ExtensionInstaller

REPORT = 'DisplayReport'


def loader():
    return DisplayInstaller()


class DisplayInstaller(ExtensionInstaller):
    def __init__(self):
        super().__init__(
            version='0.1.1',
            name='display',
            description='Data for a wall display: live readings, history, records, '
                        'forecast, sun and moon.',
            author='Manuel Hilgert',
            author_email='hilman2@gmail.com',
            report_services=['user.display.DisplayLive', 'user.display.DisplayForecast'],
            config={
                'StdReport': {
                    REPORT: {
                        'skin': 'Display',
                        'enable': 'true',
                        # WeeWX puts the HTML_ROOT of [StdReport] in front, which gives
                        # public_html/display or /var/www/html/weewx/display.
                        'HTML_ROOT': 'display',
                    },
                },
                'Display': {
                    'report': REPORT,
                    'live_interval': '2',
                    'forecast_interval': '3600',
                },
            },
            files=[
                ('bin/user', ['bin/user/display.py', 'bin/user/jsongenerator.py']),
                ('skins/Display', ['skins/Display/skin.conf',
                                   'skins/Display/station.json.tmpl',
                                   'skins/Display/summary.json.tmpl',
                                   'skins/Display/sky.json.tmpl']),
                ('skins/Display/lang', ['skins/Display/lang/de.conf',
                                        'skins/Display/lang/en.conf']),
            ],
        )
