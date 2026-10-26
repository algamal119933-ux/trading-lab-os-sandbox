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


def test_a_non_info_finding_opens_an_incident_and_nothing_else_does():
    assert cr.project(_obs())["scenario"]["incidents"] == []
    obs = _obs()
    obs["health"] = {"findings": obs["health"]["findings"] + [
        {"check": "mount:/mnt/tlos-wdc", "severity": "CRITICAL", "detail": "not mounted"}], "overall": "CRITICAL"}
    live = cr.project(obs)
    (inc,) = live["scenario"]["incidents"]
    assert inc["id"] == "HEALTH-mount:/mnt/tlos-wdc" and inc["s"] == "open" and live["scenario"]["signal"] == "incident"


def test_restore_readiness_comes_only_from_a_persisted_drill_record():
    assert cr.project(_obs())["ops"]["restore"] == ["unk", "notRecorded"]
    passed = {"backup_set": "S", "PLN_03_RESTORE_DRILL": "PASS", "_file": "d.json", "_mtime": 1_792_960_000.0,
              "checks": {"sealed:x": {"status": "PASS", "archives": [["a", "ARCHIVE_VERIFIED"], ["b", "ARCHIVE_VERIFIED"]]}}}
    failed = dict(passed, PLN_03_RESTORE_DRILL="FAIL")
    live = cr.project(_obs(drills=[passed]))
    assert live["ops"]["restore"][0] == "ok"
    sealed_row = next(r for r in live["evidence_rows"] if r[0]["en"].startswith("Sealed archives"))
    assert "2 ARCHIVE_VERIFIED" in sealed_row[1][1]["en"]
    assert cr.project(_obs(drills=[failed]))["ops"]["restore"] == ["fail", "fail"]


def test_an_unbacked_execution_audit_is_shown_as_a_finding_not_hidden():
    audit = {"evidence_dir": "/x/l2-cohort-T/evidence", "unbacked": 2, "EXECUTION_BACKED_BY_ADMITTED_DECISION": "FAIL",
             "_file": "a.json", "_mtime": 1_792_960_000.0}
    rows = cr.project(_obs(audits=[audit]))["evidence_rows"]
    row = next(r for r in rows if "l2-cohort-T" in r[0]["en"])
    assert row[1][0] == "warn" and "2 unbacked" in row[1][1]["en"]


def test_history_carries_ledger_backup_and_governance_events_in_time_order():
    ledger = [{"utc": "2026-10-25T18:37:26Z", "outcome": "STOPPED", "reason": "drill"}]
    events = cr.project(_obs(ledger_tail=ledger))["scenario"]["events"]
    kinds = {e["c"] for e in events}
    assert {"stage", "system"} <= kinds
    times = [e["t"] for e in events[:-1]]
    assert times == sorted(times) and "Health check" in events[-1]["d"]["en"]


def test_the_resume_brief_and_capability_rows_are_live_not_demo():
    live = cr.project(_obs())
    assert "DEMO" not in live["brief"] and "LIVE PROJECTION" in live["brief"]
    assert all("pre" in c and "since" in c for c in live["caps"])
    assert [r[0] for r in live["stages"]] == ["P1", "P2", "P3", "POST-BETA"]


# ---------------------------------------------------------------- slice 3: sealed cohort screens
def _write_ledger(path: Path, payloads: list[dict]) -> None:
    path.write_text("".join(json.dumps({"payload": p}) + "\n" for p in payloads), encoding="utf-8")


H = 3_600_000
T0 = 1_792_000_000_000 - (1_792_000_000_000 % H)


def _decision(pair, k, action="hold", result="NOT_REQUIRED", reasons=()):
    return {"pair": pair, "timeframe": "1h", "candle_ts": T0 + k * H, "market_event_id": f"{pair}|1h|{k}",
            "signal_state": "above", "intended_action": action, "bar_class": "LIVE", "t0_relation": "POST_T0",
            "no_action_reason": None if action != "hold" else "no cross", "ema_fast": 1.0, "ema_slow": 2.0,
            "strategy_sha256": "s" * 64, "config_sha256": "c" * 64,
            "admission": {"result": result, "reasons": list(reasons)}}


def _sealed_dir(tmp_path: Path) -> Path:
    ev = tmp_path / "l2-cohort-SYN" / "evidence"
    ev.mkdir(parents=True)
    decisions = [_decision("BTC/USDT", k) for k in range(5)] + [
        _decision("BTC/USDT", 5, "enter_long", "ADMITTED"),
        _decision("ETH/USDT", 6, "enter_long", "BLOCKED", ["max_open_trades 2 already reached (2 open)"]),
        _decision("BTC/USDT", 8, "exit_long", "ADMITTED"), _decision("ETH/USDT", 9)]
    _write_ledger(ev / "paper_decision_ledger.jsonl", decisions)
    def utc(k):  # fill one bar after the decided candle closes
        return cr._ms_utc(T0 + (k + 1) * H).replace("Z", ":01")
    trades = [
        {"trade_id": 1, "pair": "BTC/USDT", "event": "position_opened", "open_date_utc": utc(5), "open_rate": 100.0},
        {"trade_id": 2, "pair": "ETH/USDT", "event": "position_opened", "open_date_utc": utc(6), "open_rate": 10.0},
        {"trade_id": 1, "pair": "BTC/USDT", "event": "position_closed", "open_date_utc": utc(5), "close_date_utc": utc(8),
         "open_rate": 100.0, "close_rate": 99.0, "exit_reason": "exit_signal", "profit_abs": -0.19,
         "realised_pnl_currency": "USDT"},
        {"trade_id": 2, "pair": "ETH/USDT", "event": "position_closed", "open_date_utc": utc(6), "close_date_utc": utc(9),
         "open_rate": 10.0, "close_rate": 9.9, "exit_reason": "exit_signal", "profit_abs": -0.38,
         "realised_pnl_currency": "USDT"}]
    _write_ledger(ev / "paper_trade_ledger.jsonl", trades)
    _write_ledger(ev / "paper_input_ledger.jsonl", [
        {"pair": p, "timeframe": "1h", "candle": {"ts": T0 + k * H, "open": 1, "high": 2, "low": 0.5, "close": 1.5}}
        for p in ("BTC/USDT", "ETH/USDT") for k in range(70)])
    return ev


def _audit_for(ev: Path) -> dict:
    from p3 import execution_audit
    rec = execution_audit.audit(ev)
    rec.update({"_file": "audit.json", "_mtime": 1_792_960_000.0})
    return rec


def test_the_sealed_cohort_reader_lists_intents_and_the_last_decision_per_pair(tmp_path):
    ev = _sealed_dir(tmp_path)
    sealed = cr.sealed_cohort([_audit_for(ev)])
    assert sealed["cohort"] == "l2-cohort-SYN" and sealed["n_decisions"] == 9
    shown = [(d["pair"], d["intended_action"]) for d in sealed["decisions"]]
    assert shown == [("BTC/USDT", "enter_long"), ("ETH/USDT", "enter_long"), ("BTC/USDT", "exit_long"), ("ETH/USDT", "hold")]
    assert sealed["timeframes"] == ["1h"] and len(sealed["candles"]["BTC/USDT"]) == cr.SEALED_CANDLES_SHOWN


def test_sealed_decisions_trace_only_what_was_logged_and_link_backed_fills(tmp_path):
    ev = _sealed_dir(tmp_path)
    audit = _audit_for(ev)
    live = cr.project(_obs(audits=[audit], sealed=cr.sealed_cohort([audit])))
    rows = live["decisions"]["rows"]
    assert live["decisions"]["state"] == "bound"
    enter = rows[0]
    assert enter["o"][0] == "ok" and enter["tr"][3][0] == "ok" and enter["tr"][6][0] == "ok" and enter["tr"][7][0] == "ok"
    assert enter["tr"][4] == ["unk", {"en": "not logged", "ar": "غير مسجّل"}] and enter["tr"][8][0] == "unk"
    blocked = rows[1]
    assert blocked["o"][0] == "inc" and "max_open_trades" in blocked["tr"][3][1]["en"] and blocked["tr"][6][0] == "off"
    assert all(len(r["tr"]) == 9 for r in rows)


def test_closed_trades_carry_per_leg_backing_from_the_audit(tmp_path):
    ev = _sealed_dir(tmp_path)
    audit = _audit_for(ev)
    live = cr.project(_obs(audits=[audit], sealed=cr.sealed_cohort([audit])))
    rows = {r["trade_id"]: r for r in live["trades_closed"]["rows"]}
    assert rows[1]["recon"] == ["ok", "pass"] and rows[1]["outcome"][0] == "ok" and rows[1]["pnl"] == "-0.19 USDT"
    assert rows[2]["recon"][0] == "warn" and rows[2]["outcome"][0] == "warn"
    no_legs = dict(audit, executions=[])
    rows = cr.project(_obs(audits=[no_legs], sealed=cr.sealed_cohort([no_legs])))["trades_closed"]["rows"]
    assert all(r["recon"] == ["unk", "unknown"] and r["outcome"] == ["unk", "unknown"] for r in rows)


def test_missing_or_unreadable_sealed_evidence_renders_unknown_never_healthy(tmp_path):
    for sealed, state in ((None, "none"),
                          (cr.sealed_cohort([{"evidence_dir": str(tmp_path / "gone" / "evidence"), "_file": "a"}]),
                           "unreadable")):
        live = cr.project(_obs(sealed=sealed))
        for key in ("decisions", "trades_closed", "market"):
            assert live[key]["state"] == state and live[key]["why"]["en"]
        assert live["decisions"]["rows"] == [] and live["trades_closed"]["rows"] == []
        assert live["market"]["pairs"] == [] and live["market"]["end_utc"] is None
    assert "DEMO" not in json.dumps(cr.project(_obs())["settings"])


def test_market_marks_come_from_recorded_fills_and_the_view_never_claims_a_live_feed(tmp_path):
    ev = _sealed_dir(tmp_path)
    audit = _audit_for(ev)
    m = cr.project(_obs(audits=[audit], sealed=cr.sealed_cohort([audit])))["market"]
    assert m["state"] == "bound" and m["pairs"] == ["BTC/USDT", "ETH/USDT"] and m["timeframes"] == ["1h"]
    assert [k for _, k in m["marks"]["BTC/USDT"]] == ["ENTER", "EXIT"]
    js = cr.ADAPTER_JS.read_text(encoding="utf-8")
    assert "CURRENT MARKET STATE UNKNOWN" in js and "No live feed" in js


def test_the_adapter_binds_all_twelve_frozen_screens():
    js = cr.ADAPTER_JS.read_text(encoding="utf-8")
    bound = set(re.findall(r"'(\w+)'", re.search(r"const LIVE_BOUND=\[([^\]]*)\]", js).group(1)))
    proto = cr.PROTOTYPE.read_text(encoding="utf-8")
    screens = set(re.findall(r"(\w+):b\('", re.search(r"const NAME=\{(.*?)\};", proto).group(1)))
    assert bound == screens and len(bound) == 12
    for k in ("decisions", "trades", "market", "settings"):
        assert f"SCREENS.{k}={k};" in js


# ---------------------------------------------------------------- mobile: Status / Resume / Incidents / More
def _mobile_js() -> str:
    js = cr.ADAPTER_JS.read_text(encoding="utf-8")
    start = js.index("/* ---------- Mobile:")
    return js[start:js.index("function liveDevice()", start)]


def test_the_mobile_view_is_redeclared_from_the_live_identity_not_the_p2_stage_ladder():
    m = _mobile_js()
    for fn in ("function mStatus()", "function mDetail(k)", "function mobile()"):
        assert fn in m
    assert "L(LIVE.ident.stage)" in m and "STAGELBL[" not in m and "nextGate(" not in m
    assert "LIVE.project.chips" in m and "LIVE.project.gate" in m
    # data that the prototype hard-codes on mobile is replaced by records, never by DEMO values
    assert "chip(...P.backup)" in m and "chip(...P.restore)" in m and "chip(...P.reboot)" in m
    assert "POS[" not in m and "DECS" not in m and "lastDec()" not in m and "DEMO" not in m


def test_mobile_offers_no_consequential_control():
    m = _mobile_js()
    proto = cr.PROTOTYPE.read_text(encoding="utf-8")
    kept = proto[proto.index("function mResume()"):proto.index("function mDetail(k)")]  # mResume, mInc, mMore
    for src in (m, kept):
        buttons = re.findall(r"<button ([^>]*)>", src)
        assert buttons, "the mobile tabs and lists are buttons"
        for attrs in buttons:
            assert "data-mdet" in attrs or "data-mtab" in attrs, attrs  # navigation only
        for forbidden in ('id="kill"', "data-kill", "data-act", "data-ack", "data-stop", "data-restart"):
            assert forbidden not in src
    assert "never on mobile" in m


def test_mobile_decisions_and_trades_say_unknown_when_the_sealed_record_is_missing():
    m = _mobile_js()
    dec = m[m.index("if(k==='decisions')"):m.index("if(k==='trades')")]
    trd = m[m.index("if(k==='trades')"):m.index("if(k==='risk')")]
    assert "D3.state!=='bound'" in dec and "chip('unk','unknown')" in dec and "Sealed record" in dec
    assert "T.state!=='bound'" in trd and "chip('unk','unknown')" in trd
    live = cr.project(_obs(sealed=None))
    assert live["decisions"]["state"] == "none" and live["trades_closed"]["state"] == "none"


def test_the_device_follows_the_viewport_or_the_address_and_stores_nothing():
    js = cr.ADAPTER_JS.read_text(encoding="utf-8")
    dev = js[js.index("function liveDevice()"):js.index("/* ---------- route")]
    assert "(max-width: 720px)" in dev and "#mobile" in dev and "#desktop" in dev
    assert "localStorage" not in dev and "sessionStorage" not in dev and "document.cookie" not in dev


def test_the_governed_forbidden_list_replaces_the_prototypes_p2_era_list():
    live = cr.project(_obs())
    assert live["scenario"]["extraForbid"] == []
    en = [f["en"] for f in live["forbid"]]
    assert en == ["Real money", "H1 launch", "Restarting FP-CONTROL-3", "Strategy, risk or dataset change",
                  "Reopening the product shape"]
    assert all(f["ar"] for f in live["forbid"]) and not any("P3" in e for e in en)
    assert "FORBID.splice(0,FORBID.length,...LIVE.forbid);" in cr.ADAPTER_JS.read_text(encoding="utf-8")


def test_incidents_are_unknown_not_none_open_when_the_health_run_gave_no_findings():
    live = cr.project(_obs())
    assert live["incidents_state"] == {"state": "bound"}
    obs = _obs()
    obs["health"] = {"findings": [], "overall": "INFO"}
    live = cr.project(obs)
    assert live["incidents_state"]["state"] == "unknown" and "UNPROVEN" in live["incidents_state"]["why"]["en"]
    js = cr.ADAPTER_JS.read_text(encoding="utf-8")
    desk = js[js.index("function incidents()"):js.index("function incidentPage(")]
    assert "LIVE.incidents_state.state!=='bound'" in desk and "chip('unk','unknown')" in desk


def test_mobile_incidents_has_explicit_empty_and_unknown_states_and_navigation_only():
    m = _mobile_js()
    inc = m[m.index("function mInc()"):m.index("function mobile()")]
    assert "st.state!=='bound'" in inc and "chip('unk','unknown')" in inc
    assert "None open." in inc and "§19" in inc
    assert re.findall(r"<button ([^>]*)>", inc) == ['data-mdet="inc:${i.id}"']


def test_mobile_resume_reads_only_projected_fields():
    proto = cr.PROTOTYPE.read_text(encoding="utf-8")
    res = proto[proto.index("function mResume()"):proto.index("function mInc()")]
    sc = cr.project(_obs())["scenario"]
    for field in ("step", "verdict", "outcome", "law", "lgc", "lho", "known", "unknown", "affected",
                  "unverified", "extraForbid"):
        assert f"s.{field}" in res and field in sc, field
    assert sc["step"] == 6 and sc["outcome"][0] == "ok" and sc["law"]["lifecycle"][0] in ("ok", "wait")
