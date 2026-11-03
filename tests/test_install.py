#
#    Copyright (c) 2026 Manuel Hilgert
#
#    See the file LICENSE.txt for your rights.
#
"""The installer, and that it installs every file of the skin."""

import os
import pathlib
import sys

import configobj
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest.importorskip('weecfg.extension', reason="needs weewx on the path")

from install import DisplayInstaller  # noqa: E402


class Engine(object):
    def __init__(self, std_report):
        self.config_dict = {'StdReport': std_report}


def html_root(std_report):
    installer = DisplayInstaller()
    installer.configure(Engine(std_report))
    return installer['config']['StdReport']['DisplayReport'].get('HTML_ROOT')


def test_a_package_install_writes_below_its_web_root():
    assert html_root({'HTML_ROOT': '/var/www/html/weewx'}) == '/var/www/html/weewx/display'


def test_a_pip_install_writes_below_public_html():
    assert html_root({'HTML_ROOT': 'public_html'}) == os.path.join('public_html', 'display')


def test_an_html_root_the_user_has_set_stays():
    std_report = {'HTML_ROOT': '/var/www/html/weewx',
                  'DisplayReport': {'HTML_ROOT': '/srv/display'}}
    assert html_root(std_report) is None


def test_it_registers_the_services_and_the_report():
    installer = DisplayInstaller()
    assert installer['report_services'] == ['user.display.DisplayLive',
                                            'user.display.DisplayForecast']
    assert installer['config']['StdReport']['DisplayReport']['skin'] == 'Display'
    assert installer['config']['Display']['report'] == 'DisplayReport'


def test_every_file_of_the_skin_is_installed():
    installed = {path for _, files in DisplayInstaller()['files'] for path in files}
    on_disk = {str(path.relative_to(ROOT)).replace(os.sep, '/')
               for path in (ROOT / 'skins').rglob('*') if path.is_file()}
    on_disk |= {'bin/user/display.py', 'bin/user/jsongenerator.py'}
    assert installed == on_disk


def test_every_template_of_skin_conf_exists():
    skin = configobj.ConfigObj(str(ROOT / 'skins' / 'Display' / 'skin.conf'))
    for name, entry in skin['CheetahGenerator']['ToDate'].items():
        assert (ROOT / 'skins' / 'Display' / entry['template']).exists(), name
