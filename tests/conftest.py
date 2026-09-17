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


COHORT_REGISTRY = (REPO_ROOT / "research" / "fp" / "records"
                   / "forward_paper_cohort_registry.json")

# The seven values the T0 freeze writes, and the pre-freeze value of each.
# Contract section 6 fixes this list; it is restated here as data so that a test
# needing the pre-freeze state can ask for it by name.
_PRE_FREEZE_ROW = {
    "cohort_id": None,
    "status": "NOT_STARTED",
    "t0_utc": None,
    "closed_utc": None,
    "closure_reason": None,
}


def committed_registry() -> dict:
    """The cohort registry exactly as committed — whatever state it is in."""
    return json.loads(COHORT_REGISTRY.read_text(encoding="utf-8"))


def pre_t0_registry(role: str = "FP-CONTROL-2") -> dict:
    """The committed registry, with ``role`` forced to its pre-freeze state.

    A test that drives a mechanism requiring a pre-T0 row must SAY it needs one.
    Before the Owner froze a T0 the committed registry supplied that state for
    free, so dozens of fixtures read the real file and inherited it without ever
    naming the dependency — and the moment the freeze was applied, every one of
    them failed against a registry that was perfectly lawful. Inheriting a state
    is not the same as requiring it, and this function is where the difference
    is written down.

    The paths, identity and every other field stay exactly as committed: only
    the freeze's own seven values are wound back, so a test still runs against
    the real runtime identity rather than a hand-built imitation of it.
    """
    registry = committed_registry()
    registry["fp_run_active"] = False
    for row in registry["instances"]:
        if row.get("role") != role:
            continue
        row.update(_PRE_FREEZE_ROW)
        row["change_log"] = []
        identity = row.get("runtime_identity")
        if isinstance(identity, dict):
            identity["source_commit"] = None
        row.pop("outcome", None)
    return registry


@pytest.fixture
def pre_t0_registry_dict() -> dict:
    return pre_t0_registry()


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
