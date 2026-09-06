from __future__ import annotations

import os
import time
from typing import Any

import requests
from prometheus_client import Gauge, start_http_server

BASE = os.getenv("FREQTRADE_URL", "http://freqtrade:8080").rstrip("/")
USER = os.getenv("FREQTRADE_API_USER", "")
PASSWORD = os.getenv("FREQTRADE_API_PASSWORD", "")
PORT = int(os.getenv("EXPORTER_PORT", "9108"))
INTERVAL = 15

api_up = Gauge("freqtrade_api_up", "Whether the exporter can query Freqtrade API")
open_trades = Gauge("freqtrade_open_trades", "Current number of open trades")
max_open_trades = Gauge("freqtrade_max_open_trades", "Configured maximum open trades")
total_trades = Gauge("freqtrade_total_trades", "Total number of trades reported")
closed_trades = Gauge("freqtrade_closed_trades", "Closed trades reported")
winning_trades = Gauge("freqtrade_winning_trades", "Winning closed trades")
losing_trades = Gauge("freqtrade_losing_trades", "Losing closed trades")
profit_all_coin = Gauge("freqtrade_profit_all_coin", "Profit across all trades in stake currency")
profit_closed_coin = Gauge("freqtrade_profit_closed_coin", "Profit across closed trades in stake currency")
last_process_ts = Gauge("freqtrade_last_process_timestamp_seconds", "Last bot process timestamp if supplied")


def num(obj: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = obj.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def get(path: str, auth: bool = True) -> Any:
    kwargs: dict[str, Any] = {"timeout": 8}
    if auth:
        kwargs["auth"] = (USER, PASSWORD)
    response = requests.get(f"{BASE}/api/v1/{path}", **kwargs)
    response.raise_for_status()
    return response.json()


def update() -> None:
    # Unauthenticated readiness first.
    get("ping", auth=False)

    count = get("count")
    if isinstance(count, dict):
        value = num(count, "current", "open_trade_count")
        if value is not None:
            open_trades.set(value)
        value = num(count, "max", "max_open_trades")
        if value is not None:
            max_open_trades.set(value)

    profit = get("profit")
    if isinstance(profit, dict):
        mapping = [
            (total_trades, ("trade_count", "total_trades")),
            (closed_trades, ("closed_trade_count", "closed_trades")),
            (winning_trades, ("winning_trades",)),
            (losing_trades, ("losing_trades",)),
            (profit_all_coin, ("profit_all_coin",)),
            (profit_closed_coin, ("profit_closed_coin",)),
        ]
        for metric, keys in mapping:
            value = num(profit, *keys)
            if value is not None:
                metric.set(value)

    health = get("health")
    if isinstance(health, dict):
        value = num(health, "last_process_ts", "last_process_timestamp")
        if value is not None:
            last_process_ts.set(value)

    api_up.set(1)


def main() -> None:
    start_http_server(PORT)
    while True:
        try:
            update()
        except Exception as exc:
            api_up.set(0)
            print(f"exporter query failed: {exc}", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
