default: fast

fast:
    PYTHONPATH="bin${PYTHONPATH:+:$PYTHONPATH}" python3 -m pytest -q tests

docker:
    docker compose -f tests/docker/compose.yml run --rm tests
