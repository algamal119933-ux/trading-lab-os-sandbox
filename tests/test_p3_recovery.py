"""P3-PLN-04 recovery guard and reboot check, and the PLN-06 Prometheus textfile; synthetic only.

The negative controls the contract requires are produced: a CLOSED cohort, a NOT_STARTED cohort,
an Owner (kill-switch) stop with no later resume, and a tampered ledger are each refused a restart;
a reboot that did not happen, a mount or timer that did not come back, a stopped paper runtime
that came back running, and a new paper runtime each fail the reboot check.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))

from p3 import health, kill_switch, recovery  # noqa: E402

REG = {"instances": [
    {"role": "FP-CONTROL-9", "status": "RUNNING", "runtime_identity": {"bot_name": "fp-control-9"}},
    {"role": "FP-CONTROL-3", "status": "CLOSED", "runtime_identity": {"bot_name": "fp-control-3"}},
    {"role": "FP-CONTROL-8", "status": "NOT_STARTED", "runtime_identity": {"bot_name": "fp-control-8"}},
]}


class Docker:
    def __init__(self, states):
        self.states = dict(states)

    def __call__(self, cmd):
        if cmd[0] == "ps":
            return subprocess.CompletedProcess(cmd, 0, "".join(f"{n}\t{s}\n" for n, s in self.states.items()), "")
        for n in cmd[3:]:
            self.states[n] = "exited"
        return subprocess.CompletedProcess(cmd, 0, "", "")


def test_a_running_cohort_with_no_standing_stop_may_restart(tmp_path):
    assert recovery.may_restart("FP-CONTROL-9", REG, tmp_path / "none.jsonl")[0] is True


@pytest.mark.parametrize("role", ["FP-CONTROL-3", "FP-CONTROL-8", "FP-CONTROL-404"])
def test_a_terminal_or_unstarted_or_unknown_cohort_never_restarts(tmp_path, role):
    ok, why = recovery.may_restart(role, REG, tmp_path / "none.jsonl")
    assert ok is False and why


def test_an_owner_stop_stands_until_an_attributable_resume(tmp_path):
    ledger = tmp_path / "ops.jsonl"
    kill_switch.engage(reason="owner stop", ledger=ledger, operator="owner",
                       runner=Docker({"tradinglab-fp-control-9-freqtrade": "running"}))
    ok, why = recovery.may_restart("FP-CONTROL-9", REG, ledger)
    assert ok is False and "owner stop" in why
    recovery.authorize_resume("FP-CONTROL-9", reason="incident resolved", operator="owner", ledger=ledger)
    assert recovery.may_restart("FP-CONTROL-9", REG, ledger)[0] is True
    kill_switch.engage(reason="second stop", ledger=ledger, operator="owner",
                       runner=Docker({"tradinglab-fp-control-9-freqtrade": "running"}))
    assert recovery.may_restart("FP-CONTROL-9", REG, ledger)[0] is False
    assert kill_switch.verify_ledger(ledger) == []


def test_a_stop_of_another_cohort_does_not_block_this_one(tmp_path):
    ledger = tmp_path / "ops.jsonl"
    kill_switch.engage(reason="h1 stop", ledger=ledger, runner=Docker({"tlos-h1-paper-cohort-1-freqtrade": "running"}))
    assert recovery.may_restart("FP-CONTROL-9", REG, ledger)[0] is True


def test_a_tampered_ledger_refuses_rather_than_guesses(tmp_path):
    ledger = tmp_path / "ops.jsonl"
    kill_switch.engage(reason="x", ledger=ledger, runner=Docker({}))
    ledger.write_text(ledger.read_text().replace('"x"', '"y"'))
    with pytest.raises(kill_switch.KillSwitchError):
        recovery.may_restart("FP-CONTROL-9", REG, ledger)


def test_a_resume_needs_operator_and_reason(tmp_path):
    with pytest.raises(kill_switch.KillSwitchError):
        recovery.authorize_resume("FP-CONTROL-9", reason=" ", operator="owner", ledger=tmp_path / "l.jsonl")


def snap(boot, mounts=True, timer=("enabled", "active"), containers=None):
    return {"boot_id": boot, "mounts": {"/": True, "/mnt/tlos-wdc": mounts},
            "units": {"tlos-p3-backup.timer": list(timer), "tlos-p2-window-fp-control-3.timer": ["disabled", "inactive"]},
            "containers": containers if containers is not None else
            {"niche-finder-worker": "running", "tradinglab-fp-control-3-freqtrade": "exited"}}


def test_a_clean_reboot_passes():
    assert recovery.verify_after_boot(snap("a"), snap("b"))["PLN_04_REBOOT_CHECK"] == "PASS"


@pytest.mark.parametrize("after,failing", [
    (snap("a"), "rebooted"),
    (snap("b", mounts=False), "mount:/mnt/tlos-wdc"),
    (snap("b", timer=("enabled", "inactive")), "unit:tlos-p3-backup.timer"),
    (snap("b", containers={"niche-finder-worker": "exited", "tradinglab-fp-control-3-freqtrade": "exited"}),
     "container:niche-finder-worker"),
    (snap("b", containers={"niche-finder-worker": "running", "tradinglab-fp-control-3-freqtrade": "running"}),
     "paper:tradinglab-fp-control-3-freqtrade"),
    (snap("b", containers={"niche-finder-worker": "running", "tradinglab-fp-control-3-freqtrade": "exited",
                           "tlos-h1-paper-cohort-1-freqtrade": "running"}), "no_new_paper_runtime"),
])
def test_a_bad_reboot_outcome_fails(after, failing):
    report = recovery.verify_after_boot(snap("a"), after)
    assert report["PLN_04_REBOOT_CHECK"] == "FAIL" and report["checks"][failing]["status"] == "FAIL"


def test_the_prometheus_textfile_is_valid_and_atomic(tmp_path):
    findings = [{"check": "free_space:root", "severity": "INFO", "detail": ""},
                {"check": 'odd"name', "severity": "CRITICAL", "detail": ""}]
    out = tmp_path / "m" / "tlos_p3.prom"
    health.write_textfile(findings, out)
    text = out.read_text()
    assert 'tlos_p3_health_check{check="free_space:root"} 0' in text
    assert "tlos_p3_health_check{check=\"odd'name\"} 2" in text
    assert text.rstrip().endswith("tlos_p3_health_overall 2")
    assert not list(out.parent.glob("*.tmp"))


def test_the_committed_registry_refuses_restarting_fp_control_3(tmp_path):
    registry = json.loads((REPO / "research/fp/records/forward_paper_cohort_registry.json").read_text())
    ok, why = recovery.may_restart("FP-CONTROL-3", registry, tmp_path / "none.jsonl")
    assert ok is False and "CLOSED" in why


def test_a_disabled_unit_is_recorded_as_disabled_not_absent(monkeypatch):
    def fake_run(cmd, **kwargs):
        out = {"is-enabled": "disabled\n", "is-active": "inactive\n"}.get(cmd[2], "") if cmd[0] == "systemctl" else ""
        return subprocess.CompletedProcess(cmd, 1 if cmd[0] == "systemctl" else 0, out, "")
    monkeypatch.setattr(recovery.subprocess, "run", fake_run)
    assert recovery._run(["systemctl", "--user", "is-enabled", "x.timer"]) == "disabled"

