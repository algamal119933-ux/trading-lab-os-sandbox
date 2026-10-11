"""Prepare, guard, run and read one AUTH-2 Freqtrade backtest (the judged engine).

    prepare_run   write the schedule, the frozen market table and the run config
    guard_config  the paper-safety checks of scripts/paper_guard.py that apply to a
                  backtest, all enforced (see GUARD_NOT_APPLICABLE)
    command       the docker (pinned image) or local command line
    read_marks    daily equity marks from the exported Freqtrade wallet capture

PAPER / RESEARCH ONLY. The config is dry_run true, spot, keyless, and the only
command ever issued is ``backtesting``.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
REPO = _HERE.parents[1]
ENGINE_DIR = _HERE / "engine"
IMAGE = "freqtradeorg/freqtrade:2026.7"
STRATEGY = "AUTH2ScheduleFollower"
WALLET = 1000.0
# Freqtrade refuses any new entry while free cash is below the configured
# stake_amount, before custom_stake_amount is consulted; a tiny fixed proposal
# keeps that pre-check from binding (the follower sizes every order itself).
PROPOSED_STAKE = 0.001
DAY_MS = 86_400_000
FOUR_H_MS = 14_400_000

# paper_guard.check_config findings that describe the live paper RUNTIME rather
# than a backtest: the sandbox cap on simultaneous trades (a portfolio schedule
# holds up to 12 positions) and the observability API of a running bot (a
# backtest starts no server). Every other paper-guard finding fails the run.
GUARD_NOT_APPLICABLE = ("max_open_trades must be an int in", "api_server section is missing", "api_server must be enabled",
                        "inside Docker api_server.listen_ip_address", "api_server.")


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def write_feather(bars: np.ndarray, path: Path) -> None:
    import pandas as pd

    df = pd.DataFrame(bars[:, :6], columns=["date", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"].astype("int64"), unit="ms", utc=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_feather(path)


def build_config(pairs: list[str], fee: float, schedule_file: str, schedule_sha: str, datadir: str,
                 export_file: str, max_open: int) -> dict:
    return {
        "max_open_trades": max_open,
        "stake_currency": "USDT",
        "stake_amount": PROPOSED_STAKE,
        "tradable_balance_ratio": 1.0,
        "fiat_display_currency": "USD",
        "dry_run": True,
        "dry_run_wallet": WALLET,
        "cancel_open_orders_on_exit": True,
        "trading_mode": "spot",
        "margin_mode": "",
        "fee": fee,
        "force_entry_enable": False,
        "unfilledtimeout": {"entry": 10, "exit": 10, "exit_timeout_count": 0, "unit": "minutes"},
        "entry_pricing": {"price_side": "same", "use_order_book": False, "order_book_top": 1,
                          "price_last_balance": 0.0, "check_depth_of_market": {"enabled": False}},
        "exit_pricing": {"price_side": "same", "use_order_book": False, "order_book_top": 1},
        "exchange": {"name": "binance", "key": "", "secret": "", "ccxt_config": {}, "ccxt_async_config": {},
                     "pair_whitelist": list(pairs), "pair_blacklist": [], "skip_pair_validation": True},
        "pairlists": [{"method": "StaticPairList", "allow_inactive": True}],
        "telegram": {"enabled": False, "token": "", "chat_id": ""},
        "bot_name": "auth2-backtest",
        "dataformat_ohlcv": "feather",
        "datadir": datadir,
        "export": "trades",
        "exportfilename": export_file,
        "internals": {"process_throttle_secs": 5},
        "auth2": {"schedule_file": schedule_file, "schedule_sha256": schedule_sha},
    }


def guard_config(cfg: dict, path: Path) -> list[str]:
    """Paper-guard findings for a backtest config; empty = PASS."""
    sys.path.insert(0, str(REPO / "scripts"))
    import paper_guard

    v = paper_guard.Violations()
    path.write_text(json.dumps(cfg, indent=1, sort_keys=True) + "\n")
    paper_guard.check_config(path, v)
    findings = [str(x).split(": ", 1)[1] if ": " in str(x) else str(x) for x in v]
    return [f for f in findings if not any(f.startswith(n) for n in GUARD_NOT_APPLICABLE)]


def timerange(start_ms: int, end_ms: int) -> str:
    """Freqtrade timerange covering execution from start_ms to the end_ms mark (epoch seconds)."""
    return f"{(start_ms - FOUR_H_MS) // 1000}-{(end_ms + FOUR_H_MS) // 1000}"


def prepare_run(workdir: Path, pairs: list[str], bars: dict[str, np.ndarray], schedule_doc: dict,
                fee: float, start_ms: int, end_ms: int) -> dict:
    """Write every input of one engine invocation under ``workdir``; return the run spec."""
    from auth2.engine import markets as mk

    ud = workdir / "user_data"
    data = ud / "data" / "binance"
    for p in pairs:
        write_feather(bars[p], data / f"{p.replace('/', '_')}-4h.feather")
    sched_bytes = (json.dumps(schedule_doc, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (workdir / "schedule.json").write_bytes(sched_bytes)
    lows = {p: bars[p][:, 3] for p in pairs}
    markets = mk.write(pairs, workdir / "markets.json", {p: float(lows[p][lows[p] > 0].min()) for p in pairs})
    held = max([len(r["w"]) for r in schedule_doc["rows"]] + [1])
    cfg = build_config(sorted(pairs), fee, "/run/schedule.json", sha256(sched_bytes), "/run/user_data/data/binance",
                       "/run/user_data/backtest_results/auth2.json", max(held, 1) + 1)
    findings = guard_config(cfg, workdir / "config.json")
    if findings:
        raise SystemExit(f"PAPER_GUARD FAIL for the backtest config: {findings}")
    (ud / "strategies").mkdir(parents=True, exist_ok=True)
    (ud / "strategies" / f"{STRATEGY}.py").write_bytes((ENGINE_DIR / f"{STRATEGY}.py").read_bytes())
    (workdir / "run_backtest.py").write_bytes((ENGINE_DIR / "run_backtest.py").read_bytes())
    (ud / "backtest_results").mkdir(parents=True, exist_ok=True)
    return {"workdir": str(workdir), "schedule_sha256": sha256(sched_bytes), "markets_sha256": sha256(markets),
            "config_sha256": sha256((workdir / "config.json").read_bytes()),
            "strategy_sha256": sha256((ENGINE_DIR / f"{STRATEGY}.py").read_bytes()),
            "fee": fee, "timerange": timerange(start_ms, end_ms), "start_ms": start_ms, "end_ms": end_ms}


def command(spec: dict, local_python: str | None = None, keep_trade_copy: bool = False) -> list[str]:
    args = ["--markets", "/run/markets.json", *(["--keep-trade-copy"] if keep_trade_copy else []), "--", "backtesting", "--config", "/run/config.json",
            "--strategy", STRATEGY, "--strategy-path", "/run/user_data/strategies", "--timeframe", "4h",
            "--timerange", spec["timerange"], "--user-data-dir", "/run/user_data", "--cache", "none"]
    if local_python:
        return [local_python, "/run/run_backtest.py", *args]
    return ["docker", "run", "--rm", "--network", "none", "-v", f"{spec['workdir']}:/run", "--entrypoint", "python",
            IMAGE, "/run/run_backtest.py", *args]


def final_closes(workdir: Path, end_ms: int) -> dict[str, float] | None:
    """{currency: close of the bar at end_ms - 4h} when the run's data ends exactly at end_ms
    (END_AT_CLOSE, see replay.run); None when some pair has a bar opening at or after end_ms.
    Refuses a schedule that executes anything in that last bar."""
    import pandas as pd

    last_bar = end_ms - FOUR_H_MS
    out: dict[str, float] = {}
    for f in sorted((workdir / "user_data" / "data" / "binance").glob("*-4h.feather")):
        df = pd.read_feather(f)
        t = pd.to_datetime(df["date"], utc=True).dt.as_unit("ms").astype("int64").to_numpy()
        if (t >= end_ms).any():
            return None
        hit = np.flatnonzero(t == last_bar)
        if hit.size:
            out[f.name.split("_")[0]] = float(df["close"].iloc[int(hit[0])])
    if not out:
        return None
    doc = json.loads((workdir / "schedule.json").read_text())
    late = [r["t"] for r in doc["rows"] if int(r["t"]) >= last_bar] + \
           [f["t"] for f in doc["forced_exits"] if int(f["t"]) >= last_bar]
    if late:
        raise SystemExit(f"END_AT_CLOSE: the schedule executes in the last bar {late}")
    return out


def read_marks(workdir: Path, start_ms: int, end_ms: int) -> np.ndarray:
    import pandas as pd

    from auth2 import replay

    results = sorted((workdir / "user_data" / "backtest_results").glob("*.zip"))
    if len(results) != 1:
        raise SystemExit(f"expected one backtest result zip, found {results}")
    with zipfile.ZipFile(results[0]) as z:
        names = [n for n in z.namelist() if n.endswith("_wallet.feather")]
        if len(names) != 1:
            raise SystemExit(f"expected one wallet capture in the result, found {names}")
        wallet = pd.read_feather(BytesIO(z.read(names[0])))
    return replay.engine_daily_marks(wallet, start_ms, end_ms, final_close=final_closes(workdir, end_ms))


def result_sha256(workdir: Path) -> str:
    results = sorted((workdir / "user_data" / "backtest_results").glob("*.zip"))
    return sha256(results[0].read_bytes()) if results else ""
