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
    # CI gates live outside RUNTIME_TREE on purpose (contract section 5): a
    # module under scripts/ would change SEMANTIC_IDENTITY and break the
    # equivalence proof the freeze depends on. They are still tested.
    REPO_ROOT / ".github" / "gates",
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


def live_role() -> str:
    """The role whose T0 state the suite must survive, resolved from the file.

    Every caller of :func:`pre_t0_registry` means the same thing by its
    argument: *the cohort this repository is currently freezing or has frozen*.
    Spelling that as a literal made the suite correct for exactly one cohort —
    when FP-CONTROL-3 was frozen, fixtures still naming FP-CONTROL-2 wound back
    a row nobody had frozen and set ``fp_run_active`` false while a different
    row was RUNNING, manufacturing a contradiction the registry did not have.
    Twenty-nine tests failed on a lawful freeze.

    So it is derived: the RUNNING row if one exists, otherwise the single row
    still NOT_STARTED, which is the row a freeze would target next. Both states
    resolve to the cohort in question, and neither needs editing when the next
    successor arrives.
    """
    instances = committed_registry()["instances"]
    running = [row["role"] for row in instances if row.get("status") == "RUNNING"]
    if len(running) == 1:
        return running[0]
    not_started = [row["role"] for row in instances if row.get("status") == "NOT_STARTED"]
    if len(not_started) == 1:
        return not_started[0]
    raise RuntimeError(
        f"cannot resolve the live role: RUNNING={running}, NOT_STARTED={not_started}. "
        "The suite will not guess which cohort a fixture meant"
    )


def pre_t0_registry(role: str | None = None) -> dict:
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

    ``role`` defaults to :func:`live_role`, the cohort this repository is
    actually freezing. Winding back one row while leaving another RUNNING, and
    clearing ``fp_run_active`` regardless, is not a pre-T0 registry — it is an
    unlawful one, and the law would rightly refuse it.
    """
    role = role if role is not None else live_role()
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
