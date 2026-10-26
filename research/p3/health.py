"""P3-PLN-06 operational health check: capacity, recovery point, timers, runtimes, normal end.

P3_CONTRACT.md §3 PLN-06. It reuses the master plan's §19 severity model (INFO / WARNING /
CRITICAL) and checks the conditions P2 showed matter:
- free space on the root and the lane filesystems (the proposed Owner condition is at least 20 GiB);
- the age of the newest verified backup set against the recovery-point objective (RPO);
- the backup timer installed and active;
- the retired P2 restart timer still disabled (F-5);
- the WDC store mounted;
- a cohort whose trade ledger already shows a completed lifecycle while its registry row still says
  RUNNING, which means the normal end was reached and a governed stop is due (F-3).

Read-only. It changes nothing; an operator acts on its findings. Exit codes are 0 (all INFO),
1 (any WARNING) and 2 (any CRITICAL).

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

INFO, WARNING, CRITICAL = "INFO", "WARNING", "CRITICAL"
GIB = 1024 ** 3


def _finding(check: str, severity: str, detail: str) -> dict:
    return {"check": check, "severity": severity, "detail": detail}


def free_space(path: Path, minimum_gib: float, label: str) -> dict:
    probe = Path(path)
    while not probe.exists():
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    sev = INFO if free >= minimum_gib * GIB else CRITICAL
    return _finding(f"free_space:{label}", sev, f"{free / GIB:.1f} GiB free at {probe} (minimum {minimum_gib} GiB)")


def backup_recency(target: Path, rpo_hours: float, verifier: Callable[[Path], dict] | None = None,
                   now: float | None = None) -> dict:
    sets = sorted(p for p in Path(target).glob("*") if p.is_dir() and not p.name.startswith(".")
                  and (p / "BACKUP_RECORD.json").is_file()) if Path(target).is_dir() else []
    if not sets:
        return _finding("backup_recency", CRITICAL, f"no backup set under {target}")
    newest = sets[-1]
    age_h = ((now or time.time()) - (newest / "BACKUP_RECORD.json").stat().st_mtime) / 3600
    if verifier is not None and verifier(newest).get("status") != "PASS":
        return _finding("backup_recency", CRITICAL, f"newest set {newest.name} does not verify")
    sev = INFO if age_h <= rpo_hours else WARNING
    return _finding("backup_recency", sev, f"newest set {newest.name}, {age_h:.1f} h old (RPO {rpo_hours} h)")


def _unit_state(unit: str, runner) -> tuple[str, str]:
    enabled = runner(["systemctl", "--user", "is-enabled", unit]).stdout.strip() or "absent"
    active = runner(["systemctl", "--user", "is-active", unit]).stdout.strip() or "unknown"
    return enabled, active


def timer_expected(unit: str, *, want_active: bool, runner) -> dict:
    enabled, active = _unit_state(unit, runner)
    ok = (enabled == "enabled" and active == "active") if want_active else (enabled != "enabled" and active != "active")
    sev = INFO if ok else (WARNING if want_active else CRITICAL)
    want = "enabled+active" if want_active else "disabled+inactive"
    return _finding(f"timer:{unit}", sev, f"{enabled}/{active} (expected {want})")


def mounted(path: str) -> dict:
    return _finding(f"mount:{path}", INFO if os.path.ismount(path) else CRITICAL,
                    "mounted" if os.path.ismount(path) else "not mounted")


def normal_end_due(registry: dict, lane_root: Path) -> list[dict]:
    findings = []
    for row in registry.get("instances", []):
        if row.get("status") != "RUNNING":
            continue
        evidence = row.get("runtime_identity", {}).get("evidence_dir", "")
        ledger = Path(lane_root) / Path(evidence).relative_to("/freqtrade/user_data") / "paper_trade_ledger.jsonl" \
            if evidence.startswith("/freqtrade/user_data") else None
        closed = 0
        if ledger and ledger.is_file():
            closed = sum(1 for line in ledger.read_text(encoding="utf-8").splitlines()
                         if line.strip() and json.loads(line).get("payload", {}).get("event") == "position_closed")
        sev = WARNING if closed else INFO
        detail = (f"{row['role']} is RUNNING with {closed} closed lifecycle(s): NORMAL END reached, governed stop due"
                  if closed else f"{row['role']} RUNNING, no completed lifecycle yet")
        findings.append(_finding(f"normal_end:{row['role']}", sev, detail))
    if not findings:
        findings.append(_finding("normal_end", INFO, "no RUNNING cohort"))
    return findings


def overall(findings: list[dict]) -> str:
    sevs = {f["severity"] for f in findings}
    return CRITICAL if CRITICAL in sevs else WARNING if WARNING in sevs else INFO


def standard_findings(registry: dict, *, runner, verifier: Callable[[Path], dict] | None,
                      root_min_gib: float = 20.0, lane: Path = Path("/home/hamza/tlos-paper/h1-paper-cohort-1"),
                      lane_min_gib: float = 20.0, backup_target: Path = Path("/mnt/tlos-wdc/tlos-backups"),
                      rpo_hours: float = 26.0,
                      fp_lane_root: Path = Path("/home/hamza/projects/trading/trading_lab_os_final/freqtrade/user_data"),
                      ) -> list[dict]:
    """The host's standard check set, shared by the health CLI and the Control Room projection."""
    return [
        free_space(Path("/"), root_min_gib, "root"),
        free_space(lane, lane_min_gib, "h1_lane"),
        mounted("/mnt/tlos-wdc"),
        backup_recency(backup_target, rpo_hours, verifier=verifier),
        timer_expected("tlos-p3-backup.timer", want_active=True, runner=runner),
        timer_expected("tlos-p2-window-fp-control-3.timer", want_active=False, runner=runner),
        *normal_end_due(registry, fp_lane_root),
    ]


def default_runner(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


SEVERITY_VALUE = {INFO: 0, WARNING: 1, CRITICAL: 2}


def prometheus_text(findings: list[dict]) -> str:
    """Prometheus text exposition: one gauge per check (0 INFO, 1 WARNING, 2 CRITICAL) and the overall.

    Written as a node-exporter textfile (or scraped through any file-based collector), so alert
    delivery reuses the existing Prometheus/Grafana stack (§10) without touching the FP exporter.
    """
    lines = ["# HELP tlos_p3_health_check Trading Lab OS P3 health check severity (0 INFO, 1 WARNING, 2 CRITICAL)",
             "# TYPE tlos_p3_health_check gauge"]
    for f in findings:
        check = f["check"].replace("\\", "\\\\").replace('"', "'")
        lines.append(f'tlos_p3_health_check{{check="{check}"}} {SEVERITY_VALUE[f["severity"]]}')
    lines += ["# HELP tlos_p3_health_overall Worst severity across all checks",
              "# TYPE tlos_p3_health_overall gauge", f"tlos_p3_health_overall {SEVERITY_VALUE[overall(findings)]}"]
    return "\n".join(lines) + "\n"


def write_textfile(findings: list[dict], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(prometheus_text(findings), encoding="utf-8")
    os.replace(tmp, path)  # atomic: a scraper never reads a half-written file

