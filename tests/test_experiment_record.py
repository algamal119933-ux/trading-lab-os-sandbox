"""CLOUD-0 / C0.6 — the research evidence schema.

A record that validates is a record someone else can re-run. The tests below
pin down the fields that make that true and the locked-OOS refusal.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import record_experiment as rec

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_RECORD = REPO_ROOT / "research" / "records" / "EXAMPLE_experiment_record.json"


@pytest.fixture
def complete_record(repo_root):
    record = rec.template()
    rec.stamp(record, ["freqtrade/user_data/config.paper.json.example"])
    record.update(
        {
            "run_name": "unit-test-record",
            "command": "freqtrade backtesting --strategy PlumbingSmokeStrategy",
            "freqtrade_version": "2026.7",
            "dataset_hashes": {"BTC/USDT 1h": "a" * 64, "ETH/USDT 1h": "b" * 64},
            "dataset_audit_pass": True,
            "strategy": rec.strategy_fingerprint("PlumbingSmokeStrategy"),
            "metrics": {"total_return_pct": -1.0, "trade_count": 3},
            "gate": "INFORMATIONAL",
            "reason": "unit test fixture",
        }
    )
    return record


def test_schema_file_is_valid_json_schema():
    import jsonschema

    schema = rec.load_schema()
    jsonschema.validators.validator_for(schema).check_schema(schema)


def test_schema_requires_every_field_cloud_0_asks_for():
    required = set(rec.load_schema()["required"])
    for field in (
        "timestamp_utc",
        "command",
        "code_commit",
        "config_hash",
        "dataset_hashes",
        "strategy",
        "freqtrade_version",
        "pairs",
        "timeframe",
        "timerange",
        "fee_assumption",
        "wallet",
        "stake",
        "max_open_trades",
        "metrics",
        "gate",
        "reason",
    ):
        assert field in required, f"{field} must be required by the schema"
    # detail_timeframe is optional-but-declared: null means "not used".
    assert "detail_timeframe" in rec.load_schema()["properties"]


def test_a_stamped_template_validates(complete_record):
    assert rec.validate(complete_record) == []


def test_stamp_fills_repo_derived_fields():
    record = rec.template()
    rec.stamp(record, ["freqtrade/user_data/config.paper.json.example"])
    assert len(record["config_hash"]) == 64
    assert record["timestamp_utc"].endswith("Z")
    assert record["code_commit"]


def test_strategy_fingerprint_tracks_file_content(tmp_path, monkeypatch):
    strategies = tmp_path / "strategies"
    strategies.mkdir()
    path = strategies / "S.py"
    path.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(rec, "STRATEGY_DIR", strategies)
    first = rec.strategy_fingerprint("S")["sha256"]
    path.write_text("x = 2\n", encoding="utf-8")
    assert rec.strategy_fingerprint("S")["sha256"] != first


@pytest.mark.parametrize(
    "mutation",
    [
        {"gate": "MAYBE"},
        {"reason": ""},
        {"timeframe": "1hour"},
        {"timerange": "2025-2026"},
        {"pairs": []},
        {"max_open_trades": 9},
        {"wallet": 0},
        {"stake": -1},
        {"dataset_hashes": {}},
        {"dataset_hashes": {"BTC/USDT 1h": "nothex"}},
        {"config_hash": "short"},
        {"code_commit": "not-a-sha"},
        {"period_label": "whenever"},
        {"fee_assumption": {"per_side_ratio": 0.5, "source": "absurd"}},
        {"schema_version": "0.1.0"},
        {"unknown_top_level_field": True},
    ],
)
def test_schema_rejects_malformed_records(complete_record, mutation):
    record = copy.deepcopy(complete_record)
    record.update(mutation)
    assert rec.validate(record), f"schema accepted {mutation}"


@pytest.mark.parametrize("field", list(rec.template().keys()))
def test_every_required_field_is_actually_enforced(complete_record, field):
    if field not in rec.load_schema()["required"]:
        pytest.skip(f"{field} is optional")
    record = copy.deepcopy(complete_record)
    del record[field]
    assert rec.validate(record), f"schema accepted a record missing {field}"


def test_oos_records_are_locked(tmp_path, complete_record, capsys):
    record = copy.deepcopy(complete_record)
    record["period_label"] = "oos"
    path = tmp_path / "oos.json"
    path.write_text(json.dumps(record), encoding="utf-8")

    assert rec.main(["summarize", str(path)]) == 3
    assert "OOS_LOCKED" in capsys.readouterr().err
    assert rec.main(["summarize", str(path), "--unlock-oos"]) == 0


def test_markdown_summary_carries_reproduction_fields(complete_record):
    markdown = rec.to_markdown(complete_record)
    for token in ("Code commit", "Config hash", "Dataset fingerprints", "Gate", "Metrics"):
        assert token in markdown


def test_markdown_flags_a_dirty_worktree(complete_record):
    record = copy.deepcopy(complete_record)
    record["code_dirty"] = True
    assert "dirty worktree" in rec.to_markdown(record)


def test_validate_cli_reports_failures(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema_version": "1.0.0"}), encoding="utf-8")
    assert rec.main(["validate", str(bad)]) == 2
    assert "INVALID" in capsys.readouterr().err


def test_committed_example_record_validates():
    record = json.loads(EXAMPLE_RECORD.read_text(encoding="utf-8"))
    assert rec.validate(record) == []


def test_committed_example_record_is_not_presented_as_evidence():
    record = json.loads(EXAMPLE_RECORD.read_text(encoding="utf-8"))
    assert record["gate"] == "INFORMATIONAL"
    assert record["period_label"] != "oos"


def test_every_committed_record_validates(repo_root):
    """Catch a malformed record locally, not three commits later in CI.

    Both baseline records were committed with keys the schema forbids and
    `analyses` values outside its enum. CI's own "Validate committed experiment
    records" step did catch it — the gap was here: no test in this suite ever
    fed a real record to the validator, so three pushes went out red before
    anyone looked at the CI result.
    """
    records = sorted((repo_root / "research" / "records").glob("*.json"))
    assert records, "no experiment records found to validate"
    failures = {}
    for path in records:
        problems = rec.validate(json.loads(path.read_text(encoding="utf-8")))
        if problems:
            failures[path.name] = problems
    assert not failures, failures


def test_both_baseline_records_are_present_and_agree_on_the_frozen_strategy(repo_root):
    """Validation is only meaningful if it ran the same code Development did."""
    base = repo_root / "research" / "records"
    dev = json.loads((base / "baseline1_development_datasetv2.json").read_text(encoding="utf-8"))
    val = json.loads((base / "baseline1_validation_datasetv2.json").read_text(encoding="utf-8"))
    assert dev["strategy"]["sha256"] == val["strategy"]["sha256"]
    assert dev["config_hash"] == val["config_hash"]
    assert dev["dataset_hashes"] == val["dataset_hashes"]
    assert dev["period_label"] == "development"
    assert val["period_label"] == "validation"
