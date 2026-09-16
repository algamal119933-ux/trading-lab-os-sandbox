"""Shared test fixtures.

The suite imports repository scripts directly rather than shelling out, so a
failure points at a line of code instead of an exit status.
"""

from __future__ import annotations

import json
import sys

# Tests must leave the tree exactly as they found it; a stray __pycache__ is a
# write into the repository and makes a read-only clean checkout differ.
sys.dont_write_bytecode = True
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = REPO_ROOT / "freqtrade" / "user_data" / "config.paper.json.example"

for extra in (
    REPO_ROOT / "scripts",
    REPO_ROOT / "research",
    REPO_ROOT / "research" / "external",
    REPO_ROOT / "monitoring" / "exporter",
):
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


def clone_at_head(destination):
    """A disposable clone positioned at this working copy's exact commit.

    Cloning by branch name looked equivalent and was not: a `pull_request` CI
    checkout is detached, so `git branch --show-current` is empty and the clone
    failed there while passing on every branch checkout. The commit is the
    identity that matters for a reproduction proof, so the clone is taken at the
    SHA and `origin` is removed — leaving no remote-tracking refs and no way for
    the copy to depend on the repository it came from.
    """
    import subprocess
    from pathlib import Path as _Path

    destination = _Path(destination)
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", ".", str(destination)],
                   capture_output=True, text=True, timeout=600, check=True)
    subprocess.run(["git", "-C", str(destination), "checkout", "--quiet", "--detach", head],
                   capture_output=True, text=True, timeout=300, check=True)
    subprocess.run(["git", "-C", str(destination), "remote", "remove", "origin"],
                   capture_output=True, check=True)
    return destination, head
