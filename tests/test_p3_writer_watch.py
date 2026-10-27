"""P3-PLN-06 §19 'unexpected writer': research/p3/writer_watch.py on synthetic audit records only.

No real audit log, no host path is read, nothing is installed. The fixtures are hand-written raw
auditd lines in the documented format (SYSCALL + PATH grouped by msg=audit(<time>:<serial>)).
PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "research") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "research"))

from p3 import control_room, health  # noqa: E402
from p3 import writer_watch as ww  # noqa: E402

LEDGER = "/home/hamza/tlos-paper/operator-ledger/operator_ledger.jsonl"
SEALED = "/home/hamza/projects/trading/trading_lab_os_final/artifacts/l2-cohort-x/MANIFEST.sha256"
PROM = "/home/hamza/tlos-paper/p3-evidence/tlos_p3_health.prom"


def _event(serial: int, key: str | None, comm: str | None, uid: str | None, path: str, exe: str = "/usr/bin/python3.12",
           comm_raw: str | None = None, euid: str | None = None, auid: str = "1000", success: str = "yes") -> str:
    t = f"1793000000.{serial:03d}:{serial}"
    parts = [f"type=SYSCALL msg=audit({t}): arch=c000003e syscall=257 success={success} exit=3 ppid=1 "
             f"pid={1000 + serial}", f"auid={auid}"]
    if uid is not None:
        parts.append(f"uid={uid} gid={uid} euid={euid if euid is not None else uid}")
    if comm_raw is not None:
        parts.append(f"comm={comm_raw}")
    elif comm is not None:
        parts.append(f'comm="{comm}"')
    parts.append(f'exe="{exe}"')
    parts.append(f'key="{key}"' if key else "key=(null)")
    syscall = " ".join(parts)
    path_rec = f'type=PATH msg=audit({t}): item=0 name="{path}" inode=42 nametype=NORMAL'
    return syscall + "\n" + path_rec + "\n"


# One hourly health-job write: the heartbeat that proves the watch is not blind.
HEARTBEAT = _event(900, "tlos_p3_evidence", "python3", "1000", PROM)
STATUS_OK = "enabled 1\nfailure 1\npid 812\nrate_limit 0\nbacklog_limit 8192\nlost 0\nbacklog 0\n"
RULES_ALL = "\n".join(f"-w {p} -p wa -k tlos_{c.key}" for c in ww.DEFAULT_INVENTORY for p in c.paths)


def _run(log: str, status: str | None = STATUS_OK, rules: str | None = RULES_ALL, lost_baseline: int = 0,
         heartbeat: bool = True) -> dict:
    result, _ = ww.evaluate(log + (HEARTBEAT if heartbeat else ""), status, rules, lost_baseline=lost_baseline)
    return result


# --------------------------------------------------------------------------- inventory + rules


def test_inventory_is_derived_from_the_existing_repository_constants_not_a_new_list():
    paths = {c.key: c.paths for c in ww.DEFAULT_INVENTORY}
    assert str(health.RUNTIME_ROOT / "artifacts") in paths["sealed"]
    assert str(health.OPERATOR_LEDGER.parent) == paths["ledger"][0]
    assert str(health.H1_LANE) == paths["h1_lane"][0]
    assert str(control_room.EVIDENCE_DIR) == paths["p3_evidence"][0]
    assert str(control_room.BACKUP_TARGET) == paths["backups"][0]
    assert control_room.LEDGER == health.OPERATOR_LEDGER and control_room.RUNTIME_ROOT == health.RUNTIME_ROOT
    # the second-device replica root is the one scripts/replicate_to_second_device.py writes
    spec = importlib.util.spec_from_file_location("replicate", REPO_ROOT / "scripts" / "replicate_to_second_device.py")
    replicate = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec.loader.exec_module(replicate)
    assert str(control_room.BACKUP_TARGET.parent / replicate.REPLICA_ROOT_NAME) in paths["sealed"]
    # the health textfile the alert rules watch lives in the watched evidence directory
    sh = (REPO_ROOT / "scripts" / "p3" / "scheduled_health.sh").read_text(encoding="utf-8")
    assert f"{control_room.EVIDENCE_DIR}/tlos_p3_health.prom" in sh


def test_rendered_rules_watch_every_protected_path_for_writes_and_attribute_changes():
    rules = ww.render_rules()
    for cls in ww.DEFAULT_INVENTORY:
        for path in cls.paths:
            assert f"-w {path} -p wa -k tlos_{cls.key}" in rules
    assert "-b 8192" in rules and "-f 1" in rules
    assert "-e 2" not in rules  # immutable mode is an Owner decision, never generated silently
    assert ww.loaded_keys(rules) == {f"tlos_{c.key}" for c in ww.DEFAULT_INVENTORY}
    assert ww.loaded_watches(rules) == ww.expected_watches() and len(ww.expected_watches()) == 9


def test_loaded_watches_reads_both_listing_forms_and_ignores_a_trailing_slash():
    dir_form = "\n".join(f"-a always,exit -F arch=b64 -S all -F dir={p}/ -F perm=wa -F key=tlos_{c.key}"
                         for c in ww.DEFAULT_INVENTORY for p in c.paths)
    assert ww.missing_watches(dir_form) == []
    assert ww.missing_watches(RULES_ALL.replace(" -p", "/ -p")) == []


def test_every_watched_filesystem_has_its_own_canary_and_no_canary_overlaps_evidence():
    canary = [c for c in ww.DEFAULT_INVENTORY if c.key == "canary"]
    assert len(canary) == 1 and canary[0].writers == ()
    roots = {"/mnt/tlos-wdc" if p.startswith("/mnt/tlos-wdc/") else "/home" for c in ww.DEFAULT_INVENTORY for p in c.paths}
    canary_roots = {"/mnt/tlos-wdc" if p.startswith("/mnt/tlos-wdc/") else "/home" for p in canary[0].paths}
    assert canary_roots == roots == {"/home", "/mnt/tlos-wdc"}
    evidence_paths = {p for c in ww.DEFAULT_INVENTORY if c.key != "canary" for p in c.paths}
    for cp in canary[0].paths:
        assert not any(cp.startswith(p + "/") or p.startswith(cp + "/") or p == cp for p in evidence_paths)
    for serial, cp in enumerate(canary[0].paths, start=1):
        f = _run(_event(serial, "tlos_canary", "touch", "1000", f"{cp}/probe", exe="/usr/bin/touch"))
        assert f["severity"] == ww.CRITICAL and cp in f["detail"]


# --------------------------------------------------------------------------- attribution


def test_a_declared_writer_is_authorized_and_the_run_is_info_only_when_everything_is_proven():
    log = _event(1, "tlos_ledger", "python3", "1000", LEDGER)
    out = ww.classify(ww.parse_audit_log(log))
    assert [c["verdict"] for c in out] == [ww.AUTHORIZED]
    assert {k: out[0][k] for k in ("key", "comm", "exe", "uid", "euid", "auid")} == {
        "key": "tlos_ledger", "comm": "python3", "exe": "/usr/bin/python3.12", "uid": "1000", "euid": "1000",
        "auid": "1000"}
    f = _run(log)
    assert f["check"] == "unexpected_writer" and f["severity"] == ww.INFO


def test_any_write_to_a_sealed_archive_is_unexpected_and_critical_with_attribution():
    f = _run(_event(1, "tlos_sealed", "python3", "1000", SEALED, auid="1000"))
    assert f["severity"] == ww.CRITICAL
    for part in ("tlos_sealed", "comm='python3'", "exe='/usr/bin/python3.12'", "uid=1000", "auid=1000", SEALED):
        assert part in f["detail"]


def test_a_failed_attempt_is_still_classified():
    f = _run(_event(1, "tlos_sealed", "rm", "1000", SEALED, exe="/usr/bin/rm", success="no"))
    assert f["severity"] == ww.CRITICAL


def test_a_foreign_process_or_uid_on_the_ledger_is_unexpected():
    for comm, uid in (("vim", "1000"), ("python3", "1001"), ("bash", "0")):
        out = ww.classify(ww.parse_audit_log(_event(1, "tlos_ledger", comm, uid, LEDGER)))
        assert out[0]["verdict"] == ww.UNEXPECTED, (comm, uid)


def test_a_renamed_process_from_a_user_writable_binary_is_unexpected():
    # prctl(PR_SET_NAME, "python3") from ~/evil: the comm matches, the exe does not
    out = ww.classify(ww.parse_audit_log(_event(1, "tlos_ledger", "python3", "1000", LEDGER,
                                                exe="/home/hamza/.cache/evil")))
    assert out[0]["verdict"] == ww.UNEXPECTED
    out = ww.classify(ww.parse_audit_log(_event(2, "tlos_ledger", "python3", "1000", LEDGER, exe="/tmp/python3")))
    assert out[0]["verdict"] == ww.UNEXPECTED


def test_an_escalated_effective_uid_is_unexpected_even_when_the_real_uid_is_the_owner():
    out = ww.classify(ww.parse_audit_log(_event(1, "tlos_ledger", "python3", "1000", LEDGER, euid="0")))
    assert out[0]["verdict"] == ww.UNEXPECTED and "euid=0" in out[0]["why"]


def test_the_volume_export_helper_is_allowed_as_root_tar_only_on_the_backup_sets():
    bk = "/mnt/tlos-wdc/tlos-backups/20261027T033300Z/volumes/x.tar"
    tar = "/usr/bin/tar"
    assert ww.classify(ww.parse_audit_log(_event(1, "tlos_backups", "tar", "0", bk, exe=tar)))[0]["verdict"] == ww.AUTHORIZED
    assert ww.classify(ww.parse_audit_log(_event(2, "tlos_backups", "rm", "0", bk, exe="/usr/bin/rm")))[0]["verdict"] == ww.UNEXPECTED
    assert ww.classify(ww.parse_audit_log(_event(3, "tlos_ledger", "tar", "0", LEDGER, exe=tar)))[0]["verdict"] == ww.UNEXPECTED


def test_scheduled_health_mkdir_is_a_declared_writer_of_p3_evidence_only():
    cr = "/home/hamza/tlos-paper/p3-evidence/control_room"
    assert ww.classify(ww.parse_audit_log(_event(1, "tlos_p3_evidence", "mkdir", "1000", cr,
                                                 exe="/usr/bin/mkdir")))[0]["verdict"] == ww.AUTHORIZED
    assert ww.classify(ww.parse_audit_log(_event(2, "tlos_ledger", "mkdir", "1000", LEDGER,
                                                 exe="/usr/bin/mkdir")))[0]["verdict"] == ww.UNEXPECTED
    assert "mkdir -p" in (REPO_ROOT / "scripts" / "p3" / "scheduled_health.sh").read_text(encoding="utf-8")


def test_the_h1_lane_has_no_lawful_writer_while_h1_is_not_authorized():
    lane = "/home/hamza/tlos-paper/h1-paper-cohort-1/tradesv3.sqlite"
    assert _run(_event(1, "tlos_h1_lane", "freqtrade", "1000", lane))["severity"] == ww.CRITICAL


def test_hex_encoded_comm_is_decoded_before_attribution():
    # auditd hex-encodes a comm with a space: "python3 x" -> 707974686F6E332078
    log = _event(1, "tlos_ledger", None, "1000", LEDGER, comm_raw="707974686F6E332078")
    ev = ww.parse_audit_log(log)[0]
    assert ev.comm == "python3 x"
    assert ww.classify([ev])[0]["verdict"] == ww.UNEXPECTED  # not a declared comm glob


def test_enriched_log_fields_never_overwrite_the_numeric_ids():
    log = _event(1, "tlos_ledger", "python3", "1000", LEDGER).replace(
        'key="tlos_ledger"', 'key="tlos_ledger"\x1dARCH=x86_64 SYSCALL=openat AUID="root" UID="root" EUID="root"')
    ev = ww.parse_audit_log(log)[0]
    assert (ev.uid, ev.euid, ev.auid) == ("1000", "1000", "1000")


def test_an_event_without_comm_or_uid_is_unattributed_and_never_info():
    log = _event(1, "tlos_p3_evidence", None, None, "/home/hamza/tlos-paper/p3-evidence/x")
    assert ww.classify(ww.parse_audit_log(log))[0]["verdict"] == ww.UNATTRIBUTED
    f = _run(log)
    assert f["severity"] == ww.WARNING and "UNPROVEN" in f["detail"]


def test_an_unknown_tlos_key_is_unattributed():
    out = ww.classify(ww.parse_audit_log(_event(1, "tlos_nonsense", "python3", "1000", "/x")))
    assert out[0]["verdict"] == ww.UNATTRIBUTED


def test_events_without_our_keys_are_not_ours():
    assert ww.classify(ww.parse_audit_log(_event(1, None, "bash", "0", "/etc/passwd"))) == []
    assert ww.classify(ww.parse_audit_log(_event(2, "other_key", "bash", "0", "/etc/passwd"))) == []


# --------------------------------------------------------------------------- fail-closed: missing evidence


def test_no_audit_data_is_unproven_not_healthy():
    for status, rules in ((None, RULES_ALL), (STATUS_OK, None)):
        f = _run("", status=status, rules=rules)
        assert f["severity"] == ww.WARNING and "UNPROVEN" in f["detail"]
    f = ww.finding(None, status=ww.parse_status(STATUS_OK), rules_listing=RULES_ALL)
    assert f["severity"] == ww.WARNING
    f, _ = ww.evaluate(None, STATUS_OK, RULES_ALL)
    assert f["severity"] == ww.WARNING and "UNPROVEN" in f["detail"]


def test_an_empty_window_without_the_hourly_heartbeat_is_unproven():
    f = _run("", heartbeat=False)
    assert f["severity"] == ww.WARNING and "tlos_p3_evidence" in f["detail"] and "blind" in f["detail"]
    assert _run("")["severity"] == ww.INFO


def test_missing_watch_rules_are_unproven_per_path_not_only_per_key():
    partial = "\n".join(line for line in RULES_ALL.splitlines() if "tlos_sealed" not in line)
    f = _run("", rules=partial)
    assert f["severity"] == ww.WARNING and "tlos_sealed" in f["detail"]
    # the key is still loaded for the home canary, but the WDC canary watch is gone
    no_wdc_canary = "\n".join(line for line in RULES_ALL.splitlines() if "tlos-writer-canary" not in line)
    f = _run("", rules=no_wdc_canary)
    assert f["severity"] == ww.WARNING and "tlos_canary:/mnt/tlos-wdc/tlos-writer-canary" in f["detail"]


# --------------------------------------------------------------------------- event loss and coverage gaps


def test_lost_events_or_a_disabled_daemon_are_unproven():
    assert _run("", status=STATUS_OK.replace("lost 0", "lost 3"))["severity"] == ww.WARNING
    assert _run("", status=STATUS_OK.replace("lost 0", "lost 3"), lost_baseline=3)["severity"] == ww.INFO
    assert _run("", status=STATUS_OK.replace("enabled 1", "enabled 0"))["severity"] == ww.WARNING
    assert _run("", status=STATUS_OK.replace("lost 0\n", ""))["severity"] == ww.WARNING
    assert _run("", status=STATUS_OK.replace("enabled 1", "enabled 2"))["severity"] == ww.INFO  # immutable = enabled


def test_a_lost_counter_below_the_baseline_is_a_reset_and_unproven():
    f = _run("", status=STATUS_OK, lost_baseline=5)
    assert f["severity"] == ww.WARNING and "re-record the baseline" in f["detail"]


def test_a_saturated_backlog_is_unproven():
    f = _run("", status=STATUS_OK.replace("backlog 0", "backlog 8192"))
    assert f["severity"] == ww.WARNING and "backlog saturated" in f["detail"]


def test_the_daemon_stopping_inside_the_window_is_a_coverage_gap():
    for rtype in ww.GAP_RECORD_TYPES:
        log = f"type={rtype} msg=audit(1793000001.000:77): op=terminate auid=0 pid=1 res=success\n"
        f = _run(log)
        assert f["severity"] == ww.WARNING and rtype in f["detail"], rtype
    rotate = "type=DAEMON_ROTATE msg=audit(1793000001.000:78): op=rotate-logs auid=0 pid=1 res=success\n"
    assert _run(rotate)["severity"] == ww.INFO


def test_a_removed_watch_or_disabled_auditing_inside_the_window_is_a_coverage_gap():
    removed = ('type=CONFIG_CHANGE msg=audit(1793000001.000:80): auid=1000 ses=2 op=remove_rule '
               'key="tlos_ledger" list=4 res=1\n')
    f = _run(removed)
    assert f["severity"] == ww.WARNING and "tlos_ledger removed" in f["detail"] and "auid=1000" in f["detail"]
    disabled = "type=CONFIG_CHANGE msg=audit(1793000001.000:81): op=set audit_enabled=0 old=1 auid=1000 ses=2 res=1\n"
    assert "auditing disabled" in _run(disabled)["detail"]
    other = 'type=CONFIG_CHANGE msg=audit(1793000001.000:82): auid=0 ses=2 op=remove_rule key="other" list=4 res=1\n'
    assert _run(other)["severity"] == ww.INFO


def test_unexpected_wins_over_every_unproven_condition():
    log = _event(1, "tlos_sealed", "python3", "1000", SEALED)
    assert _run(log, status=None, rules=None)["severity"] == ww.CRITICAL
    gap = "type=DAEMON_END msg=audit(1793000001.000:77): op=terminate auid=0 pid=1 res=success\n"
    assert _run(log + gap, status=STATUS_OK.replace("lost 0", "lost 9"), heartbeat=False)["severity"] == ww.CRITICAL


# --------------------------------------------------------------------------- CLI


def test_the_cli_classifies_a_saved_log_and_exits_by_severity(tmp_path, capsys):
    log = tmp_path / "audit.log"
    status = tmp_path / "status.txt"
    rules = tmp_path / "rules.txt"
    status.write_text(STATUS_OK)
    rules.write_text(RULES_ALL)
    log.write_text(_event(1, "tlos_ledger", "python3", "1000", LEDGER) + HEARTBEAT)
    assert ww.main(["classify", "--log", str(log), "--status", str(status), "--rules", str(rules)]) == 0
    out = capsys.readouterr().out
    assert "COUNT tlos_ledger AUTHORIZED 1" in out and "COUNT tlos_p3_evidence AUTHORIZED 1" in out
    log.write_text(_event(2, "tlos_sealed", "cp", "1000", SEALED, exe="/usr/bin/cp"))
    assert ww.main(["classify", "--log", str(log), "--status", str(status), "--rules", str(rules)]) == 2
    assert "UNEXPECTED   tlos_sealed" in capsys.readouterr().out
    assert ww.main(["classify", "--log", str(log)]) == 2
    log.write_text("")
    assert ww.main(["classify", "--log", str(log)]) == 1
    assert ww.main(["rules"]) == 0
    assert "-k tlos_sealed" in capsys.readouterr().out


def test_the_cli_reports_unreadable_or_missing_inputs_as_unproven_not_a_crash(tmp_path, capsys):
    missing = tmp_path / "nope.log"
    rules = tmp_path / "rules.txt"
    rules.write_text(RULES_ALL)
    assert ww.main(["classify", "--log", str(missing), "--status", str(missing), "--rules", str(rules)]) == 1
    assert "UNPROVEN" in capsys.readouterr().out
    assert ww.main(["check-rules", "--rules", str(missing)]) == 1
    assert "RULES = UNPROVEN" in capsys.readouterr().out


def test_check_rules_reports_loaded_or_names_the_missing_watches(tmp_path, capsys):
    rules = tmp_path / "rules.txt"
    rules.write_text(RULES_ALL)
    assert ww.main(["check-rules", "--rules", str(rules)]) == 0
    assert "RULES = LOADED (9/9 watches)" in capsys.readouterr().out
    rules.write_text("\n".join(line for line in RULES_ALL.splitlines() if "tlos_h1_lane" not in line))
    assert ww.main(["check-rules", "--rules", str(rules)]) == 1
    assert "RULES = INCOMPLETE (8/9 watches); missing: tlos_h1_lane:" in capsys.readouterr().out


def test_the_script_runs_standalone_from_a_checkout_as_the_runbook_invokes_it():
    out = subprocess.run([sys.executable, str(REPO_ROOT / "research" / "p3" / "writer_watch.py"), "rules"],
                         capture_output=True, text=True, timeout=60, cwd=REPO_ROOT)
    assert out.returncode == 0, out.stderr
    assert out.stdout.count("-k tlos_") == 9 and "-e 2" not in out.stdout
