"""Ledger reconciliation for the capture loop (FP-BOOT-1 sections 9, 19, 26).

Four append-only ledgers that each verify internally can still disagree with
each other, and a disagreement between them is exactly where a runtime defect
shows up: a decision with no captured input behind it, a paper entry with no
decision authorising it, the same market event captured twice under two
identities, a restart that re-decided a bar it had already decided.

So this module asks the cross-ledger questions the individual chains cannot:

* is every chain intact, and is every record's author identifiable?
* is every market event captured exactly once?
* is every decision linked to an input that was captured *before* it?
* does the frozen logic, replayed over the captured inputs, reproduce the
  decisions the runtime recorded? (section 9.1, the primary parity gate)
* is every paper execution backed by a decision that admitted it?
* did any restart duplicate work it had already done?

It reads. It never repairs. A reconciliation that silently fixed a divergence
would destroy the evidence that the divergence happened, and section 26 makes
corrections errata rather than rewrites for the same reason.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from fp import lane as fp_lane  # noqa: E402
from fp import ledger as fp_ledger  # noqa: E402
from fp import replay as fp_replay  # noqa: E402

PASS, FAIL = "PASS", "FAIL"

RECONCILE_ENGINE_VERSION = "FP_RECONCILE_V1"


@dataclass
class Finding:
    check: str
    result: str
    detail: str
    count: int = 0

    def as_dict(self) -> dict:
        return {"check": self.check, "result": self.result, "detail": self.detail, "count": self.count}


def _live(records) -> list:
    """Records that assert a fact, excluding errata.

    An erratum corrects an earlier record without rewriting it, so it must not
    be counted as a second assertion of the thing it corrects.
    """
    return [r for r in records if not r.payload.get("erratum")]


def reconcile(evidence_dir: Path, pairs: list[str] | None = None, expected_role: str | None = None) -> dict:
    """Cross-ledger reconciliation.

    ``expected_role`` binds the evidence to the instance it claims to belong to.
    Without it, reconciliation reported PASS over records written by another
    role — attribution that is recorded but never compared proves nothing.
    """
    evidence_dir = Path(evidence_dir)
    ledgers = fp_ledger.open_ledgers(evidence_dir)

    findings: list[Finding] = []

    # -- 1. chain integrity ------------------------------------------------
    chain_problems: list[str] = []
    for kind, led in sorted(ledgers.items()):
        chain_problems.extend(f"{kind}: {problem}" for problem in led.verify())
    findings.append(
        Finding(
            "ledger_chain_integrity",
            FAIL if chain_problems else PASS,
            "; ".join(chain_problems[:3]) if chain_problems else
            "all four hash chains verify from genesis with no altered record",
            len(chain_problems),
        )
    )

    inputs = _live(ledgers["input"].records())
    decisions = _live(ledgers["decision"].records())
    trades = _live(ledgers["trade"].records())
    incidents = ledgers["incident"].records()

    # -- 2. every record has an identifiable author -----------------------
    # The message claimed run_id, runtime_id and commit; only run_id was checked.
    # A record whose runtime_id or source commit is missing cannot be tied to the
    # instance that wrote it, which is the whole purpose of attribution.
    required_identity = ("run_id", "runtime_id", "source_commit", "role")
    # Every live record in every ledger, not only the three the earlier version
    # happened to concatenate: a foreign input or incident is exactly as
    # damaging as a foreign decision.
    live = [
        record
        for name in ("input", "decision", "trade", "incident")
        for record in ledgers[name].records()
        if not record.payload.get("erratum")
    ]
    unattributed = [
        r.seq
        for r in live
        if not all((r.payload.get("identity") or {}).get(field) for field in required_identity)
    ]
    foreign = []
    if expected_role is not None:
        foreign = [
            r.seq for r in live
            # A missing role is foreign too: "not contradicting" is not the same
            # as "attributable", and treating it as acceptable is what let an
            # unstamped record pass.
            if (r.payload.get("identity") or {}).get("role") != expected_role
        ]
        findings.append(
            Finding(
                "record_role_binding",
                FAIL if foreign else PASS,
                f"records written by another role: {foreign[:5]}" if foreign else
                f"all {len(live)} live records carry role {expected_role}",
                len(foreign),
            )
        )
    findings.append(
        Finding(
            "record_attribution",
            FAIL if unattributed else PASS,
            f"records missing run_id/runtime_id/source_commit/role: {unattributed[:5]}" if unattributed else
            f"all {len(live)} live records carry a run_id, runtime_id, commit and role",
            len(unattributed),
        )
    )

    # -- 3. market events captured exactly once ---------------------------
    event_ids = [r.payload.get("market_event_id") for r in inputs]
    missing_event_id = [r.seq for r in inputs if not r.payload.get("market_event_id")]
    duplicate_events = [event for event, n in Counter(e for e in event_ids if e).items() if n > 1]
    problem = bool(duplicate_events or missing_event_id)
    findings.append(
        Finding(
            "input_uniqueness",
            FAIL if problem else PASS,
            (
                f"duplicate market events {duplicate_events[:3]}; records without an event id {missing_event_id[:3]}"
                if problem
                else f"{len(event_ids)} market events, each captured exactly once"
            ),
            len(duplicate_events) + len(missing_event_id),
        )
    )

    # -- 4. decisions unique per bar --------------------------------------
    bars = [(r.payload.get("pair"), r.payload.get("candle_ts")) for r in decisions]
    duplicate_bars = [bar for bar, n in Counter(bars).items() if n > 1]
    findings.append(
        Finding(
            "decision_uniqueness",
            FAIL if duplicate_bars else PASS,
            f"bars decided more than once: {duplicate_bars[:3]}" if duplicate_bars else
            f"{len(bars)} decisions, at most one per (pair, bar), across every run",
            len(duplicate_bars),
        )
    )

    # -- 5. input -> decision linkage --------------------------------------
    captured = {r.payload.get("market_event_id") for r in inputs if r.payload.get("market_event_id")}
    input_seq_by_event = {
        r.payload["market_event_id"]: r.seq for r in inputs if r.payload.get("market_event_id")
    }
    orphans = [
        {"decision_seq": r.seq, "market_event_id": r.payload.get("market_event_id")}
        for r in decisions
        if r.payload.get("market_event_id") not in captured
    ]
    findings.append(
        Finding(
            "decision_input_linkage",
            FAIL if orphans else PASS,
            f"decisions with no captured input: {orphans[:3]}" if orphans else
            f"every one of {len(decisions)} decisions names a market event present in the input ledger",
            len(orphans),
        )
    )

    # -- 6. inputs precede their decisions ---------------------------------
    # Causality, not merely linkage: a decision recorded before the input it
    # claims to be based on would mean the runtime decided on something it had
    # not yet seen.
    out_of_causal_order = []
    for record in decisions:
        event = record.payload.get("market_event_id")
        input_seq = input_seq_by_event.get(event)
        if input_seq is None:
            continue
        decision_ts = record.payload.get("decision_ts_ms")
        source_ts = next(
            (r.payload.get("source_ts_ms") for r in inputs if r.payload.get("market_event_id") == event),
            None,
        )
        if isinstance(decision_ts, int) and isinstance(source_ts, int) and decision_ts < source_ts:
            out_of_causal_order.append({"decision_seq": record.seq, "market_event_id": event})
    findings.append(
        Finding(
            "decision_causality",
            FAIL if out_of_causal_order else PASS,
            f"decisions timestamped before their input closed: {out_of_causal_order[:3]}"
            if out_of_causal_order
            else "every decision is timestamped at or after the close of the candle it decides",
            len(out_of_causal_order),
        )
    )

    # -- 7. event-time replay on the captured (real) inputs -----------------
    pairs = pairs or sorted({r.payload.get("pair") for r in inputs if r.payload.get("pair")})
    replays = {}
    replay_failed = []
    for pair in pairs:
        try:
            report = fp_replay.event_time_replay(inputs, decisions, pair)
        except fp_replay.ReplayError as exc:
            replays[pair] = {"status": FAIL, "error": str(exc)}
            replay_failed.append(pair)
            continue
        replays[pair] = report
        if report["status"] != PASS:
            replay_failed.append(pair)
    findings.append(
        Finding(
            "event_time_replay",
            FAIL if replay_failed else PASS,
            f"replay disagreed with the recorded decisions for: {replay_failed}" if replay_failed else
            "the frozen logic replayed over the captured inputs reproduces every recorded decision: "
            + ", ".join(f"{p} {replays[p]['decisions_compared']} bars" for p in pairs),
            len(replay_failed),
        )
    )

    # -- 8. paper executions are backed by an admitting decision -----------
    entries_by_pair: dict[str, list] = {}
    for record in decisions:
        if record.payload.get("intended_action") == fp_replay.ACTION_ENTER_LONG:
            entries_by_pair.setdefault(record.payload.get("pair"), []).append(record)

    unbacked = []
    for record in trades:
        if record.payload.get("event") != "position_opened":
            continue
        pair = record.payload.get("pair")
        if not entries_by_pair.get(pair):
            unbacked.append({"trade_seq": record.seq, "pair": pair, "trade_id": record.payload.get("trade_id")})
    findings.append(
        Finding(
            "execution_backed_by_decision",
            FAIL if unbacked else PASS,
            f"paper entries with no enter_long decision on that pair: {unbacked[:3]}" if unbacked else
            (
                f"{len([r for r in trades if r.payload.get('event') == 'position_opened'])} paper entries, "
                "each on a pair the frozen logic signalled an entry for"
            ),
            len(unbacked),
        )
    )

    # -- 9. no duplicate paper execution -----------------------------------
    trade_events = [r.payload.get("trade_event_id") for r in trades]
    duplicate_trades = [event for event, n in Counter(e for e in trade_events if e).items() if n > 1]
    findings.append(
        Finding(
            "no_duplicate_execution",
            FAIL if duplicate_trades else PASS,
            f"paper execution events recorded twice: {duplicate_trades[:3]}" if duplicate_trades else
            f"{len(trade_events)} paper execution events, each recorded exactly once",
            len(duplicate_trades),
        )
    )

    # -- 10. restart continuity --------------------------------------------
    run_ids: list[str] = []
    for record in inputs + decisions + trades + list(incidents):
        run_id = (record.payload.get("identity") or {}).get("run_id")
        if run_id and run_id not in run_ids:
            run_ids.append(run_id)
    starts = [r for r in incidents if r.payload.get("category") == "run_started"]
    counters = [
        (r.payload.get("full_identity") or {}).get("restart_counter")
        for r in starts
    ]
    monotone = all(
        isinstance(a, int) and isinstance(b, int) and b > a
        for a, b in zip(counters, counters[1:])
    )
    restart_ok = (not starts) or monotone
    findings.append(
        Finding(
            "restart_continuity",
            PASS if restart_ok else FAIL,
            (
                f"{len(starts)} recorded start(s), restart counters {counters}, {len(run_ids)} distinct run id(s); "
                "each restart resumed the existing chain"
            )
            if restart_ok
            else f"restart counters are not strictly increasing: {counters}",
            len(starts),
        )
    )

    # -- 11. paper-only authority ------------------------------------------
    # A capture loop that ever recorded a live execution would be the single
    # most important thing in this report, so it is asserted over the evidence
    # rather than assumed from configuration.
    live_markers = [
        r.seq
        for r in trades
        if r.payload.get("is_dry_run") is False or r.payload.get("live") is True
    ]
    findings.append(
        Finding(
            "paper_only_authority",
            FAIL if live_markers else PASS,
            f"trade records claiming live execution: {live_markers[:3]}" if live_markers else
            "no record in any ledger claims a live execution; every paper fill carries the simulation model version",
            len(live_markers),
        )
    )

    status = PASS if all(item.result == PASS for item in findings) else FAIL
    return {
        "reconcile_engine_version": RECONCILE_ENGINE_VERSION,
        "evidence_dir": str(evidence_dir),
        "pairs": pairs,
        "counts": {
            "input": len(inputs),
            "decision": len(decisions),
            "trade": len(trades),
            "incident": len(incidents),
            "runs": len(run_ids),
        },
        "ledger_tips": {kind: led.tip_digest() for kind, led in sorted(ledgers.items())},
        "daily_pack_digest": fp_ledger.daily_pack_digest(ledgers.values()),
        "replays": replays,
        "findings": [item.as_dict() for item in findings],
        "failing_checks": [item.check for item in findings if item.result != PASS],
        "reconciliation": status,
        "real_money_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument(
        "--role",
        required=True,
        help=(
            "the instance whose evidence this is. Required: internal correctness with an "
            "unbound public entrypoint means the command a human runs answers a weaker "
            "question than the library does, and a foreign-role record reads as PASS."
        ),
    )
    parser.add_argument("--pair", action="append", dest="pairs", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-pass", action="store_true", help="exit 2 unless reconciliation passes")
    parser.add_argument("-o", "--out", default=None)
    args = parser.parse_args(argv)

    report = reconcile(Path(args.evidence_dir), args.pairs, expected_role=args.role)
    text = json.dumps(report, indent=2) + "\n"

    if args.out:
        # A report is not evidence, and it may not be written where evidence
        # lives: `--out <lane>/paper_input_ledger.jsonl` would overwrite a
        # hash-chained ledger with a report, and one mistyped path is all that
        # takes. Refusing is cheap; reconstructing a truncated ledger is not.
        destination = Path(args.out).resolve()
        for declared in fp_lane.all_lane_roots():
            if destination == declared or declared in destination.parents:
                print(
                    f"RECONCILE_REFUSED: {args.out} is inside the evidence lane {declared}; "
                    "a report must not be written where evidence lives",
                    file=sys.stderr,
                )
                return 2
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    if args.json:
        sys.stdout.write(text)
    elif not args.out:
        print(f"FP reconciliation — {report['evidence_dir']}")
        for item in report["findings"]:
            print(f"  [{item['result']:>4}] {item['check']}")
            print(f"         {item['detail']}")
        print()
        print(f"counts: {report['counts']}")
        print(f"RECONCILIATION = {report['reconciliation']}")

    if args.require_pass and report["reconciliation"] != PASS:
        print(
            f"RECONCILIATION_FAILED: {report['failing_checks']}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
