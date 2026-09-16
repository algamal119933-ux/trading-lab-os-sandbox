#!/usr/bin/env python3
"""Watch a running cohort for the failures nothing else notices.

    scripts/fp_watch.py FP-CONTROL-2
    scripts/fp_watch.py FP-CONTROL-2 --json -o artifacts/watch.json

Container crashes and host reboots are already covered: every service declares
``restart: unless-stopped`` and the Docker daemon is enabled at boot. What is
not covered without this tool is the set of failures that leave everything
*looking* fine:

    a wedged loop        the process is alive, the container is up, and nothing
                         has advanced for hours
    a stopped stack      it went down and nobody restarted it; there is no crash
                         to notice and no alert to fire
    silent corruption    a chain broke between two reconciliation runs, and the
                         next one is tomorrow

All three present identically from outside — an evidence lane that is simply not
growing — and all three are only visible by comparing the lane against the clock.

This tool READS. It never writes into a lane, never repairs a chain, and never
restarts anything: a watchdog that fixes what it finds destroys the evidence
that it happened, which is the same reason reconciliation reports errata instead
of rewriting records. Its report goes outside the lane or to stdout.

Exit codes: 0 healthy; 2 a problem was found; 3 the lane could not be read at all.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from fp import archive as fp_archive  # noqa: E402
from fp import capture as fp_capture  # noqa: E402
from fp import lane as fp_lane  # noqa: E402
from fp import ledger as fp_ledger  # noqa: E402
from fp import market as fp_market  # noqa: E402
from fp import registry_law as fp_law  # noqa: E402

OK, STALLED, BROKEN, UNKNOWN = "OK", "STALLED", "BROKEN", "UNKNOWN"
WATCH_ENGINE_VERSION = "FP_WATCH_V1"

# How far behind the clock a lane may fall before it is stalled. Two candle
# periods, not one: a single period would fire on the ordinary race between a
# candle closing and the next poll picking it up, and an alarm that cries wolf
# every hour is an alarm that gets ignored on the day it matters.
STALL_CANDLE_PERIODS = 2


@dataclass
class Observation:
    name: str
    result: str
    detail: str

    def as_dict(self) -> dict:
        return {"observation": self.name, "result": self.result, "detail": self.detail}


def _parse_utc(text: str | None) -> datetime | None:
    if not text:
        return None
    for shape in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(text, shape).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def watch(role: str, *, now: datetime | None = None, registry: dict | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    registry = registry if registry is not None else fp_law.load_registry()
    observations: list[Observation] = []

    law = fp_law.check_registry(registry)
    observations.append(
        Observation("registry law", OK if not law else BROKEN,
                    "the registry's statuses, cohort ids, commits and fp_run_active agree"
                    if not law else "; ".join(law[:3]))
    )

    try:
        lane = fp_lane.resolve_lane(role, registry)
        row = fp_lane.select_row(role, registry)
    except fp_lane.LaneError as exc:
        observations.append(Observation("lane resolution", BROKEN, str(exc)))
        return _report(role, observations, {}, now)

    evidence_dir = lane.host_evidence_dir
    timeframe = (row.get("runtime_identity") or {}).get("timeframe") or "1h"
    timeframe_ms = fp_market.TIMEFRAME_MS.get(timeframe, 3_600_000)
    stall_seconds = STALL_CANDLE_PERIODS * timeframe_ms // 1000
    # A stall is only a fault for a row that claims to be running. A retained
    # qualification lane has stopped advancing because it finished, and
    # reporting that as a fault every day is how a real stall stops being
    # noticed. The age is still measured and still printed — the verdict is
    # what changes, not the observation.
    expected_live = row.get("status") == "RUNNING"

    if not evidence_dir.is_dir():
        observations.append(
            Observation("evidence lane", BROKEN,
                        f"{evidence_dir} does not exist; {role} is {row.get('status')} and nothing "
                        "is writing evidence")
        )
        return _report(role, observations, {"status": row.get("status")}, now)

    # -- is a writer actually holding the lane? ---------------------------
    # The advisory lock is the only cheap, honest answer to "is something alive
    # in there". A container that is up but wedged still holds it, which is why
    # the lock alone is never enough and the clock comparison below is.
    holding = fp_archive.lane_is_locked(evidence_dir)
    if row.get("status") == "RUNNING":
        observations.append(
            Observation("writer present", OK if holding else STALLED,
                        "a capture loop holds the lane lock" if holding else
                        f"no process holds {evidence_dir}/{fp_archive.LOCK_FILENAME}, but the "
                        f"registry says {role} is RUNNING. The stack is stopped and nothing "
                        "restarted it")
        )
    else:
        observations.append(
            Observation("writer present", OK,
                        f"{role} is {row.get('status')}; no writer is expected")
        )

    # -- chain integrity, between reconciliation runs ---------------------
    ledgers = fp_ledger.open_ledgers(evidence_dir)
    problems = [f"{kind}: {p}" for kind in sorted(ledgers) for p in ledgers[kind].verify()]
    observations.append(
        Observation("chain integrity", OK if not problems else BROKEN,
                    "all four hash chains verify from genesis" if not problems
                    else "; ".join(problems[:3]))
    )

    counts = {kind: len(ledgers[kind].records()) for kind in fp_ledger.LEDGER_KINDS}

    # -- has anything advanced? -------------------------------------------
    # Two independent clocks, because either alone can lie. The runtime snapshot
    # is written every cycle even when no candle closed, so it detects a wedged
    # loop; the last decision detects a loop that is cycling but no longer
    # deciding. A tool that watched only one of them would report health while
    # the other stood still.
    state_path = evidence_dir / fp_capture.STATE_FILENAME
    snapshot_utc = None
    if state_path.is_file():
        try:
            snapshot_utc = _parse_utc(
                json.loads(state_path.read_text(encoding="utf-8")).get("written_utc")
            )
        except (OSError, json.JSONDecodeError):
            snapshot_utc = None
    if snapshot_utc is None:
        observations.append(
            Observation("cycle heartbeat", UNKNOWN,
                        f"{state_path} is missing or carries no readable written_utc, so the loop's "
                        "own heartbeat cannot be read")
        )
    else:
        age = int((now - snapshot_utc).total_seconds())
        stalled = expected_live and age > stall_seconds
        observations.append(
            Observation("cycle heartbeat", STALLED if stalled else OK,
                        f"the loop last wrote its snapshot {age}s ago"
                        + (f", beyond {stall_seconds}s ({STALL_CANDLE_PERIODS} x {timeframe}). "
                           "The process may be alive and the container up while nothing advances"
                           if stalled else
                           f"; {role} is {row.get('status')}, so no advance is expected"
                           if not expected_live else ""))
        )

    decisions = [r for r in ledgers["decision"].records() if not r.payload.get("erratum")]
    if not decisions:
        observations.append(
            Observation("decision progress", STALLED if expected_live else UNKNOWN,
                        "the decision ledger is empty")
        )
    else:
        last_ts = max(r.payload.get("candle_ts") or 0 for r in decisions)
        age = int(now.timestamp() - (last_ts + timeframe_ms) / 1000)
        stalled = expected_live and age > stall_seconds
        observations.append(
            Observation("decision progress", STALLED if stalled else OK,
                        f"the newest decided bar closed {age}s ago "
                        f"({fp_market.iso_from_ms(last_ts + timeframe_ms)})"
                        + (f", beyond {stall_seconds}s. The loop is not deciding closed candles"
                           if stalled else
                           f"; {role} is {row.get('status')}, so no advance is expected"
                           if not expected_live else ""))
        )

    # -- gaps already recorded --------------------------------------------
    gap_incidents = [r for r in ledgers["incident"].records()
                     if r.payload.get("category") == "activation_gap"]
    if gap_incidents:
        observations.append(
            Observation("continuity gaps", OK,
                        f"{len(gap_incidents)} activation_gap incident(s) are recorded. These bars "
                        "are POST_T0 and WARMUP: contextual, counted, and never credited. They are "
                        "reported, not a fault of this watch")
        )

    return _report(role, observations, {
        "status": row.get("status"),
        "cohort_id": row.get("cohort_id"),
        "t0_utc": row.get("t0_utc"),
        "evidence_dir": str(evidence_dir),
        "counts": counts,
        "ledger_tips": {kind: ledgers[kind].tip_digest() for kind in sorted(ledgers)},
        "stall_threshold_seconds": stall_seconds,
    }, now)


def _report(role: str, observations: list[Observation], lane: dict, now: datetime) -> dict:
    results = [o.result for o in observations]
    if BROKEN in results:
        overall = BROKEN
    elif STALLED in results:
        overall = STALLED
    elif UNKNOWN in results:
        overall = UNKNOWN
    else:
        overall = OK
    return {
        "watch_engine_version": WATCH_ENGINE_VERSION,
        "observed_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "role": role,
        "lane": lane,
        "observations": [o.as_dict() for o in observations],
        "problems": [o.as_dict() for o in observations if o.result != OK],
        "watch": overall,
        "action_taken": "NONE — this tool reads; repairing a lane destroys the evidence of the fault",
        "real_money_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("role")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-o", "--out", default=None)
    args = parser.parse_args(argv)

    report = watch(args.role)
    text = json.dumps(report, indent=2) + "\n"

    if args.out:
        destination = Path(args.out).resolve()
        for declared in fp_lane.all_lane_roots():
            if destination == declared or declared in destination.parents:
                print(f"WATCH_REFUSED: {args.out} is inside the evidence lane {declared}; a report "
                      "about a lane is not written into it", file=sys.stderr)
                return 3
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")

    if args.json:
        sys.stdout.write(text)
    elif not args.out:
        print(f"FP WATCH — {report['role']} ({report['lane'].get('status')})")
        for item in report["observations"]:
            print(f"  [{item['result']:>8}] {item['observation']}")
            print(f"             {item['detail']}")
        print()
        print(f"WATCH = {report['watch']}")

    if report["watch"] == BROKEN:
        return 3
    return 0 if report["watch"] == OK else 2


if __name__ == "__main__":
    raise SystemExit(main())
