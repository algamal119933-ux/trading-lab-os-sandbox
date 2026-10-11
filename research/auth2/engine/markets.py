"""Frozen ccxt market entries for AUTH-2 engine pairs (see run_backtest.py).

Every pair gets the same neutral, plain spot market: USDT quote, active, no
minimum amount or notional. The table depends only on the pair names and each
pair's lowest price in the run's own data.

Price precision is ``None``, so Freqtrade never rounds a price: a limit price
capped at the candle low and then rounded to a tick can land a hair outside
[low, high], and the backtester then leaves the order unfilled.

Amount precision is a per-pair decimal tick (truncation). It must not be
``None``: Freqtrade 2026.7 closes a trade's books only when the remaining
amount, summed exactly over the trade's orders, truncates to zero; a residual
left after partial exits makes it book only the last exit's profit at close
and drop the profit of every earlier partial exit from the wallet. The tick is
chosen so every amount the run can produce has at most 15 significant digits
(``amount_tick``): such a decimal survives the float round trip exactly, so the
order amounts of a closed trade sum to exactly zero and no residual can occur.
The truncation it implies is below 1e-14 of an order's value.
"""

from __future__ import annotations

import json
import math

PRICE_TICK = None
SIGNIFICANT_DIGITS = 15
NOTIONAL_CEILING = 1e7  # USDT; 10,000 x the engine wallet, an upper bound on any one order


def amount_tick(min_price: float) -> float:
    """10**(k - 14), where 10**(k+1) bounds the largest amount NOTIONAL_CEILING buys at the
    pair's lowest price in the run's data."""
    if not (min_price > 0 and math.isfinite(min_price)):
        raise ValueError(f"amount_tick needs a positive finite minimum price, got {min_price}")
    k = math.floor(math.log10(NOTIONAL_CEILING / min_price))
    return float(f"1e{k - (SIGNIFICANT_DIGITS - 1)}")


def market(pair: str, tick: float) -> dict:
    base, quote = pair.split("/")
    return {
        "id": f"{base}{quote}", "symbol": pair, "base": base, "quote": quote, "settle": None,
        "baseId": base, "quoteId": quote, "settleId": None, "type": "spot", "spot": True, "margin": False,
        "swap": False, "future": False, "option": False, "index": False, "active": True, "contract": False,
        "linear": None, "inverse": None, "subType": None, "taker": 0.001, "maker": 0.001, "contractSize": None,
        "expiry": None, "expiryDatetime": None, "strike": None, "optionType": None,
        "precision": {"amount": tick, "price": PRICE_TICK, "cost": None, "base": None, "quote": None},
        "limits": {"leverage": {"min": None, "max": None}, "amount": {"min": None, "max": None},
                   "price": {"min": None, "max": None}, "cost": {"min": None, "max": None},
                   "market": {"min": None, "max": None}},
        "marginModes": {"cross": False, "isolated": False}, "created": None, "info": {},
    }


def write(pairs: list[str], path, min_price: dict[str, float]) -> bytes:
    body = (json.dumps([market(p, amount_tick(min_price[p])) for p in sorted(pairs)], indent=1,
                       sort_keys=True) + "\n").encode()
    with open(path, "wb") as fh:
        fh.write(body)
    return body
