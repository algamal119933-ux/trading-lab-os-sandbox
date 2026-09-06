#!/usr/bin/env python3
"""Fail closed if the selected Freqtrade config is not paper-safe."""

from __future__ import annotations

import json
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "freqtrade" / "user_data" / "config.json"


def fail(msg: str) -> None:
    print(f"PAPER_GUARD_FAIL: {msg}", file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    if not CONFIG.exists():
        fail(f"missing {CONFIG}; copy config.paper.json.example to config.json")

    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON: {exc}")

    if cfg.get("dry_run") is not True:
        fail("dry_run must be true")
    if cfg.get("trading_mode", "spot") != "spot":
        fail("v1 permits spot mode only")
    if cfg.get("force_entry_enable") is not False:
        fail("force_entry_enable must be false")
    if cfg.get("dry_run_wallet", 0) <= 0:
        fail("dry_run_wallet must be positive")

    exchange = cfg.get("exchange") or {}
    if exchange.get("key") or exchange.get("secret"):
        fail("exchange key/secret must be empty in the v1 config file")

    if cfg.get("max_open_trades", 0) < 1 or cfg.get("max_open_trades", 0) > 3:
        fail("v1 max_open_trades must be between 1 and 3")

    stake = cfg.get("stake_amount")
    if not isinstance(stake, (int, float)) or stake <= 0:
        fail("v1 stake_amount must be a positive fixed number")

    api = cfg.get("api_server") or {}
    if api.get("enabled") is not True:
        fail("api_server must be enabled for local observability")
    if api.get("listen_ip_address") != "0.0.0.0":
        fail("inside Docker api_server.listen_ip_address must be 0.0.0.0; host port remains localhost-bound")

    print("PAPER_GUARD_PASS")


if __name__ == "__main__":
    main()
