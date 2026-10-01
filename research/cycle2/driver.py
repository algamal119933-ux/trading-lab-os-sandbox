#!/usr/bin/env python3
"""Strategy-agnostic walk-forward / robustness driver for Cycle 2 (OPENING-1 §6.1 + §6.2).

Generalises research/mean_reversion/run_walkforward.py and
research/h1_qualification/run_qualification.py without changing either: the
same `docker run ... freqtrade backtesting` argv shape, the same
research/summarize_backtest.py normalisation, `--export trades` on every run.
What those scripts froze as module constants — strategy, grid, folds, fee
levels — comes here ONLY from a preregistration JSON validated against
research/cycle2/prereg.schema.json. There is no Hyperopt and no sweep syntax.

Fee/friction proxy (§6.2): every preregistered per-side fee level is passed to
the ENGINE with `--fee`, and the same value to the summariser — the defect
Mean-Reversion Cycle 1 had was a fee that reached only the summariser. It is
labelled a symmetric fee proxy; slippage, latency and partial fills are emitted
as NOT_SUPPORTED. The proof that the engine applied it is read from the
engine's own "Using fee" log line, at the first real run (§7.2).

Hard caps (§3): before anything runs, the planned invocations are added to what
the canonical trial ledger already records for Cycle 2, and the driver refuses
to start if any cap would be exceeded. It reads the ledger and never writes it;
preregistration and terminal records stay the operator's own ledger appends.

Every run writes a deterministic JSON summary (§11): derived, non-authoritative,
rebuildable from the artifacts it names. `--dry-run` prints the plan and the
budget and executes nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_DIR = REPO_ROOT / "research"
SCHEMA_PATH = Path(__file__).resolve().parent / "prereg.schema.json"
DEFAULT_LEDGER = RESEARCH_DIR / "records" / "trial_ledger.jsonl"

USER_DATA = REPO_ROOT / "freqtrade" / "user_data"
STRATEGY_DIR = USER_DATA / "strategies"
BACKTEST_RESULTS = USER_DATA / "backtest_results"
CONFIG_PATH_CONTAINER = "/freqtrade/user_data/config.research.json"
STRATEGY_PATH_CONTAINER = "/freqtrade/user_data/strategies"

CYCLE_ID = "OFFLINE-RESEARCH-CYCLE-2"
EXPERIMENT_PREFIX = "EXP-CYCLE2-"
FEE_MODEL = "symmetric fee proxy"
FRICTION = {"slippage": "NOT_SUPPORTED", "latency": "NOT_SUPPORTED", "partial_fills": "NOT_SUPPORTED"}
AUTHORITY = "DERIVED_NON_AUTHORITATIVE"

# OPENING-1 §3, verbatim. Hard caps, not targets; this module never extends one.
CAPS = {
    "engine_invocations": 120,
    "scientific_configurations": 24,
    "scientific_trial_ids": 12,
    "calibration_trial_ids": 6,
}
# §3 sub-limits sit inside the 24, never added to it.
CONFIG_SUBLIMITS = {"TREND": 12, "MEAN_REVERSION": 8}
REGIME_GATED_SUBLIMIT = 4

DEVELOPMENT_START, DEVELOPMENT_END = "20210101", "20241231"


class DriverRefusal(RuntimeError):
    """The driver will not start: a cap, the ledger, the schema or an identity says no."""


# -- preregistration ---------------------------------------------------------


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_prereg(path: Path) -> dict:
    import jsonschema

    prereg = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(prereg, schema)
    except jsonschema.exceptions.ValidationError as exc:
        raise DriverRefusal(f"preregistration does not match prereg.schema.json: {exc.message}") from exc
    check_semantics(prereg)
    return prereg


def check_semantics(prereg: dict) -> None:
    """What a schema cannot say: ordering, uniqueness and class/prefix agreement."""
    cls = "SCI" if prereg["trial_class"] == "scientific" else "CAL"
    if not prereg["experiment_id"].startswith(f"{EXPERIMENT_PREFIX}{cls}-"):
        raise DriverRefusal(f"experiment_id {prereg['experiment_id']} does not match trial_class "
                            f"{prereg['trial_class']}")
    ids = [c["config_id"] for c in prereg["grid"]]
    if len(set(ids)) != len(ids):
        raise DriverRefusal("grid config_ids are not unique")
    params = [json.dumps(c["params"], sort_keys=True) for c in prereg["grid"]]
    if len(set(params)) != len(params):
        raise DriverRefusal("two grid entries carry identical params")
    folds = [f["fold"] for f in prereg["folds"]]
    if len(set(folds)) != len(folds):
        raise DriverRefusal("fold numbers are not unique")
    windows = [w for f in prereg["folds"] for w in (f["train"], f["eval"])]
    if "robustness" in prereg["lanes"]:
        windows.append(prereg["robustness_window"])
    for w in windows:
        if not (DEVELOPMENT_START <= w["start"] <= w["end"] <= DEVELOPMENT_END):
            raise DriverRefusal(f"window {w} is not an ordered window inside Development "
                                f"{DEVELOPMENT_START}-{DEVELOPMENT_END}")
    for f in prereg["folds"]:
        if not f["train"]["end"] < f["eval"]["start"]:
            raise DriverRefusal(f"fold {f['fold']}: eval does not start after train ends")
    if prereg["fee_levels"]["base"] in prereg["fee_levels"]["stress"]:
        raise DriverRefusal("a stress fee level equals the base fee")


# -- plan --------------------------------------------------------------------


def timerange(window: dict) -> str:
    return f"{window['start']}-{window['end']}"


def iso(date8: str, end: bool = False) -> str:
    y, m, d = date8[:4], date8[4:6], date8[6:8]
    return f"{y}-{m}-{d}T{'23:00:00' if end else '00:00:00'}Z"


def fee_tag(fee: float) -> str:
    return f"fee{fee:g}"


def build_plan(prereg: dict) -> list[dict]:
    """Every engine invocation the preregistration implies, in execution order.

    Walk-forward, per fold: every grid config on TRAIN at the base fee, then the
    TRAIN-selected config on EVAL at the base fee and at every stress fee.
    Robustness: every grid config over the robustness window at the base fee.
    """
    base, stress = prereg["fee_levels"]["base"], prereg["fee_levels"]["stress"]
    plan: list[dict] = []
    if "walk_forward" in prereg["lanes"]:
        for fold in prereg["folds"]:
            n = fold["fold"]
            for cfg in prereg["grid"]:
                plan.append({"lane": "walk_forward", "fold": n, "phase": "train_selection",
                             "config_id": cfg["config_id"], "window": fold["train"], "fee": base,
                             "label": f"fold{n}_train_{cfg['config_id']}_{fee_tag(base)}"})
            for phase, fee in [("eval", base)] + [("cost_stress_eval", f) for f in stress]:
                plan.append({"lane": "walk_forward", "fold": n, "phase": phase,
                             "config_id": None, "window": fold["eval"], "fee": fee,
                             "label": f"fold{n}_{phase}_SELECTED_{fee_tag(fee)}"})
    if "robustness" in prereg["lanes"]:
        for cfg in prereg["grid"]:
            plan.append({"lane": "robustness", "fold": None, "phase": "robustness",
                         "config_id": cfg["config_id"], "window": prereg["robustness_window"],
                         "fee": base, "label": f"robustness_{cfg['config_id']}_{fee_tag(base)}"})
    for i, step in enumerate(plan, start=1):
        step["invocation"] = i
    return plan


# -- budget, from the canonical ledger (read-only) -------------------------------


def _ledger(path: Path):
    if str(RESEARCH_DIR) not in sys.path:
        sys.path.insert(0, str(RESEARCH_DIR))
    from trial_ledger import TERMINAL_STATES, TrialLedger

    return TrialLedger(path), TERMINAL_STATES


def ledger_budget(prereg: dict, prereg_sha256: str, ledger_path: Path) -> dict:
    """What Cycle 2 has already consumed, per the ledger, and this trial's binding.

    Fail-closed: a ledger that does not verify, another Cycle-2 trial still open,
    or a closed Cycle-2 trial whose terminal outcome does not state its
    consumption (outcome.engine_invocations, and outcome.config_ids for a
    scientific trial) is a refusal, never a zero.
    """
    ledger, terminal_states = _ledger(ledger_path)
    problems = ledger.verify()
    if problems:
        raise DriverRefusal(f"trial ledger does not verify: {problems}")

    trials: dict[str, dict] = {}
    for record in ledger:
        p = record.payload
        if not str(p.get("experiment_id", "")).startswith(EXPERIMENT_PREFIX):
            continue
        t = trials.setdefault(p["trial_id"], {"prereg": None, "terminal": None,
                                              "experiment_id": p["experiment_id"],
                                              "lineage_id": p["lineage_id"]})
        if p["state"] == "PREREGISTERED":
            t["prereg"] = p
        elif p["state"] in terminal_states:
            t["terminal"] = p

    me = prereg["trial_id"]
    consumed = {"engine_invocations": 0, "scientific_trial_ids": 0, "calibration_trial_ids": 0}
    config_keys: set[str] = set()
    lineage_configs: dict[str, set[str]] = {}
    for trial_id, t in sorted(trials.items()):
        scientific = t["experiment_id"].startswith(f"{EXPERIMENT_PREFIX}SCI-")
        consumed["scientific_trial_ids" if scientific else "calibration_trial_ids"] += 1
        if trial_id == me:
            continue
        if t["terminal"] is None:
            raise DriverRefusal(f"Cycle-2 trial {trial_id} is preregistered but not closed; its "
                                "consumption is unknown, so no budget can be computed")
        outcome = t["terminal"].get("outcome") or {}
        invocations = outcome.get("engine_invocations")
        if isinstance(invocations, bool) or not isinstance(invocations, int) or invocations < 0:
            raise DriverRefusal(f"Cycle-2 trial {trial_id}: terminal outcome does not state "
                                "engine_invocations")
        consumed["engine_invocations"] += invocations
        if scientific:
            cids = outcome.get("config_ids")
            if not isinstance(cids, list) or not all(isinstance(c, str) and c for c in cids):
                raise DriverRefusal(f"Cycle-2 trial {trial_id}: terminal outcome does not state config_ids")
            keys = {f"{t['lineage_id']}::{c}" for c in cids}
            config_keys |= keys
            lineage_configs.setdefault(t["lineage_id"], set()).update(keys)

    binding = "NOT_PREREGISTERED"
    if me in trials:
        mine = trials[me]
        if mine["terminal"] is not None:
            raise DriverRefusal(f"{me} already has a terminal ledger record; a trial is never re-run")
        identity = (mine["prereg"] or {}).get("dataset_identity") or {}
        if identity.get("prereg_sha256") != prereg_sha256:
            raise DriverRefusal(f"{me}: ledger preregistration does not carry this file's sha256 "
                                f"({prereg_sha256}) in dataset_identity.prereg_sha256")
        for field in ("family_id", "lineage_id", "candidate_id", "experiment_id", "run_id"):
            if mine["prereg"].get(field) != prereg[field]:
                raise DriverRefusal(f"{me}: ledger {field} {mine['prereg'].get(field)!r} != "
                                    f"preregistration {prereg[field]!r}")
        binding = "BOUND"
    else:
        # Not in the ledger yet: count it as if it were, so a plan never fits
        # only because its own trial ID was left out.
        consumed["scientific_trial_ids" if prereg["trial_class"] == "scientific"
                 else "calibration_trial_ids"] += 1

    return {"consumed": consumed, "config_keys": config_keys, "lineage_configs": lineage_configs,
            "binding": binding, "ledger_verify": "PASS", "ledger_records": len(ledger.records())}


def budget(prereg: dict, plan: list[dict], ledger_state: dict) -> dict:
    planned_invocations = len(plan)
    consumed = dict(ledger_state["consumed"])
    config_keys = set(ledger_state["config_keys"])
    lineage = prereg["lineage_id"]
    lineage_keys = set(ledger_state["lineage_configs"].get(lineage, set()))
    if prereg["trial_class"] == "scientific":
        mine = {f"{lineage}::{c['config_id']}" for c in prereg["grid"]}
        config_keys |= mine
        lineage_keys |= mine
    after = {
        "engine_invocations": consumed["engine_invocations"] + planned_invocations,
        "scientific_configurations": len(config_keys),
        "scientific_trial_ids": consumed["scientific_trial_ids"],
        "calibration_trial_ids": consumed["calibration_trial_ids"],
    }
    refusals = [f"{k}: {after[k]} > cap {CAPS[k]}" for k in CAPS if after[k] > CAPS[k]]
    sublimit = CONFIG_SUBLIMITS.get(prereg["lineage_kind"])
    if prereg["trial_class"] == "scientific" and sublimit is not None and len(lineage_keys) > sublimit:
        refusals.append(f"{prereg['lineage_kind']} configurations in {lineage}: {len(lineage_keys)} > "
                        f"sub-limit {sublimit}")
    gated = sum(1 for c in prereg["grid"] if c["regime_gated"])
    if prereg["trial_class"] == "scientific" and gated > REGIME_GATED_SUBLIMIT:
        refusals.append(f"regime/session-gated configurations: {gated} > sub-limit {REGIME_GATED_SUBLIMIT}")
    return {
        "caps": dict(CAPS),
        "consumed_before": {"engine_invocations": consumed["engine_invocations"],
                            "scientific_configurations": len(ledger_state["config_keys"]),
                            "scientific_trial_ids": consumed["scientific_trial_ids"],
                            "calibration_trial_ids": consumed["calibration_trial_ids"]},
        "planned_invocations": planned_invocations,
        "consumed_after": after,
        "remaining_after": {k: CAPS[k] - after[k] for k in CAPS},
        "refusals": refusals,
    }


# -- engine invocation (the Cycle-1 shape, fee added) ----------------------------


def _ensure_writable(path: Path) -> None:
    """The Freqtrade image re-chowns the bind-mounted tree on every run; reclaim
    it before every write and read (GitHub-hosted runners have passwordless sudo).
    Same mechanism as the Cycle-1 drivers."""
    if not path.exists():
        return
    subprocess.run(["sudo", "chown", "-R", f"{os.getuid()}:{os.getgid()}", str(path)], check=False)


def write_params(strategy: str, params: dict) -> None:
    _ensure_writable(STRATEGY_DIR)
    target = STRATEGY_DIR / f"{strategy}.json"
    if target.exists():
        _ensure_writable(target)
    target.write_text(json.dumps({"strategy_name": strategy, "params": params}, indent=2, sort_keys=True)
                      + "\n", encoding="utf-8")


def backtest_argv(image: str, strategy: str, window: dict, fee: float) -> list[str]:
    return [
        "docker", "run", "--rm",
        "-v", f"{USER_DATA}:/freqtrade/user_data",
        image, "backtesting",
        "--config", CONFIG_PATH_CONTAINER,
        "--strategy", strategy, "--strategy-path", STRATEGY_PATH_CONTAINER,
        "--timerange", timerange(window), "--timeframe-detail", "5m",
        "--enable-protections", "--export", "trades",
        "--fee", repr(float(fee)),
    ]


def engine_fee_propagation(fee_line: str | None, fee: float) -> str:
    if not fee_line:
        return "UNPROVEN"
    return "PROVEN" if f"{fee * 100:.4f}%" in fee_line else "UNPROVEN"


def run_backtest(image: str, strategy: str, window: dict, fee: float, label: str,
                 artifacts_dir: Path) -> dict:
    _ensure_writable(BACKTEST_RESULTS)
    log_path = artifacts_dir / f"backtest_{label}.log"
    with open(log_path, "w", encoding="utf-8") as fh:
        proc = subprocess.run(backtest_argv(image, strategy, window, fee), stdout=fh, stderr=subprocess.STDOUT)
    _ensure_writable(BACKTEST_RESULTS)
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    fee_line = next((ln for ln in log_text.splitlines() if "Using fee" in ln), None)
    common = {"log_path": str(log_path.relative_to(artifacts_dir)), "effective_fee_line": fee_line,
              "engine_fee_propagation": engine_fee_propagation(fee_line, fee)}
    ok = proc.returncode == 0 and not any(
        m in log_text for m in ("CRITICAL - Invalid configuration", "Configuration error",
                                "OperationalException"))
    if not ok:
        return {"ok": False, **common, "error": f"exit={proc.returncode}, see log"}
    candidates = [p for p in list(BACKTEST_RESULTS.glob("*.zip")) + list(BACKTEST_RESULTS.glob("*.json"))
                  if not p.name.endswith(".meta.json") and p.name != ".last_result.json"]
    if not candidates:
        return {"ok": False, **common, "error": "no backtest result produced"}
    result = max(candidates, key=lambda p: (p.stat().st_mtime, p.name))
    dest = artifacts_dir / "backtest_results" / f"{label}{result.suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(result.read_bytes())
    return {"ok": True, **common, "result_path": str(dest.relative_to(artifacts_dir))}


def summarize(result_path: Path, window: dict, fee: float, wallet: float, artifacts_dir: Path,
              label: str) -> dict:
    out_json = artifacts_dir / f"metrics_{label}.json"
    cmd = [
        sys.executable, str(RESEARCH_DIR / "summarize_backtest.py"),
        "--result", str(result_path),
        "--window-start", iso(window["start"]), "--window-end", iso(window["end"], True),
        "--wallet", str(wallet), "--fee", repr(float(fee)),
        "--out", str(out_json), "--md", str(artifacts_dir / f"metrics_{label}.md"),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_json.exists():
        return {"ok": False, "error": (proc.stdout + proc.stderr)[-2000:]}
    return {"ok": True, **json.loads(out_json.read_text(encoding="utf-8"))}


def selection_metric(metrics: dict | None) -> float:
    """Cycle-1's frozen metric: total_return_pct / max_drawdown_pct; unusable is -inf."""
    if not metrics or not metrics.get("ok"):
        return float("-inf")
    dd = metrics.get("max_drawdown_pct") or 0.0
    if dd <= 0:
        return float("-inf") if metrics.get("trade_count", 0) < 2 else metrics["total_return_pct"]
    return metrics["total_return_pct"] / dd


# -- §11 summaries ---------------------------------------------------------------


def _evidence(artifacts_dir: Path, *rel_paths: str | None) -> list[dict]:
    out = []
    for rel in rel_paths:
        if not rel:
            continue
        path = artifacts_dir / rel
        if path.exists():
            out.append({"path": rel, "sha256": sha256_file(path)})
    return out


def invocation_summary(prereg: dict, step: dict, config_id: str | None, run: dict | None,
                       metrics: dict | None, budget_state: dict, ledger_state: dict,
                       artifacts_dir: Path, executed_so_far: int) -> dict:
    caps = budget_state["caps"]
    consumed_inv = budget_state["consumed_before"]["engine_invocations"] + executed_so_far
    metrics_rel = f"metrics_{step['label']}.json" if metrics and metrics.get("ok") else None
    return {
        "authority": AUTHORITY,
        "cycle_id": CYCLE_ID,
        "family_id": prereg["family_id"],
        "lineage_id": prereg["lineage_id"],
        "candidate_id": prereg["candidate_id"],
        "config_id": config_id,
        "trial_id": prereg["trial_id"],
        "experiment_id": prereg["experiment_id"],
        "run_id": prereg["run_id"],
        "funnel_step": prereg["funnel_step"],
        "lane": step["lane"], "fold": step["fold"], "phase": step["phase"],
        "timerange": timerange(step["window"]),
        "fee_level": step["fee"],
        "fee_model": FEE_MODEL,
        "friction": dict(FRICTION),
        "engine_fee_propagation": (run or {}).get("engine_fee_propagation", "UNPROVEN"),
        "invocation": step["invocation"],
        "invocations_planned": budget_state["planned_invocations"],
        "budget": {"engine_invocations_consumed": consumed_inv,
                   "engine_invocations_remaining": caps["engine_invocations"] - consumed_inv,
                   "consumed_after_plan": budget_state["consumed_after"],
                   "remaining_after_plan": budget_state["remaining_after"]},
        "ledger": {"verify": ledger_state["ledger_verify"], "binding": ledger_state["binding"],
                   "records": ledger_state["ledger_records"]},
        "evidence": _evidence(artifacts_dir, (run or {}).get("log_path"), (run or {}).get("result_path"),
                              metrics_rel),
        "status": "OK" if (run or {}).get("ok") and metrics and metrics.get("ok") else "FAILED",
        "error": None if (run or {}).get("ok") else (run or {}).get("error"),
    }


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


# -- orchestration ---------------------------------------------------------------


def prepare(prereg_path: Path, ledger_path: Path) -> tuple[dict, str, list[dict], dict, dict]:
    prereg = load_prereg(prereg_path)
    prereg_sha = sha256_file(prereg_path)
    strategy_file = REPO_ROOT / prereg["strategy"]["file"]
    if not strategy_file.is_file() or sha256_file(strategy_file) != prereg["strategy"]["sha256"]:
        raise DriverRefusal(f"strategy file {prereg['strategy']['file']} is missing or does not match "
                            "its preregistered sha256")
    plan = build_plan(prereg)
    ledger_state = ledger_budget(prereg, prereg_sha, ledger_path)
    budget_state = budget(prereg, plan, ledger_state)
    if budget_state["refusals"]:
        raise DriverRefusal("hard cap would be exceeded: " + "; ".join(budget_state["refusals"]))
    return prereg, prereg_sha, plan, ledger_state, budget_state


def execute(prereg: dict, prereg_sha: str, plan: list[dict], ledger_state: dict, budget_state: dict,
            artifacts_dir: Path) -> dict:
    strategy, image, wallet = prereg["strategy"]["name"], prereg["engine_image"], prereg["wallet"]
    grid = {c["config_id"]: c for c in prereg["grid"]}
    order = [c["config_id"] for c in prereg["grid"]]
    invocations: list[dict] = []
    selected: dict[int, str] = {}
    train_scores: dict[int, list[tuple]] = {}

    for executed, step in enumerate(plan):
        if step["config_id"] is None:
            fold = step["fold"]
            if fold not in selected:
                scores = train_scores.get(fold, [])
                viable = [s for s in scores if s[0] != float("-inf")] or scores
                # Cycle-1 tie-break: metric, then trade count, then preregistered order.
                best = max(viable, key=lambda s: (s[0], s[1], -order.index(s[2])))
                selected[fold] = best[2]
            config_id = selected[fold]
        else:
            config_id = step["config_id"]
        write_params(strategy, grid[config_id]["params"])
        run = run_backtest(image, strategy, step["window"], step["fee"], step["label"], artifacts_dir)
        metrics = (summarize(artifacts_dir / run["result_path"], step["window"], step["fee"], wallet,
                             artifacts_dir, step["label"]) if run["ok"] else None)
        if step["phase"] == "train_selection":
            train_scores.setdefault(step["fold"], []).append(
                (selection_metric(metrics), (metrics or {}).get("trade_count", 0), config_id))
        summary = invocation_summary(prereg, step, config_id, run, metrics, budget_state, ledger_state,
                                     artifacts_dir, executed + 1)
        write_json(artifacts_dir / f"invocation_{step['label']}.json", summary)
        invocations.append(summary)

    ok = sum(1 for s in invocations if s["status"] == "OK")
    return {
        "authority": AUTHORITY,
        "cycle_id": CYCLE_ID,
        "family_id": prereg["family_id"], "lineage_id": prereg["lineage_id"],
        "candidate_id": prereg["candidate_id"], "trial_id": prereg["trial_id"],
        "experiment_id": prereg["experiment_id"], "run_id": prereg["run_id"],
        "funnel_step": prereg["funnel_step"],
        "prereg_sha256": prereg_sha,
        "fee_model": FEE_MODEL, "friction": dict(FRICTION),
        "fee_levels": prereg["fee_levels"],
        "selected_config_by_fold": {str(k): v for k, v in sorted(selected.items())},
        "budget": budget_state,
        "ledger": {"verify": ledger_state["ledger_verify"], "binding": ledger_state["binding"],
                   "records": ledger_state["ledger_records"]},
        "invocations_executed": len(invocations),
        "invocations_ok": ok,
        "evidence": [{"path": f"invocation_{s['label']}.json",
                      "sha256": sha256_file(artifacts_dir / f"invocation_{s['label']}.json")} for s in plan],
        "status": "RUNS_COMPLETED" if ok else "SYSTEMIC_FAILURE",
        "terminal_decision": None,
        "note": "Derived and non-authoritative. No research verdict is made here; the trial's terminal "
                "state is the operator's own ledger record.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prereg", required=True, type=Path)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--artifacts-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="print the plan and budget; execute nothing")
    args = parser.parse_args(argv)

    try:
        prereg, prereg_sha, plan, ledger_state, budget_state = prepare(args.prereg, args.ledger)
        if not args.dry_run and ledger_state["binding"] != "BOUND":
            raise DriverRefusal(f"{prereg['trial_id']} is not preregistered in the ledger with this "
                                "file's sha256; preregister before any outcome exists")
    except DriverRefusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps({
            "mode": "DRY_RUN", "executes": False, "cycle_id": CYCLE_ID, "trial_id": prereg["trial_id"],
            "prereg_sha256": prereg_sha, "fee_model": FEE_MODEL, "friction": FRICTION,
            "ledger": {"verify": ledger_state["ledger_verify"], "binding": ledger_state["binding"]},
            "budget": budget_state,
            "plan": [{**s, "timerange": timerange(s["window"]),
                      "argv": backtest_argv(prereg["engine_image"], prereg["strategy"]["name"],
                                            s["window"], s["fee"])} for s in plan],
        }, indent=2, sort_keys=True))
        return 0

    if args.artifacts_dir is None:
        print("REFUSED: --artifacts-dir is required for a real run", file=sys.stderr)
        return 2
    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    summary = execute(prereg, prereg_sha, plan, ledger_state, budget_state, args.artifacts_dir)
    write_json(args.artifacts_dir / "cycle2_run_summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("trial_id", "invocations_executed", "invocations_ok", "status")},
                     indent=2, sort_keys=True))
    if summary["status"] != "RUNS_COMPLETED":
        print("::error::systemic failure: no invocation produced usable metrics", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
