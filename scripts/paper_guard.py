#!/usr/bin/env python3
"""Fail closed unless every inspected Freqtrade config is paper-safe.

CLOUD-0 / C0.3 — paper-safety invariant.

The guard is deliberately conservative: anything it cannot positively prove to be
paper-safe is a failure. It never "passes by default" on a missing or unreadable
config, and it refuses configs that merely *could* be flipped to live trading
without an obvious edit.

Usage
-----
    python3 scripts/paper_guard.py                     # check every known paper config present
    python3 scripts/paper_guard.py --config path.json  # check exactly these files (must exist)
    python3 scripts/paper_guard.py --list              # show what would be checked

Exit codes
----------
    0  every inspected config passed
    2  at least one violation, or nothing could be inspected
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
USER_DATA = REPO_ROOT / "freqtrade" / "user_data"
STRATEGY_DIR = USER_DATA / "strategies"

# Configs the guard inspects when no --config is supplied. A path that does not
# exist is skipped here (the runtime scripts assert existence themselves), but if
# *none* of them exist the guard still fails closed.
DEFAULT_CANDIDATES = (
    USER_DATA / "config.json",
    USER_DATA / "config.paper.json.example",
)

# Bounds for the paper sandbox. These are intentionally small: CLOUD-0 is a
# research harness, not a capital allocator.
MAX_OPEN_TRADES_RANGE = (1, 3)
MAX_DRY_RUN_WALLET = 1000.0

# Keys that belong to the strategy, never to the config (C0.4 config isolation).
# Allowing them in the config silently overrides strategy values and makes a
# backtest non-reproducible from the strategy file alone.
STRATEGY_OWNED_KEYS = (
    "minimal_roi",
    "stoploss",
    "timeframe",
    "trailing_stop",
    "trailing_stop_positive",
    "trailing_stop_positive_offset",
    "trailing_only_offset_is_reached",
    "use_custom_stoploss",
    "process_only_new_candles",
    "startup_candle_count",
    "order_types",
    "order_time_in_force",
)

# Credential-bearing fields that must be empty inside a committed config.
EXCHANGE_CREDENTIAL_KEYS = ("key", "secret", "password", "uid", "apiKey", "privateKey", "walletAddress")

LEVERAGED_TOKEN_RE = re.compile(r"^[A-Z0-9]+(UP|DOWN|BULL|BEAR|[35]L|[35]S)/", re.IGNORECASE)


def rel(path: Path) -> str:
    """Repo-relative path when possible, absolute otherwise (temp dirs in tests)."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


class Violations(list):
    def add(self, source: str, message: str) -> None:
        self.append(f"{source}: {message}")


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_config(path: Path, violations: Violations) -> None:
    src = rel(path)

    if not path.exists():
        violations.add(src, "config file does not exist")
        return
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - any parse problem is fail-closed
        violations.add(src, f"invalid JSON: {exc}")
        return
    if not isinstance(cfg, dict):
        violations.add(src, "top-level config must be a JSON object")
        return

    # --- paper mode -------------------------------------------------------
    if cfg.get("dry_run") is not True:
        violations.add(src, "dry_run must be exactly true")

    # --- spot only, no derivatives ---------------------------------------
    if cfg.get("trading_mode") != "spot":
        violations.add(src, 'trading_mode must be explicitly "spot"')
    margin_mode = cfg.get("margin_mode", "")
    if margin_mode not in ("", None):
        violations.add(src, f"margin_mode must be empty for spot, found {margin_mode!r}")

    # --- no leverage ------------------------------------------------------
    for key in ("leverage", "max_leverage"):
        if key in cfg and cfg[key] not in (1, 1.0):
            violations.add(src, f"{key} must be absent or 1, found {cfg[key]!r}")

    # --- no shorts --------------------------------------------------------
    if cfg.get("can_short") is True:
        violations.add(src, "can_short must not be enabled")

    # --- bounded sandbox --------------------------------------------------
    max_open = cfg.get("max_open_trades")
    low, high = MAX_OPEN_TRADES_RANGE
    if not isinstance(max_open, int) or isinstance(max_open, bool) or not low <= max_open <= high:
        violations.add(src, f"max_open_trades must be an int in [{low}, {high}], found {max_open!r}")

    wallet = cfg.get("dry_run_wallet")
    if not _is_number(wallet) or not 0 < float(wallet) <= MAX_DRY_RUN_WALLET:
        violations.add(src, f"dry_run_wallet must be a number in (0, {MAX_DRY_RUN_WALLET}], found {wallet!r}")

    stake = cfg.get("stake_amount")
    if not _is_number(stake) or float(stake) <= 0:
        violations.add(src, f"stake_amount must be a positive fixed number (never 'unlimited'), found {stake!r}")
    elif _is_number(wallet) and float(stake) > float(wallet):
        violations.add(src, "stake_amount must not exceed dry_run_wallet")

    ratio = cfg.get("tradable_balance_ratio", 1.0)
    if not _is_number(ratio) or not 0 < float(ratio) <= 1:
        violations.add(src, f"tradable_balance_ratio must be in (0, 1], found {ratio!r}")

    # --- manual order injection ------------------------------------------
    if cfg.get("force_entry_enable") is not False:
        violations.add(src, "force_entry_enable must be explicitly false")

    # --- no credentials, no withdrawal path -------------------------------
    exchange = cfg.get("exchange")
    if not isinstance(exchange, dict):
        violations.add(src, "exchange section is missing")
        exchange = {}
    for key in EXCHANGE_CREDENTIAL_KEYS:
        if exchange.get(key):
            violations.add(src, f"exchange.{key} must be empty in a committed config")
    ccxt_blocks = [exchange.get("ccxt_config"), exchange.get("ccxt_async_config"), exchange.get("ccxt_sync_config")]
    for block in ccxt_blocks:
        if not isinstance(block, dict):
            continue
        for key in EXCHANGE_CREDENTIAL_KEYS:
            if block.get(key):
                violations.add(src, f"exchange ccxt config must not carry {key}")
        if block.get("sandbox") is True:
            violations.add(src, "exchange ccxt sandbox mode is not part of the paper baseline")
    for key in cfg:
        if "withdraw" in key.lower():
            violations.add(src, f"withdrawal-related config key {key!r} is forbidden")
    for key in exchange:
        if "withdraw" in key.lower():
            violations.add(src, f"withdrawal-related exchange key {key!r} is forbidden")

    # --- pair sanity: spot pairs only -------------------------------------
    whitelist = exchange.get("pair_whitelist")
    if not isinstance(whitelist, list) or not whitelist:
        violations.add(src, "exchange.pair_whitelist must be a non-empty list")
    else:
        for pair in whitelist:
            if not isinstance(pair, str) or "/" not in pair:
                violations.add(src, f"pair {pair!r} is not a spot pair string")
                continue
            if ":" in pair:
                violations.add(src, f"pair {pair!r} uses derivatives notation")
            if LEVERAGED_TOKEN_RE.match(pair):
                violations.add(src, f"pair {pair!r} looks like a leveraged token")

    # --- config/strategy isolation (C0.4) ---------------------------------
    for key in STRATEGY_OWNED_KEYS:
        if key in cfg:
            violations.add(
                src,
                f"{key!r} belongs to the strategy; keeping it in the config silently overrides "
                "the strategy value and breaks reproducibility",
            )

    # --- observability ----------------------------------------------------
    api = cfg.get("api_server")
    if not isinstance(api, dict):
        violations.add(src, "api_server section is missing")
    else:
        if api.get("enabled") is not True:
            violations.add(src, "api_server must be enabled for local observability")
        if api.get("listen_ip_address") != "0.0.0.0":
            violations.add(
                src,
                "inside Docker api_server.listen_ip_address must be 0.0.0.0; the host port stays localhost-bound",
            )

    telegram = cfg.get("telegram")
    if isinstance(telegram, dict) and telegram.get("enabled") is True:
        violations.add(src, "telegram must stay disabled in the paper baseline")


def check_strategies(violations: Violations) -> None:
    """Reject strategy files that enable shorting or derivative trading modes."""
    if not STRATEGY_DIR.is_dir():
        return
    for path in sorted(STRATEGY_DIR.glob("*.py")):
        src = rel(path)
        text = path.read_text(encoding="utf-8")
        if re.search(r"^\s*can_short\s*=\s*True", text, re.MULTILINE):
            violations.add(src, "can_short must be False in the paper baseline")
        if re.search(r"^\s*trading_mode\s*=\s*[\"'](?!spot)", text, re.MULTILINE):
            violations.add(src, "strategy declares a non-spot trading_mode")
        if re.search(r"^\s*(leverage|can_leverage)\s*=", text, re.MULTILINE):
            violations.add(src, "strategy declares leverage")


def resolve_targets(explicit: list[str]) -> tuple[list[Path], list[str]]:
    if explicit:
        return [Path(p) if Path(p).is_absolute() else (REPO_ROOT / p) for p in explicit], []
    present = [p for p in DEFAULT_CANDIDATES if p.exists()]
    notes = []
    if not present:
        notes.append(
            "no known paper config found; expected one of: "
            + ", ".join(rel(p) for p in DEFAULT_CANDIDATES)
        )
    return present, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail closed unless the Freqtrade configs are paper-safe.")
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        metavar="PATH",
        help="Config to inspect (repeatable). Must exist. Defaults to every known paper config present.",
    )
    parser.add_argument("--list", action="store_true", help="Print the configs that would be inspected and exit.")
    parser.add_argument("--skip-strategies", action="store_true", help="Do not scan strategy files.")
    args = parser.parse_args(argv)

    targets, notes = resolve_targets(args.config)

    if args.list:
        for path in targets:
            print(rel(path))
        for note in notes:
            print(f"note: {note}")
        return 0 if targets else 2

    violations = Violations()
    for note in notes:
        violations.add("paper_guard", note)
    for path in targets:
        check_config(path, violations)
    if not args.skip_strategies:
        check_strategies(violations)

    if violations:
        for item in violations:
            print(f"PAPER_GUARD_FAIL: {item}", file=sys.stderr)
        print(f"PAPER_GUARD_FAIL: {len(violations)} violation(s)", file=sys.stderr)
        return 2

    for path in targets:
        print(f"checked {rel(path)}")
    print("PAPER_GUARD_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
