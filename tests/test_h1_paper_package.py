"""H1-PAPER-COHORT-PACKAGE-1: static package law.

Nothing here starts a container, contacts an exchange or reads market data.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "research" / "paper" / "h1" / "package"

_spec = importlib.util.spec_from_file_location("h1_paper", PACKAGE / "h1_paper.py")
h1_paper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h1_paper)


def _cohort() -> dict:
    return json.loads((PACKAGE / "cohort.json").read_text(encoding="utf-8"))


def test_the_package_verifies_clean():
    assert h1_paper.verify() == []


def test_the_manifest_covers_every_package_file():
    listed = h1_paper.read_manifest()
    assert sorted(listed) == h1_paper.packaged_files()


def test_the_frozen_identity_is_the_qualified_one():
    cohort = _cohort()
    assert cohort["candidate_id"] == "H1_EMACROSS"
    assert cohort["strategy"]["sha256"] == "387cf39f58d266bb63d06865a0784bc2e08676edf54f4610c7d7709bb2a95f24"
    assert cohort["strategy"]["params_sha256"] == "9209a90e5092216af166fd10b9e7415690ab16af0fb3010c7e94e162c027e3ee"
    assert cohort["strategy"]["params"] == {"ema_period": 600, "exit_threshold": 2.0}
    assert cohort["market"]["pairs"] == ["BTC/USDT"] and cohort["market"]["timeframe"] == "1h"
    assert cohort["engine"]["image_digest"].startswith("sha256:da3428fd")


def test_no_t0_and_no_real_money():
    cohort = _cohort()
    assert cohort["t0"]["t0_utc"] is None and cohort["t0"]["activation_utc"] is None
    assert cohort["real_money_authorized"] is False
    config = json.loads((PACKAGE / "config.h1-paper.json").read_text(encoding="utf-8"))
    assert config["dry_run"] is True
    assert config["exchange"]["key"] == "" and config["exchange"]["secret"] == ""
    assert config["force_entry_enable"] is False


def test_the_gpl_strategy_is_not_vendored():
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True,
                             check=True).stdout.split()
    assert not any(Path(p).name in ("EmaCross.py", "EmaCross.json") for p in tracked)


def test_the_cohort_is_not_in_the_p2_registry():
    registry = json.loads((REPO / "research" / "fp" / "records" /
                           "forward_paper_cohort_registry.json").read_text(encoding="utf-8"))
    roles = {row["role"] for row in registry["instances"]}
    assert roles == {"FP-CONTROL-1", "FP-CONTROL-2", "FP-CONTROL-3"}
    assert not any("H1" in (row.get("cohort_id") or "") for row in registry["instances"])


# -- negatives: verify must catch each of these ------------------------------


@pytest.fixture
def scratch_package(tmp_path, monkeypatch):
    copy = tmp_path / "package"
    shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("PACKAGE_DIR", "MANIFEST", "COHORT", "CONFIG", "COMPOSE", "SCHEMA"):
        original = getattr(h1_paper, name)
        monkeypatch.setattr(h1_paper, name, copy if name == "PACKAGE_DIR" else copy / original.name)
    return copy


def _rewrite_json(path: Path, mutate) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_verify_refuses_live_trading(scratch_package):
    _rewrite_json(scratch_package / "config.h1-paper.json", lambda c: c.update(dry_run=False))
    errors = h1_paper.verify()
    assert any("dry_run" in e for e in errors)
    assert any("manifest" in e for e in errors)


def test_verify_refuses_a_second_pair(scratch_package):
    _rewrite_json(scratch_package / "config.h1-paper.json",
                  lambda c: c["exchange"].update(pair_whitelist=["BTC/USDT", "ETH/USDT"]))
    assert any("config:" in e for e in h1_paper.verify())


def test_verify_refuses_a_t0_in_the_package(scratch_package):
    _rewrite_json(scratch_package / "cohort.json",
                  lambda c: c["t0"].update(t0_utc="2026-10-01T00:00:00Z"))
    assert any(e.startswith("t0:") for e in h1_paper.verify())


def _rewrite_compose(path: Path, mutate) -> None:
    compose = yaml.safe_load(path.read_text(encoding="utf-8"))
    mutate(compose["services"]["freqtrade"])
    path.write_text(yaml.safe_dump(compose), encoding="utf-8")


def test_verify_refuses_a_p2_mount(scratch_package):
    _rewrite_compose(scratch_package / "docker-compose.h1-paper.yml",
                     lambda s: s["volumes"].__setitem__(
                         2, "/home/hamza/projects/trading/trading_lab_os_final/freqtrade/user_data/fp-control-3:/freqtrade/lane"))
    assert any("P2 path" in e for e in h1_paper.verify())


def test_verify_refuses_a_p2_port(scratch_package):
    _rewrite_compose(scratch_package / "docker-compose.h1-paper.yml",
                     lambda s: s.update(ports=["127.0.0.1:8080:8080"]))
    assert any("8080" in e for e in h1_paper.verify())


def test_verify_refuses_dropping_the_resource_caps(scratch_package):
    _rewrite_compose(scratch_package / "docker-compose.h1-paper.yml", lambda s: s.pop("mem_limit"))
    assert any("mem_limit" in e for e in h1_paper.verify())


def test_verify_refuses_an_exchange_override(scratch_package):
    _rewrite_compose(scratch_package / "docker-compose.h1-paper.yml",
                     lambda s: s["environment"].update(FREQTRADE__EXCHANGE__KEY="x"))
    assert any("exchange" in e for e in h1_paper.verify())


# -- preflight ----------------------------------------------------------------


def test_preflight_refuses_a_lane_inside_a_git_worktree(tmp_path):
    errors = h1_paper.preflight(REPO / "lane-probe", tmp_path / "strategy")
    assert any("inside a git worktree" in e for e in errors)


def test_preflight_refuses_a_reused_lane_and_wrong_strategy_files(tmp_path):
    lane, strategy = tmp_path / "lane", tmp_path / "strategy"
    lane.mkdir()
    (lane / "tradesv3.sqlite").write_bytes(b"old cohort")
    strategy.mkdir()
    (strategy / "EmaCross.py").write_text("# not the pinned bytes\n")
    errors = h1_paper.preflight(lane, strategy)
    assert any("not empty" in e for e in errors)
    assert any("must hold exactly" in e for e in errors)
    assert any("EmaCross.py does not match" in e for e in errors)


# -- incident ledger ----------------------------------------------------------


def test_incident_ledger_law(tmp_path):
    lane = tmp_path / "lane"
    with pytest.raises(SystemExit):
        h1_paper.append_incident(lane, "PROCESS_RESTART", "before start")
    start = h1_paper.append_incident(lane, "COHORT_START", "T0")
    assert start["payload"]["restart_counter"] == 0
    with pytest.raises(SystemExit):
        h1_paper.append_incident(lane, "COHORT_START", "again")
    first = h1_paper.append_incident(lane, "PROCESS_RESTART", "docker restart")
    gap = h1_paper.append_incident(lane, "ACTIVATION_GAP", "dns", missed_candles_1h=2)
    second = h1_paper.append_incident(lane, "PROCESS_RESTART", "host reboot")
    assert (first["payload"]["restart_counter"], gap["payload"]["restart_counter"],
            second["payload"]["restart_counter"]) == (1, 1, 2)
    h1_paper.append_incident(lane, "COHORT_TERMINAL", "END_UTC reached")
    with pytest.raises(SystemExit):
        h1_paper.append_incident(lane, "OPERATOR_NOTE", "after terminal")
    ledger = h1_paper.Ledger(lane / h1_paper.INCIDENT_LEDGER, "incident")
    assert ledger.verify() == []
    assert {r.payload["package_manifest_sha256"] for r in ledger.records()} == {h1_paper.manifest_digest()}


def test_incident_payload_is_schema_checked(tmp_path):
    lane = tmp_path / "lane"
    h1_paper.append_incident(lane, "COHORT_START", "T0")
    with pytest.raises(Exception):
        h1_paper.append_incident(lane, "NOT_A_TYPE", "x")
