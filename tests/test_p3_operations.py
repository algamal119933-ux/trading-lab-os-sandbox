"""P3 PLN-06 health, PLN-07 execution audit and PLN-08 kill switch, on synthetic inputs only.

No real container is touched: docker and systemctl are injected fakes. Every refusal is produced:
an unbacked fill, a fill on a BLOCKED decision, a fill outside the decided bar, a stop without a
reason, a broken operator ledger, a container that will not stop, a stale backup, a missing mount,
the retired P2 timer re-enabled, and a normal end reached while still RUNNING.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))

from p3 import execution_audit, health, kill_switch  # noqa: E402

H = 3_600_000
T = 1_792_548_000_000  # 2026-10-21T02:00Z, an hour boundary


def write_ledgers(tmp_path: Path, decisions: list[dict], trades: list[dict]) -> Path:
    ev = tmp_path / "evidence"
    ev.mkdir()
    (ev / "paper_decision_ledger.jsonl").write_text("".join(json.dumps({"payload": d}) + "\n" for d in decisions))
    (ev / "paper_trade_ledger.jsonl").write_text("".join(json.dumps({"payload": t}) + "\n" for t in trades))
    return ev


def decision(candle_ts: int, action: str, result: str = "ADMITTED", pair: str = "BTC/USDT") -> dict:
    return {"pair": pair, "candle_ts": candle_ts, "intended_action": action, "timeframe": "1h",
            "t0_relation": "POST_T0", "bar_class": "LIVE", "admission": {"result": result}}


def opened(when: str, pair: str = "BTC/USDT") -> dict:
    return {"event": "position_opened", "pair": pair, "trade_id": 1, "open_date_utc": when}


# -- PLN-07 ------------------------------------------------------------------


def test_a_fill_in_the_bar_after_an_admitted_decision_is_backed(tmp_path):
    ev = write_ledgers(tmp_path, [decision(T, "enter_long")], [opened("2026-10-21 03:00:02")])
    assert execution_audit.audit(ev)["EXECUTION_BACKED_BY_ADMITTED_DECISION"] == "PASS"


@pytest.mark.parametrize("decisions,fill", [
    ([decision(T, "enter_long", "BLOCKED")], "2026-10-21 03:00:02"),       # blocked, as ETH in P2
    ([decision(T + H, "enter_long")], "2026-10-21 03:00:02"),               # decision after the fill
    ([decision(T, "enter_long")], "2026-10-21 04:10:00"),                   # fill outside the next bar
    ([decision(T, "exit_long")], "2026-10-21 03:00:02"),                    # wrong action
    ([decision(T, "enter_long", pair="ETH/USDT")], "2026-10-21 03:00:02"),  # wrong pair
])
def test_an_unbacked_fill_fails(tmp_path, decisions, fill):
    report = execution_audit.audit(write_ledgers(tmp_path, decisions, [opened(fill)]))
    assert report["EXECUTION_BACKED_BY_ADMITTED_DECISION"] == "FAIL" and report["unbacked"] == 1


def test_a_warmup_decision_never_backs_a_fill(tmp_path):
    warm = dict(decision(T, "enter_long"), bar_class="WARMUP", t0_relation="PRE_T0")
    report = execution_audit.audit(write_ledgers(tmp_path, [warm], [opened("2026-10-21 03:00:02")]))
    assert report["EXECUTION_BACKED_BY_ADMITTED_DECISION"] == "FAIL"


# -- PLN-08 ------------------------------------------------------------------


class FakeDocker:
    def __init__(self, states: dict[str, str], stubborn: tuple[str, ...] = ()):
        self.states, self.stubborn, self.calls = dict(states), stubborn, []

    def __call__(self, cmd):
        self.calls.append(cmd)
        if cmd[0] == "ps":
            out = "".join(f"{n}\t{s}\n" for n, s in self.states.items())
            return subprocess.CompletedProcess(cmd, 0, out, "")
        if cmd[0] == "stop":
            for name in cmd[3:]:
                if name not in self.stubborn:
                    self.states[name] = "exited"
            return subprocess.CompletedProcess(cmd, 0, "", "")
        raise AssertionError(f"unexpected docker call {cmd}")


def test_the_kill_switch_stops_only_paper_runtimes_and_records_it(tmp_path):
    docker = FakeDocker({"tradinglab-fp-control-9-freqtrade": "running", "tlos-h1-paper-cohort-1-freqtrade": "running",
                         "niche-finder-worker": "running", "moneyprinterturbo-api": "running"})
    ledger = tmp_path / "ops.jsonl"
    record = kill_switch.engage(reason="drill", ledger=ledger, operator="owner", runner=docker)
    assert record["outcome"] == "STOPPED"
    assert record["targets"] == ["tlos-h1-paper-cohort-1-freqtrade", "tradinglab-fp-control-9-freqtrade"]
    assert docker.states["niche-finder-worker"] == "running" and docker.states["moneyprinterturbo-api"] == "running"
    assert all(c[0] in ("ps", "stop") for c in docker.calls), "only ps and stop are ever issued"
    assert record["operator"] == "owner" and record["reason"] == "drill" and record["prev_digest"] == "0" * 64
    assert kill_switch.verify_ledger(ledger) == []


def test_every_invocation_is_recorded_and_chained(tmp_path):
    ledger = tmp_path / "ops.jsonl"
    for reason in ("nothing to stop", "again"):
        kill_switch.engage(reason=reason, ledger=ledger, runner=FakeDocker({}))
    kill_switch.engage(reason="look", ledger=ledger, runner=FakeDocker({"tradinglab-fp-control-3-x": "running"}),
                       dry_run=True)
    lines = [json.loads(l) for l in ledger.read_text().splitlines()]
    assert [r["outcome"] for r in lines] == ["NOTHING_RUNNING", "NOTHING_RUNNING", "DRY_RUN"]
    assert lines[1]["prev_digest"] == lines[0]["digest"] and lines[2]["seq"] == 2
    assert kill_switch.verify_ledger(ledger) == []


def test_a_stop_without_a_reason_is_refused_and_records_nothing(tmp_path):
    ledger = tmp_path / "ops.jsonl"
    with pytest.raises(kill_switch.KillSwitchError, match="reason"):
        kill_switch.engage(reason="  ", ledger=ledger, runner=FakeDocker({}))
    assert not ledger.exists()


def test_a_tampered_ledger_is_refused_before_anything_is_stopped(tmp_path):
    ledger = tmp_path / "ops.jsonl"
    kill_switch.engage(reason="first", ledger=ledger, runner=FakeDocker({}))
    record = json.loads(ledger.read_text())
    record["reason"] = "rewritten"
    ledger.write_text(json.dumps(record) + "\n")
    assert kill_switch.verify_ledger(ledger)
    docker = FakeDocker({"tradinglab-fp-control-3-x": "running"})
    with pytest.raises(kill_switch.KillSwitchError, match="does not verify"):
        kill_switch.engage(reason="second", ledger=ledger, runner=docker)


def test_a_container_that_will_not_stop_is_reported_incomplete(tmp_path):
    docker = FakeDocker({"tradinglab-fp-control-3-x": "running"}, stubborn=("tradinglab-fp-control-3-x",))
    record = kill_switch.engage(reason="drill", ledger=tmp_path / "ops.jsonl", runner=docker)
    assert record["outcome"] == "STOP_INCOMPLETE" and record["still_running"] == ["tradinglab-fp-control-3-x"]


# -- PLN-06 ------------------------------------------------------------------


def unit_runner(states: dict[str, tuple[str, str]]):
    def run(cmd):
        enabled, active = states.get(cmd[-1], ("", ""))
        return subprocess.CompletedProcess(cmd, 0, (enabled if cmd[2] == "is-enabled" else active) + "\n", "")
    return run


def test_timers_are_judged_against_their_expected_state():
    run = unit_runner({"b.timer": ("enabled", "active"), "p2.timer": ("enabled", "active")})
    assert health.timer_expected("b.timer", want_active=True, runner=run)["severity"] == "INFO"
    assert health.timer_expected("p2.timer", want_active=False, runner=run)["severity"] == "CRITICAL"
    assert health.timer_expected("absent.timer", want_active=True, runner=run)["severity"] == "WARNING"


def test_backup_recency_against_the_rpo(tmp_path):
    assert health.backup_recency(tmp_path / "none", 26)["severity"] == "CRITICAL"
    s = tmp_path / "b" / "20261025T000000Z"
    s.mkdir(parents=True)
    (s / "BACKUP_RECORD.json").write_text("{}")
    mtime = (s / "BACKUP_RECORD.json").stat().st_mtime
    assert health.backup_recency(tmp_path / "b", 26, now=mtime + 3600)["severity"] == "INFO"
    assert health.backup_recency(tmp_path / "b", 26, now=mtime + 30 * 3600)["severity"] == "WARNING"
    bad = health.backup_recency(tmp_path / "b", 26, verifier=lambda p: {"status": "FAIL"}, now=mtime)
    assert bad["severity"] == "CRITICAL"


def test_free_space_and_mount_findings(tmp_path):
    assert health.free_space(tmp_path, 0, "x")["severity"] == "INFO"
    assert health.free_space(tmp_path, 10 ** 9, "x")["severity"] == "CRITICAL"
    assert health.mounted(str(tmp_path))["severity"] == "CRITICAL"


def test_a_completed_lifecycle_on_a_running_cohort_flags_the_normal_end(tmp_path):
    lane = tmp_path / "user_data"
    (lane / "fp-control-9" / "evidence").mkdir(parents=True)
    (lane / "fp-control-9" / "evidence" / "paper_trade_ledger.jsonl").write_text(
        json.dumps({"payload": {"event": "position_opened"}}) + "\n" + json.dumps({"payload": {"event": "position_closed"}}) + "\n")
    registry = {"instances": [
        {"role": "FP-CONTROL-9", "status": "RUNNING",
         "runtime_identity": {"evidence_dir": "/freqtrade/user_data/fp-control-9/evidence"}},
        {"role": "FP-CONTROL-3", "status": "CLOSED", "runtime_identity": {}}]}
    findings = health.normal_end_due(registry, lane)
    assert findings == [{"check": "normal_end:FP-CONTROL-9", "severity": "WARNING",
                         "detail": "FP-CONTROL-9 is RUNNING with 1 closed lifecycle(s): NORMAL END reached, governed stop due"}]
    assert health.normal_end_due({"instances": []}, lane)[0]["severity"] == "INFO"
    assert health.overall(findings) == "WARNING"


def test_the_committed_registry_has_no_running_cohort_to_flag():
    registry = json.loads((REPO / "research/fp/records/forward_paper_cohort_registry.json").read_text())
    assert health.normal_end_due(registry, REPO)[0]["detail"] == "no RUNNING cohort"
