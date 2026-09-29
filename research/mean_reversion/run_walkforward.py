#!/usr/bin/env python3
"""Walk-forward driver for TRIAL-MR-ZSCORE-WF-1 (MEAN-REVERSION-CYCLE1-DISCOVERY-1).

Orchestrates the preregistered 2-fold x 4-config walk-forward campaign
within one CI job, reusing the exact `docker run ... freqtrade backtesting`
invocation and `research/summarize_backtest.py` normalisation every other
lane in this project already uses — no new backtesting mechanism.

Every invocation (TRAIN selection run, EVAL run, cost-stress EVAL run) is
recorded in the output, win or lose, per Owner directive
MEAN-REVERSION-CYCLE1-DISCOVERY-1 section 6: "Never report only the best
configuration."

Selection metric, fold boundaries and the parameter grid are fixed exactly
as frozen in PREREGISTRATION.md before this script ever ran; nothing here
may change them after seeing a result.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = REPO_ROOT / "freqtrade" / "user_data" / "strategies"
BACKTEST_RESULTS = REPO_ROOT / "freqtrade" / "user_data" / "backtest_results"
DATA_DIR_CONTAINER = "/freqtrade/user_data/data/binance"

STRATEGY = "MeanReversionZScore"
CONFIG_PATH_CONTAINER = "/freqtrade/user_data/config.research.json"
STRATEGY_PATH_CONTAINER = "/freqtrade/user_data/strategies"

# -- frozen in PREREGISTRATION.md; do not edit after seeing a result --------
CONFIGS = [
    {"lookback_hours": 24, "z_threshold": 1.5},
    {"lookback_hours": 24, "z_threshold": 2.5},
    {"lookback_hours": 72, "z_threshold": 1.5},
    {"lookback_hours": 72, "z_threshold": 2.5},
]
FOLDS = [
    {"fold": 1, "train_start": "20210101", "train_end": "20221231",
     "eval_start": "20230101", "eval_end": "20231231"},
    {"fold": 2, "train_start": "20210101", "train_end": "20231231",
     "eval_start": "20240101", "eval_end": "20241231"},
]
BASE_FEE = 0.001
ADVERSE_FEE = 0.002
WALLET = 100.0
MIN_EVAL_TRADES = 10


def config_id(cfg: dict) -> str:
    return f"LB{cfg['lookback_hours']}_Z{cfg['z_threshold']}"


def selection_metric(metrics: dict) -> float:
    dd = metrics.get("max_drawdown_pct") or 0.0
    if dd <= 0:
        # No drawdown recorded (e.g. zero or one trade) is not "infinitely
        # good" — treat as unusable evidence, not a winner.
        return float("-inf") if metrics.get("trade_count", 0) < 2 else metrics["total_return_pct"]
    return metrics["total_return_pct"] / dd


def _ensure_writable(path: Path) -> None:
    """The Freqtrade image's own entrypoint chowns the whole bind-mounted
    directory to its in-container user on every `docker run`, not merely
    restricts its permission bits -- chmod cannot fix a chown, since only
    the owner or root may change a file's mode. Every one of the twelve
    backtest invocations in this campaign re-triggers it, so this reclaims
    ownership via sudo (GitHub-hosted runners carry passwordless sudo)
    before every write, not once at the start."""
    if not path.exists():
        return
    subprocess.run(["sudo", "chown", "-R", f"{os.getuid()}:{os.getgid()}", str(path)],
                    check=False)


def write_params(cfg: dict) -> None:
    _ensure_writable(STRATEGY_DIR)
    target = STRATEGY_DIR / f"{STRATEGY}.json"
    if target.exists():
        _ensure_writable(target)
    payload = {
        "strategy_name": STRATEGY,
        "params": {"buy": {"lookback_hours": cfg["lookback_hours"],
                            "z_threshold": cfg["z_threshold"]}},
    }
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_backtest(image: str, timerange: str, label: str, artifacts_dir: Path) -> dict:
    """Run one backtest invocation; return {ok, log_path, result_zip, error}."""
    _ensure_writable(BACKTEST_RESULTS)
    log_path = artifacts_dir / f"backtest_{label}.log"
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{REPO_ROOT / 'freqtrade' / 'user_data'}:/freqtrade/user_data",
        image, "backtesting",
        "--config", CONFIG_PATH_CONTAINER,
        "--strategy", STRATEGY, "--strategy-path", STRATEGY_PATH_CONTAINER,
        "--timerange", timerange, "--timeframe-detail", "5m",
        "--enable-protections", "--export", "trades",
    ]
    with open(log_path, "w", encoding="utf-8") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    # The container that just ran re-chowned the mounted tree to its own
    # in-container user on the way out; reclaim it before reading the
    # result it wrote, not just before the next write.
    _ensure_writable(BACKTEST_RESULTS)
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    ok = proc.returncode == 0 and not any(
        marker in log_text
        for marker in ("CRITICAL - Invalid configuration", "Configuration error",
                        "OperationalException")
    )
    if not ok:
        return {"ok": False, "log_path": str(log_path.relative_to(artifacts_dir.parent)),
                "error": f"exit={proc.returncode}, see log"}

    candidates = [p for p in list(BACKTEST_RESULTS.glob("*.zip")) + list(BACKTEST_RESULTS.glob("*.json"))
                  if not p.name.endswith(".meta.json") and p.name != ".last_result.json"]
    if not candidates:
        return {"ok": False, "log_path": str(log_path.relative_to(artifacts_dir.parent)),
                "error": "no backtest result produced"}
    result = max(candidates, key=lambda p: p.stat().st_mtime)
    dest = artifacts_dir / "backtest_results" / f"{label}{result.suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(result.read_bytes())
    return {"ok": True, "log_path": str(log_path.relative_to(artifacts_dir.parent)),
            "result_path": str(dest.relative_to(artifacts_dir.parent))}


def summarize(result_path: Path, window_start: str, window_end: str, fee: float,
              artifacts_dir: Path, label: str) -> dict:
    out_json = artifacts_dir / f"metrics_{label}.json"
    cmd = [
        sys.executable, str(REPO_ROOT / "research" / "summarize_backtest.py"),
        "--result", str(result_path),
        "--window-start", window_start, "--window-end", window_end,
        "--wallet", str(WALLET), "--fee", str(fee),
        "--out", str(out_json), "--md", str(artifacts_dir / f"metrics_{label}.md"),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_json.exists():
        return {"ok": False, "error": (proc.stdout + proc.stderr)[-2000:]}
    return {"ok": True, **json.loads(out_json.read_text(encoding="utf-8"))}


def iso(date8: str, end: bool = False) -> str:
    y, m, d = date8[:4], date8[4:6], date8[6:8]
    return f"{y}-{m}-{d}T{'23:00:00' if end else '00:00:00'}Z"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--artifacts-dir", required=True)
    args = parser.parse_args()

    artifacts_dir = Path(args.artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    campaign = {"configs": CONFIGS, "folds": FOLDS, "base_fee": BASE_FEE,
                "adverse_fee": ADVERSE_FEE, "train_attempts": [], "fold_results": []}

    for fold in FOLDS:
        fold_label = f"fold{fold['fold']}"
        train_attempts = []
        for cfg in CONFIGS:
            cid = config_id(cfg)
            label = f"{fold_label}_train_{cid}"
            write_params(cfg)
            run = run_backtest(args.image, f"{fold['train_start']}-{fold['train_end']}",
                                label, artifacts_dir)
            attempt = {"fold": fold["fold"], "phase": "train_selection", "config": cfg,
                       "config_id": cid, "run": run}
            if run["ok"]:
                metrics = summarize(artifacts_dir / run["result_path"],
                                     iso(fold["train_start"]), iso(fold["train_end"], True),
                                     BASE_FEE, artifacts_dir, label)
                attempt["metrics"] = metrics
                attempt["selection_metric"] = (
                    selection_metric(metrics) if metrics.get("ok") else float("-inf")
                )
            else:
                attempt["metrics"] = None
                attempt["selection_metric"] = float("-inf")
            train_attempts.append(attempt)
            campaign["train_attempts"].append(attempt)

        viable = [a for a in train_attempts if a["selection_metric"] != float("-inf")]
        pool = viable or train_attempts
        best = max(pool, key=lambda a: (a["selection_metric"],
                                          (a["metrics"] or {}).get("trade_count", 0),
                                          -a["config"]["lookback_hours"]))
        selected_cfg = best["config"]
        selected_cid = best["config_id"]

        write_params(selected_cfg)
        eval_label = f"{fold_label}_eval_{selected_cid}"
        eval_run = run_backtest(args.image, f"{fold['eval_start']}-{fold['eval_end']}",
                                 eval_label, artifacts_dir)
        eval_metrics = (summarize(artifacts_dir / eval_run["result_path"],
                                   iso(fold["eval_start"]), iso(fold["eval_end"], True),
                                   BASE_FEE, artifacts_dir, eval_label)
                        if eval_run["ok"] else None)

        stress_label = f"{fold_label}_stress_{selected_cid}"
        stress_run = run_backtest(args.image, f"{fold['eval_start']}-{fold['eval_end']}",
                                   stress_label, artifacts_dir)
        stress_metrics = (summarize(artifacts_dir / stress_run["result_path"],
                                     iso(fold["eval_start"]), iso(fold["eval_end"], True),
                                     ADVERSE_FEE, artifacts_dir, stress_label)
                          if stress_run["ok"] else None)

        campaign["fold_results"].append({
            "fold": fold["fold"], "train_window": [fold["train_start"], fold["train_end"]],
            "eval_window": [fold["eval_start"], fold["eval_end"]],
            "train_attempts_this_fold": [
                {"config_id": a["config_id"], "selection_metric": a["selection_metric"],
                 "metrics": a["metrics"]} for a in train_attempts
            ],
            "selected_config": selected_cfg, "selected_config_id": selected_cid,
            "eval_run": eval_run, "eval_metrics": eval_metrics,
            "cost_stress_run": stress_run, "cost_stress_metrics": stress_metrics,
        })

    (artifacts_dir / "walkforward_campaign.json").write_text(
        json.dumps(campaign, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps({"folds": [
        {"fold": f["fold"], "selected": f["selected_config_id"],
         "eval_ok": bool(f["eval_metrics"] and f["eval_metrics"].get("ok"))}
        for f in campaign["fold_results"]
    ]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
