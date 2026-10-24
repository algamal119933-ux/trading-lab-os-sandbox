"""The as-seen capture loop (FP-CONTROL-1 activation pack section 0.1, stop condition S19).

The capture loop is the process that turns a running paper instance into
evidence, so these tests attack the properties that would make that evidence
worthless: a candle captured twice, a bar decided twice across a restart, a
paper fill recorded twice, a malformed event accepted, a decision that no input
supports.

Every test here is offline and deterministic. The market source is a stub that
replays a fixed candle series, because a test that reached the exchange would
fail for reasons that have nothing to do with the code under test, and CI must
be able to prove these properties without a market route.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fp import capture as fp_capture

# The runnable control instance. FP-CONTROL-1 is CLOSED, and selection refuses a
# closed row, so every loop these tests build must name the pre-T0 successor —
# which is exactly what a real qualification run does.
QUALIFYING_ROLE = "FP-CONTROL-3"


@pytest.fixture(autouse=True)
def _an_executable_registry(executable_registry_file):
    """Every test here drives the runtime, which only executes an open row.

    The committed registry has no open row once the stage is closed, so these
    tests run against an isolated temporary registry in which the cohort under
    test is executable (``conftest.executable_registry``). The committed file is
    never written; that a CLOSED row is refused is proved in
    tests/test_fp_successor_instance.py against the committed registry itself.
    """
    return executable_registry_file


def make_loop(*args, **kwargs):
    kwargs.setdefault("role", QUALIFYING_ROLE)
    # The lane is created explicitly, the way capture's own entry point creates
    # it. Appending to a ledger no longer conjures the directory, so a test that
    # relied on that would have been testing a behaviour production removed.
    evidence = Path(args[0])
    evidence.mkdir(parents=True, exist_ok=True)
    return fp_capture.CaptureLoop(*args, **kwargs)
from fp import ledger as fp_ledger
from fp import market as fp_market
from fp import reconcile as fp_reconcile

HOUR_MS = 3_600_000
BASE_TS = 1_700_000_000_000 - (1_700_000_000_000 % HOUR_MS)


# --------------------------------------------------------------------------
# Deterministic market stub
# --------------------------------------------------------------------------


def make_candle(pair: str, index: int, close: float, *, now_ms: int | None = None) -> fp_market.Candle:
    open_ts = BASE_TS + index * HOUR_MS
    close_ts = open_ts + HOUR_MS - 1
    return fp_market.Candle(
        pair=pair,
        timeframe="1h",
        open_ts_ms=open_ts,
        close_ts_ms=close_ts,
        open=close - 1.0,
        high=close + 2.0,
        low=close - 2.0,
        close=close,
        volume=10.0,
        source_ts_ms=close_ts,
        receive_ts_ms=(now_ms if now_ms is not None else close_ts + 1_000),
        source_id=fp_market.SOURCE_ID,
        source_host="https://stub.invalid",
    )


class StubMarket:
    """A market source that serves a fixed series and counts what was asked.

    ``now_ms`` is frozen so bar classification is deterministic: without it the
    same series would drift from LIVE to WARMUP as the test suite ages.
    """

    def __init__(self, series: dict[str, list[fp_market.Candle]], now_ms: int) -> None:
        self.series = series
        self.now_ms_value = now_ms
        self.calls = 0

    def fetch_closed_candles(self, pair, timeframe="1h", limit=3, **kwargs):
        self.calls += 1
        return list(self.series.get(pair, []))[-limit:]

    def utc_ms(self) -> int:
        return self.now_ms_value


def rising_series(pair: str, count: int, now_ms: int) -> list[fp_market.Candle]:
    """A long rise after a decline, so EMA50 crosses EMA200 within the sample."""
    candles = []
    for i in range(count):
        if i < count // 2:
            close = 30000.0 - 20.0 * i
        else:
            close = 30000.0 - 20.0 * (count // 2) + 45.0 * (i - count // 2)
        candles.append(make_candle(pair, i, round(close, 4), now_ms=now_ms))
    return candles


@pytest.fixture
def now_ms() -> int:
    # One second after the last candle of a 900-bar series closes, so the newest
    # bar is LIVE and everything before it is warm-up.
    return BASE_TS + 900 * HOUR_MS + 1_000


@pytest.fixture
def stub_market(now_ms) -> StubMarket:
    return StubMarket({"BTC/USDT": rising_series("BTC/USDT", 900, now_ms)}, now_ms)


@pytest.fixture
def loop(tmp_path, stub_market, repo_root):
    return make_loop(
        tmp_path / "evidence",
        ["BTC/USDT"],
        config_path=repo_root / "freqtrade" / "user_data" / "config.paper.json.example",
        market_module=stub_market,
    )


# --------------------------------------------------------------------------
# 1-2. the ledgers are actually written
# --------------------------------------------------------------------------


def test_input_ledger_write_captures_real_shape(loop, tmp_path):
    summary = loop.capture_inputs("BTC/USDT", limit=5)
    assert summary["written"] == 5

    records = loop.ledgers["input"].records()
    assert len(records) == 5
    payload = records[-1].payload
    for field in (
        "pair", "timeframe", "candle", "market_event_id",
        "source_ts_ms", "receive_ts_ms", "source_id", "candle_is_closed",
    ):
        assert field in payload, f"input payload lost {field}"
    assert payload["identity"]["run_id"]
    assert loop.ledgers["input"].verify() == []


def test_decision_ledger_write_records_frozen_logic(loop):
    loop.capture_inputs("BTC/USDT", limit=900)
    summary = loop.capture_decisions("BTC/USDT")

    assert summary["written"] == 900
    payloads = [r.payload for r in loop.ledgers["decision"].records()]
    assert {p["intended_action"] for p in payloads} <= {"enter_long", "exit_long", "hold"}
    # The sample must actually exercise a signal, or the test proves nothing.
    assert any(p["intended_action"] == "enter_long" for p in payloads)
    assert all(p["strategy_sha256"] for p in payloads)
    assert loop.ledgers["decision"].verify() == []


# --------------------------------------------------------------------------
# 3. input -> decision linkage
# --------------------------------------------------------------------------


def test_every_decision_links_to_a_captured_input(loop):
    loop.capture_inputs("BTC/USDT", limit=900)
    loop.capture_decisions("BTC/USDT")

    captured = {r.payload["market_event_id"] for r in loop.ledgers["input"].records()}
    decided = {r.payload["market_event_id"] for r in loop.ledgers["decision"].records()}
    assert decided <= captured
    assert len(decided) == len(captured)


# --------------------------------------------------------------------------
# 4. duplicate input handling
# --------------------------------------------------------------------------


def test_refetching_the_same_candles_appends_nothing(loop):
    first = loop.capture_inputs("BTC/USDT", limit=10)
    second = loop.capture_inputs("BTC/USDT", limit=10)

    assert first["written"] == 10
    assert second["written"] == 0
    assert second["duplicates"] == 10
    assert len(loop.ledgers["input"].records()) == 10


def test_duplicate_input_survives_a_fresh_process(tmp_path, stub_market, repo_root):
    """A second process must not re-capture what the first already wrote."""
    config = repo_root / "freqtrade" / "user_data" / "config.paper.json.example"
    evidence = tmp_path / "evidence"

    first = make_loop(evidence, ["BTC/USDT"], config_path=config, market_module=stub_market)
    first.capture_inputs("BTC/USDT", limit=10)

    second = make_loop(evidence, ["BTC/USDT"], config_path=config, market_module=stub_market)
    summary = second.capture_inputs("BTC/USDT", limit=10)

    assert summary["written"] == 0
    assert summary["duplicates"] == 10
    assert len(second.ledgers["input"].records()) == 10


# --------------------------------------------------------------------------
# 5. duplicate decision rejection
# --------------------------------------------------------------------------


def test_a_bar_is_never_decided_twice(loop):
    loop.capture_inputs("BTC/USDT", limit=900)
    loop.capture_decisions("BTC/USDT")
    again = loop.capture_decisions("BTC/USDT")

    assert again["written"] == 0
    assert again["duplicates"] == 900
    bars = [(r.payload["pair"], r.payload["candle_ts"]) for r in loop.ledgers["decision"].records()]
    assert len(bars) == len(set(bars))


def test_duplicate_decision_rejected_across_a_restart(tmp_path, stub_market, repo_root):
    config = repo_root / "freqtrade" / "user_data" / "config.paper.json.example"
    evidence = tmp_path / "evidence"

    first = make_loop(evidence, ["BTC/USDT"], config_path=config, market_module=stub_market)
    first.capture_inputs("BTC/USDT", limit=300)
    first.capture_decisions("BTC/USDT")
    before = len(first.ledgers["decision"].records())

    restarted = make_loop(evidence, ["BTC/USDT"], config_path=config, market_module=stub_market)
    summary = restarted.capture_decisions("BTC/USDT")

    assert summary["written"] == 0
    assert summary["duplicates"] == before
    assert len(restarted.ledgers["decision"].records()) == before


# --------------------------------------------------------------------------
# 6. no duplicate paper execution
# --------------------------------------------------------------------------

OPEN_TRADE = {
    "trade_id": 1, "pair": "BTC/USDT", "is_open": True, "open_rate": 30000.0,
    "amount": 0.0003, "stake_amount": 10.0, "enter_tag": "ema_regime_up",
    "open_date": "2026-09-08T10:00:00Z", "strategy": "BaselineEmaRegimeV1",
}
CLOSED_TRADE = dict(
    OPEN_TRADE, is_open=False, close_rate=31000.0, close_date="2026-09-08T14:00:00Z",
    exit_reason="exit_signal", profit_abs=0.29, profit_ratio=0.029,
)


class StubClient:
    def __init__(self, open_trades, closed_trades):
        self.open_trades = open_trades
        self.closed_trades = closed_trades

    def status(self):
        return list(self.open_trades)

    def trades(self, limit=200):
        return list(self.closed_trades)


def test_repeated_polling_records_each_execution_once(tmp_path, stub_market, repo_root):
    config = repo_root / "freqtrade" / "user_data" / "config.paper.json.example"
    loop = make_loop(
        tmp_path / "evidence", ["BTC/USDT"], config_path=config,
        client=StubClient([OPEN_TRADE], []), market_module=stub_market,
    )

    first = loop.capture_trades()
    second = loop.capture_trades()
    third = loop.capture_trades()

    assert first["written"] == 1
    assert second["written"] == 0
    assert third["written"] == 0
    events = [r.payload["trade_event_id"] for r in loop.ledgers["trade"].records()]
    assert events == ["1|position_opened"]


def test_close_adds_one_event_and_never_reopens(tmp_path, stub_market, repo_root):
    config = repo_root / "freqtrade" / "user_data" / "config.paper.json.example"
    client = StubClient([OPEN_TRADE], [])
    loop = make_loop(
        tmp_path / "evidence", ["BTC/USDT"], config_path=config,
        client=client, market_module=stub_market,
    )
    loop.capture_trades()

    client.open_trades = []
    client.closed_trades = [CLOSED_TRADE]
    loop.capture_trades()
    loop.capture_trades()

    payloads = [r.payload for r in loop.ledgers["trade"].records()]
    assert [p["event"] for p in payloads] == ["position_opened", "position_closed"]
    closed = payloads[-1]
    assert closed["profit_abs"] == 0.29
    assert closed["exit_reason"] == "exit_signal"
    assert closed["paper_fill_model_version"] == fp_capture.PAPER_FILL_MODEL_VERSION
    assert "BTC/USDT" not in loop.state.open_positions


# --------------------------------------------------------------------------
# 7-8. restart, reopen, persistence
# --------------------------------------------------------------------------


def test_restart_resumes_the_chain_and_increments_the_counter(tmp_path, stub_market, repo_root):
    config = repo_root / "freqtrade" / "user_data" / "config.paper.json.example"
    evidence = tmp_path / "evidence"

    first = make_loop(evidence, ["BTC/USDT"], config_path=config, market_module=stub_market)
    first.record_run_started()
    first.capture_inputs("BTC/USDT", limit=10)
    tip_before = first.ledgers["input"].tip_digest()
    assert first.identity.restart_counter == 0

    second = make_loop(evidence, ["BTC/USDT"], config_path=config, market_module=stub_market)
    second.record_run_started()

    assert second.identity.restart_counter == 1
    assert second.identity.run_id != first.identity.run_id
    assert second.ledgers["input"].tip_digest() == tip_before
    assert second.ledgers["input"].verify() == []


def test_evidence_survives_reopening_by_fresh_readers(tmp_path, stub_market, repo_root):
    config = repo_root / "freqtrade" / "user_data" / "config.paper.json.example"
    evidence = tmp_path / "evidence"

    loop = make_loop(evidence, ["BTC/USDT"], config_path=config, market_module=stub_market)
    loop.capture_inputs("BTC/USDT", limit=250)
    loop.capture_decisions("BTC/USDT")
    expected = {kind: led.tip_digest() for kind, led in loop.ledgers.items()}

    reopened = fp_ledger.open_ledgers(evidence)
    for kind, led in reopened.items():
        assert led.verify() == [], f"{kind} did not survive reopening"
        assert led.tip_digest() == expected[kind]


def test_recovered_state_matches_what_was_written(tmp_path, stub_market, repo_root):
    config = repo_root / "freqtrade" / "user_data" / "config.paper.json.example"
    evidence = tmp_path / "evidence"

    loop = make_loop(evidence, ["BTC/USDT"], config_path=config, market_module=stub_market)
    loop.capture_inputs("BTC/USDT", limit=250)
    loop.capture_decisions("BTC/USDT")

    state = fp_capture.recover_state(evidence)
    assert state.input_records == 250
    assert state.decision_records == 250
    assert len(state.captured_events) == 250
    assert state.last_candle_ts["BTC/USDT"] == max(
        r.payload["candle"]["ts"] for r in loop.ledgers["input"].records()
    )


# --------------------------------------------------------------------------
# 9. existing-position recovery
# --------------------------------------------------------------------------


def test_an_open_position_is_recovered_after_restart(tmp_path, stub_market, repo_root):
    config = repo_root / "freqtrade" / "user_data" / "config.paper.json.example"
    evidence = tmp_path / "evidence"

    first = make_loop(
        evidence, ["BTC/USDT"], config_path=config,
        client=StubClient([OPEN_TRADE], []), market_module=stub_market,
    )
    first.capture_trades()
    assert "BTC/USDT" in first.state.open_positions

    restarted = make_loop(
        evidence, ["BTC/USDT"], config_path=config,
        client=StubClient([OPEN_TRADE], []), market_module=stub_market,
    )
    assert "BTC/USDT" in restarted.state.open_positions, "a live position was lost across restart"
    assert restarted.state.open_positions["BTC/USDT"]["trade_id"] == 1

    # And the recovered position must still block a second entry on that pair.
    admission = fp_capture.evaluate_admission(
        "enter_long", "BTC/USDT", restarted.config, restarted.state.open_positions, 0, HOUR_MS
    )
    assert admission["result"] == fp_capture.ADMIT_BLOCKED
    assert any("already open" in reason for reason in admission["reasons"])


# --------------------------------------------------------------------------
# 10-12. malformed, missing timestamp, out of order
# --------------------------------------------------------------------------


def _valid_payload() -> dict:
    return make_candle("BTC/USDT", 5, 30000.0).as_input_payload()


def test_valid_payload_is_accepted():
    fp_capture.validate_input_payload(_valid_payload())


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda p: p.pop("pair"), "pair"),
        (lambda p: p.pop("market_event_id"), "market_event_id"),
        (lambda p: p.pop("candle"), "candle"),
        (lambda p: p["candle"].pop("close"), "close"),
        (lambda p: p["candle"].pop("volume"), "volume"),
        (lambda p: p.update(candle="not-an-object"), "not an object"),
        (lambda p: p["candle"].update(high=1.0), "inconsistent"),
        (lambda p: p["candle"].update(volume=-5.0), "negative volume"),
        (lambda p: p.update(candle_is_closed=False), "not marked closed"),
    ],
)
def test_malformed_events_are_rejected(mutate, expected):
    payload = _valid_payload()
    mutate(payload)
    with pytest.raises(fp_capture.CaptureError) as exc:
        fp_capture.validate_input_payload(payload)
    assert expected in str(exc.value)


@pytest.mark.parametrize("field", ["source_ts_ms", "receive_ts_ms"])
def test_missing_timestamp_is_rejected(field):
    payload = _valid_payload()
    payload.pop(field)
    with pytest.raises(fp_capture.CaptureError) as exc:
        fp_capture.validate_input_payload(payload)
    assert field in str(exc.value)


@pytest.mark.parametrize("bad", [None, 0, -1, "1700000000000", 1.5, True])
def test_unusable_timestamp_values_are_rejected(bad):
    payload = _valid_payload()
    payload["source_ts_ms"] = bad
    with pytest.raises(fp_capture.CaptureError):
        fp_capture.validate_input_payload(payload)


def test_receive_before_source_is_rejected():
    """A candle cannot be received before it closed."""
    payload = _valid_payload()
    payload["receive_ts_ms"] = payload["source_ts_ms"] - 1
    with pytest.raises(fp_capture.CaptureError) as exc:
        fp_capture.validate_input_payload(payload)
    assert "precedes" in str(exc.value)


def test_out_of_order_candle_is_rejected():
    payload = _valid_payload()
    last_ts = payload["candle"]["ts"]
    with pytest.raises(fp_capture.CaptureError) as exc:
        fp_capture.validate_input_payload(payload, last_ts=last_ts)
    assert "out-of-order" in str(exc.value)

    with pytest.raises(fp_capture.CaptureError):
        fp_capture.validate_input_payload(payload, last_ts=last_ts + HOUR_MS)


def test_out_of_order_candle_becomes_an_incident_not_a_silent_drop(tmp_path, repo_root, now_ms):
    """A rejected event must leave a trace; a silent drop is indistinguishable
    from a market event that never arrived."""
    config = repo_root / "freqtrade" / "user_data" / "config.paper.json.example"
    forward = make_candle("BTC/USDT", 10, 30000.0, now_ms=now_ms)
    backward = make_candle("BTC/USDT", 4, 29000.0, now_ms=now_ms)

    class OutOfOrderMarket(StubMarket):
        def fetch_closed_candles(self, pair, timeframe="1h", limit=3, **kwargs):
            return [forward, backward]

    loop = make_loop(
        tmp_path / "evidence", ["BTC/USDT"], config_path=config,
        market_module=OutOfOrderMarket({}, now_ms),
    )
    summary = loop.capture_inputs("BTC/USDT")

    assert summary["written"] == 1
    assert summary["rejected"] == 1
    incidents = [r.payload for r in loop.ledgers["incident"].records()]
    assert any(i["category"] == "input_rejected" for i in incidents)
    assert any("out-of-order" in i["detail"] for i in incidents)


# --------------------------------------------------------------------------
# 13. reconciliation
# --------------------------------------------------------------------------


@pytest.fixture
def reconciled(tmp_path, stub_market, repo_root):
    config = repo_root / "freqtrade" / "user_data" / "config.paper.json.example"
    evidence = tmp_path / "evidence"
    loop = make_loop(
        evidence, ["BTC/USDT"], config_path=config,
        client=StubClient([], [CLOSED_TRADE]), market_module=stub_market,
    )
    loop.record_run_started()
    loop.cycle(limit=900)
    return evidence, loop


def test_reconciliation_passes_on_a_clean_capture(reconciled):
    evidence, _ = reconciled
    report = fp_reconcile.reconcile(evidence)
    assert report["reconciliation"] == fp_reconcile.PASS, report["failing_checks"]
    assert report["counts"]["input"] == 900
    assert report["counts"]["decision"] == 900
    assert report["replays"]["BTC/USDT"]["status"] == "PASS"


def test_reconciliation_detects_a_tampered_decision(reconciled):
    """The negative control. A gate that only ever passes proves nothing."""
    evidence, _ = reconciled
    path = evidence / "paper_decision_ledger.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()

    target = next(
        i for i, line in enumerate(lines)
        if json.loads(line)["payload"]["intended_action"] == "enter_long"
    )
    record = json.loads(lines[target])
    record["payload"]["intended_action"] = "hold"
    lines[target] = json.dumps(record, sort_keys=True, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = fp_reconcile.reconcile(evidence)
    assert report["reconciliation"] == fp_reconcile.FAIL
    assert "ledger_chain_integrity" in report["failing_checks"]


def test_reconciliation_detects_a_decision_with_no_input(reconciled):
    evidence, loop = reconciled
    loop.ledgers["decision"].append(
        {
            "pair": "BTC/USDT",
            "timeframe": "1h",
            "candle_ts": BASE_TS - HOUR_MS,
            "market_event_id": "BTC/USDT|1h|" + str(BASE_TS - HOUR_MS),
            "intended_action": "hold",
            "signal_state": "flat",
            "identity": loop.identity.stamp(),
        }
    )
    report = fp_reconcile.reconcile(evidence)
    assert report["reconciliation"] == fp_reconcile.FAIL
    assert "decision_input_linkage" in report["failing_checks"]


def test_reconciliation_detects_a_duplicated_execution(reconciled):
    evidence, loop = reconciled
    payload = dict(loop.ledgers["trade"].records()[0].payload)
    loop.ledgers["trade"].append(payload)

    report = fp_reconcile.reconcile(evidence)
    assert report["reconciliation"] == fp_reconcile.FAIL
    assert "no_duplicate_execution" in report["failing_checks"]


# --------------------------------------------------------------------------
# Duplicate-instance guard (section 16.13)
# --------------------------------------------------------------------------


def test_a_second_writer_is_refused(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    first = fp_capture.EvidenceLock(evidence).acquire()
    try:
        with pytest.raises(fp_capture.DuplicateInstanceError):
            fp_capture.EvidenceLock(evidence).acquire()
    finally:
        first.release()

    # Once released, a later process may take it: a crash must not wedge the
    # runtime permanently.
    second = fp_capture.EvidenceLock(evidence).acquire()
    second.release()


# --------------------------------------------------------------------------
# Warm-up boundary (activation pack A9)
# --------------------------------------------------------------------------


def test_backfilled_bars_are_warmup_and_not_executable(loop):
    loop.capture_inputs("BTC/USDT", limit=900)
    loop.capture_decisions("BTC/USDT")
    payloads = [r.payload for r in loop.ledgers["decision"].records()]

    warmup = [p for p in payloads if p["bar_class"] == fp_capture.BAR_WARMUP]
    live = [p for p in payloads if p["bar_class"] == fp_capture.BAR_LIVE]

    assert warmup, "a backfill must produce warm-up bars"
    assert len(live) == 1, "only the newest closed candle is a live decision bar"
    assert all(p["admission"]["result"] == fp_capture.ADMIT_WARMUP for p in warmup)


def test_t0_relation_reports_the_frozen_boundary_honestly(loop):
    """Every bar must be filed on the correct side of T0, or as unfrozen.

    Asserting only the unfrozen case would make this test true exactly until
    the Owner freezes T0 and useless from then on — the moment the boundary
    starts to matter. So all three states are pinned here, driven off the
    loop's own view of T0 rather than a hard-coded expectation.
    """
    loop.capture_inputs("BTC/USDT", limit=5)
    loop.capture_decisions("BTC/USDT")
    records = loop.ledgers["decision"].records()
    assert records

    if loop.t0_ms is None:
        assert {r.payload["t0_relation"] for r in records} == {"T0_NOT_FROZEN"}
        return

    for record in records:
        close_ts = record.payload["candle_ts"] + HOUR_MS
        expected = "POST_T0" if close_ts >= loop.t0_ms else "PRE_T0"
        assert record.payload["t0_relation"] == expected, record.payload["candle_ts"]


def test_t0_relation_is_unfrozen_when_the_registry_declares_no_t0(loop, monkeypatch):
    """The unfrozen case, pinned independently of the live registry."""
    monkeypatch.setattr(loop, "t0_ms", None)
    loop.capture_inputs("BTC/USDT", limit=5)
    loop.capture_decisions("BTC/USDT")
    assert {r.payload["t0_relation"] for r in loop.ledgers["decision"].records()} == {"T0_NOT_FROZEN"}


def test_the_capture_loop_can_never_write_a_t0(tmp_path, stub_market, repo_root):
    """Freezing T0 is an Owner act; the loop reads it and must not create one.

    A capture loop able to invent a T0 could manufacture prospective evidence
    out of warm-up, which is the single most damaging thing it could do.
    """
    import inspect

    source = inspect.getsource(fp_capture)
    assert 't0_utc"] =' not in source
    assert "def _registry_t0_ms" in source
    # The registry is opened read-only in this module: no write path exists.
    assert "COHORT_REGISTRY.write_text" not in source

    before = (repo_root / "research" / "fp" / "records" / "forward_paper_cohort_registry.json").read_bytes()
    loop = make_loop(
        tmp_path / "evidence", ["BTC/USDT"],
        config_path=repo_root / "freqtrade" / "user_data" / "config.paper.json.example",
        market_module=stub_market,
    )
    loop.record_run_started()
    loop.cycle(limit=10)
    after = (repo_root / "research" / "fp" / "records" / "forward_paper_cohort_registry.json").read_bytes()
    assert before == after, "the capture loop modified the cohort registry"


# --------------------------------------------------------------------------
# Paper-only authority
# --------------------------------------------------------------------------


def test_the_client_exposes_no_execution_path():
    """Structural, not aspirational: there is no method that could trade."""
    forbidden = ("forcebuy", "forceenter", "forcesell", "forceexit", "start", "stop", "post", "delete")
    exposed = {name for name in dir(fp_capture.FreqtradeClient) if not name.startswith("_")}
    assert not exposed & set(forbidden)
    assert exposed == {"ping", "status", "trades", "show_config"}


def test_admission_blocks_when_dry_run_is_not_true(repo_root):
    config = json.loads(
        (repo_root / "freqtrade" / "user_data" / "config.paper.json.example").read_text(encoding="utf-8")
    )
    config["dry_run"] = False
    result = fp_capture.evaluate_admission("enter_long", "BTC/USDT", config, {}, 0, HOUR_MS)
    assert result["result"] == fp_capture.ADMIT_BLOCKED
    assert any("dry_run" in reason for reason in result["reasons"])
