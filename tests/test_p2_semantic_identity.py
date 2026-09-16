"""SEMANTIC_IDENTITY, proved against a repository where changes can be made.

The equivalence proof is the load-bearing claim of P2's source-commit model: the
registry declares M1 while every record is stamped M2, and the two are only
honestly interchangeable if nothing that decides runtime behaviour differs
between them. A test that only ever compares a commit to itself would confirm
that equality is reflexive and nothing else.

So these tests build a small real git repository carrying the same runtime paths
the contract names, commit changes into it, and require the comparison to draw
the line in the right place — DIFFERENT for anything that changes what the
runtime does, EQUIVALENT for the two fields the contract excludes as
observations, and UNPROVEN whenever the question could not be answered at all.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from fp import semantic_identity as si

ROLE = "FP-CONTROL-2"


def _run(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                            timeout=120)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _registry(**identity_overrides) -> str:
    identity = {
        "candidate_family": "BASELINE-1 operational control",
        "source_commit": None,
        "strategy_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "engine_version": "freqtradeorg/freqtrade:2026.7",
        "image_digest": None,
        "python_version": None,
        "pairs": ["BTC/USDT", "ETH/USDT"],
        "timeframe": "1h",
        "detail_timeframe": "5m",
        "fee_model": {"per_side_ratio": 0.001},
        "sizing": {"dry_run_wallet": 100, "stake_amount": 10},
        "max_open_trades": 2,
        "order_policy": {"execution": "dry-run only"},
        "feature_sources": ["binance spot public OHLCV 1h"],
        "paper_fill_model_version": "FREQTRADE_2026.7_DRYRUN_ORDERBOOK_V1",
        "environment_variable_allowlist": ["FREQTRADE_API_USER"],
        "bot_name": "fp-control-2",
        "db_path": "/freqtrade/user_data/fp-control-2/tradesv3.sqlite",
        "wallet": 100,
        "log_path": "/freqtrade/user_data/fp-control-2/logs/freqtrade.log",
        "evidence_dir": "/freqtrade/user_data/fp-control-2/evidence",
    }
    identity.update(identity_overrides)
    return json.dumps(
        {
            "schema_version": "1.0.0",
            "fp_run_active": False,
            "instances": [
                {
                    "role": ROLE,
                    "cohort_id": None,
                    "status": "NOT_STARTED",
                    "t0_utc": None,
                    "runtime_identity": identity,
                    "change_log": [],
                }
            ],
            "real_money_authorized": False,
        },
        indent=2,
    ) + "\n"


@pytest.fixture
def scratch_repo(tmp_path):
    """A repository carrying every runtime path the contract's model names."""
    repo = tmp_path / "scratch"
    repo.mkdir()
    _run(repo, "init", "--quiet", "-b", "main")
    _run(repo, "config", "user.email", "test@example.invalid")
    _run(repo, "config", "user.name", "test")

    files = {
        "freqtrade/user_data/strategies/BaselineEmaRegimeV1.py": "class S:\n    pass\n",
        "freqtrade/user_data/config.paper.json.example": '{"dry_run": true}\n',
        "monitoring/exporter/exporter.py": "print('metrics')\n",
        "research/fp/capture.py": "VERSION = 1\n",
        "research/fp/records/forward_paper_cohort_registry.json": _registry(),
        "scripts/start_fp_control.sh": "#!/usr/bin/env bash\necho start\n",
        "scripts/verify_repo.py": "print('ok')\n",
        "docker-compose.yml": "services: {}\n",
        "docker-compose.fp.yml": "services: {}\n",
    }
    for name, body in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    _run(repo, "add", "-A")
    _run(repo, "commit", "--quiet", "-m", "base")
    return repo


def _commit(repo, path: str, body: str, message: str) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    _run(repo, "add", "-A")
    _run(repo, "commit", "--quiet", "-m", message)
    return _run(repo, "rev-parse", "HEAD")


# -- the comparison draws the line where the contract draws it -------------


def test_an_unchanged_commit_is_equivalent_to_itself(scratch_repo):
    head = _run(scratch_repo, "rev-parse", "HEAD")
    report = si.compare(head, head, ROLE, repo_root=scratch_repo)
    assert report["result"] == si.EQUIVALENT
    assert report["differences"] == []


def test_a_changed_strategy_is_a_semantic_difference(scratch_repo):
    base = _run(scratch_repo, "rev-parse", "HEAD")
    head = _commit(scratch_repo, "freqtrade/user_data/strategies/BaselineEmaRegimeV1.py",
                   "class S:\n    stoploss = -0.10\n", "change the strategy")
    report = si.compare(base, head, ROLE, repo_root=scratch_repo)
    assert report["result"] == si.DIFFERENT
    assert any(d["path"].endswith("BaselineEmaRegimeV1.py") for d in report["differences"])


def test_a_changed_research_module_is_a_semantic_difference(scratch_repo):
    """research/fp/*.py is a glob, and git pathspecs do not honour globs.

    The first implementation handed these patterns to ``git ls-tree`` as
    pathspecs, where they matched nothing while the directory prefixes beside
    them matched normally — so every module holding the runtime's own logic
    silently left the comparison, and it still reported a populated tree. This
    test exists because that failure was invisible from the outside.
    """
    base = _run(scratch_repo, "rev-parse", "HEAD")
    head = _commit(scratch_repo, "research/fp/capture.py", "VERSION = 2\n", "change capture")
    report = si.compare(base, head, ROLE, repo_root=scratch_repo)
    assert report["result"] == si.DIFFERENT
    assert any(d["path"] == "research/fp/capture.py" for d in report["differences"])


def test_a_changed_shell_launcher_is_a_semantic_difference(scratch_repo):
    base = _run(scratch_repo, "rev-parse", "HEAD")
    head = _commit(scratch_repo, "scripts/start_fp_control.sh",
                   "#!/usr/bin/env bash\necho different\n", "change the launcher")
    report = si.compare(base, head, ROLE, repo_root=scratch_repo)
    assert report["result"] == si.DIFFERENT


def test_an_executable_bit_is_a_semantic_difference(scratch_repo):
    """A shell script's mode is behaviour, and two blobs can share one id."""
    base = _run(scratch_repo, "rev-parse", "HEAD")
    _run(scratch_repo, "update-index", "--chmod=+x", "scripts/start_fp_control.sh")
    _run(scratch_repo, "commit", "--quiet", "-m", "make it executable")
    head = _run(scratch_repo, "rev-parse", "HEAD")
    report = si.compare(base, head, ROLE, repo_root=scratch_repo)
    assert report["result"] == si.DIFFERENT


def test_a_changed_risk_field_in_the_registry_is_a_semantic_difference(scratch_repo):
    base = _run(scratch_repo, "rev-parse", "HEAD")
    head = _commit(scratch_repo, "research/fp/records/forward_paper_cohort_registry.json",
                   _registry(max_open_trades=4), "widen max_open_trades")
    report = si.compare(base, head, ROLE, repo_root=scratch_repo)
    assert report["result"] == si.DIFFERENT
    assert any(d.get("field") == "runtime_identity.max_open_trades" for d in report["differences"])


@pytest.mark.parametrize(
    "field, value",
    [("image_digest", "sha256:" + "c" * 64), ("python_version", "3.14.6")],
)
def test_the_two_observation_fields_are_excluded(scratch_repo, field, value):
    """S3b binds these, and the contract excludes them — for a stated reason.

    They are observations OF a runtime, not instructions TO one, and excluding
    them applies the existing model rather than inventing a licence: FP-CONTROL-1's
    own first change_log entry binds exactly these two as class O, "observability
    only - no trading semantics are changed."
    """
    base = _run(scratch_repo, "rev-parse", "HEAD")
    head = _commit(scratch_repo, "research/fp/records/forward_paper_cohort_registry.json",
                   _registry(**{field: value}), f"bind {field}")
    assert _run(scratch_repo, "rev-parse", base) != head
    report = si.compare(base, head, ROLE, repo_root=scratch_repo)
    assert report["result"] == si.EQUIVALENT, report["differences"]


def test_the_freeze_transaction_itself_is_excluded(scratch_repo):
    """M1 and M2 differ in exactly the freeze's own bookkeeping, by construction.

    If those fields were compared, the proof the contract requires —
    SEMANTIC_IDENTITY(M1) == SEMANTIC_IDENTITY(M2) — could never hold for any
    real freeze, and the model would be unsatisfiable rather than strict.
    """
    base = _run(scratch_repo, "rev-parse", "HEAD")
    registry = json.loads((scratch_repo / "research/fp/records/forward_paper_cohort_registry.json")
                          .read_text(encoding="utf-8"))
    row = registry["instances"][0]
    row["t0_utc"] = "2026-09-20T14:00:00Z"
    row["cohort_id"] = "FP-CONTROL-2-20260920T140000Z"
    row["status"] = "RUNNING"
    row["runtime_identity"]["source_commit"] = "d" * 40
    row["change_log"] = [{"utc": "2026-09-20T14:00:00Z", "class": "O", "description": "T0 frozen."}]
    registry["fp_run_active"] = True
    head = _commit(scratch_repo, "research/fp/records/forward_paper_cohort_registry.json",
                   json.dumps(registry, indent=2) + "\n", "freeze T0")
    report = si.compare(base, head, ROLE, repo_root=scratch_repo)
    assert report["result"] == si.EQUIVALENT, report["differences"]


# -- fail-closed: an unanswerable question is never a pass -----------------


def test_an_unresolvable_revision_is_unproven(scratch_repo):
    head = _run(scratch_repo, "rev-parse", "HEAD")
    report = si.compare(head, "no-such-revision", ROLE, repo_root=scratch_repo)
    assert report["result"] == si.UNPROVEN


def test_a_role_the_registry_does_not_declare_is_unproven(scratch_repo):
    head = _run(scratch_repo, "rev-parse", "HEAD")
    report = si.compare(head, head, "FP-CANDIDATE-A", repo_root=scratch_repo)
    assert report["result"] == si.UNPROVEN


def test_a_runtime_path_that_matches_nothing_refuses(scratch_repo):
    """A rule that stops matching shrinks the comparison without anyone deciding it should."""
    _run(scratch_repo, "rm", "--quiet", "-r", "monitoring")
    _run(scratch_repo, "commit", "--quiet", "-m", "drop the exporter")
    head = _run(scratch_repo, "rev-parse", "HEAD")
    with pytest.raises(si.SemanticIdentityError, match="matched no file"):
        si.semantic_identity(head, ROLE, repo_root=scratch_repo)
    assert si.compare(head, head, ROLE, repo_root=scratch_repo)["result"] == si.UNPROVEN


def test_records_are_excluded_from_the_runtime_tree(scratch_repo):
    """research/fp/records/ is evidence and bookkeeping, not runtime behaviour."""
    head = _run(scratch_repo, "rev-parse", "HEAD")
    tree = si.runtime_tree(head, repo_root=scratch_repo)
    assert "research/fp/capture.py" in tree
    assert not any(path.startswith("research/fp/records/") for path in tree)


def test_a_glob_does_not_cross_a_directory_separator():
    assert si._matches_glob("research/fp/capture.py", "research/fp/*.py")
    assert not si._matches_glob("research/fp/records/thing.py", "research/fp/*.py")
    assert not si._matches_glob("research/other/capture.py", "research/fp/*.py")


# -- the real repository ---------------------------------------------------


def test_the_real_repository_covers_every_declared_runtime_rule():
    """Every rule in the contract names something that exists here, right now."""
    tree = si.runtime_tree("HEAD")
    for prefix in si.TREE_PREFIXES:
        assert any(p.startswith(prefix) for p in tree), prefix
    for pattern in si.TREE_GLOBS:
        assert any(si._matches_glob(p, pattern) for p in tree), pattern
    for name in si.TREE_FILES:
        assert name in tree, name
