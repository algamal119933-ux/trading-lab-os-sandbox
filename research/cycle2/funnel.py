#!/usr/bin/env python3
"""Deterministic evaluator of the frozen Cycle-2 funnel law (research/cycle2/FUNNEL_LAW_1.md).

Inputs: one driver run summary (cycle2_run_summary.json and the artifacts it
names, every one re-hashed against the sha256 the driver recorded), the
preregistration it ran, and the canonical trial ledger, read-only. Optional gate
logs from the workflow (data lock, warm-up join, lookahead, recursive).

Output: per-gate states, the funnel result, the ledger-state mapping, the null
calibration verdict and the Cycle-2 STOP flag, as one derived,
non-authoritative JSON (OPENING-1 §11 fields). It proposes; it never writes the
ledger. The terminal record stays the operator's own append.

Fail-closed everywhere: a missing or unusable input is NOT_EVALUABLE, which is
never PASS and blocks SURVIVED. A tampered artifact, a law-record or
preregistration hash mismatch, or an effective_trials that disagrees with the
N LAW is a refusal, not a verdict.

Evaluator inputs the law leaves to implementation (fixed here, applied to every
trial alike; no threshold is set by any of them):

* EVAL return and trade count per fold are the summariser's total_return_pct
  and trade_count of the fold's base-fee EVAL run of the TRAIN-selected config.
* Aggregate EVAL return = the sum of those per-fold returns (the law: "sum over
  folds"); the same sum at each stress fee for L2. A stress or base EVAL run
  whose engine fee propagation is not PROVEN leaves COST_STRESS NOT_EVALUABLE.
* DSR returns: an hourly series over each fold's EVAL window (the preregistered
  periods_per_year applies to it), each hour holding the realised profit_abs of
  trades closed in that hour divided by the wallet, folds concatenated in fold
  order. Realised-at-exit, not mark-to-market: Dataset V2 prices are not an
  input of this evaluator.
* DSR trial_sharpes: the annualised Sharpe of each grid configuration's hourly
  series over the LAST fold's TRAIN window (the one window every configuration
  ran on). One configuration gives one Sharpe; with N > 1 the audited wrapper
  then returns NOT_EVALUABLE (TRIALGATE-AUDIT-1 A2.1).
* PBO matrix: those same per-configuration hourly series as columns. One
  configuration gives a one-column matrix, which the wrapper returns
  NOT_EVALUABLE.
* DATA_TRUTH = PASS only when the lock log says "DATASET_LOCK_GATE = PASS" and
  the warm-up log says "WARMUP_OVERLAY_JOIN = PASS"; LOOKAHEAD from the engine's
  own has_bias cell for the strategy (No → PASS, Yes → FAIL); RECURSIVE = PASS
  only when the engine logs both "No variance on indicator(s) found due to
  recursive formula." and "No lookahead bias on indicators found.". Anything
  else, or no log, is NOT_EVALUABLE.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_DIR = REPO_ROOT / "research"
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

from cycle2 import config_n, multiple_testing  # noqa: E402
from cycle2.driver import DriverRefusal, load_prereg  # noqa: E402

DEFAULT_LEDGER = RESEARCH_DIR / "records" / "trial_ledger.jsonl"
LAW_RECORD = "research/cycle2/FUNNEL_LAW_1.md"
CANDIDATE_REGISTRY = RESEARCH_DIR / "external" / "candidate_registry.json"
AUTHORITY = "DERIVED_NON_AUTHORITATIVE"

PASS, FAIL = "PASS", "FAIL"
NOT_EVALUABLE, NOT_APPLICABLE, INCONCLUSIVE = "NOT_EVALUABLE", "NOT_APPLICABLE", "INCONCLUSIVE"
SUFFICIENT, INSUFFICIENT = "SUFFICIENT", "INSUFFICIENT"
REJECTED, SURVIVED = "REJECTED", "SURVIVED"

# L1, Cycle-1 frozen law: a fold with fewer EVAL trades is INSUFFICIENT.
MIN_EVAL_TRADES = 10

GATES = ("DATA_TRUTH", "LOOKAHEAD", "RECURSIVE", "LEDGER_CHAIN", "WALK_FORWARD",
         "PARAMETER_ROBUSTNESS", "COST_STRESS", "MULTIPLE_TESTING")

# NULL SEQUENCING LAW ledger mapping. The ledger has no INCONCLUSIVE state.
LEDGER_STATE = {REJECTED: "REJECTED", SURVIVED: "SURVIVED", INCONCLUSIVE: "COMPLETED"}
CALIBRATION = {REJECTED: "PASS", SURVIVED: "FAIL", INCONCLUSIVE: "NOT_PROVEN"}


class FunnelRefusal(RuntimeError):
    """The evaluator will not produce a verdict: an input is tampered, unbound or inconsistent."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _gate(state: str, reason: str, **extra) -> dict:
    return {"state": state, "reason": reason, **extra}


# -- inputs, re-verified ---------------------------------------------------------


def _checked(artifacts_dir: Path, entry: dict) -> Path:
    path = (artifacts_dir / entry["path"]).resolve()
    try:
        path.relative_to(artifacts_dir.resolve())
    except ValueError as exc:
        raise FunnelRefusal(f"evidence path {entry['path']} lies outside the artifacts directory") from exc
    if not path.is_file():
        raise FunnelRefusal(f"evidence {entry['path']} is missing")
    if sha256_file(path) != entry["sha256"]:
        raise FunnelRefusal(f"evidence {entry['path']} does not match its recorded sha256")
    return path


def load_run(summary_path: Path) -> tuple[dict, Path, list[dict]]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    artifacts_dir = summary_path.parent
    invocations = []
    for entry in summary.get("evidence", []):
        inv = json.loads(_checked(artifacts_dir, entry).read_text(encoding="utf-8"))
        for ev in inv.get("evidence", []):
            _checked(artifacts_dir, ev)
        invocations.append(inv)
    return summary, artifacts_dir, invocations


def _evidence_path(inv: dict, artifacts_dir: Path, *, prefix: str) -> Path | None:
    for ev in inv.get("evidence", []):
        if ev["path"].startswith(prefix):
            return artifacts_dir / ev["path"]
    return None


def _metrics(inv: dict | None, artifacts_dir: Path) -> dict | None:
    if not inv or inv.get("status") != "OK":
        return None
    path = _evidence_path(inv, artifacts_dir, prefix="metrics_")
    return json.loads(path.read_text(encoding="utf-8")) if path else None


def _trades(inv: dict | None, artifacts_dir: Path) -> list[dict] | None:
    if not inv or inv.get("status") != "OK":
        return None
    path = _evidence_path(inv, artifacts_dir, prefix="backtest_results/")
    if path is None:
        return None
    import summarize_backtest as sb

    result = sb.load_result(path)
    _, block = sb.load_strategy_block(result)
    return sb.find_trades(block, result, None)


def _find(invocations: list[dict], *, phase: str, fold: int | None = None, fee: float | None = None,
          config_id: str | None = None) -> dict | None:
    for inv in invocations:
        if inv.get("phase") != phase:
            continue
        if fold is not None and inv.get("fold") != fold:
            continue
        if fee is not None and inv.get("fee_level") != fee:
            continue
        if config_id is not None and inv.get("config_id") != config_id:
            continue
        return inv
    return None


# -- L1 WALK_FORWARD -------------------------------------------------------------------


def walk_forward(prereg: dict, invocations: list[dict], artifacts_dir: Path) -> dict:
    base = prereg["fee_levels"]["base"]
    folds = []
    for fold in sorted(f["fold"] for f in prereg["folds"]):
        inv = _find(invocations, phase="eval", fold=fold, fee=base)
        m = _metrics(inv, artifacts_dir)
        ret = m.get("total_return_pct") if m else None
        trades = m.get("trade_count") if m else None
        usable = (isinstance(ret, (int, float)) and not isinstance(ret, bool) and math.isfinite(ret)
                  and isinstance(trades, int) and not isinstance(trades, bool))
        folds.append({"fold": fold, "config_id": (inv or {}).get("config_id"),
                      "total_return_pct": ret if usable else None, "trade_count": trades if usable else None,
                      "sample": (SUFFICIENT if trades >= MIN_EVAL_TRADES else INSUFFICIENT) if usable
                      else NOT_EVALUABLE})
    if any(f["sample"] == NOT_EVALUABLE for f in folds):
        missing = [f["fold"] for f in folds if f["sample"] == NOT_EVALUABLE]
        return _gate(NOT_EVALUABLE, f"no usable base-fee EVAL metrics for fold(s) {missing}",
                     folds=folds, aggregate_return_pct=None, sample_evidence=NOT_EVALUABLE)
    sample = SUFFICIENT if all(f["sample"] == SUFFICIENT for f in folds) else INSUFFICIENT
    aggregate = sum(f["total_return_pct"] for f in folds)
    common = {"folds": folds, "aggregate_return_pct": aggregate, "sample_evidence": sample}
    # Applied in the order the law writes them.
    if all(f["total_return_pct"] < 0 for f in folds):
        return _gate(FAIL, "selected config's EVAL return < 0 in ALL folds → REJECTED", **common)
    if all(f["sample"] == INSUFFICIENT for f in folds):
        return _gate(INCONCLUSIVE, f"every EVAL fold has trade_count < {MIN_EVAL_TRADES} → INCONCLUSIVE",
                     **common)
    if aggregate > 0:
        return _gate(PASS, "aggregate EVAL return (sum over folds) > 0", **common)
    return _gate(FAIL, "aggregate EVAL return (sum over folds) <= 0 → REJECTED", **common)


# -- L2 COST_STRESS -----------------------------------------------------------------------


def cost_stress(prereg: dict, invocations: list[dict], artifacts_dir: Path, wf: dict) -> dict:
    stress = prereg["fee_levels"]["stress"]
    if not stress:
        return _gate(NOT_EVALUABLE, "no stress fee level is preregistered", levels=[])
    if wf["aggregate_return_pct"] is None:
        return _gate(NOT_EVALUABLE, "base aggregate EVAL return is not evaluable", levels=[])
    folds = sorted(f["fold"] for f in prereg["folds"])
    unproven = [inv.get("invocation") for inv in invocations if inv.get("phase") in ("eval", "cost_stress_eval")
                and inv.get("engine_fee_propagation") != "PROVEN"]
    base_agg = wf["aggregate_return_pct"]
    levels = []
    for fee in stress:
        rets = []
        for fold in folds:
            m = _metrics(_find(invocations, phase="cost_stress_eval", fold=fold, fee=fee), artifacts_dir)
            r = m.get("total_return_pct") if m else None
            rets.append(r if isinstance(r, (int, float)) and not isinstance(r, bool) and math.isfinite(r)
                        else None)
        if None in rets:
            levels.append({"fee": fee, "aggregate_return_pct": None, "flips_sign": None})
        else:
            agg = sum(rets)
            levels.append({"fee": fee, "aggregate_return_pct": agg, "flips_sign": (base_agg > 0) != (agg > 0)})
    # A fee the engine did not provably apply is not a measurement, so it is
    # checked before any sign comparison.
    if unproven:
        return _gate(NOT_EVALUABLE, f"engine fee propagation not PROVEN for {sorted(map(str, unproven))}",
                     levels=levels, base_aggregate_return_pct=base_agg)
    if any(lv["flips_sign"] for lv in levels):
        return _gate(FAIL, "a stress fee level flips the sign of aggregate EVAL return", levels=levels,
                     base_aggregate_return_pct=base_agg)
    if any(lv["flips_sign"] is None for lv in levels):
        return _gate(NOT_EVALUABLE, "a stress fee level has no usable EVAL metrics", levels=levels,
                     base_aggregate_return_pct=base_agg)
    return _gate(PASS, "no stress fee level flips the sign of aggregate EVAL return", levels=levels,
                 base_aggregate_return_pct=base_agg)


# -- L3 MULTIPLE_TESTING ---------------------------------------------------------------------


def _hour0(date8: str) -> datetime:
    return datetime(int(date8[:4]), int(date8[4:6]), int(date8[6:8]), tzinfo=timezone.utc)


def hourly_series(trades: list[dict], window: dict, wallet: float) -> tuple[list[float] | None, str]:
    """Realised profit per closed hour / wallet over the window's hours (00:00 first .. 23:00 last)."""
    import summarize_backtest as sb

    start = _hour0(window["start"])
    hours = int((_hour0(window["end"]) + timedelta(hours=23) - start).total_seconds() // 3600) + 1
    series = [0.0] * hours
    outside = 0
    for t in trades:
        closed = sb.parse_time(sb.pick(t, "close_date", "close_timestamp"))
        profit = sb.as_float(sb.pick(t, "profit_abs", "profit_absolute"))
        if closed is None or profit is None:
            return None, "a trade has no usable close time or profit_abs"
        idx = int((closed - start).total_seconds() // 3600)
        if 0 <= idx < hours:
            series[idx] += profit / wallet
        else:
            outside += 1
    return series, (f"{outside} trade(s) closed outside the window, excluded" if outside else "")


def annualised_sharpe(series: list[float], periods_per_year: int) -> float | None:
    if len(series) < 2:
        return None
    sd = statistics.stdev(series)
    return None if sd == 0.0 else statistics.fmean(series) / sd * math.sqrt(periods_per_year)


def _not_evaluable(threshold: float, n, reason: str) -> dict:
    return {"status": NOT_EVALUABLE, "value": None, "threshold": threshold, "effective_trials": n,
            "observations": None, "reason": reason}


def selection_debt_disclosure() -> dict:
    registry = json.loads(CANDIDATE_REGISTRY.read_text(encoding="utf-8"))
    return {"source": "research/external/candidate_registry.json → multiple_testing_accounting",
            "verbatim": registry["multiple_testing_accounting"]}


def multiple_testing_gate(prereg: dict, invocations: list[dict], artifacts_dir: Path, n_result: dict,
                          wallet: float) -> dict:
    mt = prereg["multiple_testing"]
    ppy = mt["periods_per_year"]
    n = n_result["family_configuration_N"]
    if n_result["status"] == config_n.EVALUATED and n != mt["effective_trials"]:
        raise FunnelRefusal(f"effective_trials {mt['effective_trials']} in the preregistration != "
                            f"family_configuration_N {n} recomputed under the N LAW")

    notes = []
    returns: list[float] | None = []
    base = prereg["fee_levels"]["base"]
    for fold in sorted(f["fold"] for f in prereg["folds"]):
        f = next(x for x in prereg["folds"] if x["fold"] == fold)
        trades = _trades(_find(invocations, phase="eval", fold=fold, fee=base), artifacts_dir)
        series, note = hourly_series(trades, f["eval"], wallet) if trades is not None else (None, "")
        if series is None:
            returns = None
            notes.append(f"fold {fold}: no usable EVAL trade list")
            break
        returns += series
        if note:
            notes.append(f"fold {fold} EVAL: {note}")

    last = max(prereg["folds"], key=lambda x: x["fold"])
    columns: list[list[float]] | None = []
    for cfg in prereg["grid"]:
        trades = _trades(_find(invocations, phase="train_selection", fold=last["fold"],
                               config_id=cfg["config_id"]), artifacts_dir)
        series, note = hourly_series(trades, last["train"], wallet) if trades is not None else (None, "")
        if series is None:
            columns = None
            notes.append(f"config {cfg['config_id']}: no usable fold-{last['fold']} TRAIN trade list")
            break
        columns.append(series)
        if note:
            notes.append(f"config {cfg['config_id']} TRAIN: {note}")

    if n_result["status"] != config_n.EVALUATED:
        dsr = _not_evaluable(mt["dsr_threshold"], None, f"family_configuration_N is NOT_EVALUABLE: "
                                                         f"{n_result['reason']}")
    elif returns is None or columns is None:
        dsr = _not_evaluable(mt["dsr_threshold"], n, "; ".join(notes))
    else:
        sharpes = [s for s in (annualised_sharpe(c, ppy) for c in columns) if s is not None]
        dsr = multiple_testing.dsr(returns, trial_sharpes=sharpes, periods_per_year=ppy,
                                   effective_trials=n, threshold=mt["dsr_threshold"])
    if columns is None:
        pbo = _not_evaluable(mt["pbo_threshold"], len(prereg["grid"]), "; ".join(notes))
    else:
        matrix = [list(row) for row in zip(*columns)]
        pbo = multiple_testing.pbo(matrix, block_count=mt["pbo_block_count"], threshold=mt["pbo_threshold"])

    if FAIL in (dsr["status"], pbo["status"]):
        state, reason = FAIL, "a multiple-testing statistic FAILED its preregistered threshold"
    elif dsr["status"] == PASS and pbo["status"] == PASS:
        state, reason = PASS, "DSR and PBO both PASS at the preregistered thresholds"
    else:
        state, reason = NOT_EVALUABLE, "a multiple-testing statistic is NOT_EVALUABLE (never PASS)"
    pbo_disclosure = ("PBO is NOT_EVALUABLE with a single configuration. This trial does not validate PBO; "
                      "PBO's first real exercise is a multi-configuration trial."
                      if len(prereg["grid"]) == 1 else
                      "PBO evaluated over the preregistered grid's last-fold TRAIN series.")
    return _gate(state, reason, dsr=dsr, pbo=pbo, family_configuration_N=n,
                 n_status=n_result["status"], n_derivation=n_result["derivation"],
                 preregistered_effective_trials=mt["effective_trials"],
                 selection_debt=selection_debt_disclosure(),
                 selection_debt_statement=prereg["selection_debt_statement"],
                 pbo_disclosure=pbo_disclosure, notes=notes)


# -- pre-engine gates, from the workflow's logs ------------------------------------------------


def _read(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def data_truth(lock_log: Path | None, warmup_log: Path | None) -> dict:
    lock, warm = _read(lock_log), _read(warmup_log)
    if lock is None or warm is None:
        return _gate(NOT_EVALUABLE, "data-lock or warm-up log not supplied")
    if "DATASET_LOCK_GATE = FAIL" in lock or "WARMUP_OVERLAY_JOIN = FAIL" in warm:
        return _gate(FAIL, "data lock or warm-up overlay gate FAILED")
    if "DATASET_LOCK_GATE = PASS" in lock and "WARMUP_OVERLAY_JOIN = PASS" in warm:
        return _gate(PASS, "DATASET_LOCK_GATE = PASS and WARMUP_OVERLAY_JOIN = PASS")
    return _gate(NOT_EVALUABLE, "data-lock or warm-up log carries no gate verdict")


def lookahead(log: Path | None, strategy: str) -> dict:
    text = _read(log)
    if text is None:
        return _gate(NOT_EVALUABLE, "lookahead log not supplied")
    header = None
    for line in text.splitlines():
        cells = [c.strip() for c in line.replace("┃", "|").replace("│", "|").split("|")]
        if "has_bias" in cells and "strategy" in cells:
            header = cells
            continue
        if header and len(cells) == len(header) and cells[header.index("strategy")] == strategy:
            bias = cells[header.index("has_bias")]
            if bias in ("No", "False"):
                return _gate(PASS, f"lookahead-analysis has_bias = {bias}")
            if bias in ("Yes", "True"):
                return _gate(FAIL, f"lookahead-analysis has_bias = {bias}")
    return _gate(NOT_EVALUABLE, f"no lookahead-analysis has_bias row for {strategy}")


def recursive(log: Path | None) -> dict:
    text = _read(log)
    if text is None:
        return _gate(NOT_EVALUABLE, "recursive-analysis log not supplied")
    if ("No variance on indicator(s) found due to recursive formula." in text
            and "No lookahead bias on indicators found." in text):
        return _gate(PASS, "no recursive variance and no indicator lookahead bias")
    return _gate(NOT_EVALUABLE, "recursive-analysis log does not state both no-variance and no-bias")


def ledger_chain(ledger_path: Path, prereg: dict, prereg_sha: str) -> dict:
    ledger = config_n._ledger(ledger_path)
    problems = ledger.verify()
    records = ledger.records() if not problems else []
    mine = [r.payload for r in records if r.payload.get("trial_id") == prereg["trial_id"]]
    bound = any(p.get("state") == "PREREGISTERED"
                and (p.get("dataset_identity") or {}).get("prereg_sha256") == prereg_sha for p in mine)
    info = {"verify": "PASS" if not problems else "FAIL", "binding": "BOUND" if bound else "NOT_BOUND",
            "records": len(records), "terminal_present": any(p.get("state") != "PREREGISTERED" for p in mine)}
    if problems:
        return _gate(FAIL, f"ledger does not verify: {problems}", ledger=info)
    if not bound:
        return _gate(FAIL, "no ledger preregistration carries this preregistration's sha256", ledger=info)
    return _gate(PASS, "ledger verifies and the preregistration is BOUND", ledger=info)


# -- the law ---------------------------------------------------------------------------------


def decide(gates: dict, sample: str) -> str:
    states = {name: g["state"] for name, g in gates.items() if g["state"] != NOT_APPLICABLE}
    if FAIL in states.values():
        return REJECTED
    if all(s == PASS for s in states.values()) and sample == SUFFICIENT:
        return SURVIVED
    return INCONCLUSIVE


def evaluate(run_summary_path: Path, prereg_path: Path, ledger_path: Path = DEFAULT_LEDGER, *,
             data_lock_log: Path | None = None, warmup_log: Path | None = None,
             lookahead_log: Path | None = None, recursive_log: Path | None = None) -> dict:
    try:
        prereg = load_prereg(prereg_path)
    except DriverRefusal as exc:
        raise FunnelRefusal(str(exc)) from exc
    prereg_sha = sha256_file(prereg_path)
    law = prereg["funnel_law"]
    law_path = REPO_ROOT / law["record"]
    if law["record"] != LAW_RECORD or not law_path.is_file() or sha256_file(law_path) != law["sha256"]:
        raise FunnelRefusal(f"preregistration binds funnel law {law['record']} @ {law['sha256']}, which does "
                            f"not match {LAW_RECORD} on disk")

    summary, artifacts_dir, invocations = load_run(run_summary_path)
    if summary.get("trial_id") != prereg["trial_id"] or summary.get("prereg_sha256") != prereg_sha:
        raise FunnelRefusal("run summary does not belong to this preregistration (trial_id or prereg_sha256)")
    if any(inv.get("trial_id") != prereg["trial_id"] for inv in invocations):
        raise FunnelRefusal("an invocation summary names a different trial")

    try:
        n_result = config_n.family_configuration_n(prereg["family_id"], ledger_path=ledger_path,
                                                   extra_preregs=[prereg])
    except config_n.ConfigNRefusal as exc:
        raise FunnelRefusal(f"N LAW refused: {exc}") from exc

    null = prereg["lineage_kind"] == "NULL_CALIBRATION"
    wf = walk_forward(prereg, invocations, artifacts_dir)
    chain = ledger_chain(ledger_path, prereg, prereg_sha)
    gates = {
        "DATA_TRUTH": data_truth(data_lock_log, warmup_log),
        "LOOKAHEAD": lookahead(lookahead_log, prereg["strategy"]["name"]),
        "RECURSIVE": recursive(recursive_log),
        "LEDGER_CHAIN": chain,
        "WALK_FORWARD": wf,
        "PARAMETER_ROBUSTNESS": (
            _gate(NOT_APPLICABLE, "lineage_kind NULL_CALIBRATION has no parameters") if null else
            _gate(NOT_EVALUABLE, "required for this lineage; no robustness criterion is machine-specified by "
                                 "the preregistration, so it cannot be evaluated here (never PASS)")),
        "COST_STRESS": cost_stress(prereg, invocations, artifacts_dir, wf),
        "MULTIPLE_TESTING": multiple_testing_gate(prereg, invocations, artifacts_dir, n_result,
                                                  float(prereg["wallet"])),
    }
    result = decide(gates, wf["sample_evidence"])
    calibration = None
    if null:
        verdict = CALIBRATION[result]
        calibration = {"verdict": verdict, "cycle2_stop": verdict != "PASS",
                       "rejected_by": sorted(k for k, g in gates.items() if g["state"] == FAIL),
                       "rule": "null REJECTED → PASS; SURVIVED → FAIL → STOP; INCONCLUSIVE → NOT_PROVEN → STOP"}
    outcome = {"funnel_result": result, "engine_invocations": summary.get("invocations_executed")}
    if prereg["trial_class"] == "scientific":
        outcome["config_ids"] = [c["config_id"] for c in prereg["grid"]]
    return {
        "authority": AUTHORITY,
        "evaluator": "research/cycle2/funnel.py",
        "funnel_law": {"record": law["record"], "sha256": law["sha256"]},
        "cycle_id": prereg["cycle_id"],
        "family_id": prereg["family_id"], "lineage_id": prereg["lineage_id"],
        "lineage_kind": prereg["lineage_kind"], "candidate_id": prereg["candidate_id"],
        "config_ids": [c["config_id"] for c in prereg["grid"]],
        "trial_id": prereg["trial_id"], "experiment_id": prereg["experiment_id"], "run_id": prereg["run_id"],
        "trial_class": prereg["trial_class"], "funnel_step": prereg["funnel_step"],
        "prereg_sha256": prereg_sha,
        "budget": summary.get("budget"),
        "ledger": chain["ledger"],
        "gates": gates,
        "sample_evidence": wf["sample_evidence"],
        "funnel_result": result,
        "terminal_proposal": {"ledger_state": LEDGER_STATE[result], "outcome": outcome,
                              "proposal_only": True},
        "calibration": calibration,
        "cycle2_stop": bool(calibration and calibration["cycle2_stop"]),
        "note": "Derived and non-authoritative. This evaluator never writes the ledger; the terminal record "
                "is the operator's own append.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-summary", required=True, type=Path)
    parser.add_argument("--prereg", required=True, type=Path)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--data-lock-log", type=Path)
    parser.add_argument("--warmup-log", type=Path)
    parser.add_argument("--lookahead-log", type=Path)
    parser.add_argument("--recursive-log", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        report = evaluate(args.run_summary, args.prereg, args.ledger, data_lock_log=args.data_lock_log,
                          warmup_log=args.warmup_log, lookahead_log=args.lookahead_log,
                          recursive_log=args.recursive_log)
    except (FunnelRefusal, OSError, ValueError, KeyError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("trial_id", "funnel_result", "cycle2_stop")}
                     | {"gates": {k: v["state"] for k, v in report["gates"].items()},
                        "calibration": (report["calibration"] or {}).get("verdict")},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
