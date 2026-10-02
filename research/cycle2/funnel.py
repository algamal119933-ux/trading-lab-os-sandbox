#!/usr/bin/env python3
"""Deterministic evaluator of the frozen Cycle-2 funnel law (research/cycle2/FUNNEL_LAW_1.md).

Inputs: one driver run summary (cycle2_run_summary.json and the artifacts it
names, every one re-hashed against the sha256 the driver recorded), the
preregistration it ran, and the canonical trial ledger, read-only. Optional gate
logs from the workflow (data lock, warm-up join, lookahead, recursive), and the
exposure-matched passive benchmarks the workflow computes per EVAL fold and fee
level with freqtrade/user_data/baseline_benchmarks.py (unchanged code).

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
* L1/L2 benchmark: `<benchmark-dir>/fold<N>_fee<fee>.json`, written by
  baseline_benchmarks.py for period `fold<N>_eval` over exactly the summariser's
  window (00:00 first day .. 23:00 last day). It is used only if its period, fee,
  window, pair universe and wallet match the preregistration; otherwise that
  fold is NOT_EVALUABLE. excess_f = total_return_pct − 100 × exposure_matched_return
  (both in percent).
* L2 sums excess over the folds L1 found SUFFICIENT; with none, COST_STRESS is
  NOT_EVALUABLE. A stress or base EVAL run whose engine fee propagation is not
  PROVEN leaves COST_STRESS NOT_EVALUABLE.
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

INVALID_RUN = "INVALID_RUN"
# A null whose integrity gate is not PASS is an invalid run: it can never certify the funnel.
INTEGRITY_GATES = ("DATA_TRUTH", "LOOKAHEAD", "RECURSIVE", "LEDGER_CHAIN")
# The law's L1, L2 and L3: the only gates whose FAIL can earn a null CALIBRATION = PASS.
PERFORMANCE_GATES = ("WALK_FORWARD", "COST_STRESS", "MULTIPLE_TESTING")

# NULL SEQUENCING LAW ledger mapping. The ledger has no INCONCLUSIVE or INVALID state.
LEDGER_STATE = {REJECTED: "REJECTED", SURVIVED: "SURVIVED", INCONCLUSIVE: "COMPLETED",
                INVALID_RUN: "COMPLETED"}
CALIBRATION = {REJECTED: "PASS", SURVIVED: "FAIL", INCONCLUSIVE: "NOT_PROVEN", INVALID_RUN: "NOT_PROVEN"}


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


# -- the exposure-matched passive benchmark (baseline_benchmarks.py output) ----------------


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def benchmark_file(benchmark_dir: Path, fold: int, fee: float) -> Path:
    return benchmark_dir / f"fold{fold}_fee{fee:g}.json"


def load_benchmark(prereg: dict, benchmark_dir: Path | None, fold: dict, fee: float) -> tuple[dict | None, str]:
    """The fold's exposure-matched passive return at ``fee``, or None and why it is unusable."""
    if benchmark_dir is None:
        return None, "no benchmark directory supplied"
    path = benchmark_file(benchmark_dir, fold["fold"], fee)
    if not path.is_file():
        return None, f"{path.name} is missing"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        result = report["result"]
        expected = {
            "requested_period": f"fold{fold['fold']}_eval",
            "fee_per_side": fee,
            "window_start": f"{fold['eval']['start'][:4]}-{fold['eval']['start'][4:6]}-{fold['eval']['start'][6:]}"
                            "T00:00:00Z",
            "window_end": f"{fold['eval']['end'][:4]}-{fold['eval']['end'][4:6]}-{fold['eval']['end'][6:]}"
                          "T23:00:00Z",
            "universe": prereg.get("pair_universe"),
            "exposure_matched_wallet_start": float(prereg["wallet"]),
        }
        observed = {
            "requested_period": report["requested_period"], "fee_per_side": report["fee_per_side"],
            "window_start": result["window_start"], "window_end": result["window_end"],
            "universe": result["universe"],
            "exposure_matched_wallet_start": result["exposure_matched_wallet_start"],
        }
        ret = result["exposure_matched_return"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, f"{path.name} is unreadable: {exc!r}"
    wrong = sorted(k for k in expected if observed[k] != expected[k])
    if wrong:
        return None, f"{path.name} does not match the preregistration on {wrong}"
    if not _finite(ret):
        return None, f"{path.name} has no finite exposure_matched_return"
    return {"file": path.name, "sha256": sha256_file(path), "exposure_matched_return_pct": 100.0 * ret,
            "methodology": result.get("max_exposure_matched_methodology")}, ""


# -- L1 WALK_FORWARD (benchmark-relative) ------------------------------------------------------


def walk_forward(prereg: dict, invocations: list[dict], artifacts_dir: Path,
                 benchmark_dir: Path | None = None) -> dict:
    base = prereg["fee_levels"]["base"]
    folds, problems = [], []
    for f in sorted(prereg["folds"], key=lambda x: x["fold"]):
        inv = _find(invocations, phase="eval", fold=f["fold"], fee=base)
        m = _metrics(inv, artifacts_dir)
        ret = m.get("total_return_pct") if m else None
        trades = m.get("trade_count") if m else None
        usable = _finite(ret) and isinstance(trades, int) and not isinstance(trades, bool)
        bench, why = load_benchmark(prereg, benchmark_dir, f, base)
        if not usable:
            problems.append(f"fold {f['fold']}: no usable base-fee EVAL metrics")
        if bench is None:
            problems.append(f"fold {f['fold']}: benchmark unusable ({why})")
        folds.append({
            "fold": f["fold"], "config_id": (inv or {}).get("config_id"),
            "total_return_pct": ret if usable else None, "trade_count": trades if usable else None,
            "benchmark": bench,
            "excess_pct": (ret - bench["exposure_matched_return_pct"]) if usable and bench else None,
            "sample": (SUFFICIENT if trades >= MIN_EVAL_TRADES else INSUFFICIENT) if usable else NOT_EVALUABLE,
        })
    if problems:
        return _gate(NOT_EVALUABLE, "; ".join(problems), folds=folds, aggregate_excess_pct=None,
                     sufficient_folds=[], sample_evidence=NOT_EVALUABLE)
    sample = SUFFICIENT if all(f["sample"] == SUFFICIENT for f in folds) else INSUFFICIENT
    sufficient = [f["fold"] for f in folds if f["sample"] == SUFFICIENT]
    aggregate = sum(f["excess_pct"] for f in folds if f["sample"] == SUFFICIENT)
    common = {"folds": folds, "aggregate_excess_pct": aggregate if sufficient else None,
              "sufficient_folds": sufficient, "sample_evidence": sample}
    # Applied in the order the law writes them.
    if all(f["excess_pct"] < 0 for f in folds):
        return _gate(FAIL, "excess over the exposure-matched passive < 0 in ALL folds → REJECTED", **common)
    if not sufficient:
        return _gate(INCONCLUSIVE, f"every EVAL fold has trade_count < {MIN_EVAL_TRADES} → INCONCLUSIVE",
                     **common)
    if aggregate > 0:
        return _gate(PASS, "Σ excess over sufficient folds > 0", **common)
    return _gate(FAIL, "Σ excess over sufficient folds <= 0 → REJECTED", **common)


# -- L2 COST_STRESS (benchmark-relative) ---------------------------------------------------------


def cost_stress(prereg: dict, invocations: list[dict], artifacts_dir: Path, wf: dict,
                benchmark_dir: Path | None = None) -> dict:
    stress = prereg["fee_levels"]["stress"]
    if not stress:
        return _gate(NOT_EVALUABLE, "no stress fee level is preregistered", levels=[])
    if wf["state"] == NOT_EVALUABLE or not wf["sufficient_folds"]:
        return _gate(NOT_EVALUABLE, "no sufficient fold with a usable base excess", levels=[])
    folds = [f for f in sorted(prereg["folds"], key=lambda x: x["fold"]) if f["fold"] in wf["sufficient_folds"]]
    unproven = [inv.get("invocation") for inv in invocations if inv.get("phase") in ("eval", "cost_stress_eval")
                and inv.get("engine_fee_propagation") != "PROVEN"]
    levels = []
    for fee in stress:
        excess, notes = [], []
        for f in folds:
            m = _metrics(_find(invocations, phase="cost_stress_eval", fold=f["fold"], fee=fee), artifacts_dir)
            r = m.get("total_return_pct") if m else None
            bench, why = load_benchmark(prereg, benchmark_dir, f, fee)
            if not _finite(r) or bench is None:
                excess.append(None)
                notes.append(f"fold {f['fold']}: " + (why if bench is None else "no usable stress EVAL metrics"))
            else:
                excess.append(r - bench["exposure_matched_return_pct"])
        agg = None if None in excess else sum(excess)
        levels.append({"fee": fee, "folds": [f["fold"] for f in folds], "aggregate_excess_pct": agg,
                       "non_positive": None if agg is None else agg <= 0, "notes": notes})
    common = {"levels": levels, "base_aggregate_excess_pct": wf["aggregate_excess_pct"]}
    # A fee the engine did not provably apply is not a measurement, so it is
    # checked before any comparison.
    if unproven:
        return _gate(NOT_EVALUABLE, f"engine fee propagation not PROVEN for {sorted(map(str, unproven))}",
                     **common)
    if any(lv["non_positive"] for lv in levels):
        return _gate(FAIL, "a stress fee level makes Σ excess <= 0", **common)
    if any(lv["non_positive"] is None for lv in levels):
        return _gate(NOT_EVALUABLE, "a stress fee level has no usable EVAL metrics or benchmark", **common)
    return _gate(PASS, "Σ excess > 0 at every stress fee level", **common)


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
             lookahead_log: Path | None = None, recursive_log: Path | None = None,
             benchmark_dir: Path | None = None) -> dict:
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
    wf = walk_forward(prereg, invocations, artifacts_dir, benchmark_dir)
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
        "COST_STRESS": cost_stress(prereg, invocations, artifacts_dir, wf, benchmark_dir),
        "MULTIPLE_TESTING": multiple_testing_gate(prereg, invocations, artifacts_dir, n_result,
                                                  float(prereg["wallet"])),
    }
    law_result = decide(gates, wf["sample_evidence"])
    result = law_result
    calibration = None
    if null:
        invalid = [g for g in INTEGRITY_GATES if gates[g]["state"] != PASS]
        if invalid:
            result = INVALID_RUN
        verdict = CALIBRATION[result]
        calibration = {"verdict": verdict, "cycle2_stop": verdict != "PASS",
                       "rejected_by": sorted(g for g in PERFORMANCE_GATES if gates[g]["state"] == FAIL),
                       "integrity_not_pass": invalid,
                       "law_result_before_integrity_rule": law_result,
                       "rule": "null REJECTED by L1/L2/L3 with every integrity gate PASS → PASS; any integrity "
                               "gate ≠ PASS → INVALID_RUN → NOT_PROVEN → STOP; SURVIVED → FAIL → STOP; "
                               "INCONCLUSIVE → NOT_PROVEN → STOP"}
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
    parser.add_argument("--benchmark-dir", type=Path,
                        help="baseline_benchmarks.py outputs, fold<N>_fee<fee>.json per EVAL fold and fee level")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        report = evaluate(args.run_summary, args.prereg, args.ledger, data_lock_log=args.data_lock_log,
                          warmup_log=args.warmup_log, lookahead_log=args.lookahead_log,
                          recursive_log=args.recursive_log, benchmark_dir=args.benchmark_dir)
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
