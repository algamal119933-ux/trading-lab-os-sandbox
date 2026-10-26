"""P3-PLN-06: §19 "unexpected writer" — auditd watch rules and a read-only classifier of their events.

Master plan §19 lists "unexpected writer" as CRITICAL. The health job (research/p3/health.py) cannot
see it: rehashing sealed archives catches a changed byte after the fact, but not who wrote, and not a
write to the ledger, the evidence directory or the backup sets. This module is the repository side of
the auditd-first design in docs/p3/PLN_06_UNEXPECTED_WRITER.md:

(a) ``render_rules`` turns the protected-path inventory into an auditd rules file
    (``-w <path> -p wa -k tlos_<class>``). It writes nothing; the Owner installs it.
(b) ``parse_audit_log`` groups raw ``/var/log/audit/audit.log`` (or ``ausearch --raw``) text into
    events, and ``classify`` labels each watched event AUTHORIZED, UNEXPECTED or UNATTRIBUTED against
    the declared writers of its class.
(c) ``finding`` maps a classification run to one health finding, fail-closed:
    any UNEXPECTED -> CRITICAL; no audit data, rules not loaded, lost events or an UNATTRIBUTED event
    -> WARNING "UNPROVEN"; INFO only when the rules are proven loaded, nothing was lost and every
    watched event is attributed to a declared writer.

Read-only. It installs nothing, starts nothing and is not yet part of the hourly health run.
Until the Owner installs auditd and the acceptance tests in the design document pass on the host,
"unexpected writer" stays NOT_COVERED on the host.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

INFO, WARNING, CRITICAL = "INFO", "WARNING", "CRITICAL"
AUTHORIZED, UNEXPECTED, UNATTRIBUTED = "AUTHORIZED", "UNEXPECTED", "UNATTRIBUTED"
KEY_PREFIX = "tlos_"
CHECK = "unexpected_writer"

H = "/home/hamza"
OWNER_UID = "1000"  # hamza on hamza-workstation (the WDC ntfs3 mount is uid=1000 too); override per host


@dataclass(frozen=True)
class Writer:
    """A declared writer: comm glob(s), allowed uids, optional exe prefixes. All given parts must match."""
    name: str
    comms: tuple[str, ...]
    uids: tuple[str, ...] = (OWNER_UID,)
    exe_prefixes: tuple[str, ...] = ()

    def matches(self, comm: str | None, uid: str | None, exe: str | None) -> bool:
        if not comm or uid is None:
            return False
        if not any(fnmatch.fnmatchcase(comm, c) for c in self.comms):
            return False
        if uid not in self.uids:
            return False
        if self.exe_prefixes and not (exe and any(exe.startswith(p) for p in self.exe_prefixes)):
            return False
        return True


@dataclass(frozen=True)
class ProtectedClass:
    """A class of protected paths with the writers allowed to touch it. No writers = no write is lawful."""
    key: str
    paths: tuple[str, ...]
    writers: tuple[Writer, ...] = ()
    why: str = ""


PY = ("python", "python3", "python3.*")
# The inventory, derived from docs/p3/PLN_02_STATE_INVENTORY.md and the P3 tools that write each path.
DEFAULT_INVENTORY: tuple[ProtectedClass, ...] = (
    ProtectedClass(
        "sealed", (f"{H}/projects/trading/trading_lab_os_final/artifacts", "/mnt/tlos-wdc/trading-lab-os-evidence"),
        (), "sealed P2 archives and their second-device copies: once sealed, nothing may write (a new governed "
            "archive is pre-announced and its events reviewed)"),
    ProtectedClass(
        "ledger", (f"{H}/tlos-paper/operator-ledger",),
        (Writer("kill_switch/recovery (python, owner)", PY),),
        "hash-chained operator ledger: appended only by scripts/p3/kill_switch.py and recovery.py authorize-resume"),
    ProtectedClass(
        "p3_evidence", (f"{H}/tlos-paper/p3-evidence",),
        (Writer("health job / control room / recovery snapshot (python, owner)", PY),),
        "P3 evidence: hourly health textfile, Control Room build, reboot snapshots and verify records"),
    ProtectedClass(
        "backups", ("/mnt/tlos-wdc/tlos-backups",),
        (Writer("backup.py and its helpers (owner)", (*PY, "tar", "zstd", "git", "sha256sum")),
         Writer("volume export helper container (tar as root)", ("tar",), uids=("0",))),
        "append-only backup sets written by scripts/p3/scheduled_backup.sh"),
    ProtectedClass(
        "registry", (f"{H}/projects/trading/trading_lab_os_final/research/fp/records",),
        (Writer("git (owner)", ("git",)),),
        "runtime checkout's governed records: change only through git at a merged commit"),
    ProtectedClass(
        "h1_lane", (f"{H}/tlos-paper/h1-paper-cohort-1",),
        (), "H1 lane: no lawful writer while H1_LAUNCH_AUTHORIZED = NO; the H1 grant PR adds the launcher/container "
            "writers here"),
    ProtectedClass(
        "canary", (f"{H}/tlos-paper/writer-canary",),
        (), "acceptance canary: holds no evidence; any write is UNEXPECTED by design, so the Owner can prove the alert "
            "path without touching real evidence"),
)


# --- (a) rules ---------------------------------------------------------------------------------------

def render_rules(inventory: tuple[ProtectedClass, ...] = DEFAULT_INVENTORY, *, backlog: int = 8192) -> str:
    """An auditd rules file (for /etc/audit/rules.d/tlos-evidence.rules). Watches writes and attribute changes."""
    lines = [
        "# Trading Lab OS P3-PLN-06 — §19 'unexpected writer' watches (generated by research/p3/writer_watch.py).",
        "# Installed only by the Owner (docs/p3/PLN_06_UNEXPECTED_WRITER.md). Read-only for the system it watches.",
        f"-b {backlog}",
        "--backlog_wait_time 60000",
        "-f 1",
    ]
    for cls in inventory:
        for path in cls.paths:
            lines.append(f"-w {path} -p wa -k {KEY_PREFIX}{cls.key}")
    return "\n".join(lines) + "\n"


# --- (b) parse + classify ----------------------------------------------------------------------------

_MSG_RE = re.compile(r"msg=audit\((\d+\.\d+):(\d+)\)")
_FIELD_RE = re.compile(r'(\w+)=("([^"]*)"|\S+)')
_HEX_RE = re.compile(r"^[0-9A-Fa-f]+$")


def _value(raw: str, quoted: str | None) -> str:
    if quoted is not None:
        return quoted
    if raw == "(null)":
        return ""
    # auditd hex-encodes untrusted strings (comm/exe/name/key) that contain spaces or unusual bytes.
    if _HEX_RE.match(raw) and len(raw) % 2 == 0 and len(raw) >= 2:
        try:
            decoded = bytes.fromhex(raw).decode("utf-8")
            if decoded.isprintable():
                return decoded
        except ValueError:
            pass
    return raw


@dataclass
class AuditEvent:
    event_id: str
    time: float
    key: str | None = None
    comm: str | None = None
    exe: str | None = None
    uid: str | None = None
    auid: str | None = None
    success: str | None = None
    syscall: str | None = None
    paths: list[str] = field(default_factory=list)


_STRING_FIELDS = {"comm", "exe", "key", "name"}


def parse_audit_log(text: str) -> list[AuditEvent]:
    """Group raw audit records (SYSCALL, PATH, ...) by event id into events."""
    events: dict[str, AuditEvent] = {}
    for line in text.splitlines():
        m = _MSG_RE.search(line)
        if not m:
            continue
        eid = f"{m.group(1)}:{m.group(2)}"
        ev = events.setdefault(eid, AuditEvent(eid, float(m.group(1))))
        rtype = line.split(" ", 1)[0].removeprefix("type=")
        fields = {}
        for fm in _FIELD_RE.finditer(line[m.end():]):
            name, raw, quoted = fm.group(1), fm.group(2), fm.group(3)
            fields[name] = _value(raw, quoted) if name in _STRING_FIELDS else (quoted if quoted is not None else raw)
        if rtype == "SYSCALL":
            ev.key = fields.get("key") or None
            ev.comm = fields.get("comm") or None
            ev.exe = fields.get("exe") or None
            ev.uid = fields.get("uid")
            ev.auid = fields.get("auid")
            ev.success = fields.get("success")
            ev.syscall = fields.get("syscall")
        elif rtype == "PATH" and fields.get("name"):
            ev.paths.append(fields["name"])
    return sorted(events.values(), key=lambda e: e.event_id)


def classify(events: list[AuditEvent], inventory: tuple[ProtectedClass, ...] = DEFAULT_INVENTORY) -> list[dict]:
    """Label every event that carries one of our watch keys. Events without a tlos_ key are not ours."""
    by_key = {f"{KEY_PREFIX}{c.key}": c for c in inventory}
    out = []
    for ev in events:
        if not ev.key or not ev.key.startswith(KEY_PREFIX):
            continue
        cls = by_key.get(ev.key)
        base = {"event": ev.event_id, "key": ev.key, "comm": ev.comm, "exe": ev.exe, "uid": ev.uid,
                "paths": ev.paths[:4]}
        if cls is None:
            out.append({**base, "verdict": UNATTRIBUTED, "why": "watch key not in the inventory"})
        elif not ev.comm or ev.uid is None:
            out.append({**base, "verdict": UNATTRIBUTED, "why": "event lacks comm or uid"})
        elif any(w.matches(ev.comm, ev.uid, ev.exe) for w in cls.writers):
            out.append({**base, "verdict": AUTHORIZED, "why": f"declared writer of {cls.key}"})
        else:
            out.append({**base, "verdict": UNEXPECTED,
                        "why": f"no declared writer of {cls.key} matches comm={ev.comm!r} uid={ev.uid}"})
    return out


# --- auditd self-state (the rules are loaded; nothing was lost) --------------------------------------

def parse_status(text: str) -> dict[str, int]:
    """``auditctl -s`` output ('enabled 1', 'lost 0', 'backlog 0', ...) -> {name: int}."""
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].lstrip("-").isdigit():
            out[parts[0]] = int(parts[1])
    return out


def loaded_keys(rules_listing: str) -> set[str]:
    """``auditctl -l`` output -> the set of tlos_ keys that are actually loaded."""
    return set(re.findall(r"-k\s+(" + KEY_PREFIX + r"\w+)", rules_listing)) | \
        set(re.findall(r"key=(" + KEY_PREFIX + r"\w+)", rules_listing))


# --- (c) one health finding, fail-closed --------------------------------------------------------------

def finding(classified: list[dict] | None, *, status: dict[str, int] | None, rules_listing: str | None,
            inventory: tuple[ProtectedClass, ...] = DEFAULT_INVENTORY, lost_baseline: int = 0) -> dict:
    """INFO only if everything is proven: rules loaded for every class, auditd enabled, no lost events
    since the baseline, and every watched event attributed to a declared writer."""
    def f(sev: str, detail: str) -> dict:
        return {"check": CHECK, "severity": sev, "detail": detail}

    unexpected = [c for c in (classified or []) if c["verdict"] == UNEXPECTED]
    if unexpected:
        first = unexpected[0]
        return f(CRITICAL, f"{len(unexpected)} unexpected write(s); first: key={first['key']} comm={first['comm']!r} "
                           f"uid={first['uid']} path={(first['paths'] or ['?'])[0]}")
    if rules_listing is None or status is None or classified is None:
        return f(WARNING, "UNPROVEN: audit data unavailable (auditd not installed, not readable, or not queried)")
    want = {f"{KEY_PREFIX}{c.key}" for c in inventory}
    missing = sorted(want - loaded_keys(rules_listing))
    if missing:
        return f(WARNING, f"UNPROVEN: watch rules not loaded for {', '.join(missing)}")
    if status.get("enabled", 0) < 1:
        return f(WARNING, "UNPROVEN: auditd is not enabled")
    lost = status.get("lost")
    if lost is None:
        return f(WARNING, "UNPROVEN: auditd lost counter unavailable")
    if lost > lost_baseline:
        return f(WARNING, f"UNPROVEN: auditd lost {lost - lost_baseline} event(s) since the baseline")
    unattributed = [c for c in classified if c["verdict"] == UNATTRIBUTED]
    if unattributed:
        return f(WARNING, f"UNPROVEN: {len(unattributed)} watched event(s) could not be attributed")
    return f(INFO, f"{len(classified)} watched write(s), all by declared writers; rules loaded for {len(want)} "
                   f"classes; no events lost")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("rules", help="print the auditd rules file for the default inventory")
    cls = sub.add_parser("classify", help="classify a raw audit log; read-only")
    cls.add_argument("--log", type=Path, required=True)
    cls.add_argument("--status", type=Path, help="saved `auditctl -s` output")
    cls.add_argument("--rules", type=Path, help="saved `auditctl -l` output")
    cls.add_argument("--lost-baseline", type=int, default=0)
    args = parser.parse_args(argv)
    if args.command == "rules":
        sys.stdout.write(render_rules())
        return 0
    classified = classify(parse_audit_log(args.log.read_text(encoding="utf-8", errors="replace")))
    status = parse_status(args.status.read_text(encoding="utf-8")) if args.status else None
    rules = args.rules.read_text(encoding="utf-8") if args.rules else None
    result = finding(classified, status=status, rules_listing=rules, lost_baseline=args.lost_baseline)
    for c in classified:
        if c["verdict"] != AUTHORIZED:
            print(f"  {c['verdict']:12} {c['key']:18} comm={c['comm']!r} uid={c['uid']} {c['why']}")
    print(f"  {result['severity']:8} {result['check']} {result['detail']}")
    return {INFO: 0, WARNING: 1, CRITICAL: 2}[result["severity"]]


if __name__ == "__main__":
    raise SystemExit(main())
