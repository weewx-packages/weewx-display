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

import os

from weecfg.extension import ExtensionInstaller

REPORT = 'DisplayReport'


def loader():
    return DisplayInstaller()


class DisplayInstaller(ExtensionInstaller):
    def __init__(self):
        super().__init__(
            version='0.1.0',
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

    def configure(self, engine):
        # The report writes into a subdirectory of the HTML_ROOT of [StdReport]. A
        # relative HTML_ROOT in the report's own section would be taken relative to
        # WEEWX_ROOT, not to that HTML_ROOT. A package install has it at
        # /var/www/html/weewx, a pip install at public_html, so it is worked out here.
        # An HTML_ROOT the user has set already stays as it is.
        std_report = engine.config_dict.get('StdReport', {})
        if 'HTML_ROOT' not in std_report.get(REPORT, {}):
            html_root = std_report.get('HTML_ROOT', 'public_html')
            self['config']['StdReport'][REPORT]['HTML_ROOT'] = os.path.join(html_root,
                                                                            'display')
        # Only the installer's own 'config' changed, which the engine merges next.
        return False
