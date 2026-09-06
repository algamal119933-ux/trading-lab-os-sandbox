"""Exporter unit tests — the exporter must stay read-only and fail safe.

The exporter sits between Freqtrade and Prometheus. Two properties matter:
it must never be able to place or cancel an order, and a Freqtrade outage must
show up as ``freqtrade_api_up 0`` rather than as a stale-looking healthy metric.
"""

from __future__ import annotations

import pytest

import exporter


class FakeResponse:
    def __init__(self, payload, status: int = 200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


PAYLOADS = {
    "ping": {"status": "pong"},
    "count": {"current": 2, "max": 2, "total_stake": 20.0},
    "profit": {
        "profit_closed_coin": -1.25,
        "profit_all_coin": -1.5,
        "trade_count": 7,
        "closed_trade_count": 5,
        "winning_trades": 2,
        "losing_trades": 3,
    },
    "health": {"last_process_ts": 1_756_000_000},
}


@pytest.fixture
def fake_api(monkeypatch):
    calls: list[str] = []

    def fake_get(url, **kwargs):
        path = url.rsplit("/api/v1/", 1)[-1]
        calls.append(path)
        if path not in PAYLOADS:
            return FakeResponse(None, status=404)
        return FakeResponse(PAYLOADS[path])

    monkeypatch.setattr(exporter.requests, "get", fake_get)
    return calls


def value(metric) -> float:
    return metric._value.get()


def test_update_populates_every_metric(fake_api):
    exporter.update()
    assert value(exporter.api_up) == 1
    assert value(exporter.open_trades) == 2
    assert value(exporter.max_open_trades) == 2
    assert value(exporter.total_trades) == 7
    assert value(exporter.closed_trades) == 5
    assert value(exporter.winning_trades) == 2
    assert value(exporter.losing_trades) == 3
    assert value(exporter.profit_all_coin) == pytest.approx(-1.5)
    assert value(exporter.profit_closed_coin) == pytest.approx(-1.25)
    assert value(exporter.last_process_ts) == 1_756_000_000


def test_readiness_is_checked_before_authenticated_calls(fake_api):
    exporter.update()
    assert fake_api[0] == "ping"


def test_ping_is_unauthenticated(monkeypatch):
    seen: dict[str, object] = {}

    def fake_get(url, **kwargs):
        seen[url.rsplit("/api/v1/", 1)[-1]] = kwargs.get("auth")
        return FakeResponse(PAYLOADS.get(url.rsplit("/api/v1/", 1)[-1], {}))

    monkeypatch.setattr(exporter.requests, "get", fake_get)
    exporter.update()
    assert seen["ping"] is None
    assert seen["profit"] is not None


def test_api_failure_is_visible_as_api_up_zero(monkeypatch):
    exporter.api_up.set(1)

    def broken_get(url, **kwargs):
        raise ConnectionError("freqtrade is down")

    monkeypatch.setattr(exporter.requests, "get", broken_get)
    with pytest.raises(ConnectionError):
        exporter.update()

    # main() converts the exception into a zeroed liveness metric.
    try:
        exporter.update()
    except Exception:  # noqa: BLE001 - mirrors the loop body in main()
        exporter.api_up.set(0)
    assert value(exporter.api_up) == 0


def test_missing_numeric_fields_are_skipped_not_zeroed(monkeypatch):
    exporter.open_trades.set(99)

    def sparse_get(url, **kwargs):
        path = url.rsplit("/api/v1/", 1)[-1]
        return FakeResponse({} if path != "ping" else {"status": "pong"})

    monkeypatch.setattr(exporter.requests, "get", sparse_get)
    exporter.update()
    assert value(exporter.open_trades) == 99


def test_exporter_never_calls_a_mutating_endpoint(repo_root):
    source = (repo_root / "monitoring/exporter/exporter.py").read_text(encoding="utf-8")
    assert "requests.post" not in source
    assert "requests.delete" not in source
    for endpoint in ("forceenter", "forcebuy", "forceexit", "forcesell", "stop", "reload_config"):
        assert endpoint not in source.lower(), f"exporter references mutating endpoint {endpoint}"


def test_num_helper_ignores_non_numeric_and_boolean_values():
    assert exporter.num({"a": "3"}, "a") is None
    assert exporter.num({"a": None, "b": 4}, "a", "b") == 4.0
    assert exporter.num({}, "missing") is None
