"""Shared test fixtures.

The suite imports repository scripts directly rather than shelling out, so a
failure points at a line of code instead of an exit status.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = REPO_ROOT / "freqtrade" / "user_data" / "config.paper.json.example"

for extra in (REPO_ROOT / "scripts", REPO_ROOT / "research", REPO_ROOT / "monitoring" / "exporter"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def example_config() -> dict:
    return json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))


@pytest.fixture
def write_config(tmp_path):
    """Write a config dict to a temp file and return its path."""

    def _write(config: dict, name: str = "config.json") -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        return path

    return _write
