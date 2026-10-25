"""P3-PLN-08 kill switch: one governed command stops every paper runtime and records who did it.

P3_CONTRACT.md §3 PLN-08. Acceptance: the kill switch stops everything within a bounded time and
leaves an attributable record. P2 observation O-1: a governed stop left no attributable record.

Scope is exactly the paper runtimes this project owns, matched by container name:
``tradinglab-fp-control-*`` (FP cohorts) and ``tlos-h1-paper-cohort-*`` (H1). Nothing else on the
host is touched. Unrelated workloads, monitoring stacks of other projects and the Docker daemon
itself are out of scope. The command uses ``docker stop`` only, never ``rm``, ``down -v`` or
anything that would delete a lane. Evidence stays exactly where it is.

Every invocation, including a dry run and a "nothing to stop" result, appends one record to a
hash-chained JSONL operator ledger. Each record carries the operator, reason, host, UTC time,
targets, their state before and after, and the elapsed time, plus ``prev_digest`` and ``digest``.
A record that does not chain is refused on read (``verify_ledger``).

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import fnmatch
import getpass
import hashlib
import json
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

PAPER_RUNTIME_PATTERNS = ("tradinglab-fp-control-*", "tlos-h1-paper-cohort-*")
GENESIS = "0" * 64
DEFAULT_TIMEOUT_S = 30

Runner = Callable[[list[str]], subprocess.CompletedProcess]


class KillSwitchError(Exception):
    pass


def _docker(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *cmd], capture_output=True, text=True, timeout=300)


def paper_containers(runner: Runner = _docker) -> dict[str, str]:
    """{name: state} for every container (any state) whose name is a paper runtime."""
    result = runner(["ps", "-a", "--format", "{{.Names}}\t{{.State}}"])
    if result.returncode != 0:
        raise KillSwitchError(f"docker ps failed: {result.stderr.strip()[:300]}")
    found = {}
    for line in result.stdout.splitlines():
        name, _, state = line.partition("\t")
        if any(fnmatch.fnmatchcase(name, p) for p in PAPER_RUNTIME_PATTERNS):
            found[name] = state
    return found


def _digest(record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "digest"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_ledger(path: Path) -> list[str]:
    problems, prev = [], GENESIS
    if not Path(path).exists():
        return problems
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines()):
        record = json.loads(line)
        if record.get("prev_digest") != prev:
            problems.append(f"record {n}: prev_digest does not chain")
        if record.get("digest") != _digest(record):
            problems.append(f"record {n}: digest does not match its body")
        prev = record.get("digest", "")
    return problems


def _append(ledger: Path, record: dict) -> dict:
    ledger = Path(ledger)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    problems = verify_ledger(ledger)
    if problems:
        raise KillSwitchError(f"operator ledger {ledger} does not verify: {problems[:3]}")
    lines = ledger.read_text(encoding="utf-8").splitlines() if ledger.exists() else []
    record["seq"] = len(lines)
    record["prev_digest"] = json.loads(lines[-1])["digest"] if lines else GENESIS
    record["digest"] = _digest(record)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def engage(*, reason: str, ledger: Path, operator: str | None = None, dry_run: bool = False,
           timeout_s: int = DEFAULT_TIMEOUT_S, runner: Runner = _docker,
           clock: Callable[[], float] = time.monotonic) -> dict:
    if not reason or not reason.strip():
        raise KillSwitchError("a reason is required; an unexplained stop is the O-1 defect this exists to prevent")
    started = clock()
    before = paper_containers(runner)
    running = sorted(n for n, s in before.items() if s in ("running", "restarting", "paused"))
    outcome, stop_error = "NOTHING_RUNNING", None
    if running and not dry_run:
        result = runner(["stop", "--time", str(timeout_s), *running])
        if result.returncode != 0:
            stop_error = result.stderr.strip()[:300]
    after = paper_containers(runner)
    still = sorted(n for n in running if after.get(n) in ("running", "restarting", "paused"))
    if dry_run:
        outcome = "DRY_RUN"
    elif running:
        outcome = "STOPPED" if not still and stop_error is None else "STOP_INCOMPLETE"
    record = {
        "record_type": "P3_KILL_SWITCH_V1",
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "operator": operator or getpass.getuser(),
        "host": socket.gethostname(),
        "reason": reason.strip(),
        "dry_run": dry_run,
        "patterns": list(PAPER_RUNTIME_PATTERNS),
        "targets": running,
        "state_before": before,
        "state_after": after,
        "still_running": still,
        "stop_error": stop_error,
        "elapsed_s": round(clock() - started, 3),
        "outcome": outcome,
        "real_money_authorized": False,
    }
    return _append(ledger, record)
