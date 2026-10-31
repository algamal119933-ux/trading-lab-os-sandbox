"""P3-PLN-07 data truth, gaps G-1, G-2 and G-4 of docs/p3/PLN_07_DATA_TRUTH_COVERAGE.md.

G-1  research/p3/data_truth.audit_input_ledger: the missing-bar audit of a captured input ledger.
G-2  research/p3/data_truth.compare_feeds: the exact per-bar live-vs-engine comparator.
G-4  the frozen-universe configuration pin: the shipped paper config, the frozen strategy, the compose
     overlay and the cohort registry agree on Binance spot, BTC/USDT + ETH/USDT, 1h, dry-run, long-only.
     It asserts; it changes nothing.

Every audit test builds a synthetic hash-chained ledger with fp.ledger itself and real input payloads
(fp.market.Candle.as_input_payload), so the audit reads exactly the shape the capture loop writes. Each
control is shown failing on the defect it exists to catch. Offline; no market data is fetched.
PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import audit_data
from fp import capture as fp_capture
from fp import ledger as fp_ledger
from fp import market as fp_market
from p3 import data_truth as dt

REPO = Path(__file__).resolve().parents[1]
HOUR_MS = 3_600_000
BASE_TS = 1_700_000_000_000 - (1_700_000_000_000 % HOUR_MS)
PAIRS = ["BTC/USDT", "ETH/USDT"]
ROLE = "FP-CONTROL-3"


def iso(ms: int) -> str:
    return fp_market.iso_from_ms(ms)


def bar_ts(index: int) -> int:
    return BASE_TS + index * HOUR_MS


def input_payload(pair: str, index: int, *, timeframe: str = "1h", ts: int | None = None,
                  receive_lag_ms: int = 5_000, close: float = 101.0) -> dict:
    open_ts = bar_ts(index) if ts is None else ts
    candle = fp_market.Candle(pair, timeframe, open_ts, open_ts + HOUR_MS - 1, 100.0, 102.0, 98.0, close, 5.0,
                              open_ts + HOUR_MS - 1, open_ts + HOUR_MS + receive_lag_ms, fp_market.SOURCE_ID,
                              fp_market.MARKET_HOSTS[0])
    return candle.as_input_payload()


def build_lane(tmp_path: Path, inputs: list[dict], incidents: list[dict] = ()) -> Path:
    lane = tmp_path / "lane" / "evidence"
    ledgers = fp_ledger.open_ledgers(lane, create=True)
    for payload in inputs:
        ledgers["input"].append(payload, recorded_utc="2026-10-28T00:00:00.000Z")
    for payload in incidents:
        ledgers["incident"].append(payload, recorded_utc="2026-10-28T00:00:00.000Z")
    return lane


def full(indices: list[int], pairs=PAIRS) -> list[dict]:
    return [input_payload(pair, i) for i in indices for pair in pairs]


def finding(report: dict, check: str) -> dict:
    return next(f for f in report["findings"] if f["check"] == check)


def audit(lane: Path, **kwargs) -> dict:
    return dt.audit_input_ledger(lane, pairs=kwargs.pop("pairs", PAIRS), timeframe="1h", **kwargs)


# --- G-1: the clean case and the findings law ---------------------------------------------------------

def test_a_complete_ledger_passes_with_every_finding_emitted(tmp_path):
    report = audit(build_lane(tmp_path, full(list(range(6)))))
    assert report["result"] == dt.PASS, report["findings"]
    assert [f["check"] for f in report["findings"]] == list(dt.LEDGER_FINDINGS)
    assert report["per_pair"]["BTC/USDT"]["expected"] == report["per_pair"]["BTC/USDT"]["captured"] == 6
    assert report["real_money_authorized"] is False


# --- G-1: each missing-bar class, and the negative control --------------------------------------------

def test_a_missing_bar_with_a_fetch_failure_in_its_opportunity_is_recorded_not_a_finding(tmp_path):
    inputs = full([0, 1, 3])
    failed_at = bar_ts(3) + 60_000                    # the cycle right after bar 2 closed failed
    lane = build_lane(tmp_path, inputs, [
        {"category": "market_fetch_failed", "detail": "DNS", "pair": pair, "observed_utc": iso(failed_at)}
        for pair in PAIRS])
    report = audit(lane)
    assert report["result"] == dt.PASS, report["findings"]
    per = report["per_pair"]["ETH/USDT"]
    assert (per["expected"], per["captured"], per["missing"]) == (4, 3, 1)
    assert per["classification"][dt.FETCH_FAILURE] == 1
    assert per["gap_clusters"][0]["missing_candles"] == 1


def test_a_missing_bar_followed_by_a_restart_is_downtime_then_restart(tmp_path):
    lane = build_lane(tmp_path, full([0, 1, 4]), [
        {"category": "run_started", "detail": "restart_counter=1", "observed_utc": iso(bar_ts(4) + 30_000)}])
    report = audit(lane)
    assert report["result"] == dt.PASS
    assert report["per_pair"]["BTC/USDT"]["classification"][dt.DOWNTIME_THEN_RESTART] == 2


def test_a_rejected_input_explains_its_own_bar_exactly(tmp_path):
    incidents = [{"category": "input_rejected", "detail": "OHLC inconsistent", "pair": pair,
                  "market_event_id": fp_market.market_event_id(pair, "1h", bar_ts(1)),
                  "observed_utc": iso(bar_ts(2) + 1)} for pair in PAIRS]
    report = audit(build_lane(tmp_path, full([0, 2]), incidents))
    assert report["result"] == dt.PASS
    assert report["per_pair"]["BTC/USDT"]["classification"][dt.INPUT_REJECTED] == 1


def test_an_unexplained_missing_bar_fails(tmp_path):
    report = audit(build_lane(tmp_path, full([0, 1, 3])))
    assert report["result"] == dt.FAIL
    assert finding(report, "missing_bars")["result"] == dt.FAIL
    assert report["per_pair"]["BTC/USDT"]["unexplained_bars_utc"] == [audit_data.iso(bar_ts(2))]


def test_an_incident_outside_the_bars_opportunity_explains_nothing(tmp_path):
    # Negative control: the failure was recorded after the lane had already captured bar 3, i.e. after it
    # had moved past bar 2 for good, and a failure on the other pair does not explain this one.
    incidents = [
        {"category": "market_fetch_failed", "detail": "late", "pair": "BTC/USDT", "observed_utc": iso(bar_ts(9))},
        {"category": "market_fetch_failed", "detail": "other pair", "pair": "ETH/USDT",
         "observed_utc": iso(bar_ts(3) + 60_000)},
        {"category": "run_started", "detail": "before the bar closed", "observed_utc": iso(bar_ts(2) + 10)},
        {"category": "market_fetch_failed", "detail": "no time", "pair": "BTC/USDT", "observed_utc": "garbage"},
    ]
    inputs = full([0, 1, 3], pairs=["BTC/USDT"]) + full([0, 1, 2, 3], pairs=["ETH/USDT"])
    report = audit(build_lane(tmp_path, inputs, incidents))
    assert report["result"] == dt.FAIL
    assert report["per_pair"]["BTC/USDT"]["classification"][dt.UNEXPLAINED] == 1


def test_a_named_window_counts_bars_the_lane_never_captured(tmp_path):
    report = audit(build_lane(tmp_path, full([2, 3])), start_ms=bar_ts(0), end_ms=bar_ts(3))
    assert report["per_pair"]["BTC/USDT"]["missing"] == 2
    assert report["result"] == dt.FAIL


# --- G-1: structural defects (written straight into the ledger, bypassing the capture loop's guards) ---

def test_a_duplicate_bar_fails_uniqueness(tmp_path):
    report = audit(build_lane(tmp_path, full([0, 1]) + [input_payload("BTC/USDT", 1)]))
    assert finding(report, "bar_uniqueness")["result"] == dt.FAIL
    assert report["result"] == dt.FAIL


def test_a_bar_recorded_after_a_newer_one_fails_ordering(tmp_path):
    inputs = [input_payload(p, i) for i in (0, 2) for p in PAIRS] + [input_payload("BTC/USDT", 1)]
    report = audit(build_lane(tmp_path, inputs + [input_payload("ETH/USDT", 1)]))
    assert finding(report, "bar_ordering")["result"] == dt.FAIL


def test_an_off_grid_bar_fails_alignment(tmp_path):
    report = audit(build_lane(tmp_path, full([0, 1]) + [input_payload("BTC/USDT", 0, ts=bar_ts(2) + 60_000)]))
    assert finding(report, "bar_alignment")["result"] == dt.FAIL


def test_a_foreign_pair_or_timeframe_fails(tmp_path):
    foreign = audit(build_lane(tmp_path / "a", full([0, 1]) + [input_payload("SOL/USDT", 0)]))
    assert finding(foreign, "universe_conformance")["result"] == dt.FAIL
    wrong_tf = audit(build_lane(tmp_path / "b", full([0, 1]) + [input_payload("BTC/USDT", 2, timeframe="4h")]))
    assert finding(wrong_tf, "timeframe_conformance")["result"] == dt.FAIL


def test_a_frozen_pair_with_no_bar_is_unproven_not_pass(tmp_path):
    report = audit(build_lane(tmp_path, full([0, 1], pairs=["BTC/USDT"])))
    assert finding(report, "universe_conformance")["result"] == dt.UNPROVEN
    assert report["result"] == dt.UNPROVEN


def test_a_tampered_ledger_fails_chain_integrity(tmp_path):
    lane = build_lane(tmp_path, full([0, 1, 2]))
    path = lane / "paper_input_ledger.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace('"close": 101.0', '"close": 99.5', 1), encoding="utf-8")
    report = audit(lane)
    assert finding(report, "ledger_chain_integrity")["result"] == dt.FAIL
    assert report["result"] == dt.FAIL


@pytest.mark.parametrize("make", ["missing_dir", "garbage", "empty"])
def test_unreadable_or_empty_evidence_is_unproven_with_the_full_findings_law(tmp_path, make):
    lane = tmp_path / "lane" / "evidence"
    if make != "missing_dir":
        lane.mkdir(parents=True)
        (lane / "paper_input_ledger.jsonl").write_text("{not json\n" if make == "garbage" else "", encoding="utf-8")
    report = audit(lane)
    assert report["result"] == dt.UNPROVEN
    assert sorted(f["check"] for f in report["findings"]) == sorted(dt.LEDGER_FINDINGS)
    assert finding(report, "ledger_readable")["result"] == dt.UNPROVEN


def test_the_audit_writes_nothing(tmp_path):
    lane = build_lane(tmp_path, full([0, 1, 3]), [
        {"category": "run_started", "detail": "x", "observed_utc": iso(bar_ts(3) + 1)}])
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in lane.iterdir()}
    audit(lane)
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in lane.iterdir()} == before


def test_the_real_capture_loop_miss_is_classified_as_a_recorded_fetch_failure(tmp_path, repo_root, monkeypatch,
                                                                                executable_registry_file):
    """End to end: the capture loop's own incident for a missed bar explains that bar in the audit."""
    now = bar_ts(3) + 60_000
    monkeypatch.setattr(fp_capture, "utc_now", lambda: iso(now))

    def candle(i):
        return fp_market.Candle("BTC/USDT", "1h", bar_ts(i), bar_ts(i) + HOUR_MS - 1, 100.0, 102.0, 98.0, 101.0,
                                5.0, bar_ts(i) + HOUR_MS - 1, now, fp_market.SOURCE_ID, "https://stub.invalid")

    answers = [[candle(0)], fp_market.MarketError("no market host served BTC/USDT 1h"), [candle(2)]]

    class Market:
        def fetch_closed_candles(self, pair, timeframe="1h", limit=3, **kwargs):
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        def utc_ms(self):
            return now

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    loop = fp_capture.CaptureLoop(evidence, ["BTC/USDT"], role=ROLE, market_module=Market(),
                                  config_path=repo_root / "freqtrade" / "user_data" / "config.paper.json.example")
    for _ in range(3):
        loop.capture_inputs("BTC/USDT", limit=1)
    report = dt.audit_input_ledger(evidence, pairs=["BTC/USDT"], timeframe="1h")
    assert report["result"] == dt.PASS, report["findings"]
    assert report["per_pair"]["BTC/USDT"]["classification"][dt.FETCH_FAILURE] == 1


# --- G-2: the live-vs-engine comparator --------------------------------------------------------------

def rows(indices, override: dict | None = None) -> list[dict]:
    override = override or {}
    out = []
    for i in indices:
        row = {"ts": bar_ts(i), "open": 100.0, "high": 102.0, "low": 98.0, "close": 101.0, "volume": 5.0}
        row.update(override.get(i, {}))
        out.append(row)
    return out


def compare(live, engine, **kwargs) -> dict:
    return dt.compare_feeds(live, engine, pair="BTC/USDT", timeframe="1h", **kwargs)


def test_identical_feeds_pass_exactly(tmp_path):
    report = compare(rows(range(4)), rows(range(4)))
    assert report["result"] == dt.PASS
    assert report["tolerance"] == "exact"
    assert [f["check"] for f in report["findings"]] == list(dt.FEED_FINDINGS)


def test_a_value_difference_is_a_finding_however_small():
    report = compare(rows(range(3)), rows(range(3), {1: {"volume": 5.0 + 1e-9}}))
    equality = finding(report, "value_equality")
    assert report["result"] == dt.FAIL and equality["result"] == dt.FAIL
    assert "volume" in equality["detail"]


def test_a_bar_on_one_side_only_is_a_finding_in_both_directions():
    missing_in_engine = compare(rows(range(3)), rows([0, 2]))
    extra_in_engine = compare(rows([0, 1]), rows(range(3)))
    for report in (missing_in_engine, extra_in_engine):
        assert finding(report, "bar_coverage")["result"] == dt.FAIL
        assert report["result"] == dt.FAIL


def test_conflicting_duplicate_and_off_grid_bars_fail():
    dup = compare(rows(range(2)), rows(range(2)) + rows([1], {1: {"close": 100.5}}))
    assert finding(dup, "bar_uniqueness")["result"] == dt.FAIL
    assert finding(dup, "value_equality")["result"] == dt.FAIL
    off = compare(rows(range(2)), rows(range(2)) + [{**rows([2])[0], "ts": bar_ts(2) + 1}])
    assert finding(off, "bar_alignment")["result"] == dt.FAIL


@pytest.mark.parametrize("bad", [
    {"ts": True, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
    {"ts": BASE_TS, "open": "nan", "high": 1, "low": 1, "close": 1, "volume": 1},
    {"ts": BASE_TS, "open": 1, "high": 1, "low": 1, "close": 1},
    "not a row",
])
def test_an_unreadable_row_withholds_pass(bad):
    report = compare(rows(range(2)), rows(range(2)) + [bad])
    assert finding(report, "rows_readable")["result"] == dt.UNPROVEN
    assert report["result"] == dt.UNPROVEN


def test_nothing_to_compare_is_unproven():
    assert compare([], [])["result"] == dt.UNPROVEN


def test_an_explicit_window_bounds_both_sides_equally():
    # The engine holds warm-up history the lane never captured; in the named window both sides agree.
    report = compare(rows(range(5, 8)), rows(range(0, 8)), start_ms=bar_ts(5), end_ms=bar_ts(7))
    assert report["result"] == dt.PASS
    assert compare(rows(range(5, 8)), rows(range(0, 8)))["result"] == dt.FAIL


def test_the_comparator_never_reaches_a_market(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("the comparator fetched market data")
    monkeypatch.setattr(fp_market, "_get", refuse)
    assert compare(rows(range(2)), rows(range(2)))["result"] == dt.PASS


def test_the_live_side_is_read_from_the_input_ledger_and_a_broken_chain_refuses(tmp_path):
    lane = build_lane(tmp_path, full([0, 1, 2], pairs=["BTC/USDT"]))
    live = dt.live_rows_from_input_ledger(lane, "BTC/USDT")
    assert compare(live, rows(range(3)))["result"] == dt.PASS
    path = lane / "paper_input_ledger.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace('"volume": 5.0', '"volume": 6.0', 1), encoding="utf-8")
    with pytest.raises(dt.DataTruthError):
        dt.live_rows_from_input_ledger(lane, "BTC/USDT")


# --- the CLI: exit codes and the no-write-into-evidence rule ---------------------------------------------

def cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(REPO / "scripts" / "p3" / "data_truth.py"), *args],
                          capture_output=True, text=True, timeout=120)


def test_cli_exit_codes_follow_the_result(tmp_path):
    good = build_lane(tmp_path / "g", full([0, 1, 2]))
    bad = build_lane(tmp_path / "b", full([0, 2]))
    common = ["--pair", "BTC/USDT", "--pair", "ETH/USDT", "--timeframe", "1h"]
    assert cli("ledger-bars", "--evidence-dir", str(good), *common).returncode == 0
    assert cli("ledger-bars", "--evidence-dir", str(bad), *common).returncode == 1
    assert cli("ledger-bars", "--evidence-dir", str(tmp_path / "nowhere"), *common).returncode == 2
    engine = tmp_path / "engine.json"
    engine.write_text(json.dumps(rows(range(3))), encoding="utf-8")
    out = cli("feed-compare", "--evidence-dir", str(good), "--pair", "BTC/USDT", "--timeframe", "1h",
              "--engine-bars", str(engine), "--json", str(tmp_path / "report.json"))
    assert out.returncode == 0, out.stdout + out.stderr
    assert json.loads((tmp_path / "report.json").read_text())["result"] == dt.PASS


def test_cli_refuses_to_write_a_report_into_the_evidence_directory(tmp_path):
    lane = build_lane(tmp_path, full([0, 1]))
    before = sorted(p.name for p in lane.iterdir())
    out = cli("ledger-bars", "--evidence-dir", str(lane), "--pair", "BTC/USDT", "--timeframe", "1h",
              "--json", str(lane / "paper_input_ledger.jsonl"))
    assert out.returncode == 2 and "REFUSED" in out.stderr
    assert sorted(p.name for p in lane.iterdir()) == before


# --- G-4: the frozen-universe configuration pin (asserts; changes nothing) ----------------------------------

FROZEN_PAIRS = ["BTC/USDT", "ETH/USDT"]
FROZEN_TIMEFRAME = "1h"
PAPER_CONFIG = REPO / "freqtrade" / "user_data" / "config.paper.json.example"
STRATEGY = REPO / "freqtrade" / "user_data" / "strategies" / "BaselineEmaRegimeV1.py"


def _keys(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield f"{path}.{key}".lstrip("."), key
            yield from _keys(value, f"{path}.{key}")
    elif isinstance(node, list):
        for value in node:
            yield from _keys(value, path)


def _class_constants(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = {}
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        for stmt in cls.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                try:
                    out[stmt.targets[0].id] = ast.literal_eval(stmt.value)
                except ValueError:
                    continue
    return out


def test_the_shipped_paper_config_trades_only_the_frozen_spot_universe():
    config = json.loads(PAPER_CONFIG.read_text(encoding="utf-8"))
    assert config["dry_run"] is True
    assert config["trading_mode"] == "spot"
    assert config.get("margin_mode") in (None, "")
    assert config["exchange"]["name"] == "binance"
    assert config["exchange"]["key"] == "" and config["exchange"]["secret"] == ""
    assert config["pairlists"] == [{"method": "StaticPairList"}], "a dynamic pairlist selects pairs at run time"
    assert config["exchange"]["pair_whitelist"] == FROZEN_PAIRS
    assert config["exchange"].get("pair_blacklist", []) == []
    assert not any(":" in pair for pair in config["exchange"]["pair_whitelist"]), "a ':' pair is a derivative"
    forbidden = {"leverage", "max_leverage", "liquidation_buffer", "can_short", "futures_funding_rate"}
    assert not [path for path, key in _keys(config) if key in forbidden]


def test_the_frozen_strategy_is_long_only_on_the_frozen_timeframe():
    constants = _class_constants(STRATEGY)
    assert constants["timeframe"] == FROZEN_TIMEFRAME
    assert constants["can_short"] is False


def test_the_registry_froze_this_config_this_strategy_and_this_universe():
    registry = json.loads((REPO / "research" / "fp" / "records" / "forward_paper_cohort_registry.json")
                          .read_text(encoding="utf-8"))
    config_sha = hashlib.sha256(PAPER_CONFIG.read_bytes()).hexdigest()
    strategy_sha = hashlib.sha256(STRATEGY.read_bytes()).hexdigest()
    rows_ = [i for i in registry["instances"] if i["role"].startswith("FP-CONTROL-")]
    assert any(i["role"] == ROLE for i in rows_)
    for instance in rows_:
        identity = instance["runtime_identity"]
        assert identity["pairs"] == FROZEN_PAIRS, instance["role"]
        assert identity["timeframe"] == FROZEN_TIMEFRAME, instance["role"]
        assert identity["config_sha256"] == config_sha, f"{instance['role']}: the shipped config is not the frozen one"
        assert identity["strategy_sha256"] == strategy_sha, instance["role"]
        assert identity["feature_sources"] == ["binance spot public OHLCV 1h"], instance["role"]


def test_the_overlay_runs_the_frozen_strategy_and_captures_exactly_the_frozen_universe():
    overlay = yaml.safe_load((REPO / "docker-compose.fp.yml").read_text(encoding="utf-8"))
    engine = overlay["services"]["freqtrade"]["command"].split()
    assert engine[engine.index("--strategy") + 1] == "BaselineEmaRegimeV1"
    assert "--timeframe" not in engine, "the engine timeframe comes from the frozen strategy, not an override"
    capture = overlay["services"]["fp-capture"]["command"]
    assert [a.split("=", 1)[1] for a in capture if a.startswith("--pair=")] == FROZEN_PAIRS
    assert [a.split("=", 1)[1] for a in capture if a.startswith("--timeframe=")] == [FROZEN_TIMEFRAME]
