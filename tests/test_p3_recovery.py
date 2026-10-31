"""P3-PLN-04 recovery guard and reboot check, and the PLN-06 Prometheus textfile; synthetic only.

The negative controls the contract requires are produced: a CLOSED cohort, a NOT_STARTED cohort,
an Owner (kill-switch) stop with no later resume, and a tampered ledger are each refused a restart;
a reboot that did not happen, a mount or timer that did not come back, a stopped paper runtime
that came back running, and a new paper runtime each fail the reboot check.
"""

from __future__ import annotations

import fnmatch
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


def snap(boot, mounts=True, timer=("enabled", "active"), containers=None, runtime=("enabled", "active"), linger="yes"):
    return {"boot_id": boot, "mounts": {"/": True, "/mnt/tlos-wdc": mounts},
            "units": {"tlos-p3-backup.timer": list(timer), "tlos-p2-window-fp-control-3.timer": ["disabled", "inactive"],
                      "tlos-p3-health.timer": ["enabled", "active"], "tlos-runtime.service": list(runtime)},
            "linger": linger,
            "containers": containers if containers is not None else
            {"niche-finder-worker": "running", "tradinglab-fp-control-3-freqtrade": "exited"}}


def test_a_clean_reboot_passes():
    assert recovery.verify_after_boot(snap("a"), snap("b"))["PLN_04_REBOOT_CHECK"] == "PASS"


@pytest.mark.parametrize("after,failing", [
    (snap("a"), "rebooted"),
    (snap("b", mounts=False), "mount:/mnt/tlos-wdc"),
    (snap("b", timer=("enabled", "inactive")), "boot_required:tlos-p3-backup.timer"),
    (snap("b", runtime=("enabled", "inactive")), "boot_required:tlos-runtime.service"),
    (snap("b", linger="no"), "linger"),
    (snap("b", linger="unknown"), "linger"),
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



# --- Boot posture (2026-10-30: the monitoring runtime did not return after an unclean power loss) ---

def test_a_hand_started_runtime_that_was_never_enabled_fails_the_reboot_check():
    """The host case of 2026-10-30: tlos-runtime.service was started by hand (active) but not enabled.
    Its state was 'preserved' across the power loss (disabled -> disabled/inactive), which the old
    preserved-state rule passed. Reboot correctness requires it to come back."""
    before = snap("a", runtime=("disabled", "active"))
    after = snap("b", runtime=("disabled", "inactive"))
    report = recovery.verify_after_boot(before, after)
    assert report["PLN_04_REBOOT_CHECK"] == "FAIL"
    assert report["checks"]["boot_required:tlos-runtime.service"]["status"] == "FAIL"
    assert "unit:tlos-runtime.service" not in report["checks"]


def test_a_required_unit_missing_from_an_older_baseline_is_still_judged():
    before = snap("a")
    for unit in ("tlos-runtime.service", "tlos-p3-health.timer"):
        del before["units"][unit]
    before.pop("linger")
    assert recovery.verify_after_boot(before, snap("b"))["PLN_04_REBOOT_CHECK"] == "PASS"
    after = snap("b")
    del after["units"]["tlos-p3-health.timer"]
    report = recovery.verify_after_boot(before, after)
    assert report["checks"]["boot_required:tlos-p3-health.timer"]["status"] == "FAIL"


def _fake_host(enabled, active, linger):
    def runner(cmd):
        if cmd[0] == "docker":
            return "tlos_runtime-grafana-1\trunning"
        if cmd[0] == "loginctl":
            assert cmd == ["loginctl", "show-user", recovery._user(), "-p", "Linger", "--value"]
            return linger
        if cmd[:2] == ["systemctl", "--user"]:
            return {"is-enabled": enabled, "is-active": active}[cmd[2]].get(cmd[3], "")
        raise AssertionError(cmd)
    return runner


def test_every_snapshot_records_the_required_units_and_linger_whatever_the_caller_passes():
    on = {u: "enabled" for u in recovery.REQUIRED_AT_BOOT}
    up = {u: "active" for u in recovery.REQUIRED_AT_BOOT}
    s = recovery.snapshot(("/",), ("tlos-p2-window-fp-control-3.timer",), runner=_fake_host(on, up, "yes"))
    assert set(recovery.REQUIRED_AT_BOOT) <= set(s["units"]) and "tlos-p2-window-fp-control-3.timer" in s["units"]
    assert s["linger"] == "yes" and s["boot_posture"] == {"status": "READY", "problems": []}


@pytest.mark.parametrize("enabled,active,linger,needle", [
    ({"tlos-runtime.service": "disabled"}, {}, "yes", "tlos-runtime.service is disabled"),
    ({}, {"tlos-p3-health.timer": "inactive"}, "yes", "tlos-p3-health.timer is inactive"),
    ({}, {}, "no", "linger is 'no'"),
    ({}, {}, "", "linger is 'unknown'"),
])
def test_the_snapshot_shows_a_bad_boot_posture_before_the_reboot(enabled, active, linger, needle):
    on = {u: "enabled" for u in recovery.REQUIRED_AT_BOOT} | enabled
    up = {u: "active" for u in recovery.REQUIRED_AT_BOOT} | active
    posture = recovery.snapshot(("/",), (), runner=_fake_host(on, up, linger))["boot_posture"]
    assert posture["status"] == "NOT_READY" and any(needle in p for p in posture["problems"])


def test_no_paper_runtime_is_ever_required_at_boot():
    for unit in recovery.REQUIRED_AT_BOOT:
        assert not any(fnmatch.fnmatchcase(unit, p) for p in kill_switch.PAPER_RUNTIME_PATTERNS)
        assert "freqtrade" not in unit and "cohort" not in unit and "fp-control" not in unit
