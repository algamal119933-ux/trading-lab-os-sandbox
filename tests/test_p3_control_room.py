"""P3-PLN-09 Control Room projection, on synthetic observations only.

Every refusal and every degraded mapping is produced: a prototype with another digest, a WARNING
health finding, a broken operator ledger, an unreadable docker, an expired authorization and a missing
reconciliation. Nothing observed is ever shown as healthy; real money is blocked in every case.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))

from p3 import control_room as cr  # noqa: E402

DIM_ORDER = ["health", "authority", "evidence", "freshness", "runtime", "recon"]


def _obs(**over) -> dict:
    obs = {
        "observed_epoch": 1_792_965_000.0, "observed_utc": "2026-10-25 21:50Z", "hostname": "test-host",
        "health": {"findings": [{"check": "backup_recency", "severity": "INFO", "detail": "newest set S, 1.0 h old"},
                                {"check": "timer:tlos-p3-backup.timer", "severity": "INFO", "detail": "enabled/active"}],
                   "overall": "INFO"},
        "health_timer": {"check": "timer:tlos-p3-health.timer", "severity": "INFO", "detail": "enabled/active"},
        "paper_containers": {}, "paper_error": None, "running_containers": ["other-a"],
        "ledger": {"records": 2, "problems": [], "last": {"outcome": "STOPPED", "utc": "2026-10-25T18:37:00Z"}},
        "fp_control_3_restart": {"allowed": False, "reason": "FP-CONTROL-3 is CLOSED"},
        "registry": {"real_money_authorized": False, "fp_run_active": False, "updated_utc": "x",
                     "instances": [{"role": "FP-CONTROL-3", "cohort_id": "FP-CONTROL-3-20260924T120000Z",
                                    "status": "CLOSED", "closed_utc": "2026-10-24T21:37:57Z",
                                    "lifecycle": "OBSERVED"}]},
        "authorization": {"present": True, "expires_utc": "2027-01-31T23:59:59Z", "real_money": True, "h1_launch": True},
        "p2_reconcile": {"passed": 14, "total": 14},
        "governance": {"main": "a" * 40, "merges": [
            {"sha": "b" * 40, "epoch": "1792962000", "subject": "Merge pull request #78 from x/y"}]},
        "runtime": {"pin": "c" * 40, "clean": True},
        "host": {"uptime_s": 172800.0, "boot_id": "boot-1", "ntp_synced": True},
        "backup_sets": ["20261025T211956Z"],
        "workstreams": json.loads(cr.WORKSTREAMS.read_text(encoding="utf-8")),
    }
    for key, value in over.items():
        obs[key] = value
    return obs


def test_a_healthy_host_with_no_runtime_maps_to_the_frozen_dimensions_in_order():
    live = cr.project(_obs())
    dims = live["scenario"]["dims"]
    assert list(dims) == DIM_ORDER
    assert [dims[k][0] for k in DIM_ORDER] == ["ok", "ok", "ok", "ok", "off", "ok"]
    assert "runtime" in live["scenario"]["exc"] and "health" not in live["scenario"]["exc"]
    assert live["scenario"]["dec"]["none"] and live["scenario"]["pos"] == []


def test_a_warning_finding_degrades_health_and_is_listed_as_an_exception():
    obs = _obs()
    obs["health"] = {"findings": obs["health"]["findings"] + [
        {"check": "free_space:root", "severity": "WARNING", "detail": "low"}], "overall": "WARNING"}
    live = cr.project(obs)
    assert live["scenario"]["dims"]["health"] == ["warn", "degraded"]
    assert "free_space:root" in live["scenario"]["exc"]["health"]["en"]


def test_a_broken_operator_ledger_fails_the_evidence_dimension():
    obs = _obs(ledger={"records": 2, "problems": ["record 1: digest does not match its body"], "last": None})
    live = cr.project(obs)
    assert live["scenario"]["dims"]["evidence"][0] == "fail"
    assert "digest does not match" in live["scenario"]["exc"]["evidence"]["en"]


def test_an_unverified_backup_fails_the_evidence_dimension():
    obs = _obs()
    obs["health"]["findings"][0] = {"check": "backup_recency", "severity": "CRITICAL", "detail": "does not verify"}
    obs["health"]["overall"] = "CRITICAL"
    live = cr.project(obs)
    assert live["scenario"]["dims"]["evidence"][0] == "fail"
    assert live["scenario"]["dims"]["health"][0] == "inc"


def test_an_unreadable_docker_is_unknown_never_stopped_or_healthy():
    live = cr.project(_obs(paper_containers=None, paper_error="docker ps failed", running_containers=None))
    assert live["scenario"]["dims"]["runtime"] == ["unk", "unknown"]
    assert live["scenario"]["sys"]["containers"] == ["unk", "unknown"]


def test_an_expired_or_missing_authorization_is_not_valid():
    expired = _obs(authorization={"present": True, "expires_utc": "2026-01-01T00:00:00Z", "real_money": True,
                                  "h1_launch": True})
    missing = _obs(authorization={"present": False, "expires_utc": None, "real_money": False, "h1_launch": False})
    for obs in (expired, missing):
        assert cr.project(obs)["scenario"]["dims"]["authority"][0] == "fail"


def test_a_missing_reconciliation_record_is_unknown():
    assert cr.project(_obs(p2_reconcile=None))["scenario"]["dims"]["recon"] == ["unk", "unknown"]


def test_a_running_paper_runtime_is_shown_running():
    live = cr.project(_obs(paper_containers={"tlos-h1-paper-cohort-1": "running"}))
    assert live["scenario"]["dims"]["runtime"] == ["ok", "running"]
    assert "runtime" not in live["scenario"]["exc"]


@pytest.mark.parametrize("obs", [_obs(), _obs(paper_containers={"tradinglab-fp-control-x": "running"}),
                                 _obs(registry={"real_money_authorized": None, "instances": []})])
def test_real_money_is_never_shown_allowed(obs):
    live = cr.project(obs)
    real = next(c for c in live["caps"] if c["k"]["en"] == "Real money")
    assert real["st"][0] in ("blocked", "unk") and live["real_money_authorized"] is False


def test_the_build_refuses_a_prototype_with_another_digest(tmp_path):
    fake = tmp_path / "proto.html"
    fake.write_text("<html><body></body></html>")
    with pytest.raises(cr.ControlRoomError, match="refusing"):
        cr.build(cr.project(_obs()), prototype=fake)


def test_the_build_keeps_the_prototype_verbatim_and_appends_one_script():
    raw = cr.PROTOTYPE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == cr.PROTOTYPE_SHA256
    html = cr.build(cr.project(_obs()))
    head = raw.decode("utf-8").split("</body>")[0]
    assert html.startswith(head)
    added, tail = html[len(head):].split("</body>")
    assert added.count("<script>") == 1 and added.count("</script>") == 1
    assert tail == raw.decode("utf-8").split("</body>")[1]
    assert "connect-src 'none'" in html


def test_the_payload_cannot_close_its_script_element():
    obs = _obs()
    obs["workstreams"] = copy.deepcopy(obs["workstreams"])
    obs["workstreams"]["owner"]["en"] = "</script><script>alert(1)</script>"
    html = cr.build(cr.project(obs))
    tail = html.split("const LIVE=", 1)[1]
    assert "</script><script>alert(1)" not in tail.split("\n", 1)[0]


def test_the_adapter_is_offline_and_binds_the_command_center_first():
    js = cr.ADAPTER_JS.read_text(encoding="utf-8")
    for forbidden in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon", "localStorage.setItem"):
        assert forbidden not in js
    bound = re.search(r"const LIVE_BOUND=\[([^\]]*)\]", js).group(1)
    assert "'command'" in bound


def test_the_workstream_record_lists_the_twelve_contract_workstreams():
    ws = json.loads(cr.WORKSTREAMS.read_text(encoding="utf-8"))
    assert [w["id"] for w in ws["workstreams"]] == [f"PLN-{n:02d}" for n in range(12)]
    assert {w["status"] for w in ws["workstreams"]} <= {"ACCEPTED", "PARTIAL", "IN_PROGRESS", "PENDING"}
    assert all(w["evidence"] for w in ws["workstreams"])


def test_collect_reads_only_through_injected_runners(tmp_path):
    calls = []

    def runner(cmd):
        calls.append(cmd)
        out = {"cat": "172800.00 1.0", "timedatectl": "yes"}.get(cmd[0], "")
        if cmd[:2] == ["systemctl", "--user"]:
            out = "enabled" if "is-enabled" in cmd else "active"
        return subprocess.CompletedProcess(cmd, 0, out, "")

    def docker(cmd):
        return subprocess.CompletedProcess(cmd, 0, "unrelated\trunning\n", "")

    ledger = tmp_path / "ledger.jsonl"
    obs = cr.collect(runner=runner, docker=docker, ledger_path=ledger, backup_target=tmp_path / "none",
                     findings=[{"check": "backup_recency", "severity": "INFO", "detail": "ok"}], now=1_792_965_000.0)
    assert obs["paper_containers"] == {} and obs["ledger"]["records"] == 0
    assert obs["fp_control_3_restart"]["allowed"] is False
    assert obs["host"]["ntp_synced"] is True and obs["backup_sets"] == []
    assert all(c[0] in ("git", "cat", "timedatectl", "systemctl", "docker") for c in calls)
    assert not any(word in " ".join(c) for c in calls for word in (" stop", " rm", " start", " restart", "push"))
    cr.project(obs)
