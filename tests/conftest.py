#
#    Copyright (c) 2026 Manuel Hilgert
#
#    See the file LICENSE.txt for your rights.
#
"""Shared fixtures: the time zone of the reference station."""

import os
import time

import pytest


@pytest.fixture
def berlin():
    """Run a test in the time zone of Central Europe, with summer time."""
    before = os.environ.get('TZ')
    os.environ['TZ'] = 'CET-1CEST,M3.5.0,M10.5.0/3'
    time.tzset()
    yield
    if before is None:
        del os.environ['TZ']
    else:
        os.environ['TZ'] = before
    time.tzset()
