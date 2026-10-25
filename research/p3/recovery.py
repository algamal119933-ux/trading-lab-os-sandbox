"""P3-PLN-04 restart / reboot / host recovery: a terminal-state guard and a reboot check.

P3_CONTRACT.md §3 PLN-04. Acceptance:
- after a reboot, the stack's state is correct;
- a cohort in a terminal or Owner-stopped state is **never** restarted automatically (negative test);
- a host-recovery drill from backup passes (PLN-03 provides it).

P2 finding F-5: the host timer undid an Owner-authorized stop, because its restart path had no
guard. ``may_restart`` is that guard, for any recovery automation. It allows a restart only when:
- the registry row is RUNNING;
- no kill-switch STOPPED record for the role's containers stands in the operator ledger, unless a
  later RESUME_AUTHORIZED record for the role exists.

``snapshot`` / ``verify_after_boot`` prove a reboot actually happened (the boot id changed) and that
what must come back did, and that what must stay stopped did.

Read-only, apart from ``authorize_resume``, which appends one attributable ledger record.
PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import fnmatch
import json
import os
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from p3 import kill_switch

BOOT_ID = Path("/proc/sys/kernel/random/boot_id")


def _ledger(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    problems = kill_switch.verify_ledger(path)
    if problems:
        raise kill_switch.KillSwitchError(f"operator ledger does not verify: {problems[:3]}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _role_pattern(row: dict) -> str:
    bot = row.get("runtime_identity", {}).get("bot_name") or row["role"].lower()
    return f"tradinglab-{bot}-*"


def may_restart(role: str, registry: dict, ledger: Path) -> tuple[bool, str]:
    row = next((r for r in registry.get("instances", []) if r.get("role") == role), None)
    if row is None:
        return False, f"{role} is not in the registry"
    if row.get("status") != "RUNNING":
        return False, f"{role} is {row.get('status')}; only a RUNNING cohort may be restarted"
    pattern = _role_pattern(row)
    standing = None
    for record in _ledger(ledger):
        if record.get("outcome") == "STOPPED" and any(fnmatch.fnmatchcase(t, pattern) for t in record.get("targets", [])):
            standing = record
        elif record.get("record_type") == "P3_RESUME_AUTHORIZED_V1" and record.get("role") == role:
            standing = None
    if standing is not None:
        return False, (f"{role} was stopped by {standing.get('operator')} at {standing.get('utc')} "
                       f"({standing.get('reason')!r}); no later RESUME_AUTHORIZED record")
    return True, f"{role} is RUNNING and no governed stop stands"


def authorize_resume(role: str, *, reason: str, operator: str, ledger: Path) -> dict:
    if not reason.strip() or not operator.strip():
        raise kill_switch.KillSwitchError("a resume needs an operator and a reason")
    record = {"record_type": "P3_RESUME_AUTHORIZED_V1", "role": role, "operator": operator, "reason": reason.strip(),
              "host": socket.gethostname(), "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
              "real_money_authorized": False}
    return kill_switch._append(ledger, record)  # noqa: SLF001 — the same chained ledger, by design


def _run(cmd: list[str]) -> str:
    # systemctl is-enabled / is-active print the state AND exit non-zero for "disabled" or
    # "inactive"; the printed state is the answer, so the exit code must not discard it.
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return result.stdout.strip()


def snapshot(mounts: tuple[str, ...], units: tuple[str, ...], runner=_run) -> dict:
    containers = {}
    for line in runner(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.State}}"]).splitlines():
        name, _, state = line.partition("\t")
        containers[name] = state
    return {
        "snapshot_version": "P3_REBOOT_SNAPSHOT_V1",
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "boot_id": BOOT_ID.read_text().strip() if BOOT_ID.exists() else "",
        "mounts": {m: os.path.ismount(m) for m in mounts},
        "units": {u: [runner(["systemctl", "--user", "is-enabled", u]) or "absent",
                      runner(["systemctl", "--user", "is-active", u]) or "inactive"] for u in units},
        "containers": containers,
    }


def verify_after_boot(before: dict, after: dict) -> dict:
    checks = {}
    checks["rebooted"] = {"status": "PASS" if before["boot_id"] and after["boot_id"] != before["boot_id"] else "FAIL",
                          "detail": f"boot_id {before['boot_id'][:8]} -> {after['boot_id'][:8]}"}
    for mount, was in before["mounts"].items():
        if was:
            ok = after["mounts"].get(mount, False)
            checks[f"mount:{mount}"] = {"status": "PASS" if ok else "FAIL", "detail": "back" if ok else "missing"}
    for unit, (enabled, _active) in before["units"].items():
        now = after["units"].get(unit, ["absent", "inactive"])
        ok = now[0] == enabled and (now[1] == "active") == (enabled == "enabled")
        checks[f"unit:{unit}"] = {"status": "PASS" if ok else "FAIL", "detail": f"{enabled} -> {now[0]}/{now[1]}"}
    for name, state in before["containers"].items():
        now = after["containers"].get(name)
        paper = any(fnmatch.fnmatchcase(name, p) for p in kill_switch.PAPER_RUNTIME_PATTERNS)
        if paper:
            ok = now != "running" if state != "running" else True
            checks[f"paper:{name}"] = {"status": "PASS" if ok else "FAIL",
                                       "detail": f"{state} -> {now} (a stopped paper runtime must stay stopped)"}
        elif state == "running":
            checks[f"container:{name}"] = {"status": "PASS" if now == "running" else "FAIL", "detail": f"running -> {now}"}
    new_paper = [n for n, s in after["containers"].items() if s == "running" and n not in before["containers"]
                 and any(fnmatch.fnmatchcase(n, p) for p in kill_switch.PAPER_RUNTIME_PATTERNS)]
    checks["no_new_paper_runtime"] = {"status": "PASS" if not new_paper else "FAIL", "detail": new_paper or "none"}
    verdict = all(c["status"] == "PASS" for c in checks.values())
    return {"checks": checks, "PLN_04_REBOOT_CHECK": "PASS" if verdict else "FAIL", "real_money_authorized": False}
