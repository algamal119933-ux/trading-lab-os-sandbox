"""Point-in-time universe law for Dataset V3 (FUNNEL_LAW_2.md §POINT_IN_TIME_UNIVERSE_LAW).

Pure functions over per-symbol 1h kline summaries. Nothing here reads prices
to judge an outcome: the only inputs are listing segments, quote volume and
kline presence, all known at the selection timestamp, plus a design-intent
classification table written before any AUTH-2 result.

Operationalisations of the frozen law (each is listed in
research/auth2/IMPLEMENTATION_NOTES.md):

* LISTING SEGMENT. A symbol's archive history is split wherever no 1h kline
  exists for >= HALT_GAP_HOURS consecutive hours. Each segment is one listing:
  its first kline is the listing date and its last kline is the delisting
  date ("last archived kline followed by no data"). This keeps a reused
  ticker (e.g. LUNAUSDT before and after May 2022) from being joined into one
  price path.
* ELIGIBILITY at selection timestamp T: not excluded; the symbol has a kline
  in [T - 24h, T) (it is trading at T); the current segment's first kline is
  <= T - 365 days (U6) or <= T - 90 days (U12, U8).
* RANKING STATISTIC: sum of quote volume of the klines opening in
  [T - 90 days, T). Ties break by symbol name.
* PRICE DATA ON A DAY: the 23:00 UTC kline of that day exists (it carries the
  daily close every decision uses).
* COVERAGE WINDOW: member-days from 2019-01-01 to 2026-08-31 (scored window
  and secondary confirmation), with each window also reported separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

HOUR_MS = 3_600_000
DAY_MS = 24 * HOUR_MS
HALT_GAP_HOURS = 168  # 7 days without any kline ends a listing segment
TERMINAL_LOOKBACK = 24  # klines before the last one that must exist with volume > 0
DELISTING_HAIRCUT = 0.80
DIAGNOSTIC_HAIRCUTS = (1.00, 0.60)
DATA_LIMITED_THRESHOLD = 0.01  # > 1.0% of member-days without price data

# ---------------------------------------------------------------------------
# Design-intent exclusion table. Classified from each asset's stated design at
# listing (what it was issued to be), never from what later happened to it:
# an algorithmic stablecoin is a stablecoin even though UST later collapsed.

STABLECOIN_OR_FIAT = {
    "AEUR": "euro stablecoin", "AUD": "AUD fiat pair", "BFUSD": "Binance yield-bearing USD stablecoin",
    "BKRW": "KRW stablecoin", "BUSD": "USD stablecoin", "DAI": "USD stablecoin (crypto-collateralised)",
    "EUR": "EUR fiat pair", "EURI": "euro stablecoin", "FDUSD": "USD stablecoin", "GBP": "GBP fiat pair",
    "PAX": "USD stablecoin (Paxos Standard)", "TUSD": "USD stablecoin", "USDC": "USD stablecoin",
    "USDP": "USD stablecoin (Paxos)", "USDS": "USD stablecoin", "USDSB": "USD stablecoin",
    "USDSOLD": "USD stablecoin (legacy ticker)", "USD1": "USD stablecoin", "USDE": "synthetic USD stablecoin",
    "RLUSD": "USD stablecoin", "XUSD": "USD stablecoin", "SUSD": "synthetic USD stablecoin",
    "UST": "algorithmic USD stablecoin", "USTC": "algorithmic USD stablecoin (TerraUSD Classic)",
    "KGST": "KGS fiat-pegged stablecoin", "ERN": None,
}
COMMODITY_PEGGED = {"PAXG": "gold-backed token", "XAUT": "gold-backed token"}
LEVERAGED_BASES = ("1INCH", "AAVE", "ADA", "BCH", "BNB", "BTC", "DOT", "EOS", "ETH", "FIL", "LINK", "LTC",
                   "SUSHI", "SXP", "TRX", "UNI", "XLM", "XRP", "XTZ", "YFI")
LEVERAGED_EXTRA = {"BULL": "3x long BTC token", "BEAR": "3x short BTC token"}
WRAPPED_DUPLICATE = {"WBTC": "wrapped BTC", "WBETH": "wrapped staked ETH", "BETH": "staked ETH receipt",
                     "BNSOL": "staked SOL receipt"}


def classify(symbol: str, equity_pegged: frozenset[str] = frozenset()) -> tuple[str, str]:
    """(class, reason) for a USDT spot symbol; class INCLUDED means it may be ranked."""
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    reason = STABLECOIN_OR_FIAT.get(base)
    if reason:
        return "EXCLUDED_STABLECOIN_OR_FIAT_PEGGED", reason
    if base in COMMODITY_PEGGED:
        return "EXCLUDED_COMMODITY_PEGGED", COMMODITY_PEGGED[base]
    if base in equity_pegged:
        return "EXCLUDED_EXTERNAL_ASSET_PEGGED", "tokenised equity / ETF tracker"
    if base in LEVERAGED_EXTRA:
        return "EXCLUDED_LEVERAGED", LEVERAGED_EXTRA[base]
    for b in LEVERAGED_BASES:
        for suffix in ("UP", "DOWN", "BULL", "BEAR"):
            if base == b + suffix:
                return "EXCLUDED_LEVERAGED", f"leveraged token on {b}"
    if base in WRAPPED_DUPLICATE:
        return "EXCLUDED_WRAPPED_DUPLICATE", WRAPPED_DUPLICATE[base]
    return "INCLUDED", "ordinary crypto asset"


# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    first_ms: int
    last_ms: int


def segments(open_ms: list[int]) -> list[Segment]:
    """Listing segments of a sorted kline open-time list (see module docstring)."""
    if not open_ms:
        return []
    out, start, prev = [], open_ms[0], open_ms[0]
    for t in open_ms[1:]:
        if t - prev > HALT_GAP_HOURS * HOUR_MS:
            out.append(Segment(start, prev))
            start = t
        prev = t
    out.append(Segment(start, prev))
    return out


def terminal_trustworthy(open_ms: list[int], volume: list[float], last_index: int) -> bool:
    """The 24 klines before the last one are all present (contiguous hours) with volume > 0."""
    if last_index < TERMINAL_LOOKBACK:
        return False
    last = open_ms[last_index]
    for k in range(1, TERMINAL_LOOKBACK + 1):
        i = last_index - k
        if open_ms[i] != last - k * HOUR_MS or not volume[i] > 0:
            return False
    return True


def ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def iso(t_ms: int) -> str:
    return datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def u6_dates() -> list[int]:
    return [ms(datetime(y, 1, 1)) for y in range(2019, 2027)]


def monthly_dates() -> list[int]:
    """Selection timestamps at each month end from 2018-12-31 (00:00 UTC of the next day)."""
    out, y, m = [], 2019, 1
    while (y, m) <= (2026, 8):
        out.append(ms(datetime(y, m, 1)))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def next_selection(t: int, dates: list[int], end_ms: int) -> int:
    later = [d for d in dates if d > t]
    return later[0] if later else end_ms


@dataclass(frozen=True)
class SymbolSummary:
    """What selection needs from one symbol, all derived from its 1h klines."""
    symbol: str
    cls: str
    segments: tuple[Segment, ...]
    open_ms: tuple[int, ...]
    quote_volume_prefix: tuple[float, ...]  # prefix sums aligned with open_ms (len + 1)


def _bisect_left(a, x) -> int:
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def eligible_stat(s: SymbolSummary, t: int, min_listing_days: int) -> float | None:
    """Ranking statistic of ``s`` at ``t`` if it is eligible, else None."""
    if s.cls != "INCLUDED":
        return None
    i_now = _bisect_left(s.open_ms, t)  # klines strictly before t: [0, i_now)
    if i_now == 0 or s.open_ms[i_now - 1] < t - DAY_MS:
        return None  # not trading in the 24h before t
    seg = next(g for g in s.segments if g.first_ms <= s.open_ms[i_now - 1] <= g.last_ms)
    if seg.first_ms > t - min_listing_days * DAY_MS:
        return None
    i_lo = _bisect_left(s.open_ms, t - 90 * DAY_MS)
    return s.quote_volume_prefix[i_now] - s.quote_volume_prefix[i_lo]


def select(summaries: list[SymbolSummary], t: int, top: int, min_listing_days: int) -> dict:
    ranked = []
    for s in summaries:
        stat = eligible_stat(s, t, min_listing_days)
        if stat is not None:
            ranked.append((s.symbol, stat))
    ranked.sort(key=lambda r: (-r[1], r[0]))
    return {"selection_utc": iso(t), "eligible": [[sym, stat] for sym, stat in ranked],
            "members": [sym for sym, _ in ranked[:top]]}


def segment_at(s: SymbolSummary, t: int) -> Segment:
    i_now = _bisect_left(s.open_ms, t)
    last = s.open_ms[i_now - 1]
    return next(g for g in s.segments if g.first_ms <= last <= g.last_ms)


def build_membership(summaries: list[SymbolSummary], kind: str, end_ms: int) -> list[dict]:
    """Membership periods [start, end) with members and their listing segment."""
    by = {s.symbol: s for s in summaries}
    if kind == "U6":
        dates, top, listing = u6_dates(), 6, 365
    elif kind in ("U12", "U8"):
        dates, top, listing = monthly_dates(), (12 if kind == "U12" else 8), 90
    else:
        raise ValueError(kind)
    out = []
    for t in dates:
        sel = select(summaries, t, top, listing)
        period_end = next_selection(t, dates, end_ms)
        members = []
        for rank, sym in enumerate(sel["members"], start=1):
            seg = segment_at(by[sym], t)
            members.append({"symbol": sym, "rank": rank, "segment_first_utc": iso(seg.first_ms),
                            "segment_last_utc": iso(seg.last_ms)})
        out.append({"selection_utc": sel["selection_utc"], "period_start_utc": iso(t),
                    "period_end_utc": iso(period_end), "members": members,
                    "eligible_count": len(sel["eligible"]), "eligible": sel["eligible"]})
    return out
