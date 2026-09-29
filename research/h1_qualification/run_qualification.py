#!/usr/bin/env python3
"""H1 paper-readiness qualification driver (H1-PAPER-READINESS-QUALIFICATION-1).

Runs the preregistered diagnostic trials for the frozen H1_EMACROSS candidate
-- 8 parameter-sensitivity neighbors, 4 temporal-stability slices, 1
cost-stress adverse-fee run -- reusing the exact `pin_upstream.py` fetch
mechanism, `docker run ... freqtrade backtesting` invocation, and
`research/summarize_backtest.py` normalisation every other lane in this
project already uses. The frozen center configuration (ema_period=600,
exit_threshold=2.0) is never re-run here: it is TRIAL-H1-CD1, already
canonical, cited not re-executed.

Nothing here may change H1's identity. Every invocation is recorded, win or
lose, per the Owner directive's accounting law.
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
CONFIG_BASE = REPO_ROOT / "freqtrade" / "user_data" / "config.research.json"
CONFIG_STRESS = REPO_ROOT / "freqtrade" / "user_data" / "config.research.stress.json"

STRATEGY = "EmaCross"
STRATEGY_PATH_CONTAINER = "/freqtrade/user_data/strategies"

WINDOW_START, WINDOW_END = "20210101", "20241231"
BASE_FEE = 0.001
ADVERSE_FEE = 0.002
WALLET = 100.0
CENTER = {"ema_period": 600, "exit_threshold": 2.0}

# -- frozen in PREREGISTRATION.md; do not edit after seeing a result --------
NEIGHBORS = [
    {"ema_period": 500, "exit_threshold": 1.5}, {"ema_period": 500, "exit_threshold": 2.0},
    {"ema_period": 500, "exit_threshold": 2.5}, {"ema_period": 600, "exit_threshold": 1.5},
    {"ema_period": 600, "exit_threshold": 2.5}, {"ema_period": 700, "exit_threshold": 1.5},
    {"ema_period": 700, "exit_threshold": 2.0}, {"ema_period": 700, "exit_threshold": 2.5},
]
SLICES = [
    {"year": 2021, "start": "20210101", "end": "20211231"},
    {"year": 2022, "start": "20220101", "end": "20221231"},
    {"year": 2023, "start": "20230101", "end": "20231231"},
    {"year": 2024, "start": "20240101", "end": "20241231"},
]


def cfg_id(p: dict) -> str:
    return f"EMA{p['ema_period']}_TH{p['exit_threshold']}"


def _ensure_writable(path: Path) -> None:
    if not path.exists():
        return
    subprocess.run(["sudo", "chown", "-R", f"{os.getuid()}:{os.getgid()}", str(path)],
                    check=False)


def write_params(params: dict) -> None:
    """EmaCross.py declares `ema_period` under space="buy" and
    `exit_threshold` under space="sell" (confirmed by reading the actual
    hash-verified upstream source: research/external/pin_upstream.py's own
    materialised copy). Freqtrade's HyperStrategyMixin auto-load only
    matches a parameter under its own declared space key; a flat, unnested
    "params" dict silently matches nothing and every run falls back to the
    class defaults (ema_period=800, exit_threshold=1.0) without any error --
    exactly what happened in TRIAL-H1-QUAL-1's first, aborted attempt, where
    every one of 9 differently-configured runs produced byte-identical
    output."""
    _ensure_writable(STRATEGY_DIR)
    target = STRATEGY_DIR / f"{STRATEGY}.json"
    if target.exists():
        _ensure_writable(target)
    nested = {}
    if "ema_period" in params:
        nested.setdefault("buy", {})["ema_period"] = params["ema_period"]
    if "exit_threshold" in params:
        nested.setdefault("sell", {})["exit_threshold"] = params["exit_threshold"]
    target.write_text(json.dumps({"strategy_name": STRATEGY, "params": nested}, indent=2) + "\n",
                       encoding="utf-8")


def write_stress_config() -> None:
    """A separate config, differing only in fee, so the change reaches the
    real engine (via --config) rather than only the summariser."""
    base = json.loads(CONFIG_BASE.read_text(encoding="utf-8"))
    base["fee"] = ADVERSE_FEE
    CONFIG_STRESS.write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")


def run_backtest(image: str, timerange: str, label: str, artifacts_dir: Path,
                  config_path: str) -> dict:
    _ensure_writable(BACKTEST_RESULTS)
    log_path = artifacts_dir / f"backtest_{label}.log"
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{REPO_ROOT / 'freqtrade' / 'user_data'}:/freqtrade/user_data",
        image, "backtesting",
        "--config", config_path,
        "--strategy", STRATEGY, "--strategy-path", STRATEGY_PATH_CONTAINER,
        "--timerange", timerange, "--timeframe-detail", "5m",
        "--enable-protections", "--export", "trades",
    ]
    with open(log_path, "w", encoding="utf-8") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    _ensure_writable(BACKTEST_RESULTS)
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    ok = proc.returncode == 0 and not any(
        m in log_text for m in ("CRITICAL - Invalid configuration", "Configuration error",
                                 "OperationalException")
    )
    fee_line = next((ln for ln in log_text.splitlines() if "Using fee" in ln), None)
    if not ok:
        return {"ok": False, "log_path": str(log_path.relative_to(artifacts_dir)),
                "effective_fee_line": fee_line, "error": f"exit={proc.returncode}, see log"}
    candidates = [p for p in list(BACKTEST_RESULTS.glob("*.zip")) + list(BACKTEST_RESULTS.glob("*.json"))
                  if not p.name.endswith(".meta.json") and p.name != ".last_result.json"]
    if not candidates:
        return {"ok": False, "log_path": str(log_path.relative_to(artifacts_dir)),
                "effective_fee_line": fee_line, "error": "no backtest result produced"}
    result = max(candidates, key=lambda p: p.stat().st_mtime)
    dest = artifacts_dir / "backtest_results" / f"{label}{result.suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(result.read_bytes())
    return {"ok": True, "log_path": str(log_path.relative_to(artifacts_dir)),
            "effective_fee_line": fee_line,
            "result_path": str(dest.relative_to(artifacts_dir))}


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


def do_trial(image: str, artifacts_dir: Path, label: str, params: dict, timerange: str,
             ws: str, we: str, fee: float, config_path: str) -> dict:
    write_params(params)
    run = run_backtest(image, timerange, label, artifacts_dir, config_path)
    metrics = (summarize(artifacts_dir / run["result_path"], ws, we, fee, artifacts_dir, label)
               if run["ok"] else None)
    return {"label": label, "params": params, "timerange": timerange, "fee": fee,
            "config_path": config_path, "run": run, "metrics": metrics}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--artifacts-dir", required=True)
    args = parser.parse_args()
    artifacts_dir = Path(args.artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    results = {"neighbors": [], "slices": [], "cost_stress": None}

    full_ws, full_we = iso(WINDOW_START), iso(WINDOW_END, True)
    full_tr = f"{WINDOW_START}-{WINDOW_END}"

    for n in NEIGHBORS:
        label = f"paramsens_{cfg_id(n)}"
        results["neighbors"].append(
            do_trial(args.image, artifacts_dir, label, n, full_tr, full_ws, full_we,
                      BASE_FEE, "/freqtrade/user_data/config.research.json")
        )

    for s in SLICES:
        label = f"temporal_{s['year']}"
        tr = f"{s['start']}-{s['end']}"
        results["slices"].append(
            do_trial(args.image, artifacts_dir, label, CENTER, tr,
                      iso(s["start"]), iso(s["end"], True), BASE_FEE,
                      "/freqtrade/user_data/config.research.json")
        )

    write_stress_config()
    effective_fee = json.loads(CONFIG_STRESS.read_text(encoding="utf-8"))["fee"]
    assert effective_fee == ADVERSE_FEE, "stress config fee did not write correctly"
    stress = do_trial(args.image, artifacts_dir, "cost_stress_adverse", CENTER, full_tr,
                       full_ws, full_we, ADVERSE_FEE,
                       "/freqtrade/user_data/config.research.stress.json")
    fee_line = (stress["run"] or {}).get("effective_fee_line") or ""
    stress["engine_fee_propagation_proven"] = "0.2000%" in fee_line or "0.2%" in fee_line
    results["cost_stress"] = stress

    (artifacts_dir / "qualification_results.json").write_text(
        json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8"
    )

    all_attempts = results["neighbors"] + results["slices"] + [results["cost_stress"]]
    ok_count = sum(1 for a in all_attempts if a["metrics"] and a["metrics"].get("ok"))
    print(json.dumps({"total_attempts": len(all_attempts), "ok": ok_count,
                       "stress_fee_proven": results["cost_stress"]["engine_fee_propagation_proven"]},
                      indent=2))
    if ok_count == 0:
        print("::error::systemic failure: zero attempts produced usable metrics", file=sys.stderr)
        return 1
    if not results["cost_stress"]["engine_fee_propagation_proven"]:
        print("::error::cost-stress fee propagation could not be proven from the engine's own log",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
