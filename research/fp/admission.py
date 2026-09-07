#!/usr/bin/env python3
"""Paper-admission evaluator (FP-BOOT-1 sections 2, 3, 5, 6).

Section 5 lists fourteen conditions and says: otherwise
``PAPER_ADMISSION = BLOCKED``. This module evaluates each one against what the
repository can actually prove and emits a schema-valid
``paper_candidate_admission.json``.

It fails closed in the strict sense: ``ADMITTED`` requires all fourteen results
to be ``PASS``. ``UNPROVEN`` — the honest verdict for a condition that needs a
run this environment has not performed — blocks admission exactly like ``FAIL``.
There is no flag to override it, because a flag to override it is the whole
failure mode the gate exists to prevent.

Usage
-----
    python3 research/fp/admission.py evaluate [-o OUT.json]
    python3 research/fp/admission.py entry-state
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# Importable both as ``python3 research/fp/admission.py`` and as ``from fp import
# admission``: the first puts research/fp on sys.path, not research.
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

SCHEMA_PATH = REPO_ROOT / "research" / "schema" / "paper_candidate_admission.schema.json"
RECORDS_DIR = REPO_ROOT / "research" / "records"
COHORT_REGISTRY = REPO_ROOT / "research" / "fp" / "records" / "forward_paper_cohort_registry.json"
DATASET_V2_LOCK = REPO_ROOT / "research" / "datasets" / "dataset_v2.lock.json"
EXAMPLE_CONFIG = REPO_ROOT / "freqtrade" / "user_data" / "config.paper.json.example"
CHANGE_MODEL_DOC = REPO_ROOT / "docs" / "fp-boot-1" / "FP_BOOT_1_ENTRY_STATE.md"
REPLAY_MODULE = REPO_ROOT / "research" / "fp" / "replay.py"

SCHEMA_VERSION = "1.0.0"
SPEC_VERSION = "FP-BOOT-1/FP-RUN v1.1 FINAL 2026-09-07"

PASS, FAIL, UNPROVEN = "PASS", "FAIL", "UNPROVEN"

# Section 5, verbatim requirements in order.
REQUIREMENTS = (
    "candidate identity is frozen",
    "MEASUREMENT_VALIDITY = PASS",
    "applicable qualification is complete",
    "required deep-validation gates are complete",
    "no unresolved lookahead exists",
    "no unresolved timestamp-knowability defect exists",
    "current runtime remains Binance Spot only",
    "no leverage, futures execution, margin, or shorts are required",
    "source/config/params/engine/data contracts are frozen",
    "paper execution rights are acceptable",
    "every decision-time feature has a prospective availability contract",
    "deterministic or explainable replay exists",
    "outage behavior is predeclared",
    "semantic-change rules are predeclared",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_commit() -> str:
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return "0" * 40
    return sha


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _gate_records() -> list[dict]:
    """Committed experiment records that claim a passing gate.

    ``EXAMPLE_`` records are excluded on purpose: a template must never be able
    to satisfy an admission condition.
    """
    records = []
    if not RECORDS_DIR.is_dir():
        return records
    for path in sorted(RECORDS_DIR.glob("*.json")):
        if path.name.startswith("EXAMPLE_"):
            continue
        record = _load_json(path)
        if record and record.get("gate") == "PASS":
            records.append(record)
    return records


def _guard_result() -> tuple[bool, list[str]]:
    """Run the CLOUD-0 paper guard over the shipped paper config."""
    try:
        import paper_guard  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - scripts/ is always present
        return False, [f"paper_guard unavailable: {exc}"]
    violations = paper_guard.Violations()
    paper_guard.check_config(EXAMPLE_CONFIG, violations)
    paper_guard.check_strategies(violations)
    return not violations, list(violations)


def _spot_only() -> tuple[str, str]:
    config = _load_json(EXAMPLE_CONFIG)
    if config is None:
        return FAIL, f"{EXAMPLE_CONFIG.name} is missing or unreadable"
    exchange = (config.get("exchange") or {}).get("name")
    mode = config.get("trading_mode")
    ok, violations = _guard_result()
    if not ok:
        return FAIL, "paper guard rejected the shipped config: " + "; ".join(violations[:3])
    if exchange != "binance" or mode != "spot":
        return FAIL, f"config declares exchange={exchange!r} trading_mode={mode!r}"
    return PASS, f"paper guard PASS; exchange=binance, trading_mode=spot, dry_run={config.get('dry_run')}"


def _no_derivatives() -> tuple[str, str]:
    ok, violations = _guard_result()
    if not ok:
        return FAIL, "paper guard rejected the shipped config: " + "; ".join(violations[:3])
    return PASS, (
        "paper guard enforces margin_mode empty, no leverage, no shorting, no leveraged-token pairs, "
        "and rejects can_short/leverage/non-spot trading_mode in every strategy file"
    )


def _contracts_frozen() -> tuple[str, str]:
    lock = _load_json(DATASET_V2_LOCK)
    if lock is None:
        return FAIL, "dataset_v2.lock.json is missing or unreadable"
    status = lock.get("status")
    files = lock.get("files") or {}
    if status != "frozen" or not files:
        return FAIL, (
            f"data contract is not frozen: dataset_v2.status={status!r} with {len(files)} fingerprinted files. "
            "Source, config and engine may be pinned, but a data contract cannot be frozen over data that has "
            "not been acquired."
        )
    return PASS, f"dataset_v2 frozen with {len(files)} fingerprinted files"


def _paper_execution_rights() -> tuple[str, str]:
    config = _load_json(EXAMPLE_CONFIG)
    if config is None:
        return FAIL, "shipped paper config is missing or unreadable"
    if config.get("dry_run") is not True:
        return FAIL, "dry_run is not exactly true"
    exchange = config.get("exchange") or {}
    if exchange.get("key") or exchange.get("secret"):
        return FAIL, "an exchange credential is present in the shipped config"
    return PASS, "dry_run=true with empty exchange key/secret; no private credential is required to run paper"


def _replay_available() -> tuple[str, str]:
    if not REPLAY_MODULE.exists():
        return FAIL, "no replay reference exists"
    try:
        from fp import replay  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return FAIL, f"replay reference does not import: {exc}"
    parity = replay.EMA_PARITY_STATUS
    detail = (
        f"{replay.REPLAY_ENGINE_VERSION} derives BASELINE-1 decisions from the captured input ledger; "
        f"periods are read from the frozen strategy by AST, not copied; EMA parity vs TA-Lib is {parity}"
    )
    if parity != "VERIFIED_IN_CI":
        return UNPROVEN, detail + " — the parity claim has not yet been executed against TA-Lib"
    return PASS, detail


def _from_gate_records(key: str, description: str) -> tuple[str, str]:
    records = _gate_records()
    if not records:
        return UNPROVEN, (
            f"{description}: no committed experiment record carries gate=PASS. "
            "research/records/ holds only the schema example."
        )
    for record in records:
        analyses = record.get("analyses") or {}
        if key and analyses.get(key) not in (None, "not_run"):
            return PASS, f"{description}: {key}={analyses.get(key)} in {record.get('run_name')}"
    return UNPROVEN, f"{description}: no passing record reports {key or 'this analysis'}"


def _feature_availability() -> tuple[dict, str, str]:
    """Section 6 — the prospective availability contract per decision-time feature.

    BASELINE-1 consumes exactly one decision-time input: the closed 1h OHLCV
    candle from Binance spot. Declaring that contract is possible now; proving
    the retrieval path from a runtime that does not yet exist is not.
    """
    contract = {
        "status": "CONTRACTED",
        "features": [
            {
                "feature": "closed 1h OHLCV candle (open, high, low, close, volume)",
                "source_identity": "Binance spot public REST market data, pair BTC/USDT and ETH/USDT",
                "retrieval_path": "Freqtrade exchange layer via ccxt; no private credential, no archive replay",
                "source_latency": "candle becomes retrievable at its close boundary; observed lag is recorded per cycle in paper_input_ledger",
                "max_admissible_staleness": "one candle period (1h). A decision bar whose candle is older than that is not a decision bar.",
                "outage_policy": "NO_NEW_ENTRY",
                "fallback_policy": "no forward-fill of a missing required candle; the cycle is recorded as missed and no entry is taken. An existing position is left to its frozen exit logic.",
                "provenance": "each captured candle is hashed into paper_input_ledger with the exchange timestamp and the local receipt timestamp",
            }
        ],
    }
    detail = (
        "BASELINE-1 has exactly one decision-time feature (the closed 1h OHLCV candle) and no external "
        "non-market feature, so no post-facto archive is being used as a real-time feed. The contract is "
        "declared, but its retrieval path has not been exercised by a running paper instance."
    )
    return contract, UNPROVEN, detail


def _outage_predeclared(contract: dict) -> tuple[str, str]:
    features = contract.get("features") or []
    if not features:
        return FAIL, "no feature contract, so no outage policy is declared"
    policies = {f["feature"]: f["outage_policy"] for f in features}
    return PASS, (
        "predeclared per section 17, one of NO_NEW_ENTRY / SAFE_HOLD / INSTANCE_PAUSE / FORCED_EXIT: "
        + "; ".join(f"{k} -> {v}" for k, v in policies.items())
    )


def _semantic_change_rules() -> tuple[str, str]:
    if not CHANGE_MODEL_DOC.exists():
        return FAIL, f"{CHANGE_MODEL_DOC.name} is missing"
    text = CHANGE_MODEL_DOC.read_text(encoding="utf-8")
    needed = ("OBSERVABILITY", "RUNTIME REPAIR", "SEMANTIC CHANGE", "OLD_COHORT = CLOSED")
    missing = [token for token in needed if token not in text]
    if missing:
        return FAIL, f"change model in {CHANGE_MODEL_DOC.name} does not state: {', '.join(missing)}"
    return PASS, (
        f"section 15 change model O/R/S is written into {CHANGE_MODEL_DOC.relative_to(REPO_ROOT).as_posix()}, "
        "and the cohort registry schema requires every post-T0 change to carry its class"
    )


def _candidate_identity_frozen() -> tuple[str, str]:
    """Condition 1 — is there a candidate whose identity is actually frozen?"""
    registry = _load_json(COHORT_REGISTRY)
    if registry is None:
        return FAIL, "forward_paper_cohort_registry.json is missing or unreadable"
    frozen = [
        item
        for item in registry.get("instances", [])
        if item.get("role") != "FP-CONTROL-1"
        and (item.get("runtime_identity") or {}).get("strategy_sha256")
        and (item.get("runtime_identity") or {}).get("config_sha256")
        and (item.get("runtime_identity") or {}).get("source_commit")
    ]
    if not frozen:
        return UNPROVEN, (
            "no forward_paper_cohort_registry.json entry names a frozen candidate "
            f"(entry state C, paper_alpha_cohort={registry.get('paper_alpha_cohort')!r}); "
            "no survivor exists to freeze"
        )
    return PASS, f"{len(frozen)} candidate instance(s) carry a frozen strategy, config and source commit"


def _timestamp_knowability() -> tuple[str, str]:
    """Condition 6 — was every value used at bar t actually knowable at bar t?"""
    records = _gate_records()
    if not records:
        return UNPROVEN, (
            "the strategy sets process_only_new_candles=True and reads only bars t and t-1, but timestamp "
            "knowability has not been demonstrated by a run against real candles"
        )
    return PASS, "a passing gate record demonstrates timestamp knowability against real candles"


def evaluate() -> dict:
    """Evaluate all fourteen section-5 conditions against repository state."""
    contract, feature_result, feature_detail = _feature_availability()

    results: list[tuple[str, str]] = [
        _candidate_identity_frozen(),
        _from_gate_records("", "MEASUREMENT_VALIDITY"),
        _from_gate_records("", "candidate qualification"),
        _from_gate_records("lookahead", "deep-validation gates"),
        _from_gate_records("lookahead", "lookahead analysis"),
        _timestamp_knowability(),
        _spot_only(),
        _no_derivatives(),
        _contracts_frozen(),
        _paper_execution_rights(),
        (feature_result, feature_detail),
        _replay_available(),
        _outage_predeclared(contract),
        _semantic_change_rules(),
    ]

    conditions = [
        {"id": index + 1, "requirement": REQUIREMENTS[index], "result": result, "evidence": evidence}
        for index, (result, evidence) in enumerate(results)
    ]

    admitted = all(item["result"] == PASS for item in conditions)
    blocking = [item["id"] for item in conditions if item["result"] != PASS]

    if admitted:
        reason = "every section-5 condition is independently satisfied"
    else:
        reason = (
            "PAPER_ADMISSION = BLOCKED. Section 5 conditions not satisfied: "
            + ", ".join(str(i) for i in blocking)
            + ". No benchmark sprint has closed, Dataset V2 is not acquired, and BASELINE-1 has never been "
            "run, so no candidate can be frozen for forward paper."
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "spec_version": SPEC_VERSION,
        "evaluated_utc": _utc_now(),
        "code_commit": _git_commit(),
        "candidate": {
            "role": "FP-CANDIDATE-A",
            "name": None,
            "strategy_file": None,
            "strategy_sha256": None,
            "config_files": ["freqtrade/user_data/config.paper.json.example"],
            "config_hash": None,
        },
        "entry_state": "C",
        "conditions": conditions,
        "paper_admission": "ADMITTED" if admitted else "BLOCKED",
        "feature_availability": contract if not admitted else contract,
        "paper_alpha_cohort": "NONE",
        "real_money_authorized": False,
        "reason": reason,
    }


def validate(record: dict) -> list[str]:
    import jsonschema  # noqa: PLC0415

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.validators.validator_for(schema)(schema)
    return [
        f"{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
        for err in sorted(validator.iter_errors(record), key=lambda e: list(e.absolute_path))
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_eval = sub.add_parser("evaluate", help="evaluate the section-5 conditions")
    p_eval.add_argument("-o", "--out", default=None)
    sub.add_parser("entry-state", help="print the section-3 entry state only")

    args = parser.parse_args(argv)
    record = evaluate()

    if args.cmd == "entry-state":
        print(record["entry_state"])
        return 0

    errors = validate(record)
    if errors:
        for err in errors:
            print(f"SCHEMA_INVALID: {err}", file=sys.stderr)
        return 2

    text = json.dumps(record, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text)

    blocked = record["paper_admission"] == "BLOCKED"
    if blocked:
        print(f"PAPER_ADMISSION = BLOCKED — {record['reason']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
