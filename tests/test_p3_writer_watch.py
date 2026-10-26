"""P3-PLN-06 §19 'unexpected writer': research/p3/writer_watch.py on synthetic audit records only.

No real audit log, no host path is read, nothing is installed. The fixtures are hand-written raw
auditd lines in the documented format (SYSCALL + PATH grouped by msg=audit(<time>:<serial>)).
PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "research") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "research"))

from p3 import writer_watch as ww  # noqa: E402

LEDGER = "/home/hamza/tlos-paper/operator-ledger/operator_ledger.jsonl"
SEALED = "/home/hamza/projects/trading/trading_lab_os_final/artifacts/l2-cohort-x/MANIFEST.sha256"


def _event(serial: int, key: str | None, comm: str | None, uid: str | None, path: str, exe: str = "/usr/bin/python3.12",
           comm_raw: str | None = None) -> str:
    t = f"1793000000.{serial:03d}:{serial}"
    parts = [f"type=SYSCALL msg=audit({t}): arch=c000003e syscall=257 success=yes exit=3 ppid=1 pid={1000 + serial}",
             "auid=1000"]
    if uid is not None:
        parts.append(f"uid={uid} gid={uid} euid={uid}")
    if comm_raw is not None:
        parts.append(f"comm={comm_raw}")
    elif comm is not None:
        parts.append(f'comm="{comm}"')
    parts.append(f'exe="{exe}"')
    parts.append(f'key="{key}"' if key else "key=(null)")
    syscall = " ".join(parts)
    path_rec = f'type=PATH msg=audit({t}): item=0 name="{path}" inode=42 nametype=NORMAL'
    return syscall + "\n" + path_rec + "\n"


STATUS_OK = "enabled 1\nfailure 1\npid 812\nrate_limit 0\nbacklog_limit 8192\nlost 0\nbacklog 0\n"
RULES_ALL = "\n".join(f"-w {p} -p wa -k tlos_{c.key}" for c in ww.DEFAULT_INVENTORY for p in c.paths)


def _run(log: str, status: str | None = STATUS_OK, rules: str | None = RULES_ALL, lost_baseline: int = 0) -> dict:
    classified = ww.classify(ww.parse_audit_log(log))
    return ww.finding(classified, status=None if status is None else ww.parse_status(status),
                      rules_listing=rules, lost_baseline=lost_baseline)


def test_rendered_rules_watch_every_protected_path_for_writes_and_attribute_changes():
    rules = ww.render_rules()
    for cls in ww.DEFAULT_INVENTORY:
        for path in cls.paths:
            assert f"-w {path} -p wa -k tlos_{cls.key}" in rules
    assert "-b 8192" in rules and "-f 1" in rules
    assert "-e 2" not in rules  # immutable mode is an Owner decision, never generated silently
    assert ww.loaded_keys(rules) == {f"tlos_{c.key}" for c in ww.DEFAULT_INVENTORY}


def test_a_declared_writer_is_authorized_and_the_run_is_info_only_when_everything_is_proven():
    log = _event(1, "tlos_ledger", "python3", "1000", LEDGER)
    out = ww.classify(ww.parse_audit_log(log))
    assert [c["verdict"] for c in out] == [ww.AUTHORIZED]
    f = _run(log)
    assert f["check"] == "unexpected_writer" and f["severity"] == ww.INFO


def test_any_write_to_a_sealed_archive_is_unexpected_and_critical():
    f = _run(_event(1, "tlos_sealed", "python3", "1000", SEALED))
    assert f["severity"] == ww.CRITICAL and "tlos_sealed" in f["detail"]


def test_a_foreign_process_or_uid_on_the_ledger_is_unexpected():
    for comm, uid in (("vim", "1000"), ("python3", "1001"), ("bash", "0")):
        out = ww.classify(ww.parse_audit_log(_event(1, "tlos_ledger", comm, uid, LEDGER)))
        assert out[0]["verdict"] == ww.UNEXPECTED, (comm, uid)


def test_the_volume_export_helper_is_allowed_as_root_tar_only_on_the_backup_sets():
    bk = "/mnt/tlos-wdc/tlos-backups/20261027T033300Z/volumes/x.tar"
    assert ww.classify(ww.parse_audit_log(_event(1, "tlos_backups", "tar", "0", bk)))[0]["verdict"] == ww.AUTHORIZED
    assert ww.classify(ww.parse_audit_log(_event(2, "tlos_backups", "rm", "0", bk)))[0]["verdict"] == ww.UNEXPECTED
    assert ww.classify(ww.parse_audit_log(_event(3, "tlos_ledger", "tar", "0", LEDGER)))[0]["verdict"] == ww.UNEXPECTED


def test_the_h1_lane_has_no_lawful_writer_while_h1_is_not_authorized():
    lane = "/home/hamza/tlos-paper/h1-paper-cohort-1/tradesv3.sqlite"
    assert _run(_event(1, "tlos_h1_lane", "freqtrade", "1000", lane))["severity"] == ww.CRITICAL


def test_hex_encoded_comm_is_decoded_before_attribution():
    # auditd hex-encodes a comm with a space: "python3 x" -> 707974686F6E332078
    log = _event(1, "tlos_ledger", None, "1000", LEDGER, comm_raw="707974686F6E332078")
    ev = ww.parse_audit_log(log)[0]
    assert ev.comm == "python3 x"
    assert ww.classify([ev])[0]["verdict"] == ww.UNEXPECTED  # not a declared comm glob


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


def test_no_audit_data_is_unproven_not_healthy():
    for status, rules in ((None, RULES_ALL), (STATUS_OK, None)):
        f = _run("", status=status, rules=rules)
        assert f["severity"] == ww.WARNING and "UNPROVEN" in f["detail"]
    f = ww.finding(None, status=ww.parse_status(STATUS_OK), rules_listing=RULES_ALL)
    assert f["severity"] == ww.WARNING


def test_missing_watch_rules_are_unproven():
    partial = "\n".join(line for line in RULES_ALL.splitlines() if "tlos_sealed" not in line)
    f = _run("", rules=partial)
    assert f["severity"] == ww.WARNING and "tlos_sealed" in f["detail"]


def test_lost_events_or_a_disabled_daemon_are_unproven():
    assert _run("", status=STATUS_OK.replace("lost 0", "lost 3"))["severity"] == ww.WARNING
    assert _run("", status=STATUS_OK.replace("lost 0", "lost 3"), lost_baseline=3)["severity"] == ww.INFO
    assert _run("", status=STATUS_OK.replace("enabled 1", "enabled 0"))["severity"] == ww.WARNING
    assert _run("", status=STATUS_OK.replace("lost 0\n", ""))["severity"] == ww.WARNING


def test_unexpected_wins_over_every_unproven_condition():
    log = _event(1, "tlos_sealed", "python3", "1000", SEALED)
    assert _run(log, status=None, rules=None)["severity"] == ww.CRITICAL


def test_the_cli_classifies_a_saved_log_and_exits_by_severity(tmp_path, capsys):
    log = tmp_path / "audit.log"
    status = tmp_path / "status.txt"
    rules = tmp_path / "rules.txt"
    status.write_text(STATUS_OK)
    rules.write_text(RULES_ALL)
    log.write_text(_event(1, "tlos_ledger", "python3", "1000", LEDGER))
    assert ww.main(["classify", "--log", str(log), "--status", str(status), "--rules", str(rules)]) == 0
    log.write_text(_event(2, "tlos_sealed", "cp", "1000", SEALED))
    assert ww.main(["classify", "--log", str(log), "--status", str(status), "--rules", str(rules)]) == 2
    assert ww.main(["classify", "--log", str(log)]) == 2
    log.write_text("")
    assert ww.main(["classify", "--log", str(log)]) == 1
    assert ww.main(["rules"]) == 0
    assert "-k tlos_sealed" in capsys.readouterr().out


def test_the_acceptance_canary_has_no_lawful_writer_and_holds_no_evidence_path():
    canary = [c for c in ww.DEFAULT_INVENTORY if c.key == "canary"]
    assert len(canary) == 1 and canary[0].writers == ()
    evidence_paths = {p for c in ww.DEFAULT_INVENTORY if c.key != "canary" for p in c.paths}
    assert not any(canary[0].paths[0].startswith(p) or p.startswith(canary[0].paths[0]) for p in evidence_paths)
    f = _run(_event(1, "tlos_canary", "touch", "1000", "/home/hamza/tlos-paper/writer-canary/probe"))
    assert f["severity"] == ww.CRITICAL
