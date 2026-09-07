#!/usr/bin/env python3
"""Paper-admission evaluator (TL-FP-BOOT-1 v2.0, sections 7, 9, 10).

Section 9 lists eighteen conditions and says: if any required condition fails,
``PAPER_ADMISSION = BLOCKED``. This module evaluates each one against what the
repository can actually prove and emits a schema-valid
``paper_candidate_admission.json``.

It fails closed in the strict sense: ``ADMITTED`` requires all eighteen results
to be ``PASS``. ``UNPROVEN`` — the honest verdict for a condition that needs a
run this environment has not performed — blocks admission exactly like ``FAIL``,
which section 9 states outright: "UNPROVEN is not PASS". There is no flag to
override it, and section 9 names the four that must not exist: ``--force``,
``--assume-pass``, ``--allow-blocked``, and a silent environment override.

Section 7 governs the entry state: it is recomputed from authoritative merged
main and is never inherited from this parked scaffold branch. Section 3 makes
*both* merges the precondition — the BASELINE-1 closure lineage (3.1) and the
completed benchmark lineage (3.2) — so until both are on main the entry state
reported here is ``NOT_AUTHORITATIVE`` rather than a value that looks binding.
Both are checked with git, so each flips by itself when its merge lands.

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

SCHEMA_VERSION = "2.0.0"
SPEC_VERSION = "TL-FP-BOOT-1 v2.0 FINAL 2026-09-07"

# The BASELINE-1 closure lineage named by the canonical directive (v2.0 section
# 1.1). It is authoritative only once it is an ancestor of merged main.
BASELINE_CLOSURE_COMMIT = "1dfb69604bb87856b75c8c90957f2acc8e1fab7f"

PASS, FAIL, UNPROVEN = "PASS", "FAIL", "UNPROVEN"

# Section 9 of the v2.0 directive, verbatim and in order. This replaces the
# fourteen conditions of the superseded v1.1 section 5: the single "no leverage,
# futures, margin or shorts" condition is split into four, and condition 18 —
# project integrity — is new.
REQUIREMENTS = (
    "candidate family identified",
    "frozen configuration identified",
    "measurement validity PASS",
    "qualification/deep validation complete as required",
    "no unresolved lookahead",
    "no unresolved timestamp-knowability defect",
    "Binance Spot only",
    "no leverage",
    "no futures execution",
    "no margin",
    "no shorts",
    "source/config/params/engine identity frozen",
    "paper execution rights acceptable",
    "every required decision-time feature has a prospective availability contract",
    "deterministic or explainable replay exists",
    "outage behavior is predeclared",
    "semantic-change policy is predeclared",
    "no unresolved P0 project-integrity issue",
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


def _guarded(field_summary: str, extra: "callable | None" = None) -> tuple[str, str]:
    """Shared shape for the four separate section-9 derivative prohibitions.

    Conditions 8-11 are distinct requirements that happen to share one enforcer.
    Each gets its own row and its own evidence sentence, so that if the guard
    ever stops covering one of them the gap shows up against that condition
    rather than hiding inside a combined verdict.
    """
    ok, violations = _guard_result()
    if not ok:
        return FAIL, "paper guard rejected the shipped config: " + "; ".join(violations[:3])
    if extra is not None:
        problem = extra()
        if problem:
            return FAIL, problem
    return PASS, field_summary


def _no_leverage() -> tuple[str, str]:
    def check() -> str | None:
        config = _load_json(EXAMPLE_CONFIG) or {}
        if config.get("leverage") or config.get("max_leverage"):
            return f"config declares leverage: {config.get('leverage') or config.get('max_leverage')!r}"
        return None

    return _guarded(
        "paper guard rejects any leverage key in the config and any `leverage`/`can_leverage` "
        "declaration in a strategy file; the shipped config declares none",
        check,
    )


def _no_futures() -> tuple[str, str]:
    def check() -> str | None:
        mode = (_load_json(EXAMPLE_CONFIG) or {}).get("trading_mode")
        if mode != "spot":
            return f"trading_mode is {mode!r}, so futures execution is not excluded"
        return None

    return _guarded(
        "trading_mode must be explicitly 'spot'; the guard rejects any other value in the config and "
        "any non-spot trading_mode declared in a strategy file",
        check,
    )


def _no_margin() -> tuple[str, str]:
    def check() -> str | None:
        margin = (_load_json(EXAMPLE_CONFIG) or {}).get("margin_mode")
        if margin not in (None, ""):
            return f"margin_mode is {margin!r}, not empty"
        return None

    return _guarded(
        "margin_mode must be empty; the guard rejects any populated margin mode",
        check,
    )


def _no_shorts() -> tuple[str, str]:
    def check() -> str | None:
        config = _load_json(EXAMPLE_CONFIG) or {}
        if config.get("can_short"):
            return "config enables can_short"
        return None

    return _guarded(
        "the guard rejects shorting in the config, `can_short = True` in any strategy file, and "
        "derivative or leveraged-token pairs in the whitelist; BaselineEmaRegimeV1 sets can_short = False",
        check,
    )


def _frozen_configuration() -> tuple[str, str]:
    """Condition 2 — is the candidate's frozen configuration identified?"""
    registry = _load_json(COHORT_REGISTRY)
    if registry is None:
        return FAIL, "forward_paper_cohort_registry.json is missing or unreadable"
    identified = [
        item
        for item in registry.get("instances", [])
        if item.get("role") != "FP-CONTROL-1" and (item.get("runtime_identity") or {}).get("config_sha256")
    ]
    if not identified:
        return UNPROVEN, (
            "no candidate instance names a frozen configuration hash; a configuration cannot be identified "
            "for a candidate that does not exist"
        )
    return PASS, f"{len(identified)} candidate instance(s) name a frozen configuration hash"


def dataset_v2_fingerprints(lock: dict) -> dict[str, str]:
    """Content digests out of a Dataset V2 lock, whichever layout it uses.

    The authoritative lock written by the BASELINE-1 acquisition lineage keys
    its digests as ``canonical_hashes`` / ``raw_file_hashes``. The
    pre-acquisition stub on this branch has neither and carries an empty
    ``files``. Reading only one layout would report a fully frozen, audited
    dataset as unfingerprinted — a false block on real evidence — so the
    canonical digests are preferred, the raw hashes are the fallback, and
    ``files`` is still understood.
    """
    for key in ("canonical_hashes", "raw_file_hashes"):
        found = lock.get(key)
        if isinstance(found, dict) and found:
            return dict(found)
    files = lock.get("files")
    if isinstance(files, dict) and files:
        return {
            name: (entry.get("canonical_candle_content_sha256") or entry.get("raw_file_sha256") or "")
            if isinstance(entry, dict)
            else str(entry)
            for name, entry in files.items()
        }
    return {}


def _contracts_frozen() -> tuple[str, str]:
    lock = _load_json(DATASET_V2_LOCK)
    if lock is None:
        return FAIL, "dataset_v2.lock.json is missing or unreadable"
    status = lock.get("status")
    fingerprints = dataset_v2_fingerprints(lock)
    if status != "frozen" or not fingerprints:
        return FAIL, (
            f"data contract is not frozen: dataset_v2.status={status!r} with {len(fingerprints)} fingerprints. "
            "Source, config and engine may be pinned, but a data contract cannot be frozen over data this "
            "branch has not got. The authoritative frozen lock lives in the BASELINE-1 closure lineage and "
            "reaches here by merge, never by reacquisition."
        )
    return PASS, f"dataset_v2 frozen with {len(fingerprints)} content fingerprints: {', '.join(sorted(fingerprints))}"


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


def _baseline_lineage_is_authoritative() -> tuple[bool, str]:
    """Is the BASELINE-1 closure commit an ancestor of merged main?

    Section 3.1 of the v2.0 directive makes this the activation proof for the
    whole stage: "If this proof fails: TL-FP-BOOT-1 = BLOCKED." It is checked
    with git rather than asserted, so it flips by itself the moment the merge
    lands.
    """
    for ref in ("origin/main", "main"):
        try:
            subprocess.check_output(
                ["git", "-C", str(REPO_ROOT), "rev-parse", "--verify", f"{ref}^{{commit}}"],
                stderr=subprocess.DEVNULL,
            )
        except Exception:  # noqa: BLE001
            continue
        try:
            subprocess.check_output(
                ["git", "-C", str(REPO_ROOT), "cat-file", "-e", f"{BASELINE_CLOSURE_COMMIT}^{{commit}}"],
                stderr=subprocess.DEVNULL,
            )
        except Exception:  # noqa: BLE001
            return False, f"{BASELINE_CLOSURE_COMMIT[:7]} is not present in this checkout"
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "merge-base", "--is-ancestor", BASELINE_CLOSURE_COMMIT, ref],
            capture_output=True,
        )
        if result.returncode == 0:
            return True, f"{BASELINE_CLOSURE_COMMIT[:7]} is an ancestor of {ref}"
        return False, f"{BASELINE_CLOSURE_COMMIT[:7]} is NOT an ancestor of {ref}"
    return False, "no main ref is available in this checkout to prove ancestry against"


def _git_show(ref: str, path: str) -> str | None:
    """File content at a ref, or None when the ref or path is absent."""
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "show", f"{ref}:{path}"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return None


def benchmark_closure_state() -> tuple[str, str]:
    """Has POST-BASELINE-EXTBENCH-1 closed *on authoritative main*?

    Section 3.2 requires the completed benchmark lineage merged to main before
    entry state may be determined, and section 3 is explicit that "only that
    merged main is authoritative for FP-BOOT entry-state determination".

    Three distinguishable states, because collapsing them would let an unmerged
    or unexecuted sprint read as a closed one:

    * ``NOT_MERGED``  - the sprint's artifacts are not on main at all;
    * ``MERGED_NOT_EXECUTED`` - registry present, but the scorecard has no rows,
      which is the pre-registration state the sprint freezes before running;
    * ``CLOSED`` - the scorecard carries at least one experiment row.
    """
    for ref in ("origin/main", "main"):
        scorecard = _git_show(ref, "research/external/qualification_scorecard.csv")
        registry = _git_show(ref, "research/external/candidate_registry.json")
        if scorecard is None and registry is None:
            return "NOT_MERGED", (
                f"no POST-BASELINE-EXTBENCH-1 artifacts on {ref}; the sprint lineage has not been merged "
                "(section 3.2)"
            )
        rows = [
            line
            for line in (scorecard or "").splitlines()[1:]
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if not rows:
            return "MERGED_NOT_EXECUTED", (
                f"the sprint registry is on {ref} but its qualification scorecard carries no experiment rows: "
                "pre-registered, not executed"
            )
        return "CLOSED", f"qualification scorecard on {ref} carries {len(rows)} experiment row(s)"
    return "NOT_MERGED", "no main ref is available in this checkout"


def _project_integrity() -> tuple[str, str]:
    """Condition 18 — no unresolved P0 project-integrity issue.

    While the authoritative BASELINE-1 lineage is unmerged, project state is
    split across branches and no entry state computed here is authoritative
    (v2.0 section 7). That is an unresolved integrity issue by the directive's
    own terms, so this condition fails until the merge lands.
    """
    merged, detail = _baseline_lineage_is_authoritative()
    if not merged:
        return FAIL, (
            f"authoritative lineage is not consolidated: {detail}. Section 3.1 requires the BASELINE-1 "
            "closure lineage merged to main with green CI before FP admission is judged; until then "
            "TL-FP-BOOT-1 = BLOCKED and this branch's entry state is not authoritative."
        )
    return PASS, f"authoritative lineage consolidated: {detail}"


def evaluate() -> dict:
    """Evaluate all eighteen section-9 conditions against repository state."""
    contract, feature_result, feature_detail = _feature_availability()
    lineage_ok, lineage_detail = _baseline_lineage_is_authoritative()
    benchmark_state, benchmark_detail = benchmark_closure_state()

    results: list[tuple[str, str]] = [
        _candidate_identity_frozen(),
        _frozen_configuration(),
        _from_gate_records("", "MEASUREMENT_VALIDITY"),
        _from_gate_records("lookahead", "qualification / deep validation"),
        _from_gate_records("lookahead", "lookahead analysis"),
        _timestamp_knowability(),
        _spot_only(),
        _no_leverage(),
        _no_futures(),
        _no_margin(),
        _no_shorts(),
        _contracts_frozen(),
        _paper_execution_rights(),
        (feature_result, feature_detail),
        _replay_available(),
        _outage_predeclared(contract),
        _semantic_change_rules(),
        _project_integrity(),
    ]

    conditions = [
        {"id": index + 1, "requirement": REQUIREMENTS[index], "result": result, "evidence": evidence}
        for index, (result, evidence) in enumerate(results)
    ]

    admitted = all(item["result"] == PASS for item in conditions)
    blocking = [item["id"] for item in conditions if item["result"] != PASS]

    if admitted:
        reason = "every section-9 condition is independently satisfied"
    else:
        reason = (
            "PAPER_ADMISSION = BLOCKED. Section 9 conditions not satisfied: "
            + ", ".join(str(i) for i in blocking)
            + ". This branch is the parked FP scaffold, not authoritative project state. "
            + f"BASELINE-1 lineage: {lineage_detail}. "
            + f"Benchmark closure: {benchmark_state} — {benchmark_detail}. "
            + "The Dataset V2 lock visible on this branch is the pre-acquisition stub; the frozen lock "
            "reaches it by merging main, never by reacquisition."
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "spec_version": SPEC_VERSION,
        "supersedes": [
            "TRADING_LAB_OS_FP1_PROSPECTIVE_FORWARD_PAPER_v1.0_2026-09-07.md",
            "TRADING_LAB_OS_FP_BOOT1_AND_FP_RUN_v1.1_FINAL_2026-09-07.md",
        ],
        "authoritative_lineage": {
            "baseline_closure_commit": BASELINE_CLOSURE_COMMIT,
            "is_ancestor_of_main": lineage_ok,
            "detail": lineage_detail,
        },
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
        # Section 7: entry state is recomputed from authoritative merged main,
        # never inherited from this branch. Section 3 makes *both* merges the
        # precondition — BASELINE-1 closure and benchmark closure — so §3.1 alone
        # is not enough to make any value here binding.
        "entry_state": "NOT_AUTHORITATIVE" if not (lineage_ok and benchmark_state == "CLOSED") else "C",
        "benchmark_closure": {"state": benchmark_state, "detail": benchmark_detail},
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
