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

CHECKS = (
    "Paper Guard / safety gate PASS",
    "effective config is Spot + dry-run",
    "no exchange secret required",
    "candidate/config hashes match the frozen registry",
    "market-data ingestion works",
    "external-feature ingestion works if required",
    "paper_input_ledger works",
    "paper_decision_ledger works",
    "DB state is isolated",
    "monitoring is alive",
    "shadow/event-time replay works on a bounded sample",
    "no duplicate-instance risk exists",
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


def _check_spot_dry_run() -> tuple[str, str]:
    config = _load_json(EXAMPLE_CONFIG)
    if config is None:
        return FAIL, "shipped paper config is missing or unreadable"
    if config.get("dry_run") is not True:
        return FAIL, f"dry_run is {config.get('dry_run')!r}, not exactly true"
    if config.get("trading_mode") != "spot":
        return FAIL, f"trading_mode is {config.get('trading_mode')!r}, not 'spot'"
    if config.get("margin_mode") not in (None, ""):
        return FAIL, f"margin_mode is {config.get('margin_mode')!r}"
    return PASS, "dry_run=true, trading_mode='spot', margin_mode empty"


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
        PASS,
        f"{count} as-seen candles captured and chain-verified; an altered payload is detected",
        {"input_records": count, "input_tip": input_ledger.tip_digest()},
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
        {"decision_records": len(records), "decision_tip": decision.tip_digest()},
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
        PASS,
        f"{report['decisions_compared']} decisions replayed from the as-seen inputs with 0 mismatches; "
        f"a single flipped action is detected ({negative['mismatch_count']} mismatch). "
        f"EMA parity vs TA-Lib: {fp_replay.EMA_PARITY_STATUS}",
        {"decisions_compared": report["decisions_compared"], "negative_control": "detected"},
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

        outcomes = [
            _check_guard(),
            _check_spot_dry_run(),
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

    return {
        "spec_version": "FP-BOOT-1/FP-RUN v1.1 FINAL 2026-09-07",
        "evaluated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checks": checks,
        "blocking_checks": blocking,
        "preflight": status,
        "t0_permitted": status == PASS,
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

    if args.require_pass and not report["t0_permitted"]:
        print(
            f"PREFLIGHT_BLOCKED: checks {report['blocking_checks']} are not PASS; no candidate T0 may be created.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
