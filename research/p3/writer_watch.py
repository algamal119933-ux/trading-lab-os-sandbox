"""P3-PLN-06: §19 "unexpected writer" — auditd watch rules and a read-only classifier of their events.

Master plan §19 lists "unexpected writer" as CRITICAL. The health job (research/p3/health.py) cannot
see it: rehashing sealed archives catches a changed byte after the fact, but not who wrote, and not a
write to the ledger, the evidence directory or the backup sets. This module is the repository side of
the auditd-first design in docs/p3/PLN_06_UNEXPECTED_WRITER.md:

(a) ``render_rules`` turns the protected-path inventory into an auditd rules file
    (``-w <path> -p wa -k tlos_<class>``). It writes nothing; the Owner installs it.
(b) ``parse_audit_log`` groups raw ``/var/log/audit/audit.log`` (or ``ausearch --raw``) text into
    events (SYSCALL + CWD + PATH + PROCTITLE by serial), and ``classify`` labels each watched event
    AUTHORIZED, UNEXPECTED or UNATTRIBUTED against the declared writers of every class it touches: the
    class of its key and the class of every PATH name (resolved against CWD). A writer must match comm,
    exe (a system binary of the same program), uid, euid and the login uid (auid), all of them.
(c) ``coverage_gaps`` finds what the counters cannot: the daemon stopping, restarting, resuming or
    erroring inside the window, a ``tlos_`` watch removed, or auditing switched off.
(d) ``finding`` maps one run to one health finding, fail-closed:
    any UNEXPECTED -> CRITICAL; no audit data, a watch not loaded, auditd not connected, no lost
    baseline, lost events, a saturated backlog, a coverage gap, an UNATTRIBUTED event or a silent
    heartbeat class -> WARNING "UNPROVEN";
    INFO only when everything is proven.

The protected paths are not a new list: they are derived from the constants the health job and the
Control Room already use (``health.RUNTIME_ROOT``, ``health.OPERATOR_LEDGER``, ``health.H1_LANE``,
``control_room.EVIDENCE_DIR``) and the backup store, so a moved path moves here too. The store comes from
``p3.storage`` when that module exists (PR #98: configured once, no fallback): with no usable store the backup
and second-device paths are not watched, the rules are refused and the finding is UNPROVEN, so the watch never
guards a fallback path instead of the real store. Before #98 is merged the store is ``control_room.BACKUP_TARGET``,
exactly as on main. Either merge order of #90 and #98 is therefore correct without a follow-up patch.

Read-only. It installs nothing, starts nothing and is not yet part of the hourly health run.
Until the Owner installs auditd and the acceptance tests in the design document pass on the host,
"unexpected writer" stays NOT_COVERED on the host.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import fnmatch
import posixpath
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
# The login uid of a process started outside any login session (a container started by dockerd/containerd).
AUID_UNSET = "4294967295"
# Writers must run a root-owned system binary: a process that renames itself (comm) from a binary in
# a user-writable place does not pass as a declared writer.
SYSTEM_BIN = ("/usr/bin/", "/bin/", "/usr/local/bin/", "/usr/sbin/", "/sbin/")

# --- protected paths, derived from the existing repository constants ---------------------------------
RUNTIME_ROOT = health.RUNTIME_ROOT                                  # the runtime checkout
LEDGER_DIR = health.OPERATOR_LEDGER.parent                          # hash-chained operator ledger
PAPER_ROOT = LEDGER_DIR.parent                                      # ~/tlos-paper
H1_LANE = health.H1_LANE                                            # H1 lane (absent while not authorized)
EVIDENCE_DIR = control_room.EVIDENCE_DIR                            # P3 evidence (health textfile, records)
try:                                                                # PR #98: the configured backup store
    from p3 import storage  # noqa: E402
except ImportError:                                                 # main before #98: the Control Room's constant
    storage = None
STORE_ERROR: str | None = None
if storage is not None:
    try:
        _STORE = storage.load()
    except storage.StorageConfigError as _exc:
        _STORE, STORE_ERROR = None, str(_exc)
    BACKUP_TARGET = _STORE.target if _STORE else None               # append-only backup sets
    STORE_ROOT = Path(_STORE.backup_mount) if _STORE else None      # the store's mount point
else:
    BACKUP_TARGET = control_room.BACKUP_TARGET
    STORE_ROOT = BACKUP_TARGET.parent
SECOND_DEVICE_REPLICA = (STORE_ROOT / "trading-lab-os-evidence"     # scripts/replicate_to_second_device.REPLICA_ROOT_NAME
                         if STORE_ROOT else None)
SEALED_ARTIFACTS = RUNTIME_ROOT / "artifacts"                       # sealed P2 archives
REGISTRY_DIR = RUNTIME_ROOT / "research" / "fp" / "records"         # runtime checkout's governed records
# One canary per watched filesystem (root fs and the WDC). A watch on a path under a mount point that
# is mounted after the rules load can attach to the wrong inode, so each filesystem proves itself.
CANARIES = (PAPER_ROOT / "writer-canary",) + ((STORE_ROOT / "tlos-writer-canary",) if STORE_ROOT else ())


@dataclass(frozen=True)
class Writer:
    """A declared writer: one program (comm globs that its exe's file name must match too), allowed uids
    (uid and euid), allowed login uids (auid) and exe prefixes. Every part must match; a missing field never
    matches. The exe test ties the comm to the binary: a system binary that renames itself (prctl) to an
    allowed comm is not that program."""
    name: str
    comms: tuple[str, ...]
    uids: tuple[str, ...] = (OWNER_UID,)
    exe_prefixes: tuple[str, ...] = SYSTEM_BIN
    auids: tuple[str, ...] = (OWNER_UID,)

    def matches(self, comm: str | None, uid: str | None, exe: str | None, euid: str | None,
                auid: str | None) -> bool:
        if not comm or not uid or not euid or not auid or not exe:
            return False
        if not any(fnmatch.fnmatchcase(comm, c) for c in self.comms):
            return False
        if uid not in self.uids or euid not in self.uids or auid not in self.auids:
            return False
        if self.exe_prefixes and not any(exe.startswith(p) for p in self.exe_prefixes):
            return False
        return any(fnmatch.fnmatchcase(exe.rsplit("/", 1)[-1], c) for c in self.comms)


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
        "sealed", (str(SEALED_ARTIFACTS),) + ((str(SECOND_DEVICE_REPLICA),) if SECOND_DEVICE_REPLICA else ()),
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
        "backups", (str(BACKUP_TARGET),) if BACKUP_TARGET else (),
        (Writer("backup.py (python, owner)", PY),
         *(Writer(f"backup.py helper {prog} (owner)", (prog,)) for prog in ("tar", "zstd", "git", "sha256sum")),
         Writer("volume export helper container (tar as root, no login session)", ("tar",), uids=("0",),
                auids=(AUID_UNSET,))),
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
    The kernel records only the key of the FIRST rule an event matches, so the classes with no lawful writer
    come first: an event that reaches one of them (e.g. through a symlinked name the classifier cannot
    resolve) carries its key. Immutable mode (-e 2) is an Owner decision and is never generated here."""
    lines = [
        "# Trading Lab OS P3-PLN-06 — §19 'unexpected writer' watches (generated by research/p3/writer_watch.py).",
        "# Installed only by the Owner (docs/p3/PLN_06_UNEXPECTED_WRITER.md). Read-only for the system it watches.",
        f"-b {backlog}",
        "--backlog_wait_time 60000",
        "-f 1",
    ]
    for cls in sorted(inventory, key=lambda c: bool(c.writers)):  # stable: no-writer classes first
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
    # auditd writes an untrusted string (comm/exe/name/key/cwd) quoted, or hex-encoded when it holds a space,
    # a quote or a control byte (a multi-key field holds \x01). An unquoted hex value is always decoded, so
    # a name with a newline or a key list is read as what it is, never skipped as an opaque token.
    if _HEX_RE.match(raw) and len(raw) % 2 == 0 and len(raw) >= 2:
        return bytes.fromhex(raw).decode("utf-8", errors="backslashreplace")
    return raw


@dataclass
class AuditEvent:
    event_id: str
    time: float
    key: str | None = None             # the first tlos_ key, else the first key
    keys: list[str] = field(default_factory=list)
    comm: str | None = None
    exe: str | None = None
    uid: str | None = None
    euid: str | None = None
    auid: str | None = None
    pid: str | None = None
    success: str | None = None
    syscall: str | None = None
    cwd: str | None = None
    paths: list[str] = field(default_factory=list)                         # PATH names, by item number
    path_items: list[tuple[str, str]] = field(default_factory=list)       # (name, nametype), by item number
    types: set[str] = field(default_factory=set)
    config_changes: list[dict] = field(default_factory=list)


_STRING_FIELDS = {"comm", "exe", "key", "name", "cwd"}


def parse_audit_log(text: str) -> list[AuditEvent]:
    """Group raw audit records (SYSCALL, PATH, CONFIG_CHANGE, DAEMON_*, ...) by event id into events.
    Only the raw part before an ENRICHED log's 0x1d separator is read, so the interpreted upper-case
    fields (UID="hamza") never overwrite the numeric ones."""
    events: dict[str, AuditEvent] = {}
    items: dict[str, dict[int, tuple[str, str]]] = {}
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
            ev.keys = [k for k in (fields.get("key") or "").split("\x01") if k]
            ev.key = next((k for k in ev.keys if k.startswith(KEY_PREFIX)), ev.keys[0] if ev.keys else None)
            ev.comm = fields.get("comm") or None
            ev.exe = fields.get("exe") or None
            ev.uid = fields.get("uid")
            ev.euid = fields.get("euid")
            ev.auid = fields.get("auid")
            ev.pid = fields.get("pid")
            ev.success = fields.get("success")
            ev.syscall = fields.get("syscall")
        elif rtype == "CWD":
            ev.cwd = fields.get("cwd") or None
        elif rtype == "PATH" and fields.get("name"):
            # one entry per item number: a record duplicated by overlapping input is not a second name
            per = items.setdefault(eid, {})
            item = int(fields["item"]) if fields.get("item", "").isdigit() else len(per)
            per[item] = (fields["name"], fields.get("nametype", ""))
        elif rtype == "CONFIG_CHANGE":
            ev.config_changes.append(fields)
    for eid, per in items.items():
        events[eid].path_items = [per[i] for i in sorted(per)]
        events[eid].paths = [name for name, _ in events[eid].path_items]
    return sorted(events.values(), key=lambda e: (e.time, int(e.event_id.split(":")[1])))


MODIFY_NAMETYPES = ("CREATE", "DELETE")


def _resolve(name: str, cwd: str | None) -> str | None:
    """A PATH name as an absolute, lexically normalised path ('..' folded); None if it cannot be resolved.
    Names are lexical: a symlinked name resolves to where it points only in the kernel's inode match
    (the key), never here."""
    if name.startswith("/"):
        return posixpath.normpath(name)
    if cwd and cwd.startswith("/"):
        return posixpath.normpath(posixpath.join(cwd, name))
    return None


def _under(path: str, root: str) -> bool:
    root = root.rstrip("/") or "/"
    return path == root or path.startswith(root + "/")


def classify(events: list[AuditEvent], inventory: tuple[ProtectedClass, ...] = DEFAULT_INVENTORY) -> list[dict]:
    """Label every write event that touches a protected class, through its key or through its PATH names.

    - The classes of an event are the class of each ``tlos_`` key plus the class of every PATH name under a
      protected path (resolved against CWD; ``..`` folded). The kernel records only the first matching
      rule's key, so a rename or link across two trees is judged against both, never by rule order.
    - An event with no ``tlos_`` key is ours only if a PATH record CREATEs or DELETEs a name under a
      protected path (another rule took the key first); a read audited by some other rule is not.
    - A class with no lawful writer (sealed, H1 lane, canary) makes the event UNEXPECTED even when it cannot
      be attributed. Otherwise a missing comm/uid/euid/auid (or no SYSCALL record) is UNATTRIBUTED.
    - A link or a move under a ``tlos_`` key that creates a name outside every protected tree is UNEXPECTED:
      writes through that name would carry no key.
    - Otherwise the event is AUTHORIZED only if, for EVERY class it touches, a declared writer matches.
    A failed attempt (success=no) is classified like a write: the attempt itself is the finding."""
    by_key = {f"{KEY_PREFIX}{c.key}": c for c in inventory}
    by_name = {c.key: c for c in inventory}
    protected = [(c.key, p) for c in inventory for p in c.paths]
    out = []
    for ev in events:
        tlos_keys = [k for k in ev.keys if k.startswith(KEY_PREFIX)]
        resolved = [(_resolve(name, ev.cwd), nametype) for name, nametype in ev.path_items]
        considered = resolved if tlos_keys else [(p, nt) for p, nt in resolved if nt in MODIFY_NAMETYPES]
        classes: list[str] = []
        for name in [by_key[k].key for k in tlos_keys if k in by_key] + \
                [c for p, _ in considered if p for c, root in protected if _under(p, root)]:
            if name not in classes:
                classes.append(name)
        if not tlos_keys and not classes:
            continue
        who = f"comm={ev.comm!r} exe={ev.exe!r} uid={ev.uid} euid={ev.euid} auid={ev.auid}"
        base = {"event": ev.event_id, "key": ev.key or "(none)", "classes": classes, "comm": ev.comm, "exe": ev.exe,
                "uid": ev.uid, "euid": ev.euid, "auid": ev.auid, "pid": ev.pid, "success": ev.success,
                "paths": [p or n for (p, _), n in zip(resolved, ev.paths)][:4]}

        def verdict(v: str, why: str) -> None:
            out.append({**base, "verdict": v, "why": why})

        no_writer = [c for c in classes if not by_name[c].writers]
        unknown = [k for k in tlos_keys if k not in by_key]
        missing = ["SYSCALL record"] if "SYSCALL" not in ev.types else \
            [f for f in ("comm", "uid", "euid", "auid") if not getattr(ev, f)]
        is_link_or_move = any(nt == "CREATE" for _, nt in resolved) and \
            any(nt in ("DELETE", "NORMAL") for _, nt in resolved)
        created = [p for p, nt in resolved if nt == "CREATE"]
        if no_writer:
            verdict(UNEXPECTED, f"{no_writer[0]} has no lawful writer; {who}")
        elif unknown:
            verdict(UNATTRIBUTED, f"watch key {unknown[0]} not in the inventory")
        elif missing:
            verdict(UNATTRIBUTED, f"event lacks {', '.join(missing)}")
        elif tlos_keys and is_link_or_move and None in created:
            verdict(UNATTRIBUTED, "a link or move whose new name cannot be resolved (no CWD record)")
        elif tlos_keys and is_link_or_move and any(not any(_under(p, r) for _, r in protected) for p in created):
            outside = next(p for p in created if not any(_under(p, r) for _, r in protected))
            verdict(UNEXPECTED, f"a link or move places watched content outside the protected trees ({outside}); "
                                f"{who}")
        else:
            denied = [c for c in classes
                      if not any(w.matches(ev.comm, ev.uid, ev.exe, ev.euid, ev.auid) for w in by_name[c].writers)]
            if denied:
                verdict(UNEXPECTED, f"no declared writer of {denied[0]} matches {who}")
            else:
                verdict(AUTHORIZED, f"declared writer of {', '.join(classes)}")
    return out


# --- (c) coverage: the watch itself stopped, was removed or was switched off -------------------------

# DAEMON_START / DAEMON_RESUME inside the window mean the daemon was not writing just before them (a kill -9
# leaves no DAEMON_END; a disk-full suspend ends with DAEMON_RESUME). DAEMON_ROTATE is not a gap.
GAP_RECORD_TYPES = ("DAEMON_END", "DAEMON_ABORT", "DAEMON_ERR", "DAEMON_START", "DAEMON_RESUME")


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
            inventory: tuple[ProtectedClass, ...] = DEFAULT_INVENTORY, lost_baseline: int | None = None,
            gaps: list[str] | None = None, heartbeat_keys: tuple[str, ...] = HEARTBEAT_KEYS,
            store_error: str | None = STORE_ERROR) -> dict:
    """INFO only if everything is proven: every watch loaded, auditd enabled and connected, a lost baseline
    recorded and no event lost since it, the backlog not saturated, no coverage gap in the window, every watched event attributed
    to a declared writer, and each heartbeat class seen at least once."""
    def f(sev: str, detail: str) -> dict:
        return {"check": CHECK, "severity": sev, "detail": detail}

    unexpected = [c for c in (classified or []) if c["verdict"] == UNEXPECTED]
    if unexpected:
        first = unexpected[0]
        return f(CRITICAL, f"{len(unexpected)} unexpected write(s); first: key={first['key']} comm={first['comm']!r} "
                           f"exe={first.get('exe')!r} uid={first['uid']} auid={first.get('auid')} "
                           f"path={(first['paths'] or ['?'])[0]}")
    if store_error is not None:
        return f(WARNING, f"UNPROVEN: backup store not configured, so the backup and second-device paths are not "
                          f"watched ({store_error[:120]})")
    if rules_listing is None or status is None or classified is None:
        return f(WARNING, "UNPROVEN: audit data unavailable (auditd not installed, not readable, or not queried)")
    missing = missing_watches(rules_listing, inventory)
    if missing:
        return f(WARNING, f"UNPROVEN: watch rules not loaded for {', '.join(missing)}")
    if status.get("enabled", 0) < 1:
        return f(WARNING, "UNPROVEN: auditd is not enabled")
    if not status.get("pid"):
        return f(WARNING, "UNPROVEN: auditd is not connected to the kernel (pid 0 or absent); records go to the "
                          "kernel log, not audit.log")
    lost = status.get("lost")
    if lost is None:
        return f(WARNING, "UNPROVEN: auditd lost counter unavailable")
    if lost_baseline is None:
        return f(WARNING, "UNPROVEN: no lost baseline recorded (auditctl -s at install or after each reboot)")
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


def evaluate(log_text: str | None, status_text: str | None, rules_text: str | None, *,
             lost_baseline: int | None = None,
             heartbeat_keys: tuple[str, ...] = HEARTBEAT_KEYS,
             inventory: tuple[ProtectedClass, ...] = DEFAULT_INVENTORY) -> tuple[dict, list[dict]]:
    """Text in, (finding, classified) out. A missing input is None and makes the result UNPROVEN at best."""
    events = parse_audit_log(log_text) if log_text is not None else None
    classified = classify(events, inventory) if events is not None else None
    result = finding(classified, status=parse_status(status_text) if status_text is not None else None,
                     rules_listing=rules_text, inventory=inventory, lost_baseline=lost_baseline,
                     gaps=coverage_gaps(events) if events is not None else None, heartbeat_keys=heartbeat_keys)
    return result, classified or []


SELFTEST_FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "p3_writer_watch_selftest.audit"
_EXPECT_RE = re.compile(r"^# EXPECT (\S+) (AUTHORIZED|UNEXPECTED|UNATTRIBUTED|IGNORED) (.*)$")


def self_test(fixture: Path = SELFTEST_FIXTURE) -> int:
    """Read-only acceptance pre-check (AT-0): classify the synthetic fixture shipped with the repository and
    compare every event with its ``# EXPECT <event> <verdict> <case>`` line. IGNORED = not ours. PASS only if
    every expectation holds, no unexpected event is classified, and all three verdicts occur."""
    text = _read(fixture)
    if text is None:
        print(f"SELFTEST = UNPROVEN (cannot read {fixture})")
        return 1
    expect = {m.group(1): (m.group(2), m.group(3)) for m in map(_EXPECT_RE.match, text.splitlines()) if m}
    got = {c["event"]: c for c in classify(parse_audit_log(text))}
    failures = 0
    for eid, (want, case) in expect.items():
        have = got.get(eid, {}).get("verdict", "IGNORED")
        ok = have == want
        failures += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {eid:24} {want:12} {case}" + ("" if ok else f" (got {have})"))
    stray = sorted(set(got) - set(expect))
    for eid in stray:
        print(f"  FAIL {eid:24} {got[eid]['verdict']:12} classified but has no EXPECT line")
    covered = {v for v, _ in expect.values()} >= {AUTHORIZED, UNEXPECTED, UNATTRIBUTED}
    if not expect or not covered:
        print("  FAIL fixture does not exercise AUTHORIZED, UNEXPECTED and UNATTRIBUTED")
    passed = failures == 0 and not stray and covered and bool(expect)
    print(f"SELFTEST = {'PASS' if passed else 'FAIL'} ({len(expect) - failures}/{len(expect)} expectations)")
    return 0 if passed else 1


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
    cls.add_argument("--lost-baseline", help="the recorded `lost` counter; missing or not an integer = UNPROVEN")
    st = sub.add_parser("self-test", help="classify the shipped synthetic audit fixture and compare it with its "
                                          "# EXPECT lines; reads nothing from the host")
    st.add_argument("--fixture", type=Path, default=SELFTEST_FIXTURE)
    args = parser.parse_args(argv)
    if args.command == "rules":
        if STORE_ERROR is not None:
            print(f"RULES_REFUSED: backup store not configured ({STORE_ERROR})", file=sys.stderr)
            return 3
        sys.stdout.write(render_rules())
        return 0
    if args.command == "self-test":
        return self_test(args.fixture)
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
    baseline = args.lost_baseline.strip() if args.lost_baseline is not None else ""
    result, classified = evaluate(_read(args.log), _read(args.status), _read(args.rules),
                                  lost_baseline=int(baseline) if re.fullmatch(r"\d+", baseline) else None)
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
