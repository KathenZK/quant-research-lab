"""Select private research tests explicitly; never rewrite test failures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_LOCAL_DATA_CASES = json.loads(Path(__file__).with_name("local_data_cases.json").read_text())


def pytest_addoption(parser):
    parser.addoption(
        "--run-local-data", action="store_true", default=False,
        help="Run private-data tests; missing inputs remain failures.",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.nodeid.split("[", 1)[0] in _LOCAL_DATA_CASES:
            item.add_marker(pytest.mark.local_data)
        if item.get_closest_marker("local_data") and not config.getoption("--run-local-data"):
            item.add_marker(pytest.mark.skip(reason="Private research inputs require --run-local-data"))
