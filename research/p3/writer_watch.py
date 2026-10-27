"""P3-PLN-06: §19 "unexpected writer" — auditd watch rules and a read-only classifier of their events.

Master plan §19 lists "unexpected writer" as CRITICAL. The health job (research/p3/health.py) cannot
see it: rehashing sealed archives catches a changed byte after the fact, but not who wrote, and not a
write to the ledger, the evidence directory or the backup sets. This module is the repository side of
the auditd-first design in docs/p3/PLN_06_UNEXPECTED_WRITER.md:

(a) ``render_rules`` turns the protected-path inventory into an auditd rules file
    (``-w <path> -p wa -k tlos_<class>``). It writes nothing; the Owner installs it.
(b) ``parse_audit_log`` groups raw ``/var/log/audit/audit.log`` (or ``ausearch --raw``) text into
    events, and ``classify`` labels each watched event AUTHORIZED, UNEXPECTED or UNATTRIBUTED against
    the declared writers of its class (comm + uid + euid + exe, all of them).
(c) ``coverage_gaps`` finds what the counters cannot: the daemon stopping or erroring inside the
    window, a ``tlos_`` watch removed, or auditing switched off.
(d) ``finding`` maps one run to one health finding, fail-closed:
    any UNEXPECTED -> CRITICAL; no audit data, a watch not loaded, lost events, a saturated backlog,
    a coverage gap, an UNATTRIBUTED event or a silent heartbeat class -> WARNING "UNPROVEN";
    INFO only when everything is proven.

The protected paths are not a new list: they are derived from the constants the health job and the
Control Room already use (``health.RUNTIME_ROOT``, ``health.OPERATOR_LEDGER``, ``health.H1_LANE``,
``control_room.EVIDENCE_DIR``, ``control_room.BACKUP_TARGET``), so a moved path moves here too.

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
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parents[1]
if str(_RESEARCH) not in sys.path:  # run as `python3 research/p3/writer_watch.py` on the host
    sys.path.insert(0, str(_RESEARCH))

from p3 import control_room, health  # noqa: E402

INFO, WARNING, CRITICAL = "INFO", "WARNING", "CRITICAL"
AUTHORIZED, UNEXPECTED, UNATTRIBUTED = "AUTHORIZED", "UNEXPECTED", "UNATTRIBUTED"
KEY_PREFIX = "tlos_"
CHECK = "unexpected_writer"

OWNER_UID = "1000"  # hamza on hamza-workstation (the WDC ntfs3 mount is uid=1000 too); override per host
# Writers must run a root-owned system binary: a process that renames itself (comm) from a binary in
# a user-writable place does not pass as a declared writer.
SYSTEM_BIN = ("/usr/bin/", "/bin/", "/usr/local/bin/", "/usr/sbin/", "/sbin/")

# --- protected paths, derived from the existing repository constants ---------------------------------
RUNTIME_ROOT = health.RUNTIME_ROOT                                  # the runtime checkout
LEDGER_DIR = health.OPERATOR_LEDGER.parent                          # hash-chained operator ledger
PAPER_ROOT = LEDGER_DIR.parent                                      # ~/tlos-paper
H1_LANE = health.H1_LANE                                            # H1 lane (absent while not authorized)
EVIDENCE_DIR = control_room.EVIDENCE_DIR                            # P3 evidence (health textfile, records)
BACKUP_TARGET = control_room.BACKUP_TARGET                          # append-only backup sets (WDC)
WDC_ROOT = BACKUP_TARGET.parent                                     # the second device's mount point
SECOND_DEVICE_REPLICA = WDC_ROOT / "trading-lab-os-evidence"        # scripts/replicate_to_second_device.REPLICA_ROOT_NAME
SEALED_ARTIFACTS = RUNTIME_ROOT / "artifacts"                       # sealed P2 archives
REGISTRY_DIR = RUNTIME_ROOT / "research" / "fp" / "records"         # runtime checkout's governed records
# One canary per watched filesystem (root fs and the WDC). A watch on a path under a mount point that
# is mounted after the rules load can attach to the wrong inode, so each filesystem proves itself.
CANARIES = (PAPER_ROOT / "writer-canary", WDC_ROOT / "tlos-writer-canary")


@dataclass(frozen=True)
class Writer:
    """A declared writer: comm glob(s), allowed uids (uid and euid), exe prefixes. All given parts must match."""
    name: str
    comms: tuple[str, ...]
    uids: tuple[str, ...] = (OWNER_UID,)
    exe_prefixes: tuple[str, ...] = SYSTEM_BIN

    def matches(self, comm: str | None, uid: str | None, exe: str | None, euid: str | None = None) -> bool:
        if not comm or uid is None:
            return False
        if not any(fnmatch.fnmatchcase(comm, c) for c in self.comms):
            return False
        if uid not in self.uids or (euid is not None and euid not in self.uids):
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
DEFAULT_INVENTORY: tuple[ProtectedClass, ...] = (
    ProtectedClass(
        "sealed", (str(SEALED_ARTIFACTS), str(SECOND_DEVICE_REPLICA)),
        (), "sealed P2 archives and their second-device copies: once sealed, nothing may write (a new governed "
            "archive is pre-announced and its events reviewed)"),
    ProtectedClass(
        "ledger", (str(LEDGER_DIR),),
        (Writer("kill_switch/recovery (python, owner)", PY),),
        "hash-chained operator ledger: appended only by scripts/p3/kill_switch.py and recovery.py authorize-resume"),
    ProtectedClass(
        "p3_evidence", (str(EVIDENCE_DIR),),
        (Writer("health job / control room / recovery snapshot (python, owner)", PY),
         Writer("scheduled_health.sh `mkdir -p` of the Control Room dir (owner)", ("mkdir",))),
        "P3 evidence: hourly health textfile, Control Room build, reboot snapshots and verify records"),
    ProtectedClass(
        "backups", (str(BACKUP_TARGET),),
        (Writer("backup.py and its helpers (owner)", (*PY, "tar", "zstd", "git", "sha256sum")),
         Writer("volume export helper container (tar as root)", ("tar",), uids=("0",))),
        "append-only backup sets written by scripts/p3/scheduled_backup.sh"),
    ProtectedClass(
        "registry", (str(REGISTRY_DIR),),
        (Writer("git (owner)", ("git",)),),
        "runtime checkout's governed records: change only through git at a merged commit"),
    ProtectedClass(
        "h1_lane", (str(H1_LANE),),
        (), "H1 lane: no lawful writer while H1_LAUNCH_AUTHORIZED = NO; the H1 grant PR adds the launcher/container "
            "writers here"),
    ProtectedClass(
        "canary", tuple(str(c) for c in CANARIES),
        (), "acceptance canaries (root fs and WDC): hold no evidence; any write is UNEXPECTED by design, so the "
            "Owner can prove the alert path without touching real evidence"),
)

# The hourly health job writes the textfile into EVIDENCE_DIR on every run. Over any window that
# contains a health run, no event on this key means the watch is blind, not that all is well.
HEARTBEAT_KEYS: tuple[str, ...] = (f"{KEY_PREFIX}p3_evidence",)


def expected_watches(inventory: tuple[ProtectedClass, ...] = DEFAULT_INVENTORY) -> set[tuple[str, str]]:
    return {(p.rstrip("/"), f"{KEY_PREFIX}{c.key}") for c in inventory for p in c.paths}


# --- (a) rules ---------------------------------------------------------------------------------------

def render_rules(inventory: tuple[ProtectedClass, ...] = DEFAULT_INVENTORY, *, backlog: int = 8192) -> str:
    """An auditd rules file (for /etc/audit/rules.d/tlos-evidence.rules). Watches writes and attribute changes.
    Immutable mode (-e 2) is an Owner decision and is never generated here."""
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
    euid: str | None = None
    auid: str | None = None
    pid: str | None = None
    success: str | None = None
    syscall: str | None = None
    paths: list[str] = field(default_factory=list)
    types: set[str] = field(default_factory=set)
    config_changes: list[dict] = field(default_factory=list)


_STRING_FIELDS = {"comm", "exe", "key", "name"}


def parse_audit_log(text: str) -> list[AuditEvent]:
    """Group raw audit records (SYSCALL, PATH, CONFIG_CHANGE, DAEMON_*, ...) by event id into events.
    Only the raw part before an ENRICHED log's 0x1d separator is read, so the interpreted upper-case
    fields (UID="hamza") never overwrite the numeric ones."""
    events: dict[str, AuditEvent] = {}
    for line in text.splitlines():
        line = line.split("\x1d", 1)[0]
        m = _MSG_RE.search(line)
        if not m:
            continue
        eid = f"{m.group(1)}:{m.group(2)}"
        ev = events.setdefault(eid, AuditEvent(eid, float(m.group(1))))
        rtype = line.split(" ", 1)[0].removeprefix("type=")
        ev.types.add(rtype)
        fields = {}
        for fm in _FIELD_RE.finditer(line[m.end():]):
            name, raw, quoted = fm.group(1), fm.group(2), fm.group(3)
            fields[name] = _value(raw, quoted) if name in _STRING_FIELDS else (quoted if quoted is not None else raw)
        if rtype == "SYSCALL":
            ev.key = fields.get("key") or None
            ev.comm = fields.get("comm") or None
            ev.exe = fields.get("exe") or None
            ev.uid = fields.get("uid")
            ev.euid = fields.get("euid")
            ev.auid = fields.get("auid")
            ev.pid = fields.get("pid")
            ev.success = fields.get("success")
            ev.syscall = fields.get("syscall")
        elif rtype == "PATH" and fields.get("name"):
            ev.paths.append(fields["name"])
        elif rtype == "CONFIG_CHANGE":
            ev.config_changes.append(fields)
    return sorted(events.values(), key=lambda e: (e.time, int(e.event_id.split(":")[1])))


def classify(events: list[AuditEvent], inventory: tuple[ProtectedClass, ...] = DEFAULT_INVENTORY) -> list[dict]:
    """Label every write event that carries one of our watch keys. Events without a tlos_ key are not ours.
    A failed attempt (success=no) is classified like a write: the attempt itself is the finding."""
    by_key = {f"{KEY_PREFIX}{c.key}": c for c in inventory}
    out = []
    for ev in events:
        if "SYSCALL" not in ev.types or not ev.key or not ev.key.startswith(KEY_PREFIX):
            continue
        cls = by_key.get(ev.key)
        base = {"event": ev.event_id, "key": ev.key, "comm": ev.comm, "exe": ev.exe, "uid": ev.uid,
                "euid": ev.euid, "auid": ev.auid, "pid": ev.pid, "success": ev.success, "paths": ev.paths[:4]}
        if cls is None:
            out.append({**base, "verdict": UNATTRIBUTED, "why": "watch key not in the inventory"})
        elif not ev.comm or ev.uid is None:
            out.append({**base, "verdict": UNATTRIBUTED, "why": "event lacks comm or uid"})
        elif any(w.matches(ev.comm, ev.uid, ev.exe, ev.euid) for w in cls.writers):
            out.append({**base, "verdict": AUTHORIZED, "why": f"declared writer of {cls.key}"})
        else:
            out.append({**base, "verdict": UNEXPECTED,
                        "why": f"no declared writer of {cls.key} matches comm={ev.comm!r} exe={ev.exe!r} "
                               f"uid={ev.uid} euid={ev.euid}"})
    return out


# --- (c) coverage: the watch itself stopped, was removed or was switched off -------------------------

GAP_RECORD_TYPES = ("DAEMON_END", "DAEMON_ABORT", "DAEMON_ERR")


def coverage_gaps(events: list[AuditEvent]) -> list[str]:
    """Things inside the window that mean writes may have gone unseen, even if the counters look clean."""
    gaps = []
    for ev in events:
        for rtype in GAP_RECORD_TYPES:
            if rtype in ev.types:
                gaps.append(f"{rtype} at {ev.event_id}")
        for cc in ev.config_changes:
            key = cc.get("key") or ""
            if cc.get("op") == "remove_rule" and key.startswith(KEY_PREFIX):
                gaps.append(f"watch {key} removed at {ev.event_id} by auid={cc.get('auid')}")
            if cc.get("audit_enabled") == "0":
                gaps.append(f"auditing disabled at {ev.event_id} by auid={cc.get('auid')}")
    return gaps


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


_KEY_IN_LINE = re.compile(r"(?:-k\s+|key=)(" + KEY_PREFIX + r"\w+)")
_PATH_IN_LINE = re.compile(r"(?:-w\s+|dir=|path=)(\S+)")


def loaded_watches(rules_listing: str) -> set[tuple[str, str]]:
    """``auditctl -l`` output -> {(path, key)} for every loaded tlos_ watch. Both the ``-w`` form and the
    ``-F dir=… -F key=…`` form are read; a trailing slash is ignored."""
    out = set()
    for line in rules_listing.splitlines():
        key, path = _KEY_IN_LINE.search(line), _PATH_IN_LINE.search(line)
        if key and path:
            out.add((path.group(1).rstrip("/") or "/", key.group(1)))
    return out


def missing_watches(rules_listing: str, inventory: tuple[ProtectedClass, ...] = DEFAULT_INVENTORY) -> list[str]:
    return sorted(f"{key}:{path}" for path, key in expected_watches(inventory) - loaded_watches(rules_listing))


# --- (d) one health finding, fail-closed --------------------------------------------------------------

def finding(classified: list[dict] | None, *, status: dict[str, int] | None, rules_listing: str | None,
            inventory: tuple[ProtectedClass, ...] = DEFAULT_INVENTORY, lost_baseline: int = 0,
            gaps: list[str] | None = None, heartbeat_keys: tuple[str, ...] = HEARTBEAT_KEYS) -> dict:
    """INFO only if everything is proven: every watch loaded, auditd enabled, no event lost since the
    baseline, the backlog not saturated, no coverage gap in the window, every watched event attributed
    to a declared writer, and each heartbeat class seen at least once."""
    def f(sev: str, detail: str) -> dict:
        return {"check": CHECK, "severity": sev, "detail": detail}

    unexpected = [c for c in (classified or []) if c["verdict"] == UNEXPECTED]
    if unexpected:
        first = unexpected[0]
        return f(CRITICAL, f"{len(unexpected)} unexpected write(s); first: key={first['key']} comm={first['comm']!r} "
                           f"exe={first.get('exe')!r} uid={first['uid']} auid={first.get('auid')} "
                           f"path={(first['paths'] or ['?'])[0]}")
    if rules_listing is None or status is None or classified is None:
        return f(WARNING, "UNPROVEN: audit data unavailable (auditd not installed, not readable, or not queried)")
    missing = missing_watches(rules_listing, inventory)
    if missing:
        return f(WARNING, f"UNPROVEN: watch rules not loaded for {', '.join(missing)}")
    if status.get("enabled", 0) < 1:
        return f(WARNING, "UNPROVEN: auditd is not enabled")
    lost = status.get("lost")
    if lost is None:
        return f(WARNING, "UNPROVEN: auditd lost counter unavailable")
    if lost > lost_baseline:
        return f(WARNING, f"UNPROVEN: auditd lost {lost - lost_baseline} event(s) since the baseline")
    if lost < lost_baseline:
        return f(WARNING, f"UNPROVEN: auditd lost counter {lost} is below the baseline {lost_baseline} "
                          "(reset since the baseline, e.g. a reboot); re-record the baseline")
    backlog, limit = status.get("backlog"), status.get("backlog_limit")
    if backlog is not None and limit and backlog >= limit:
        return f(WARNING, f"UNPROVEN: audit backlog saturated ({backlog}/{limit}); events may be dropped")
    if gaps:
        return f(WARNING, f"UNPROVEN: coverage gap in the window: {'; '.join(gaps[:3])}"
                          + (f" (+{len(gaps) - 3} more)" if len(gaps) > 3 else ""))
    unattributed = [c for c in classified if c["verdict"] == UNATTRIBUTED]
    if unattributed:
        return f(WARNING, f"UNPROVEN: {len(unattributed)} watched event(s) could not be attributed")
    seen = {c["key"] for c in classified}
    silent = [k for k in heartbeat_keys if k not in seen]
    if silent:
        return f(WARNING, f"UNPROVEN: no watched write seen on {', '.join(silent)} in the window; the hourly "
                          "health job writes there, so the watch may be blind")
    return f(INFO, f"{len(classified)} watched write(s), all by declared writers; "
                   f"{len(expected_watches(inventory))} watches loaded; no events lost")


def evaluate(log_text: str | None, status_text: str | None, rules_text: str | None, *, lost_baseline: int = 0,
             heartbeat_keys: tuple[str, ...] = HEARTBEAT_KEYS,
             inventory: tuple[ProtectedClass, ...] = DEFAULT_INVENTORY) -> tuple[dict, list[dict]]:
    """Text in, (finding, classified) out. A missing input is None and makes the result UNPROVEN at best."""
    events = parse_audit_log(log_text) if log_text is not None else None
    classified = classify(events, inventory) if events is not None else None
    result = finding(classified, status=parse_status(status_text) if status_text is not None else None,
                     rules_listing=rules_text, inventory=inventory, lost_baseline=lost_baseline,
                     gaps=coverage_gaps(events) if events is not None else None, heartbeat_keys=heartbeat_keys)
    return result, classified or []


def _read(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("rules", help="print the auditd rules file for the default inventory")
    chk = sub.add_parser("check-rules", help="compare saved `auditctl -l` output with the inventory; read-only")
    chk.add_argument("--rules", type=Path, required=True)
    cls = sub.add_parser("classify", help="classify a raw audit log; read-only")
    cls.add_argument("--log", type=Path, required=True)
    cls.add_argument("--status", type=Path, help="saved `auditctl -s` output")
    cls.add_argument("--rules", type=Path, help="saved `auditctl -l` output")
    cls.add_argument("--lost-baseline", type=int, default=0)
    args = parser.parse_args(argv)
    if args.command == "rules":
        sys.stdout.write(render_rules())
        return 0
    if args.command == "check-rules":
        text = _read(args.rules)
        if text is None:
            print(f"RULES = UNPROVEN (cannot read {args.rules})")
            return 1
        missing, total = missing_watches(text), len(expected_watches())
        if missing:
            print(f"RULES = INCOMPLETE ({total - len(missing)}/{total} watches); missing: {', '.join(missing)}")
            return 1
        print(f"RULES = LOADED ({total}/{total} watches)")
        return 0
    result, classified = evaluate(_read(args.log), _read(args.status), _read(args.rules),
                                  lost_baseline=args.lost_baseline)
    for c in classified:
        if c["verdict"] != AUTHORIZED:
            print(f"  {c['verdict']:12} {c['key']:18} comm={c['comm']!r} exe={c['exe']!r} uid={c['uid']} "
                  f"auid={c['auid']} path={(c['paths'] or ['?'])[0]} {c['why']}")
    for (key, verdict), n in sorted(Counter((c["key"], c["verdict"]) for c in classified).items()):
        print(f"  COUNT {key} {verdict} {n}")
    print(f"  {result['severity']:8} {result['check']} {result['detail']}")
    return {INFO: 0, WARNING: 1, CRITICAL: 2}[result["severity"]]


if __name__ == "__main__":
    raise SystemExit(main())
