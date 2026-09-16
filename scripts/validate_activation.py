#!/usr/bin/env python3
"""Validate that a cohort actually activated, and say what its gap cost.

    scripts/validate_activation.py FP-CONTROL-2 --source-commit <M2>
    scripts/validate_activation.py FP-CONTROL-2 --json -o artifacts/activation.json

Contract section 7. The capture loop reads T0 **once**, at construction, so a
loop that was already running when T0 was frozen will never see it. That is how
the code behaves, not a preference, and it means the cohort requires a fresh
process start after the merge. This tool is what proves the start that happened
is that one.

THE ACTIVATION GAP. The registry has four statuses. A cohort whose T0 is frozen
but whose runtime has not started cannot be NOT_STARTED — the schema forbids a
T0 on it — and cannot be PAUSED, because a paused row is not executable. It must
be RUNNING. So an interval necessarily exists in which the registry says RUNNING
and nothing runs. It cannot be designed away; it can only be bounded, made
visible, and kept out of the credited evidence. The crediting law already
refuses those bars — they are POST_T0 and WARMUP, which is contextual — and this
tool counts them, names the candles they cover, and fails if the interval
exceeded one candle period, because beyond that at least one bar that should
have been watched live was not.

Exit codes: 0 activation valid; 2 not valid. UNPROVEN counts as invalid.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from fp import lane as fp_lane  # noqa: E402
from fp import ledger as fp_ledger  # noqa: E402
from fp import market as fp_market  # noqa: E402
from fp import preflight as fp_preflight  # noqa: E402
from fp import reconcile as fp_reconcile  # noqa: E402
from fp import registry_law as fp_law  # noqa: E402

PASS, FAIL, UNPROVEN = "PASS", "FAIL", "UNPROVEN"
ACTIVATION_ENGINE_VERSION = "FP_ACTIVATION_VALIDATION_V1"

# One candle period. Beyond it, at least one bar that should have been observed
# live closed while nothing was running, and the cohort's first credited bar is
# not its first prospective bar. The bound is the instant the gap becomes
# evidentially visible, which is the only non-arbitrary place to put it.
MAX_ACTIVATION_GAP_CANDLE_PERIODS = 1

# Contract section 7, the window law. The prospective active window is clocked
# from ACTIVATION_UTC — the instant this validator first proves a lawful
# POST_T0 + LIVE record — and not from T0_UTC. Counting from T0 would run the
# clock through the one interval whose records are explicitly not credited.
WINDOW_HARD_CAP_DAYS = 30


@dataclass
class Check:
    number: int
    name: str
    result: str
    detail: str

    def as_dict(self) -> dict:
        return {"check": self.number, "name": self.name, "result": self.result, "detail": self.detail}


def _live(records) -> list:
    return [r for r in records if not r.payload.get("erratum")]


def _identity(record) -> dict:
    return record.payload.get("identity") or {}


def validate(role: str, source_commit: str | None = None, registry: dict | None = None) -> dict:
    """The nine activation checks of contract section 7, plus the gap report."""
    checks: list[Check] = []
    registry = registry if registry is not None else fp_law.load_registry()

    law = fp_law.check_registry(registry)
    if law:
        return _report(role, [Check(0, "registry law", FAIL, "; ".join(law[:3]))], {}, {})

    try:
        lane = fp_lane.resolve_lane(role, registry)
        row = fp_lane.select_row(role, registry)
    except fp_lane.LaneError as exc:
        return _report(role, [Check(0, "lane resolution", FAIL, str(exc))], {}, {})

    t0_utc = row.get("t0_utc")
    cohort_id = row.get("cohort_id")
    declared_commit = (row.get("runtime_identity") or {}).get("source_commit")
    if row.get("status") != "RUNNING" or not t0_utc or not cohort_id:
        return _report(
            role,
            [Check(0, "cohort is frozen", FAIL,
                   f"{role} is {row.get('status')} with t0_utc={t0_utc!r} and cohort_id="
                   f"{cohort_id!r}; there is no activation to validate")],
            {}, {},
        )

    timeframe = (row.get("runtime_identity") or {}).get("timeframe") or "1h"
    timeframe_ms = fp_market.TIMEFRAME_MS.get(timeframe, 3_600_000)
    t0_ms = int(
        datetime.strptime(t0_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        * 1000
    )

    evidence_dir = lane.host_evidence_dir
    if not evidence_dir.is_dir():
        return _report(
            role,
            [Check(0, "evidence lane exists", FAIL,
                   f"{evidence_dir} does not exist; the cohort's runtime has written nothing")],
            {}, {},
        )
    ledgers = fp_ledger.open_ledgers(evidence_dir)
    all_live = [r for kind in fp_ledger.LEDGER_KINDS for r in _live(ledgers[kind].records())]
    decisions = _live(ledgers["decision"].records())
    incidents = ledgers["incident"].records()

    # -- 1. exactly one run_started, restart_counter 0 ---------------------
    starts = [r for r in incidents if r.payload.get("category") == "run_started"]
    counters = [(r.payload.get("full_identity") or {}).get("restart_counter") for r in starts]
    if len(starts) == 1 and counters == [0]:
        checks.append(Check(1, "single fresh run", PASS,
                            "exactly one run_started, restart_counter 0: this process is the "
                            "cohort's first, which is what a lane that never ran before requires"))
    else:
        checks.append(Check(1, "single fresh run", FAIL,
                            f"{len(starts)} run_started record(s) with restart counters {counters}; "
                            "activation is validated on the first start, and a lane that already "
                            "restarted was not fresh when T0 was frozen"))

    # -- 2. four chains verify from genesis, no erratum --------------------
    problems = [f"{kind}: {p}" for kind in sorted(ledgers) for p in ledgers[kind].verify()]
    errata = [r.seq for kind in fp_ledger.LEDGER_KINDS for r in ledgers[kind].records()
              if r.payload.get("erratum")]
    if problems or errata:
        checks.append(Check(2, "chains verify, no erratum", FAIL,
                            f"chain problems {problems[:3]}; errata at {errata[:3]}"))
    else:
        checks.append(Check(2, "chains verify, no erratum", PASS,
                            f"all four hash chains verify from genesis over {len(all_live)} "
                            "record(s), and no record has been corrected"))

    # -- 3. role, cohort id and a SINGLE source commit ---------------------
    expected_commit = source_commit or fp_reconcile.repository_head()
    roles = {_identity(r).get("role") for r in all_live}
    cohorts = {_identity(r).get("cohort_id") for r in all_live}
    commits = {_identity(r).get("source_commit") for r in all_live}
    problems3 = []
    if not all_live:
        problems3.append("the lane holds no record at all")
    if roles - {role}:
        problems3.append(f"records carry role(s) {sorted(str(x) for x in roles)}")
    if cohorts - {cohort_id}:
        problems3.append(f"records carry cohort id(s) {sorted(str(x) for x in cohorts)}, not {cohort_id}")
    if len(commits) != 1:
        problems3.append(f"records carry {len(commits)} distinct source commits: "
                         f"{sorted(str(x)[:8] for x in commits)}")
    elif expected_commit is None:
        problems3.append("this repository's HEAD could not be read, so the stamped commit is unchecked")
    elif commits != {expected_commit}:
        problems3.append(f"records were written from {sorted(str(x)[:8] for x in commits)}, "
                         f"not from {expected_commit[:8]}")
    if problems3:
        result3 = UNPROVEN if problems3 == ["this repository's HEAD could not be read, so the "
                                            "stamped commit is unchecked"] else FAIL
        checks.append(Check(3, "one identity throughout", result3, "; ".join(problems3)))
    else:
        checks.append(Check(3, "one identity throughout", PASS,
                            f"all {len(all_live)} records carry role {role}, cohort {cohort_id} and "
                            f"the single source commit {expected_commit[:8]}"))

    # -- 4. no record carries T0_NOT_FROZEN --------------------------------
    unfrozen = [r.seq for r in decisions if r.payload.get("t0_relation") == "T0_NOT_FROZEN"]
    if unfrozen:
        checks.append(Check(4, "lane was fresh", FAIL,
                            f"{len(unfrozen)} decision(s) read T0_NOT_FROZEN (seq {unfrozen[:5]}); "
                            "those were written before this T0 existed, so this is not a fresh lane"))
    else:
        checks.append(Check(4, "lane was fresh", PASS,
                            "no record reads T0_NOT_FROZEN: every record in this lane was written "
                            "after the boundary was frozen"))

    # -- 5. no record is both PRE_T0 and LIVE ------------------------------
    impossible = [r.seq for r in decisions
                  if r.payload.get("t0_relation") == "PRE_T0" and r.payload.get("bar_class") == "LIVE"]
    if impossible:
        checks.append(Check(5, "warm-up never executable", FAIL,
                            f"{len(impossible)} decision(s) are PRE_T0 and LIVE (seq {impossible[:5]}); "
                            "on a lane created after the freeze that combination cannot occur"))
    else:
        checks.append(Check(5, "warm-up never executable", PASS,
                            "no decision is both PRE_T0 and LIVE; warm-up was never executable"))

    # -- 6. the first credited decision is on the first boundary after T0 --
    first_close = ((t0_ms + timeframe_ms - 1) // timeframe_ms) * timeframe_ms
    expected_candle_ts = first_close - timeframe_ms
    credited = sorted(
        (r for r in decisions
         if r.payload.get("t0_relation") == "POST_T0" and r.payload.get("bar_class") == "LIVE"),
        key=lambda r: (r.payload.get("candle_ts") or 0),
    )
    if not credited:
        checks.append(Check(6, "first credited bar", FAIL,
                            f"no decision is POST_T0 and LIVE; the cohort has produced no credited "
                            f"evidence. The first {timeframe} boundary at or after {t0_utc} closes at "
                            f"{fp_market.iso_from_ms(first_close)}"))
    else:
        actual = credited[0].payload.get("candle_ts")
        if actual == expected_candle_ts:
            checks.append(Check(6, "first credited bar", PASS,
                                f"the first POST_T0 and LIVE decision is the bar closing at "
                                f"{fp_market.iso_from_ms(first_close)}, the first {timeframe} "
                                f"boundary at or after {t0_utc}"))
        else:
            checks.append(Check(6, "first credited bar", FAIL,
                                f"the first POST_T0 and LIVE decision is the bar opening at "
                                f"{fp_market.iso_from_ms(actual)}, not {fp_market.iso_from_ms(expected_candle_ts)}; "
                                "the bars between were not observed live"))

    # -- 7. reconciliation -------------------------------------------------
    reconciliation = fp_reconcile.reconcile(
        evidence_dir, expected_role=role, expected_source_commit=expected_commit
    )
    checks.append(Check(
        7, "reconciliation",
        PASS if reconciliation["reconciliation"] == fp_reconcile.PASS else FAIL,
        f"RECONCILIATION = {reconciliation['reconciliation']}"
        + (f"; failing {reconciliation['failing_checks']}" if reconciliation["failing_checks"] else ""),
    ))

    # -- 8. preflight, with check 5 now passing for the frozen cohort ------
    preflight = fp_preflight.run(
        runtime=fp_preflight.RuntimeContext(evidence_dir=evidence_dir, role=role)
    )
    passed = sum(1 for c in preflight["checks"] if c["result"] == PASS)
    checks.append(Check(
        8, "preflight", PASS if preflight["preflight"] == PASS else FAIL,
        f"PREFLIGHT = {preflight['preflight']} ({passed}/{len(preflight['checks'])})"
        + (f"; blocking {preflight['blocking_checks']}" if preflight["blocking_checks"] else ""),
    ))

    # -- the gap, measured before check 9 asks about its record ------------
    gap_decisions = [r for r in decisions
                     if r.payload.get("t0_relation") == "POST_T0"
                     and r.payload.get("bar_class") == "WARMUP"]
    first_start_utc = starts[0].payload.get("observed_utc") if starts else None
    elapsed_seconds = None
    if first_start_utc:
        try:
            started = datetime.strptime(first_start_utc[:19] + "Z", "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
            elapsed_seconds = int(started.timestamp() - t0_ms / 1000)
        except ValueError:
            elapsed_seconds = None
    gap = {
        "t0_utc": t0_utc,
        "first_run_started_utc": first_start_utc,
        "elapsed_seconds": elapsed_seconds,
        "max_elapsed_seconds": MAX_ACTIVATION_GAP_CANDLE_PERIODS * timeframe_ms // 1000,
        "post_t0_warmup_decisions": len(gap_decisions),
        "candles_covered": sorted(
            {
                f"{r.payload.get('pair')}@{fp_market.iso_from_ms(r.payload.get('candle_ts'))}"
                for r in gap_decisions
            }
        ),
        "disposition": (
            "CONTEXTUAL, NEVER CREDITED. A POST_T0 bar recovered by backfill rather than observed "
            "live is a continuity gap: it is counted and reported here, and the crediting law "
            "refuses it."
        ),
    }

    # -- 9. the gap is recorded where it happened, not only here -----------
    gap_incidents = [r for r in incidents if r.payload.get("category") == "activation_gap"]
    if gap_decisions and not gap_incidents:
        checks.append(Check(9, "activation gap recorded", FAIL,
                            f"{len(gap_decisions)} decision(s) are POST_T0 and WARMUP but the lane "
                            "holds no activation_gap incident; a gap visible only in a report "
                            "written afterwards is not recorded in the evidence"))
    elif len(gap_incidents) < len(gap_decisions):
        checks.append(Check(9, "activation gap recorded", FAIL,
                            f"{len(gap_decisions)} gap bar(s) but only {len(gap_incidents)} "
                            "activation_gap incident(s); each missed candle is its own fact"))
    elif gap_decisions:
        checks.append(Check(9, "activation gap recorded", PASS,
                            f"{len(gap_incidents)} activation_gap incident(s) name the "
                            f"{len(gap_decisions)} bar(s) that closed after T0 without being "
                            "observed live"))
    else:
        checks.append(Check(9, "activation gap recorded", PASS,
                            "no bar closed after T0 without being observed live, so there is no gap "
                            "to record; the absence of an incident is the correct evidence"))

    # The bound itself, reported as its own line rather than folded into a
    # check: exceeding it is a fact about the activation, not about a ledger.
    if elapsed_seconds is None:
        checks.append(Check(10, "activation within bound", UNPROVEN,
                            "the first run_started carries no readable timestamp, so the "
                            "freeze-to-start interval cannot be measured"))
    elif elapsed_seconds < 0:
        checks.append(Check(10, "activation within bound", PASS,
                            f"the runtime started {abs(elapsed_seconds)}s before T0, so no "
                            "post-T0 bar closed while nothing was running"))
    elif elapsed_seconds <= gap["max_elapsed_seconds"]:
        checks.append(Check(10, "activation within bound", PASS,
                            f"the runtime started {elapsed_seconds}s after T0, within one "
                            f"{timeframe} candle period ({gap['max_elapsed_seconds']}s)"))
    else:
        checks.append(Check(10, "activation within bound", FAIL,
                            f"the runtime started {elapsed_seconds}s after T0, beyond one "
                            f"{timeframe} candle period ({gap['max_elapsed_seconds']}s); at least "
                            "one bar that should have been observed live was not"))

    # -- the window clock --------------------------------------------------
    # ACTIVATION_UTC is a property of the EVIDENCE, not of when this tool ran:
    # it is the decision timestamp of the first lawful POST_T0 + LIVE record, so
    # re-running the validator a week later reports the same instant.
    activation_utc = None
    if credited:
        first = credited[0].payload
        activation_ms = first.get("decision_ts_ms")
        if not isinstance(activation_ms, int):
            activation_ms = (first.get("candle_ts") or 0) + timeframe_ms
        # Second precision, the same shape the registry uses for t0_utc. Two
        # timestamp shapes for the same kind of field in one report is how a
        # later comparison ends up working by string truncation.
        activation_utc = datetime.fromtimestamp(
            activation_ms / 1000, timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    window = {
        "t0_utc": t0_utc,
        "activation_utc": activation_utc,
        "window_starts_at": "ACTIVATION_UTC",
        "hard_cap_days": WINDOW_HARD_CAP_DAYS,
        "hard_cap_utc": None,
        "elapsed_days": None,
        "state": "NOT_ACTIVATED",
        "normal_end": (
            "the first naturally completed full paper trade lifecycle, AND all twelve "
            "capability properties satisfied, AND reconciliation, evidence and safety PASS"
        ),
        "at_hard_cap_close_as": "P2 INCONCLUSIVE / INSUFFICIENT",
        "automatic_extension": False,
        "forbidden_to_end_the_window": (
            "an artificial trade · a threshold change · a forced entry or exit · any strategy "
            "modification. A window that could be extended until it produced a trade would be a "
            "window that always produces one."
        ),
    }
    if activation_utc:
        activated = datetime.strptime(activation_utc[:19] + "Z", "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        cap = activated + timedelta(days=WINDOW_HARD_CAP_DAYS)
        now = datetime.now(timezone.utc)
        window["hard_cap_utc"] = cap.strftime("%Y-%m-%dT%H:%M:%SZ")
        window["elapsed_days"] = round((now - activated).total_seconds() / 86400, 3)
        window["state"] = "OPEN" if now < cap else "HARD_CAP_REACHED"

    return _report(role, checks, gap, {
        "cohort_id": cohort_id,
        "t0_utc": t0_utc,
        "declared_source_commit": declared_commit,
        "stamped_source_commit": sorted(str(c) for c in commits)[:1],
        "evidence_dir": str(evidence_dir),
        "counts": reconciliation["counts"],
        "ledger_tips": reconciliation["ledger_tips"],
        "daily_pack_digest": reconciliation["daily_pack_digest"],
    }, window=window)


def _report(role: str, checks: list[Check], gap: dict, cohort: dict,
            window: dict | None = None) -> dict:
    status = PASS if checks and all(c.result == PASS for c in checks) else FAIL
    return {
        "activation_engine_version": ACTIVATION_ENGINE_VERSION,
        "evaluated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "role": role,
        "cohort": cohort,
        "checks": [c.as_dict() for c in checks],
        "failing_checks": [c.number for c in checks if c.result != PASS],
        "activation_gap": gap,
        "window": window or {"state": "NOT_ACTIVATED", "window_starts_at": "ACTIVATION_UTC"},
        "activation": status,
        "prospective_paper_edge": "NOT_EVALUATED",
        "real_money_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("role")
    parser.add_argument("--source-commit", default=None,
                        help="M2, the commit the runtime ran at. Defaults to this repository's HEAD.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-o", "--out", default=None)
    args = parser.parse_args(argv)

    report = validate(args.role, args.source_commit)
    text = json.dumps(report, indent=2) + "\n"

    if args.out:
        destination = Path(args.out).resolve()
        for declared in fp_lane.all_lane_roots():
            if destination == declared or declared in destination.parents:
                print(f"ACTIVATION_REFUSED: {args.out} is inside the evidence lane {declared}",
                      file=sys.stderr)
                return 2
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")

    if args.json:
        sys.stdout.write(text)
    elif not args.out:
        print(f"ACTIVATION VALIDATION — {report['role']} {report['cohort'].get('cohort_id', '')}")
        for check in report["checks"]:
            print(f"  [{check['result']:>8}] {check['check']}. {check['name']}")
            print(f"             {check['detail']}")
        gap = report["activation_gap"]
        if gap:
            print()
            print(f"ACTIVATION GAP  T0 {gap['t0_utc']}  first start {gap['first_run_started_utc']}")
            print(f"  elapsed        {gap['elapsed_seconds']}s (bound {gap['max_elapsed_seconds']}s)")
            print(f"  gap bars       {gap['post_t0_warmup_decisions']} {gap['candles_covered'][:4]}")
            print(f"  {gap['disposition']}")
        window = report["window"]
        if window.get("activation_utc"):
            print()
            print(f"WINDOW          starts at ACTIVATION_UTC, not T0_UTC")
            print(f"  T0_UTC         {window['t0_utc']}")
            print(f"  ACTIVATION_UTC {window['activation_utc']}")
            print(f"  hard cap       {window['hard_cap_utc']} "
                  f"({window['hard_cap_days']} days, no automatic extension)")
            print(f"  elapsed        {window['elapsed_days']} days — {window['state']}")
            print(f"  at the cap     close as {window['at_hard_cap_close_as']}")
        print()
        print(f"ACTIVATION = {report['activation']}")
        print("PROSPECTIVE_PAPER_EDGE = NOT_EVALUATED")

    return 0 if report["activation"] == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
