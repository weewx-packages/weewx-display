#
#    Copyright (c) 2026 Manuel Hilgert
#
#    See the file LICENSE.txt for your rights.
#
"""The installer, and that it installs every file of the skin."""

import os
import pathlib
import shutil
import subprocess
import sys

import configobj
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest.importorskip('weecfg.extension', reason="needs weewx on the path")

from install import DisplayInstaller  # noqa: E402

WEECTL = shutil.which('weectl')


def installed_html_root(tmp_path, std_html_root=None, report_html_root=None):
    """Install the extension with weectl into a new station, and return the report's
    HTML_ROOT as weewx.conf has it afterwards.

    Args:
        tmp_path (pathlib.Path): Where the station goes.
        std_html_root (str|None): The HTML_ROOT of [StdReport], or None for the one a
            new station gets, which is that of a pip install.
        report_html_root (str|None): An HTML_ROOT set for DisplayReport before the
            install, or None.
    """
    station = tmp_path / 'station'
    config_path = str(station / 'weewx.conf')
    subprocess.run([WEECTL, 'station', 'create', str(station), '--no-prompt'], check=True,
                   capture_output=True)
    config = configobj.ConfigObj(config_path, encoding='utf-8')
    if std_html_root is not None:
        config['StdReport']['HTML_ROOT'] = std_html_root
    if report_html_root is not None:
        config['StdReport']['DisplayReport'] = {'HTML_ROOT': report_html_root}
    config.write()
    subprocess.run([WEECTL, 'extension', 'install', str(ROOT), '--config', config_path,
                    '--yes'], check=True, capture_output=True)
    return configobj.ConfigObj(config_path, encoding='utf-8')['StdReport']['DisplayReport'][
        'HTML_ROOT']


@pytest.mark.skipif(WEECTL is None, reason="needs weectl")
def test_a_pip_install_writes_below_public_html(tmp_path):
    assert installed_html_root(tmp_path) == 'public_html/display'


@pytest.mark.skipif(WEECTL is None, reason="needs weectl")
def test_a_package_install_writes_below_its_web_root(tmp_path):
    assert (installed_html_root(tmp_path, std_html_root='/var/www/html/weewx')
            == '/var/www/html/weewx/display')


@pytest.mark.skipif(WEECTL is None, reason="needs weectl")
def test_an_html_root_the_user_has_set_stays(tmp_path):
    assert installed_html_root(tmp_path, report_html_root='/srv/display') == '/srv/display'


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
