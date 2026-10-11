#!/usr/bin/env python3
"""Run Freqtrade backtesting offline against a frozen market table (AUTH-2 engine launcher).

Freqtrade loads exchange markets through ccxt before it backtests. Binance's
trading API refuses GitHub runners (HTTP 451), and delisted symbols are absent
from today's market list, so AUTH-2 supplies the markets itself: a frozen JSON
list of plain USDT spot markets (one per engine pair, neutral precision, no
minimum notional) written by research/auth2/engine/markets.py. This launcher
replaces ccxt's market loader with that list and then hands control to
Freqtrade's own CLI.

One engine behaviour is switched off, disclosed in IMPLEMENTATION_NOTES.md:
the price tick Freqtrade's backtester infers from the candle data (the most
decimals printed in each month) is replaced by the frozen market's price
precision, which is none. With the inferred tick, every exit price is rounded
to the tick of the month the trade OPENED in, so an exit capped at the candle
low can round to just below it and Freqtrade then leaves the order unfilled
until the next scheduled change; and the A2 +0.05%/side surcharge on cheap
coins is rounded away or doubled. Orders therefore fill at exactly the open
plus or minus the schedule's slippage, capped to the candle's range, which is
the cost law.

One engine safeguard is bypassed for speed, also disclosed: before each
strategy callback that receives a trade (adjust_trade_position, the custom
price callbacks), Freqtrade deep-copies the trade with its full order history
so a careless strategy cannot mutate it. A schedule follower that rebalances
daily accumulates thousands of orders per trade, which makes that copy
quadratic (over 90% of the run time). AUTH2ScheduleFollower only reads a
trade's pair, amount, stake amount and open date and never writes to it, so
the copy is skipped; the engine parity tests prove the exported trades and
wallet are byte-identical with and without the copy.

Everything else in the engine is untouched: fills, fees, wallet and position
accounting are Freqtrade 2026.7's.

Usage (inside the pinned image or any freqtrade==2026.7 environment):
    python run_backtest.py --markets markets.json [--keep-trade-copy] -- backtesting --config ... --strategy ...

(``--keep-trade-copy`` runs the unmodified copy path; used only by the test that
proves skipping it changes nothing.)

PAPER / RESEARCH ONLY. dry_run stays true, no key is ever configured, and
backtesting places no order.
"""

from __future__ import annotations

import hashlib
import json
import sys


def install_frozen_markets(markets_path: str) -> str:
    raw = open(markets_path, "rb").read()
    markets = json.loads(raw)

    import ccxt
    import ccxt.async_support as ccxt_async

    async def load_markets_helper(self, reload=False, params={}):  # noqa: B006 - ccxt signature
        return self.set_markets([dict(m) for m in markets], None)

    def load_markets_sync(self, reload=False, params={}):  # noqa: B006 - ccxt signature
        return self.set_markets([dict(m) for m in markets], None)

    ccxt_async.binance.load_markets_helper = load_markets_helper
    ccxt.binance.load_markets = load_markets_sync
    return hashlib.sha256(raw).hexdigest()


def use_market_price_precision() -> None:
    from freqtrade.optimize.backtesting import Backtesting

    def get_pair_precision(self, pair, current_time):
        return self.exchange.get_precision_price(pair), self.precision_mode_price

    Backtesting.get_pair_precision = get_pair_precision


def skip_defensive_trade_copy() -> None:
    from freqtrade.strategy import strategy_wrapper

    strategy_wrapper.deepcopy = lambda obj: obj


def main(argv: list[str]) -> int:
    if len(argv) < 4 or argv[0] != "--markets" or "--" not in argv:
        print(__doc__)
        return 2
    sha = install_frozen_markets(argv[1])
    use_market_price_precision()
    if "--keep-trade-copy" in argv[:argv.index("--")]:
        copy_note = "defensive trade copy kept"
    else:
        skip_defensive_trade_copy()
        copy_note = "defensive trade copy skipped"
    print(f"AUTH2 frozen markets {argv[1]} sha256={sha}; price precision from the frozen markets; {copy_note}",
          flush=True)
    rest = argv[argv.index("--") + 1:]
    from freqtrade.main import main as ft_main

    return ft_main(rest) or 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
