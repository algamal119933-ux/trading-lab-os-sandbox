#!/usr/bin/env python3
"""FP-BOOT-1 preflight gate (specification section 12).

"No candidate T0 before preflight PASS." This module runs the twelve preflight
checks and refuses to emit a T0 unless every one of them is ``PASS``.

Three of the checks — input ledger, decision ledger, event-time replay — are
executed here as real self-tests against a synthetic bounded sample in a
temporary directory, including a **negative control**: the replay check
deliberately corrupts one decision and requires the gate to catch it. A gate
that can only ever report PASS is not evidence of anything.

The checks that need a live paper runtime (market-data ingestion, external
feature ingestion, monitoring liveness) are reported ``UNPROVEN`` in an
environment that has no such runtime. ``UNPROVEN`` blocks T0 exactly as ``FAIL``
does.

Usage
-----
    python3 research/fp/preflight.py                # human-readable report
    python3 research/fp/preflight.py --json         # machine-readable
    python3 research/fp/preflight.py --require-pass # exit 2 unless all PASS

Exit codes: 0 report produced, 2 preflight not PASS under ``--require-pass``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if extra not in sys.path:
        sys.path.insert(0, extra)

from fp import ledger as fp_ledger  # noqa: E402
from fp import replay as fp_replay  # noqa: E402

EXAMPLE_CONFIG = REPO_ROOT / "freqtrade" / "user_data" / "config.paper.json.example"
COHORT_REGISTRY = REPO_ROOT / "research" / "fp" / "records" / "forward_paper_cohort_registry.json"

PASS, FAIL, UNPROVEN = "PASS", "FAIL", "UNPROVEN"

# The mechanisms this environment can exercise, as opposed to the checks that
# need a live candidate. Section 1.3 keeps the two verdicts apart: validating
# the scaffold is not runtime readiness. Every key here must be reported by some
# check, so a mechanism that silently stops running fails the verdict rather
# than vanishing from it.
MECHANISM_KEYS = (
    "mechanism_input_ledger",
    "mechanism_decision_ledger",
    "mechanism_event_time_replay",
    "mechanism_persistence",
    "mechanism_restart",
)

# Section 16 of the v2.0 directive, verbatim and in order. Four checks are new
# relative to the superseded v1.1 section 12 (clock tolerance, evidence
# persistence, the pre-T0 restart drill, and the split of dry-run from Spot),
# and two that the scaffold previously reported PASS now say "real": a synthetic
# sample cannot satisfy them.
CHECKS = (
    "Paper Guard PASS",
    "effective config is dry_run=true",
    "effective mode is Spot",
    "no live exchange secret required",
    "runtime hashes match registry",
    "real market-data ingestion works",
    "required external-feature ingestion works if applicable",
    "input ledger works on real incoming data",
    "decision ledger works",
    "DB is isolated",
    "monitoring is alive",
    "event-time replay works on a bounded real-data sample",
    "no duplicate-instance risk",
    "clock/timestamp handling is within tolerance",
    "disk/evidence persistence works",
    "candidate can be restarted safely in a controlled pre-T0 drill",
)


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# Synthetic bounded sample
# --------------------------------------------------------------------------


def synthetic_candles(count: int = 900, start_ts: int = 1_609_459_200_000, step_ms: int = 3_600_000) -> list[dict]:
    """A deterministic 1h series containing at least one EMA50/EMA200 cross.

    Longer than the strategy's declared ``startup_candle_count`` (3 x 200), so the
    sample contains bars that would actually be scored, not only warm-up.

    Built from integer arithmetic so it is identical on every platform: a long
    decline followed by a sustained recovery, which forces the fast EMA through
    the slow one in both directions.
    """
    candles = []
    for i in range(count):
        if i < count // 2:
            close = 30000.0 - 20.0 * i
        else:
            close = 30000.0 - 20.0 * (count // 2) + 45.0 * (i - count // 2)
        close += 60.0 * (((i * 17) % 7) - 3)
        candles.append(
            {
                "ts": start_ts + i * step_ms,
                "open": round(close - 5.0, 8),
                "high": round(close + 25.0, 8),
                "low": round(close - 25.0, 8),
                "close": round(close, 8),
                "volume": round(100.0 + (i % 13), 8),
            }
        )
    return candles


def _capture_sample(evidence_dir: Path, pair: str = "BTC/USDT") -> tuple[fp_ledger.Ledger, fp_ledger.Ledger, int]:
    """Write a synthetic cycle through the real input and decision ledgers."""
    ledgers = fp_ledger.open_ledgers(evidence_dir)
    candles = synthetic_candles()

    # A bulk capture, so the batch form is the honest one to exercise here; the
    # per-append durability path is covered by the ledger tests.
    ledgers["input"].extend(
        [
            {
                "pair": pair,
                "timeframe": "1h",
                "candle": candle,
                "exchange_ts": candle["ts"] + 3_600_000,
                "received_utc": "2021-01-01T00:00:00.000Z",
                "source_id": "synthetic:preflight",
            }
            for candle in candles
        ]
    )

    ledgers["decision"].extend(
        [
            {
                "pair": pair,
                "timeframe": "1h",
                "candle_ts": decision.candle_ts,
                "signal_state": decision.signal_state,
                "intended_action": decision.intended_action,
                "no_action_reason": decision.no_action_reason,
                "runtime_version": fp_replay.REPLAY_ENGINE_VERSION,
                "restart_counter": 0,
            }
            for decision in fp_replay.derive_decisions(candles, pair)
        ]
    )

    return ledgers["input"], ledgers["decision"], len(candles)


# --------------------------------------------------------------------------
# Individual checks
# --------------------------------------------------------------------------


def _check_guard() -> tuple[str, str]:
    try:
        import paper_guard  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        return FAIL, f"paper_guard unavailable: {exc}"
    violations = paper_guard.Violations()
    paper_guard.check_config(EXAMPLE_CONFIG, violations)
    paper_guard.check_strategies(violations)
    if violations:
        return FAIL, "; ".join(violations[:5])
    return PASS, "scripts/paper_guard.py accepts the shipped paper config and every strategy file"


def _check_dry_run() -> tuple[str, str]:
    config = _load_json(EXAMPLE_CONFIG)
    if config is None:
        return FAIL, "shipped paper config is missing or unreadable"
    if config.get("dry_run") is not True:
        return FAIL, f"dry_run is {config.get('dry_run')!r}, not exactly true"
    return PASS, "dry_run is exactly true (not truthy: the guard rejects 1, 'true' and null)"


def _check_spot_mode() -> tuple[str, str]:
    config = _load_json(EXAMPLE_CONFIG)
    if config is None:
        return FAIL, "shipped paper config is missing or unreadable"
    if config.get("trading_mode") != "spot":
        return FAIL, f"trading_mode is {config.get('trading_mode')!r}, not 'spot'"
    if config.get("margin_mode") not in (None, ""):
        return FAIL, f"margin_mode is {config.get('margin_mode')!r}, not empty"
    return PASS, "trading_mode='spot' with margin_mode empty"


def _check_clock_tolerance() -> tuple[str, str]:
    """Section 16.14 — is clock and timestamp handling within tolerance?

    What the scaffold enforces structurally can be stated; what it cannot state
    is the skew between this machine and the exchange, which needs a runtime
    talking to the exchange.
    """
    return UNPROVEN, (
        "structurally enforced: the ledger refuses any recorded_utc that is not UTC ISO-8601 ending in Z, "
        "and replay refuses out-of-order or duplicate candle timestamps. Exchange-versus-local clock skew "
        "cannot be measured without a runtime that talks to the exchange, and section 21 makes serious skew "
        "an INSTANCE_PAUSE condition rather than something to tolerate silently."
    )


def _check_evidence_persistence(evidence_dir: Path) -> tuple[str, str, dict]:
    """Section 16.15 — does evidence survive the process that wrote it?

    Executed, not asserted: the ledgers written earlier in this run are reopened
    from disk by fresh objects and re-verified. A ledger that only verifies
    while its writer is alive is not evidence.
    """
    reopened = fp_ledger.open_ledgers(evidence_dir)
    counts = {}
    for kind, ledger in sorted(reopened.items()):
        problems = ledger.verify()
        if problems:
            return FAIL, f"{kind} ledger did not survive reopening: {problems[0]}", {"mechanism_persistence": FAIL}
        counts[kind] = len(ledger.records())
    if not counts.get("input") or not counts.get("decision"):
        return FAIL, f"expected persisted input and decision records, found {counts}", {"mechanism_persistence": FAIL}
    digest = fp_ledger.daily_pack_digest(reopened.values())
    return (
        PASS,
        f"reopened from disk by fresh readers and re-verified: {counts}; "
        f"daily-pack digest {digest[:16]}... binds the ledger tips",
        {"mechanism_persistence": PASS},
    )


def _check_restart_drill(evidence_dir: Path) -> tuple[str, str, dict]:
    """Section 16.16 / 17 — can the candidate restart safely before T0?

    The ledger half of a restart is executable here and is executed: a fresh
    writer continues the existing chain rather than starting a second one or
    re-emitting a decision. The rest of the drill is not.
    """
    ledgers = fp_ledger.open_ledgers(evidence_dir)
    decision = ledgers["decision"]
    before = decision.records()
    if not before:
        return FAIL, "no decisions were recorded, so a restart cannot be exercised", {"mechanism_restart": FAIL}

    restarted = fp_ledger.Ledger(decision.path, "decision")
    resumed = restarted.append(
        {
            "pair": "BTC/USDT",
            "candle_ts": before[-1].payload.get("candle_ts", 0) + 3_600_000,
            "signal_state": before[-1].payload.get("signal_state"),
            "intended_action": "hold",
            "no_action_reason": "restart_drill",
            "restart_counter": 1,
        }
    )
    if resumed.seq != before[-1].seq + 1:
        return FAIL, f"a restarted writer resumed at seq {resumed.seq}, expected {before[-1].seq + 1}", {"mechanism_restart": FAIL}
    if resumed.prev_digest != before[-1].digest:
        return FAIL, "a restarted writer did not continue the existing chain", {"mechanism_restart": FAIL}
    if restarted.verify():
        return FAIL, "the chain broke across a restart", {"mechanism_restart": FAIL}
    timestamps = [r.payload.get("candle_ts") for r in restarted.records() if not r.payload.get("erratum")]
    if len(timestamps) != len(set(timestamps)):
        return FAIL, "a restart produced a duplicate decision for a candle already decided", {"mechanism_restart": FAIL}

    return (
        UNPROVEN,
        "the ledger half is executed and passes: a fresh writer resumed at the next sequence number, "
        "continued the hash chain, and produced no duplicate decision for an already-decided candle "
        f"(restart_counter recorded, {len(timestamps)} unique decision bars). Section 17 also requires a "
        "database reopen, a monitoring restart, a market-data interruption and state reconciliation, none "
        "of which exist without a running candidate.",
        {"mechanism_restart": PASS},
    )


def _check_no_secret() -> tuple[str, str]:
    config = _load_json(EXAMPLE_CONFIG)
    if config is None:
        return FAIL, "shipped paper config is missing or unreadable"
    exchange = config.get("exchange") or {}
    present = [key for key in ("key", "secret", "password", "uid") if exchange.get(key)]
    if present:
        return FAIL, f"exchange credential fields are populated: {present}"
    return PASS, "exchange key and secret are empty; paper runs without any private credential"


def _check_hashes_match_registry() -> tuple[str, str]:
    registry = _load_json(COHORT_REGISTRY)
    if registry is None:
        return FAIL, "forward_paper_cohort_registry.json is missing or unreadable"
    frozen = [
        item
        for item in registry.get("instances", [])
        if (item.get("runtime_identity") or {}).get("strategy_sha256")
    ]
    if not frozen:
        return UNPROVEN, (
            "the registry declares no frozen runtime identity to compare against "
            f"(paper_alpha_cohort={registry.get('paper_alpha_cohort')!r})"
        )
    return UNPROVEN, "hash comparison requires the running instance; not executed here"


def _check_market_data_ingestion() -> tuple[str, str]:
    return UNPROVEN, (
        "no paper runtime exists and this sandbox cannot reach Binance (egress returns 403 to CONNECT for "
        "api.binance.com). Ingestion must be proven on a host that has the exchange route."
    )


def _check_external_features() -> tuple[str, str]:
    return PASS, (
        "BASELINE-1 requires no external non-market feature: its only decision-time input is the closed 1h "
        "OHLCV candle, so section 6's post-facto-archive hazard does not arise for this candidate"
    )


def _check_input_ledger(evidence_dir: Path) -> tuple[str, str, dict]:
    input_ledger, _, count = _capture_sample(evidence_dir)
    problems = input_ledger.verify()
    if problems:
        return FAIL, "; ".join(problems[:3]), {}

    # Negative control: an altered payload must break the chain.
    text = input_ledger.path.read_text(encoding="utf-8").splitlines()
    tampered = evidence_dir / "tampered_input.jsonl"
    record = json.loads(text[10])
    record["payload"]["candle"]["close"] = record["payload"]["candle"]["close"] + 1
    text[10] = json.dumps(record, sort_keys=True, ensure_ascii=False)
    tampered.write_text("\n".join(text) + "\n", encoding="utf-8")
    detected = bool(fp_ledger.Ledger(tampered, "input").verify())
    if not detected:
        return FAIL, "the input ledger did not detect an altered candle payload", {}

    return (
        UNPROVEN,
        f"the mechanism works: {count} as-seen candles captured and chain-verified, and an altered payload "
        "is detected. But section 16.8 requires the input ledger to work on *real incoming data*, and every "
        "candle in this sample is synthetic. This is FP_INFRASTRUCTURE_SCAFFOLD_VALIDATION, not "
        "FP_RUNTIME_READINESS: no candle here came from an exchange.",
        {
            "input_records": count,
            "input_tip": input_ledger.tip_digest(),
            "input_sample": "synthetic",
            "mechanism_input_ledger": PASS,
        },
    )


def _check_decision_ledger(evidence_dir: Path) -> tuple[str, str, dict]:
    ledgers = fp_ledger.open_ledgers(evidence_dir)
    decision = ledgers["decision"]
    problems = decision.verify()
    if problems:
        return FAIL, "; ".join(problems[:3]), {}
    records = decision.records()
    if not records:
        return FAIL, "no decisions were recorded", {}

    erratum = decision.append_erratum(records[0].seq, "preflight erratum self-test", {"note": "no-op"})
    if decision.verify():
        return FAIL, "appending an erratum broke the decision chain", {}
    if decision.records()[0].digest != records[0].digest:
        return FAIL, "the erratum rewrote the record it corrects", {}

    return (
        PASS,
        f"{len(records)} decisions recorded append-only; an erratum at seq {erratum.seq} corrects "
        f"seq {records[0].seq} without rewriting it",
        {
            "decision_records": len(records),
            "decision_tip": decision.tip_digest(),
            "mechanism_decision_ledger": PASS,
        },
    )


def _check_db_isolation() -> tuple[str, str]:
    registry = _load_json(COHORT_REGISTRY)
    if registry is None:
        return FAIL, "forward_paper_cohort_registry.json is missing or unreadable"
    instances = registry.get("instances", [])
    fields = ("db_path", "bot_name", "log_path", "evidence_dir")
    declared = [
        {field: (item.get("runtime_identity") or {}).get(field) for field in fields} for item in instances
    ]
    populated = [item for item in declared if any(item.values())]
    if not populated:
        return UNPROVEN, "no instance declares a db_path/bot_name/log_path/evidence_dir to check for collisions"
    for field in fields:
        values = [item[field] for item in populated if item[field]]
        if len(values) != len(set(values)):
            return FAIL, f"two instances share the same {field}; section 14 forbids shared mutable state"
    return PASS, f"{len(populated)} instances declare distinct {', '.join(fields)}"


def _check_monitoring() -> tuple[str, str]:
    return UNPROVEN, (
        "the exporter image builds and serves /metrics in CI, but 'monitoring is alive' is a statement about a "
        "running instance. Section 18: monitoring health and candidate-runtime health are distinct states, and "
        "neither is observable here."
    )


def _check_replay(evidence_dir: Path) -> tuple[str, str, dict]:
    ledgers = fp_ledger.open_ledgers(evidence_dir)
    inputs = ledgers["input"].records()
    decisions = [r for r in ledgers["decision"].records() if not r.payload.get("erratum")]

    report = fp_replay.event_time_replay(inputs, decisions, "BTC/USDT")
    if report["status"] != PASS:
        return FAIL, f"event-time replay failed on its own captured sample: {report['mismatches'][:2]}", {}

    # Negative control: flip one recorded action and require the gate to fail.
    corrupted = []
    flipped = False
    for record in decisions:
        payload = dict(record.payload)
        if not flipped and payload["intended_action"] == fp_replay.ACTION_ENTER_LONG:
            payload["intended_action"] = fp_replay.ACTION_HOLD
            flipped = True
        corrupted.append(fp_ledger.Record(record.seq, record.kind, record.recorded_utc, record.prev_digest, record.digest, payload))
    if not flipped:
        return FAIL, "the synthetic sample produced no entry signal, so the negative control cannot run", {}

    negative = fp_replay.event_time_replay(inputs, corrupted, "BTC/USDT")
    if negative["status"] == PASS:
        return FAIL, "event-time replay accepted a decision that contradicts the frozen logic", {}

    return (
        UNPROVEN,
        f"the mechanism works: {report['decisions_compared']} decisions replayed from the as-seen inputs "
        f"with 0 mismatches, and a single flipped action is detected ({negative['mismatch_count']} "
        "mismatch). But section 16.12 requires a bounded *real-data* sample, and this one is synthetic. "
        f"EMA parity vs TA-Lib is {fp_replay.EMA_PARITY_STATUS}, which per section 14 means "
        "EMA_IMPLEMENTATION_PARITY = PASS only: it does not prove exchange-input, strategy-level, "
        "position-state or execution parity.",
        {
            "decisions_compared": report["decisions_compared"],
            "negative_control": "detected",
            "replay_sample": "synthetic",
            "mechanism_event_time_replay": PASS,
        },
    )


def _check_duplicate_instance() -> tuple[str, str]:
    registry = _load_json(COHORT_REGISTRY)
    if registry is None:
        return FAIL, "forward_paper_cohort_registry.json is missing or unreadable"
    running = [item for item in registry.get("instances", []) if item.get("status") == "RUNNING"]
    roles = [item.get("role") for item in running]
    if len(roles) != len(set(roles)):
        return FAIL, f"two running instances share a role: {roles}"
    if not running:
        return UNPROVEN, (
            "no instance is running, so duplicate-instance risk cannot be observed. A single-writer lock on "
            "each db_path must be demonstrated before T0."
        )
    return UNPROVEN, "role uniqueness holds in the registry, but process-level exclusion was not observed"


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------


def run(evidence_dir: Path | None = None) -> dict:
    temp_dir = None
    if evidence_dir is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="fp-preflight-"))
        evidence_dir = temp_dir

    try:
        details: dict = {}
        input_result, input_evidence, input_extra = _check_input_ledger(evidence_dir)
        details.update(input_extra)
        decision_result, decision_evidence, decision_extra = _check_decision_ledger(evidence_dir)
        details.update(decision_extra)
        replay_result, replay_evidence, replay_extra = _check_replay(evidence_dir)
        details.update(replay_extra)
        # Persistence and the restart drill must run last: both read back what the
        # checks above wrote, and the restart drill appends to the decision ledger.
        persistence_result, persistence_evidence, persistence_extra = _check_evidence_persistence(evidence_dir)
        details.update(persistence_extra)
        restart_result, restart_evidence, restart_extra = _check_restart_drill(evidence_dir)
        details.update(restart_extra)

        outcomes = [
            _check_guard(),
            _check_dry_run(),
            _check_spot_mode(),
            _check_no_secret(),
            _check_hashes_match_registry(),
            _check_market_data_ingestion(),
            _check_external_features(),
            (input_result, input_evidence),
            (decision_result, decision_evidence),
            _check_db_isolation(),
            _check_monitoring(),
            (replay_result, replay_evidence),
            _check_duplicate_instance(),
            _check_clock_tolerance(),
            (persistence_result, persistence_evidence),
            (restart_result, restart_evidence),
        ]
    finally:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)

    checks = [
        {"id": index + 1, "check": CHECKS[index], "result": result, "evidence": evidence}
        for index, (result, evidence) in enumerate(outcomes)
    ]
    blocking = [item["id"] for item in checks if item["result"] != PASS]
    status = PASS if not blocking else "BLOCKED"

    # Section 1.3 draws the distinction this report must not blur: the scaffold
    # mechanisms can be validated here, runtime readiness cannot. Each mechanism
    # check reports its own verdict rather than having it inferred from prose.
    mechanism_verdicts = {k: v for k, v in details.items() if k.startswith("mechanism_")}
    missing = set(MECHANISM_KEYS) - set(mechanism_verdicts)
    if missing or any(v != PASS for v in mechanism_verdicts.values()):
        scaffold_validation = FAIL
    else:
        scaffold_validation = PASS

    return {
        "spec_version": "TL-FP-BOOT-1 v2.0 FINAL 2026-09-07",
        "evaluated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checks": checks,
        "blocking_checks": blocking,
        "preflight": status,
        "t0_permitted": status == PASS,
        "fp_infrastructure_scaffold_validation": scaffold_validation,
        "mechanism_verdicts": mechanism_verdicts,
        "fp_runtime_readiness": PASS if status == PASS else "NOT_PROVEN",
        "details": details,
        "real_money_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--require-pass", action="store_true", help="exit 2 unless every check passes")
    args = parser.parse_args(argv)

    report = run()

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"FP-BOOT-1 preflight — {report['evaluated_utc']}")
        for item in report["checks"]:
            print(f"  [{item['result']:>8}] {item['id']:>2}. {item['check']}")
            print(f"             {item['evidence']}")
        print()
        print(f"PREFLIGHT = {report['preflight']}")
        print(f"T0_PERMITTED = {'YES' if report['t0_permitted'] else 'NO'}")
        print(f"FP_INFRASTRUCTURE_SCAFFOLD_VALIDATION = {report['fp_infrastructure_scaffold_validation']}")
        print(f"FP_RUNTIME_READINESS = {report['fp_runtime_readiness']}")

    if args.require_pass and not report["t0_permitted"]:
        print(
            f"PREFLIGHT_BLOCKED: checks {report['blocking_checks']} are not PASS; no candidate T0 may be created.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
