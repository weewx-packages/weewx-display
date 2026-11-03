# The environment of the test suite, with every version fixed.
FROM python:3.13.9-slim-bookworm

RUN pip install --no-cache-dir weewx==5.5.2 ephem==4.2 pytest==8.4.2 pytest-timeout==2.4.0

RUN useradd --create-home tester
USER tester
