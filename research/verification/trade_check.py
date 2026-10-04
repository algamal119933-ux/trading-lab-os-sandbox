#!/usr/bin/env python3
"""Trade History Health Check: one CSV of closed trades in, one report out.

    python research/verification/trade_check.py trades.csv --out-dir /path/outside/repo \
        [--fraction 1.0] [--paths 5000] [--seed 0] [--ruin-drawdown 0.5]

Writes trade_check.json (all numbers) and trade_check.md (the client-facing
summary) into --out-dir, which must not be inside a git checkout: client material
never enters a repository (COMMERCIAL-VERIFICATION-LANE-1 §2).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verification import monte_carlo, trade_stats  # noqa: E402

DISCLAIMER = (
    "This check describes a list of past trades. It cannot detect look-ahead bias, overfitting "
    "or data errors, which need the strategy code and its data. It is not investment advice and "
    "not a forecast. A result of NO_RED_FLAGS_FOUND is not a pass."
)


def _inside_git_checkout(path: Path) -> bool:
    probe = path if path.exists() else path.parent
    result = subprocess.run(["git", "-C", str(probe), "rev-parse", "--is-inside-work-tree"],
                            capture_output=True, text=True, check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def _pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def _num(value, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def render_markdown(report: dict) -> str:
    s, mc = report["stats"], report["monte_carlo"]
    lines = [
        "# Trade History Health Check",
        "",
        f"**Result: {s['verdict']}**",
        "",
        f"Input: `{report['input']['name']}` (sha256 `{report['input']['sha256'][:16]}…`), "
        f"{s['trades']} trades, {s['first_close'][:10]} to {s['last_close'][:10]}. "
        f"Equity fraction per trade: {s['fraction']}.",
        "",
        "## Red flags",
        "",
    ]
    lines += [f"- {flag}" for flag in s["red_flags"]] or ["- None found by these checks."]
    lines += [
        "",
        "## Statistics",
        "",
        "| Measure | Value |",
        "| --- | --- |",
        f"| Total return (compounded) | {_pct(s['total_return'])} |",
        f"| Expectancy per trade | {_pct(s['expectancy_per_trade'])} |",
        f"| Profit factor | {_num(s['profit_factor'])} |",
        f"| Win rate | {_pct(s['win_rate'])} |",
        f"| Average win / average loss | {_pct(s['avg_win'])} / {_pct(s['avg_loss'])} |",
        f"| Max drawdown | {_pct(s['max_drawdown'])} |",
        f"| Sharpe (annualised, per-trade) | {_num(s['sharpe_annualised'])} |",
        f"| Longest win / loss streak | {s['longest_win_streak']} / {s['longest_loss_streak']} |",
        f"| Top trade share of net profit | {_pct(s['top_trade_share_of_net'])} |",
        f"| Top 5% trades share of net profit | {_pct(s['top_5pct_trades_share_of_net'])} |",
        f"| Positive months | {_pct(s['positive_month_share'])} of {s['months']} |",
        f"| Worst / best month | {_pct(s['worst_month'])} / {_pct(s['best_month'])} |",
        "",
        f"## Monte Carlo ({mc['paths']} resampled paths, seed {mc['seed']})",
        "",
        "| Measure | Value |",
        "| --- | --- |",
        f"| Return P5 / P50 / P95 | {_pct(mc['return_p5'])} / {_pct(mc['return_p50'])} / {_pct(mc['return_p95'])} |",
        f"| Probability of ending at a loss | {_pct(mc['probability_of_loss'])} |",
        f"| Max drawdown P50 / P95 | {_pct(mc['max_drawdown_p50'])} / {_pct(mc['max_drawdown_p95'])} |",
        f"| Risk of ruin (drawdown ≥ {mc['ruin_drawdown']:.0%}) | {_pct(mc['risk_of_ruin'])} |",
        "",
        "Limits: " + "; ".join(mc["limitations"]) + ".",
        "",
        "## What this check cannot tell you",
        "",
        DISCLAIMER,
        "",
    ]
    return "\n".join(lines)


def run(csv_path: Path, *, fraction: float, paths: int, seed: int, ruin_drawdown: float) -> dict:
    trades = trade_stats.load_trades(csv_path)
    stats = trade_stats.summarize(trades, fraction)
    mc = monte_carlo.simulate([t.ret for t in trades], fraction=fraction, paths=paths,
                              seed=seed, ruin_drawdown=ruin_drawdown)
    return {
        "check": "TRADE_HISTORY_HEALTH_CHECK",
        "input": {"name": csv_path.name, "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest()},
        "stats": stats,
        "monte_carlo": mc,
        "disclaimer": DISCLAIMER,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--fraction", type=float, default=1.0)
    parser.add_argument("--paths", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--ruin-drawdown", type=float, default=0.5)
    args = parser.parse_args(argv)

    if _inside_git_checkout(args.out_dir.resolve()):
        print("REFUSED: --out-dir is inside a git checkout; client output never enters a repository",
              file=sys.stderr)
        return 2
    try:
        report = run(args.csv, fraction=args.fraction, paths=args.paths, seed=args.seed,
                     ruin_drawdown=args.ruin_drawdown)
    except (trade_stats.TradeFileError, ValueError, OSError) as exc:
        print(f"INPUT_REJECTED: {exc}", file=sys.stderr)
        return 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "trade_check.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.out_dir / "trade_check.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"{report['stats']['verdict']}: {len(report['stats']['red_flags'])} red flag(s); "
          f"wrote {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
