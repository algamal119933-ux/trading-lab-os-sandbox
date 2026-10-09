"""CEA-1 §3/§15: the protected list is real, protects itself, and covers every judge.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import cea_policy as cp

REPO_ROOT = Path(__file__).resolve().parents[1]


def tracked() -> list[str]:
    out = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files"], capture_output=True, text=True, check=True)
    files = set(out.stdout.split())
    # Files this branch adds count before they are committed, so the suite gives
    # the same answer before and after the commit.
    status = subprocess.run(["git", "-C", str(REPO_ROOT), "status", "--porcelain", "-uall"],
                            capture_output=True, text=True, check=True).stdout
    files |= {line[3:].strip() for line in status.splitlines() if line.startswith("??")}
    return sorted(files)


GLOBS = cp.protected_at(REPO_ROOT, None)


@pytest.mark.parametrize("glob", [g for g, future in GLOBS if not future])
def test_every_present_glob_matches_a_tracked_file(glob):
    assert any(cp.glob_match(glob, p) for p in tracked()), glob


@pytest.mark.parametrize("path", [
    ".github/gates/protected_paths.txt", ".github/gates/merge_law.py", ".github/gates/cea_policy.py",
    ".github/gates/resolve_next_unit.py", ".github/gates/AUTONOMY_STATE.json", ".github/gates/ACTIVATION.json",
    ".github/workflows/merge-law.yml", "CLAUDE.md", "pytest.ini", "tests/conftest.py",
    "scripts/verify_repo.py", "research/trial_ledger.py", "research/cycle2/funnel.py",
    "research/cycle2/multiple_testing.py", "research/cycle2/config_n.py", "research/cycle2/driver.py",
    "tests/test_p2_scope_audit.py", "docs/p2/P2_CONTRACT.md",
    "docs/governance/CONTINUOUS_EXECUTION_AUTHORITY_1.md", "charters/COMMERCIAL-VERIFICATION-LANE-1.json",
    "research/datasets/dataset_v2.lock.json", "scripts/paper_guard.py",
])
def test_every_judge_is_protected(path):
    assert cp.is_protected(path, GLOBS), path


@pytest.mark.parametrize("path", ["verification/runner/run.py", "tests/test_verification_runner.py",
                                  "MANIFEST.txt"])
def test_product_paths_stay_routine(path):
    assert not cp.is_protected(path, GLOBS), path


@pytest.mark.parametrize("pattern,path,expected", [
    ("research/cycle2/*.py", "research/cycle2/funnel.py", True),
    ("research/cycle2/*.py", "research/cycle2/sub/x.py", False),
    (".github/**", ".github/gates/x.py", True),
    ("tests/test_p2_*.py", "tests/test_p2_scope_audit.py", True),
    ("tests/test_p2_*.py", "tests/test_verification_x.py", False),
])
def test_glob_semantics(pattern, path, expected):
    assert cp.glob_match(pattern, path) is expected
