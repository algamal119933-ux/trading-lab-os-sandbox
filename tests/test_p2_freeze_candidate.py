"""The CI gate a freeze candidate must pass, exercised on real freeze commits.

A gate whose only evidence is "it passed on a branch that changed nothing" has
not been exercised. So these tests build a scratch repository, commit freezes
into it — one lawful, and one for each way the transaction can be malformed —
and require the gate to draw the line where contract section 6 draws it:

    EXACTLY TWO FILES, EXACTLY SEVEN VALUES, the other row byte-identical

and, just as importantly, to stay silent on every change that is not a freeze.
A gate that fired on ordinary work would be switched off within a week, and the
day it mattered it would already be off.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import check_freeze_candidate as gate
from fp import registry_law as fp_law

ROLE = "FP-CONTROL-2"
CLOSED = "FP-CONTROL-1"
T0 = "2026-09-20T14:00:00Z"


def _run(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                            timeout=120)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _identity(**overrides) -> dict:
    identity = {
        "candidate_family": "BASELINE-1 operational control",
        "source_commit": None,
        "strategy_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "engine_version": "freqtradeorg/freqtrade:2026.7",
        "image_digest": None,
        "python_version": None,
        "pairs": ["BTC/USDT"],
        "timeframe": "1h",
        "fee_model": {"per_side_ratio": 0.001},
        "sizing": {"stake_amount": 10},
        "max_open_trades": 2,
        "paper_fill_model_version": "FREQTRADE_2026.7_DRYRUN_ORDERBOOK_V1",
        "bot_name": "fp-control-2",
        "db_path": "/freqtrade/user_data/fp-control-2/tradesv3.sqlite",
        "log_path": "/freqtrade/user_data/fp-control-2/logs/freqtrade.log",
        "evidence_dir": "/freqtrade/user_data/fp-control-2/evidence",
    }
    identity.update(overrides)
    return identity


def base_registry() -> dict:
    closed_identity = _identity(
        bot_name="fp-control-1",
        db_path="/freqtrade/user_data/fp-control-1/tradesv3.sqlite",
        log_path="/freqtrade/user_data/fp-control-1/logs/freqtrade.log",
        evidence_dir="/freqtrade/user_data/fp-control-1/evidence",
        source_commit="c" * 40,
    )
    return {
        "schema_version": "1.0.0",
        "registry_updated_utc": "2026-09-14T00:00:00Z",
        "fp_run_active": False,
        "instances": [
            {
                "role": CLOSED,
                "cohort_id": fp_law.cohort_id_for(CLOSED, "2026-09-08T12:15:13Z"),
                "status": "CLOSED",
                "t0_utc": "2026-09-08T12:15:13Z",
                "runtime_identity": closed_identity,
                "change_log": [],
            },
            {
                "role": ROLE,
                "cohort_id": None,
                "status": "NOT_STARTED",
                "t0_utc": None,
                "runtime_identity": _identity(),
                "change_log": [],
            },
        ],
        "real_money_authorized": False,
    }


@pytest.fixture
def repo(tmp_path):
    """A scratch repository carrying the runtime paths and a pre-freeze registry."""
    root = tmp_path / "repo"
    root.mkdir()
    _run(root, "init", "--quiet", "-b", "main")
    _run(root, "config", "user.email", "test@example.invalid")
    _run(root, "config", "user.name", "test")
    for name, body in {
        "freqtrade/user_data/strategies/BaselineEmaRegimeV1.py": "class S: pass\n",
        "freqtrade/user_data/config.paper.json.example": '{"dry_run": true}\n',
        "monitoring/exporter/exporter.py": "print('m')\n",
        "research/fp/capture.py": "V = 1\n",
        "scripts/verify_repo.py": "print('ok')\n",
        "scripts/start_fp_control.sh": "#!/usr/bin/env bash\n",
        "docker-compose.yml": "services: {}\n",
        "docker-compose.fp.yml": "services: {}\n",
        "MANIFEST.txt": "# manifest\n",
        gate.REGISTRY_PATH: json.dumps(base_registry(), indent=2) + "\n",
    }.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    _run(root, "add", "-A")
    _run(root, "commit", "--quiet", "-m", "M1")
    # The freeze is a candidate on a branch the Owner merges, never a direct
    # write to main — so the gate is given the diff it will actually see.
    _run(root, "checkout", "--quiet", "-b", "claude/p2-freeze")
    return root


def write(repo, files: dict[str, str], message: str) -> str:
    for name, body in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    _run(repo, "add", "-A")
    _run(repo, "commit", "--quiet", "-m", message)
    return _run(repo, "rev-parse", "HEAD")


def frozen_registry(repo, m1: str, **mutations) -> dict:
    registry = base_registry()
    row = next(item for item in registry["instances"] if item["role"] == ROLE)
    row["t0_utc"] = T0
    row["cohort_id"] = fp_law.cohort_id_for(ROLE, T0)
    row["status"] = "RUNNING"
    row["runtime_identity"]["source_commit"] = m1
    row["change_log"] = [{"utc": T0, "class": "O", "description": "T0 frozen."}]
    registry["fp_run_active"] = True
    registry["registry_updated_utc"] = "2026-09-20T13:00:00Z"
    for path, value in mutations.items():
        target = registry
        parts = path.split(".")
        for part in parts[:-1]:
            target = target[int(part)] if part.isdigit() else target[part]
        key = parts[-1]
        target[int(key) if key.isdigit() else key] = value
    return registry


def freeze(repo, m1: str, *, extra: dict | None = None, **mutations) -> str:
    files = {
        gate.REGISTRY_PATH: json.dumps(frozen_registry(repo, m1, **mutations), indent=2) + "\n",
        "MANIFEST.txt": "# manifest, regenerated\n",
    }
    files.update(extra or {})
    return write(repo, files, "Freeze T0")


def run(repo, head="HEAD"):
    return gate.check("main", head, repo_root=repo)


# -- the gate stays silent on everything that is not a freeze --------------


def test_a_branch_that_does_not_touch_the_registry_is_not_this_gates_business(repo):
    write(repo, {"research/fp/capture.py": "V = 2\n"}, "ordinary work")
    report = run(repo)
    assert report["classification"] == gate.NOT_A_FREEZE
    assert report["result"] == "PASS"


def test_a_registry_change_that_is_not_a_freeze_passes(repo):
    """A closure or a class-O binding moves the registry and is not a T0."""
    registry = base_registry()
    row = next(item for item in registry["instances"] if item["role"] == ROLE)
    row["runtime_identity"]["image_digest"] = "sha256:" + "d" * 64
    write(repo, {gate.REGISTRY_PATH: json.dumps(registry, indent=2) + "\n"}, "bind observations")
    report = run(repo)
    assert report["classification"] == gate.NOT_A_FREEZE
    assert report["result"] == "PASS"


# -- the lawful freeze -----------------------------------------------------


def test_a_lawful_freeze_passes(repo):
    m1 = _run(repo, "rev-parse", "HEAD")
    freeze(repo, m1)
    report = run(repo)
    assert report["classification"] == gate.FREEZE_CANDIDATE
    assert report["result"] == "PASS", report["problems"]
    assert report["cohort_id"] == fp_law.cohort_id_for(ROLE, T0)


# -- exactly two files -----------------------------------------------------


def test_a_freeze_that_also_changes_code_is_refused(repo):
    """Two files is what makes the equivalence proof reviewable in one line."""
    m1 = _run(repo, "rev-parse", "HEAD")
    freeze(repo, m1, extra={"research/fp/capture.py": "V = 2\n"})
    report = run(repo)
    assert report["result"] == "FAIL"
    assert any("also\nchanges" in p or "also changes" in p for p in report["problems"]), report["problems"]


def test_a_freeze_that_also_changes_a_doc_is_refused(repo):
    m1 = _run(repo, "rev-parse", "HEAD")
    freeze(repo, m1, extra={"docs/p2/NOTE.md": "a note\n"})
    report = run(repo)
    assert report["result"] == "FAIL"


def test_a_freeze_that_forgets_the_manifest_is_refused(repo):
    m1 = _run(repo, "rev-parse", "HEAD")
    write(repo, {gate.REGISTRY_PATH: json.dumps(frozen_registry(repo, m1), indent=2) + "\n"},
          "freeze without manifest")
    report = run(repo)
    assert report["result"] == "FAIL"


# -- exactly seven values --------------------------------------------------


def test_a_freeze_that_also_moves_a_risk_field_is_refused(repo):
    m1 = _run(repo, "rev-parse", "HEAD")
    freeze(repo, m1, **{"instances.1.runtime_identity.max_open_trades": 4})
    report = run(repo)
    assert report["result"] == "FAIL"
    assert any("may not touch" in p for p in report["problems"]), report["problems"]


def test_a_freeze_that_leaves_the_flag_false_is_refused(repo):
    m1 = _run(repo, "rev-parse", "HEAD")
    freeze(repo, m1, **{"fp_run_active": False})
    report = run(repo)
    assert report["result"] == "FAIL"


def test_a_freeze_that_touches_the_closed_row_is_refused(repo):
    """A closed cohort's record is history and never moves."""
    m1 = _run(repo, "rev-parse", "HEAD")
    freeze(repo, m1, **{"instances.0.closure_reason": "rewritten"})
    report = run(repo)
    assert report["result"] == "FAIL"
    assert any("byte-identical" in p for p in report["problems"]), report["problems"]


def test_a_cohort_id_that_does_not_derive_from_t0_is_refused(repo):
    m1 = _run(repo, "rev-parse", "HEAD")
    freeze(repo, m1, **{"instances.1.cohort_id": "FP-CONTROL-2-20200101T000000Z"})
    report = run(repo)
    assert report["result"] == "FAIL"
    assert any("derives" in p for p in report["problems"]), report["problems"]


def test_two_change_log_entries_are_refused(repo):
    m1 = _run(repo, "rev-parse", "HEAD")
    freeze(repo, m1, **{"instances.1.change_log": [
        {"utc": T0, "class": "O", "description": "one"},
        {"utc": T0, "class": "S", "description": "two"},
    ]})
    report = run(repo)
    assert report["result"] == "FAIL"


def test_a_declared_commit_that_is_not_equivalent_is_refused(repo):
    """M1 and M2 must run the same system, and the gate computes that."""
    m1 = _run(repo, "rev-parse", "HEAD")
    older = write(repo, {"research/fp/capture.py": "V = 99\n"}, "move the runtime")
    freeze(repo, m1)
    report = run(repo)
    assert report["result"] == "FAIL"
    assert any("SEMANTIC_IDENTITY" in p for p in report["problems"]), report["problems"]


def test_a_freeze_declaring_no_source_commit_is_refused(repo):
    m1 = _run(repo, "rev-parse", "HEAD")
    freeze(repo, m1, **{"instances.1.runtime_identity.source_commit": None})
    report = run(repo)
    assert report["result"] == "FAIL"
