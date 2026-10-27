"""P3-PLN-07 data truth (master plan §13; contract §4): the live-feed validators, exercised on synthetic data.

docs/p3/PLN_07_DATA_TRUTH_COVERAGE.md maps every §13 item to its control. The frozen-dataset controls
(scripts/audit_data.py) already have their own suite, tests/test_data_audit.py. The live retrieval path that
a paper runtime reads, research/fp/market.py, was only ever replaced by a stub in the capture tests. Its own
refusals were never produced. These tests produce them, and they produce the contract's §4 rule on the
capture loop: a missing or duplicate candle is recorded, never filled.

Offline and deterministic. ``market._get`` is replaced by a fake that serves fixed kline rows, so no test
reaches an exchange. No market data is manufactured beyond the few synthetic rows each test needs.
PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fp import capture as fp_capture
from fp import market as fp_market

HOUR_MS = 3_600_000
BASE_TS = 1_700_000_000_000 - (1_700_000_000_000 % HOUR_MS)
ROLE = "FP-CONTROL-3"  # the runnable control row of the isolated registry (conftest.executable_registry)


@pytest.fixture(autouse=True)
def _an_executable_registry(executable_registry_file):
    return executable_registry_file


def kline(index: int, *, o=100.0, h=102.0, low=98.0, c=101.0, v=5.0) -> list:
    """A Binance REST kline row: [open_ts, o, h, l, c, v, close_ts, ...]; values as strings, as served."""
    open_ts = BASE_TS + index * HOUR_MS
    return [open_ts, str(o), str(h), str(low), str(c), str(v), open_ts + HOUR_MS - 1, "0", 0, "0", "0", "0"]


def serve(monkeypatch, responses: dict[str, object], receive_ms: int) -> list[str]:
    """Replace market._get: each host returns its rows (JSON) or raises its exception. Returns the call log."""
    calls: list[str] = []

    def fake_get(url: str):
        host = next(h for h in responses if url.startswith(h))
        calls.append(host)
        answer = responses[host]
        if isinstance(answer, Exception):
            raise answer
        return json.dumps(answer).encode(), receive_ms

    monkeypatch.setattr(fp_market, "_get", fake_get)
    return calls


# --- §13 "missing / partial": the still-forming candle never becomes evidence --------------------------------

def test_the_forming_candle_is_dropped_and_closed_candles_come_back_in_order(monkeypatch):
    now = BASE_TS + 3 * HOUR_MS + 1_000          # bars 0..2 are closed; bar 3 is still forming
    rows = [kline(2), kline(0), kline(1), kline(3)]
    serve(monkeypatch, {fp_market.MARKET_HOSTS[0]: rows}, receive_ms=now)
    candles = fp_market.fetch_closed_candles("BTC/USDT", "1h", limit=4)
    assert [c.open_ts_ms for c in candles] == [BASE_TS, BASE_TS + HOUR_MS, BASE_TS + 2 * HOUR_MS]
    assert all(c.close_ts_ms < now for c in candles)
    # the exchange close time is the source timestamp; the receipt time is separate and never earlier
    assert all(c.source_ts_ms == c.close_ts_ms and c.receive_ts_ms == now for c in candles)


def test_a_candle_that_closes_exactly_at_receipt_is_still_forming(monkeypatch):
    close_of_bar_0 = BASE_TS + HOUR_MS - 1
    serve(monkeypatch, {fp_market.MARKET_HOSTS[0]: [kline(0)]}, receive_ms=close_of_bar_0)
    assert fp_market.fetch_closed_candles("BTC/USDT", "1h") == []


# --- §13 structural truth of a received candle ------------------------------------------------------------

@pytest.mark.parametrize("row, why", [
    (kline(0, h=99.0), "OHLC is not internally consistent"),        # high below open and close
    (kline(0, low=101.5), "OHLC is not internally consistent"),     # low above open
    (kline(0, v=-1.0), "negative volume"),
    (kline(0)[:6], r"not a 7\+ element array"),                     # truncated row: no close time
    ([BASE_TS, "x", "1", "1", "1", "1", BASE_TS + HOUR_MS - 1], "unparsable kline row"),
])
def test_a_malformed_kline_is_refused_not_repaired(row, why):
    with pytest.raises(fp_market.MarketError, match=why):
        fp_market._parse_row(row, "BTC/USDT", "1h", "https://stub.invalid", BASE_TS + 10 * HOUR_MS)


def test_one_malformed_row_fails_the_whole_response_rather_than_being_skipped(monkeypatch):
    now = BASE_TS + 5 * HOUR_MS
    serve(monkeypatch, {fp_market.MARKET_HOSTS[0]: [kline(0), kline(1, v=-3.0), kline(2)]}, receive_ms=now)
    with pytest.raises(fp_market.MarketError, match="negative volume"):
        fp_market.fetch_closed_candles("BTC/USDT", "1h")


# --- §13 source identity: a fallback host is recorded, a dead route is never an empty success ----------------

def test_the_fallback_host_serves_and_is_named_in_every_candle(monkeypatch):
    primary, fallback = fp_market.MARKET_HOSTS[:2]
    now = BASE_TS + 2 * HOUR_MS + 1
    calls = serve(monkeypatch, {primary: OSError("unreachable"), fallback: [kline(0), kline(1)]}, receive_ms=now)
    candles = fp_market.fetch_closed_candles("ETH/USDT", "1h")
    assert calls == [primary, fallback]
    assert {c.source_host for c in candles} == {fallback}
    assert {c.source_id for c in candles} == {fp_market.SOURCE_ID}


@pytest.mark.parametrize("answers", [
    {"a": OSError("down"), "b": OSError("down")},
    {"a": [], "b": {"code": -1121, "msg": "Invalid symbol."}},
])
def test_no_usable_host_raises_instead_of_returning_no_candles(monkeypatch, answers):
    hosts = tuple(fp_market.MARKET_HOSTS[:2])
    serve(monkeypatch, dict(zip(hosts, answers.values())), receive_ms=BASE_TS)
    with pytest.raises(fp_market.MarketError, match="no market host served"):
        fp_market.fetch_closed_candles("BTC/USDT", "1h", hosts=hosts)


# --- §13 duplicate candles: one market event has one identity --------------------------------------------

def test_the_market_event_identity_is_pair_timeframe_and_open_time_only():
    a = fp_market.market_event_id("BTC/USDT", "1h", BASE_TS)
    assert a == fp_market.market_event_id("BTC/USDT", "1h", BASE_TS)
    assert a != fp_market.market_event_id("BTC/USDT", "1h", BASE_TS + HOUR_MS)
    assert a != fp_market.market_event_id("ETH/USDT", "1h", BASE_TS)
    assert a != fp_market.market_event_id("BTC/USDT", "5m", BASE_TS)


# --- §13 timezone consistency: UTC milliseconds throughout, and a bounded clock ------------------------------

def test_timestamps_render_as_utc():
    assert fp_market.iso_from_ms(BASE_TS).endswith("Z")
    assert fp_market.iso_from_ms(0) == "1970-01-01T00:00:00.000Z"


def test_clock_skew_tolerance_is_one_candle_period_and_symmetric():
    def reading(skew_ms: int) -> fp_market.ClockReading:
        return fp_market.ClockReading("h", server_time_ms=BASE_TS + skew_ms, local_mid_ms=BASE_TS, round_trip_ms=40)

    assert fp_market.CLOCK_SKEW_STOP_MS == fp_market.TIMEFRAME_MS["1h"]
    assert reading(fp_market.CLOCK_SKEW_STOP_MS - 1).within_tolerance
    assert reading(-(fp_market.CLOCK_SKEW_STOP_MS - 1)).within_tolerance
    assert not reading(fp_market.CLOCK_SKEW_STOP_MS).within_tolerance
    assert not reading(-fp_market.CLOCK_SKEW_STOP_MS).within_tolerance
    assert reading(1234).as_payload()["skew_ms"] == 1234


# --- contract §4: missing and duplicate candles are recorded, never filled ------------------------------------

def candle(index: int, now_ms: int) -> fp_market.Candle:
    open_ts = BASE_TS + index * HOUR_MS
    return fp_market.Candle("BTC/USDT", "1h", open_ts, open_ts + HOUR_MS - 1, 100.0, 102.0, 98.0, 101.0, 5.0,
                            open_ts + HOUR_MS - 1, now_ms, fp_market.SOURCE_ID, "https://stub.invalid")


class ScriptedMarket:
    """Serves one scripted answer per call: a list of candles, or an exception to raise."""

    def __init__(self, answers: list, now_ms: int) -> None:
        self.answers, self.now = list(answers), now_ms

    def fetch_closed_candles(self, pair, timeframe="1h", limit=3, **kwargs):
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def utc_ms(self) -> int:
        return self.now


def make_loop(tmp_path: Path, repo_root: Path, market) -> fp_capture.CaptureLoop:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    return fp_capture.CaptureLoop(evidence, ["BTC/USDT"], role=ROLE, market_module=market,
                                  config_path=repo_root / "freqtrade" / "user_data" / "config.paper.json.example")


def test_a_missed_bar_is_an_incident_and_is_never_backfilled(tmp_path, repo_root):
    now = BASE_TS + 10 * HOUR_MS
    market = ScriptedMarket([[candle(0, now)], fp_market.MarketError("no market host served BTC/USDT 1h"),
                             [candle(2, now)]], now)
    loop = make_loop(tmp_path, repo_root, market)
    first, failed, third = (loop.capture_inputs("BTC/USDT", limit=1) for _ in range(3))

    assert (first["written"], failed["written"], third["written"]) == (1, 0, 1)
    assert "error" in failed
    incidents = [r.payload for r in loop.ledgers["incident"].records()]
    assert [i["category"] for i in incidents] == ["market_fetch_failed"]
    # bar 1 was never received, so it is absent from the evidence: not interpolated, not copied forward
    captured = [r.payload["candle"]["ts"] for r in loop.ledgers["input"].records()]
    assert captured == [BASE_TS, BASE_TS + 2 * HOUR_MS]


def test_a_candle_served_twice_in_one_response_is_written_once(tmp_path, repo_root):
    now = BASE_TS + 10 * HOUR_MS
    loop = make_loop(tmp_path, repo_root, ScriptedMarket([[candle(0, now), candle(0, now), candle(1, now)]], now))
    summary = loop.capture_inputs("BTC/USDT")
    assert (summary["written"], summary["duplicates"]) == (2, 1)
    captured = [r.payload["market_event_id"] for r in loop.ledgers["input"].records()]
    assert len(captured) == len(set(captured)) == 2
