"""Real public market input for the as-seen capture loop (FP-BOOT-1 sections 6, 8, 16.8).

The capture loop's first obligation is that the candle it records was actually
received from an exchange at a knowable moment. Section 16.8 asks for the input
ledger to work "on real incoming data", and section 6 requires a prospective
availability contract per decision-time feature: the closed 1h OHLCV candle,
retrieved live, never replayed out of an archive.

That distinction is the reason this module exists separately from
``scripts/fetch_binance_public_data.py``. The fetch script pulls *monthly
archives* to build the frozen Dataset V2 — a post-facto source, correct for
research and inadmissible as a real-time feed. This module reads the live REST
klines endpoint, which is the same path a running dry-run sees.

Two timestamps are captured for every candle and neither is derived from the
other:

``source_ts_ms``   the exchange's own close time for the candle
``receive_ts_ms``  local UTC when this process finished reading the response

``receive_ts_ms`` is taken *after* the response is read, so it can never be
earlier than the moment the bytes existed locally. A candle whose close time is
not strictly in the past at receipt is refused: an unclosed candle still moves,
and recording one as evidence would let a later value masquerade as a value that
was knowable at decision time. That is the timestamp-knowability defect the
whole protocol exists to exclude, so it fails closed here rather than being
filtered downstream.

Public market data only. No credential is read, sent, or accepted.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Both hosts serve the same public spot klines. ``data-api`` is the read-only
# market-data endpoint and is preferred; ``api`` is the fallback, because a
# single-host dependency turns routine upstream maintenance into a stop
# condition. Neither accepts or requires a credential.
MARKET_HOSTS = (
    "https://data-api.binance.vision",
    "https://api.binance.com",
)

KLINES_PATH = "/api/v3/klines"
TIME_PATH = "/api/v3/time"

TIMEOUT_SECONDS = 20
# Names the project and the retrieval path, not one instance: this module is
# shared by whichever lane is running, and stamping a single instance name
# onto every request made the closed cohort look like the current runtime.
USER_AGENT = "trading-lab-os-fp-capture/1.0 (public market data; paper only)"

# The identity of this retrieval path, recorded into every input record. A
# change of source must be visible in the evidence rather than inferred from a
# commit date.
SOURCE_ID = "binance:spot:public-rest:klines"

TIMEFRAME_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

# Section 16.14 tolerance. The protocol's own stop condition S16 is "clock skew
# beyond one candle period", so the candle period is the bound, and anything
# approaching it is already an incident rather than a healthy runtime.
CLOCK_SKEW_STOP_MS = 3_600_000
CLOCK_SKEW_WARN_MS = 30_000


class MarketError(RuntimeError):
    """Raised when the market route is unusable or returns unusable data."""


def utc_ms() -> int:
    return int(time.time() * 1000)


def iso_from_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def pair_to_symbol(pair: str) -> str:
    """``BTC/USDT`` -> ``BTCUSDT``. The ledger keeps the pair form throughout."""
    return pair.replace("/", "").replace("-", "").upper()


def _get(url: str) -> tuple[bytes, int]:
    """Fetch ``url``; return the body and the local receipt time in ms.

    The receipt stamp is taken after the body is fully read. Stamping before the
    read would record a time at which the data demonstrably did not yet exist
    locally.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        body = response.read()
    return body, utc_ms()


@dataclass(frozen=True)
class Candle:
    """One closed OHLCV candle exactly as it was received."""

    pair: str
    timeframe: str
    open_ts_ms: int
    close_ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    source_ts_ms: int
    receive_ts_ms: int
    source_id: str
    source_host: str

    @property
    def lag_ms(self) -> int:
        """How long after the candle closed this process saw it."""
        return self.receive_ts_ms - self.close_ts_ms

    def as_input_payload(self) -> dict:
        """The ``paper_input_ledger`` payload for this candle.

        ``candle`` keeps the shape ``research/fp/replay.py`` already consumes
        (``ts``/``close``), so the replay reference reads real captured input
        with no translation layer that could quietly change a value.
        """
        return {
            "pair": self.pair,
            "timeframe": self.timeframe,
            "candle": {
                "ts": self.open_ts_ms,
                "open": self.open,
                "high": self.high,
                "low": self.low,
                "close": self.close,
                "volume": self.volume,
            },
            "market_event_id": market_event_id(self.pair, self.timeframe, self.open_ts_ms),
            "open_ts_ms": self.open_ts_ms,
            "close_ts_ms": self.close_ts_ms,
            "exchange_ts": self.source_ts_ms,
            "source_ts_ms": self.source_ts_ms,
            "source_ts_utc": iso_from_ms(self.source_ts_ms),
            "receive_ts_ms": self.receive_ts_ms,
            "received_utc": iso_from_ms(self.receive_ts_ms),
            "receive_lag_ms": self.lag_ms,
            "source_id": self.source_id,
            "source_host": self.source_host,
            "candle_is_closed": True,
        }


def market_event_id(pair: str, timeframe: str, open_ts_ms: int) -> str:
    """Stable identity of one market event.

    Deliberately derived from (pair, timeframe, open time) and nothing else: the
    same candle re-fetched must collide with its earlier capture so the loop can
    recognise a duplicate instead of appending a second copy under a new id.
    """
    return f"{pair}|{timeframe}|{open_ts_ms}"


def _parse_row(row: list, pair: str, timeframe: str, source_host: str, receive_ts_ms: int) -> Candle:
    if not isinstance(row, list) or len(row) < 7:
        raise MarketError(f"{pair} {timeframe}: kline row is not a 7+ element array: {row!r}")
    try:
        open_ts = int(row[0])
        close_ts = int(row[6])
        values = [float(row[index]) for index in (1, 2, 3, 4, 5)]
    except (TypeError, ValueError) as exc:
        raise MarketError(f"{pair} {timeframe}: unparsable kline row: {exc}") from exc

    open_, high, low, close, volume = values
    if not (low <= open_ <= high and low <= close <= high):
        raise MarketError(
            f"{pair} {timeframe} @{open_ts}: OHLC is not internally consistent "
            f"(o={open_} h={high} l={low} c={close})"
        )
    if volume < 0:
        raise MarketError(f"{pair} {timeframe} @{open_ts}: negative volume {volume}")

    return Candle(
        pair=pair,
        timeframe=timeframe,
        open_ts_ms=open_ts,
        close_ts_ms=close_ts,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        # The exchange's close time is the source timestamp: it is the instant
        # the candle became a fact, which is what a later replay must key on.
        source_ts_ms=close_ts,
        receive_ts_ms=receive_ts_ms,
        source_id=SOURCE_ID,
        source_host=source_host,
    )


def fetch_closed_candles(
    pair: str,
    timeframe: str = "1h",
    limit: int = 3,
    hosts: tuple[str, ...] = MARKET_HOSTS,
    now_ms: int | None = None,
) -> list[Candle]:
    """Closed candles for ``pair``, newest last. Unclosed candles are dropped.

    The exchange returns the still-forming candle as the last row. It is
    excluded here rather than by the caller: a forming candle is not evidence,
    and letting one reach the ledger would be a timestamp-knowability defect.
    """
    if timeframe not in TIMEFRAME_MS:
        raise MarketError(f"unsupported timeframe {timeframe!r}; known: {sorted(TIMEFRAME_MS)}")
    symbol = pair_to_symbol(pair)
    query = f"{KLINES_PATH}?symbol={symbol}&interval={timeframe}&limit={max(2, int(limit))}"

    errors: list[str] = []
    for host in hosts:
        try:
            body, receive_ts = _get(host + query)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            errors.append(f"{host}: {exc}")
            continue
        try:
            rows = json.loads(body)
        except json.JSONDecodeError as exc:
            errors.append(f"{host}: response is not JSON: {exc}")
            continue
        if not isinstance(rows, list) or not rows:
            errors.append(f"{host}: empty or non-list klines response")
            continue

        reference_ms = now_ms if now_ms is not None else receive_ts
        candles = []
        for row in rows:
            candle = _parse_row(row, pair, timeframe, host, receive_ts)
            # Strictly closed: close time must already have passed locally.
            if candle.close_ts_ms < reference_ms:
                candles.append(candle)
        candles.sort(key=lambda item: item.open_ts_ms)
        return candles

    raise MarketError(f"no market host served {pair} {timeframe}: " + "; ".join(errors))


@dataclass(frozen=True)
class ClockReading:
    """One measurement of local-versus-exchange clock skew."""

    host: str
    server_time_ms: int
    local_mid_ms: int
    round_trip_ms: int

    @property
    def skew_ms(self) -> int:
        """Exchange time minus local time; positive means local is behind."""
        return self.server_time_ms - self.local_mid_ms

    @property
    def within_tolerance(self) -> bool:
        return abs(self.skew_ms) < CLOCK_SKEW_STOP_MS

    def as_payload(self) -> dict:
        return {
            "host": self.host,
            "server_time_ms": self.server_time_ms,
            "local_mid_ms": self.local_mid_ms,
            "round_trip_ms": self.round_trip_ms,
            "skew_ms": self.skew_ms,
            "tolerance_ms": CLOCK_SKEW_STOP_MS,
            "warn_ms": CLOCK_SKEW_WARN_MS,
            "within_tolerance": self.within_tolerance,
        }


def measure_clock_skew(hosts: tuple[str, ...] = MARKET_HOSTS, samples: int = 3) -> ClockReading:
    """Measure skew against the exchange, keeping the lowest-latency sample.

    Skew is estimated at the midpoint of the request, so a symmetric round trip
    cancels out; the residual error is bounded by half the round-trip time,
    which is recorded alongside the estimate rather than hidden. The
    lowest-latency sample is kept because it has the tightest bound, not because
    it is the most favourable.
    """
    readings: list[ClockReading] = []
    errors: list[str] = []
    for host in hosts:
        for _ in range(max(1, samples)):
            started = utc_ms()
            try:
                body, finished = _get(host + TIME_PATH)
                server_time = int(json.loads(body)["serverTime"])
            except Exception as exc:  # noqa: BLE001 - any failure is just a lost sample
                errors.append(f"{host}: {exc}")
                break
            readings.append(
                ClockReading(
                    host=host,
                    server_time_ms=server_time,
                    local_mid_ms=(started + finished) // 2,
                    round_trip_ms=finished - started,
                )
            )
        if readings:
            break
    if not readings:
        raise MarketError("could not measure clock skew: " + "; ".join(errors))
    return min(readings, key=lambda item: item.round_trip_ms)


def probe_hosts(hosts: tuple[str, ...] = MARKET_HOSTS) -> list[dict]:
    """Reachability of each public market host, for the preflight record."""
    results = []
    for host in hosts:
        started = utc_ms()
        try:
            _get(host + KLINES_PATH + "?symbol=BTCUSDT&interval=1h&limit=1")
            results.append({"host": host, "reachable": True, "elapsed_ms": utc_ms() - started})
        except Exception as exc:  # noqa: BLE001
            results.append({"host": host, "reachable": False, "error": str(exc)[:200]})
    return results
