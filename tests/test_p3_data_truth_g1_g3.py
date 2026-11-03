"""P3-PLN-07 Owner decisions 2026-11-03 (PLN_07 §9): G-1 EXPLAINED_HOST_DOWN and the G-3 engine-bar recorder.

G-1: a missing bar the lane's own records do not explain counts as EXPLAINED_HOST_DOWN only when an Owner-accepted
out-of-lane host record covers its **whole** opportunity, from its close to the lane's next capture. The record
sources are the journal's boot boundaries, a NUT event, or the health record. Each way a record can fail to qualify
is produced here and explains nothing: partial cover, a foreign source, inverted or unreadable times, or an
open-ended opportunity. In-lane classes keep precedence.

G-3: one cycle reads ``pair_candles`` through the read-only API (GET only, that endpoint only) and appends the
**closed** bars to a file outside every lane. Atomic per cycle; a revision is appended so the G-2 comparator sees
the conflict; one writer; no secret is printed. Offline: the API is a stub, and no engine or market data is used.
"""

from __future__ import annotations

import fcntl
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from p3 import data_truth as dt
from p3 import engine_bars as eb
from test_p3_data_truth_audits import HOUR_MS, PAIRS, audit, bar_ts, build_lane, finding, full, input_payload, iso

REPO = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------------------------------------------------
# G-1: EXPLAINED_HOST_DOWN
# ------------------------------------------------------------------------------------------------------------

def gap_lane(tmp_path):
    """Bar 2 missing for both pairs. Its opportunity runs from its close (bar_ts(3)) to the receipt of bar 3
    (bar_ts(4) + 5 s, the payload's receive lag)."""
    return build_lane(tmp_path, full([0, 1, 3]))


OPP_START, OPP_END = bar_ts(3), bar_ts(4) + 5_000


def down(start, end, source="journal_boot_boundary"):
    return {"start_ms": start, "end_ms": end, "source": source}


@pytest.mark.parametrize("source", ["journal_boot_boundary", "nut", "health"])
def test_a_host_record_covering_the_whole_opportunity_explains_the_bar(tmp_path, source):
    report = audit(gap_lane(tmp_path), host_down=[down(OPP_START - 1, OPP_END + 1, source)])
    assert report["result"] == dt.PASS, report["findings"]
    for pair in PAIRS:
        assert report["per_pair"][pair]["classification"][dt.HOST_DOWN] == 1
    assert report["host_down_records"]["accepted"][0]["source"] == source


@pytest.mark.parametrize("record,why", [
    (down(OPP_START + 1, OPP_END + 1), "starts after the bar closed"),
    (down(OPP_START - 1, OPP_END - 1), "ends before the lane's next capture"),
    (down(OPP_START + 60_000, OPP_END - 60_000), "inside only"),
])
def test_a_record_that_does_not_cover_the_whole_opportunity_explains_nothing(tmp_path, record, why):
    report = audit(gap_lane(tmp_path), host_down=[record])
    assert report["result"] == dt.FAIL, why
    assert finding(report, "missing_bars")["result"] == dt.FAIL
    assert report["per_pair"]["BTC/USDT"]["classification"][dt.HOST_DOWN] == 0
    assert report["per_pair"]["BTC/USDT"]["unexplained_bars_utc"]


@pytest.mark.parametrize("record,reason", [
    (down(OPP_START - 1, OPP_END + 1, "operator_note"), "is not an accepted host record"),
    (down(OPP_END + 1, OPP_START - 1), "start is not before end"),
    ({"start_utc": "garbage", "end_utc": iso(OPP_END + 1), "source": "nut"}, "unreadable start or end"),
    ("not-an-object", "not an object"),
    (down(OPP_START - 1, 10 ** 15), "outside the readable calendar"),
])
def test_a_record_from_a_foreign_source_or_with_bad_times_is_rejected_and_explains_nothing(tmp_path, record, reason):
    report = audit(gap_lane(tmp_path), host_down=[record])
    assert report["result"] == dt.FAIL
    assert report["host_down_records"]["accepted"] == []
    assert reason in report["host_down_records"]["rejected"][0]["reason"]


def test_iso_times_are_accepted_as_well_as_milliseconds(tmp_path):
    record = {"start_utc": iso(OPP_START - 1000), "end_utc": iso(OPP_END + 1000), "source": "health"}
    assert audit(gap_lane(tmp_path), host_down=[record])["result"] == dt.PASS


def test_an_in_lane_explanation_keeps_precedence(tmp_path):
    incidents = [{"category": "market_fetch_failed", "detail": "x", "pair": None,
                  "observed_utc": iso(bar_ts(3) + 60_000)}]
    report = audit(build_lane(tmp_path, full([0, 1, 3]), incidents), host_down=[down(OPP_START - 1, OPP_END + 1)])
    assert report["per_pair"]["BTC/USDT"]["classification"][dt.FETCH_FAILURE] == 1
    assert report["per_pair"]["BTC/USDT"]["classification"][dt.HOST_DOWN] == 0


def test_an_open_ended_opportunity_is_never_covered(tmp_path):
    # Bars 2.. are missing to the end of the named window: no later capture bounds their opportunity.
    lane = build_lane(tmp_path, full([0, 1]))
    report = audit(lane, end_ms=bar_ts(3), host_down=[down(bar_ts(-1000), bar_ts(1000))])
    assert report["result"] == dt.FAIL
    assert report["per_pair"]["BTC/USDT"]["classification"][dt.HOST_DOWN] == 0


def test_without_host_records_the_audit_is_unchanged(tmp_path):
    report = audit(gap_lane(tmp_path))
    assert report["result"] == dt.FAIL and report["host_down_records"] == {"accepted": [], "rejected": [],
                                                                         "rejected_count": 0}


def test_journal_boot_boundaries_give_inward_rounded_intervals_only_between_listed_boots():
    boots = [  # journalctl --list-boots -o json (microseconds)
        {"index": -2, "boot_id": "a", "first_entry": 1_000_000_000_000, "last_entry": 2_000_000_000_500},
        {"index": -1, "boot_id": "b", "first_entry": 2_000_100_000_700, "last_entry": 3_000_000_000_000},
        {"index": 0, "boot_id": "c", "first_entry": 2_900_000_000_000, "last_entry": 4_000_000_000_000},  # overlaps b
        {"index": 1, "boot_id": "d", "first_entry": "x", "last_entry": 5},                                # unreadable
    ]
    out = dt.host_down_from_journal_boots(boots)
    assert out == [{"start_ms": 2_000_000_001, "end_ms": 2_000_100_000, "source": "journal_boot_boundary",
                    "boots": ["a", "b"]}]
    assert dt.host_down_from_journal_boots("not a list") == []


def test_cli_ledger_bars_takes_journal_boots(tmp_path):
    lane = gap_lane(tmp_path)
    boots = tmp_path / "boots.json"
    boots.write_text(json.dumps([
        {"boot_id": "a", "first_entry": 0, "last_entry": (OPP_START - 1) * 1000},
        {"boot_id": "b", "first_entry": (OPP_END + 1) * 1000, "last_entry": (OPP_END + 99) * 1000}]))
    cmd = [sys.executable, str(REPO / "scripts" / "p3" / "data_truth.py"), "ledger-bars", "--evidence-dir", str(lane),
           "--pair", "BTC/USDT", "--pair", "ETH/USDT", "--timeframe", "1h"]
    assert subprocess.run(cmd, capture_output=True, text=True).returncode == 1
    run = subprocess.run(cmd + ["--host-boots", str(boots)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


# ------------------------------------------------------------------------------------------------------------
# G-3: the read-only engine-bar recorder
# ------------------------------------------------------------------------------------------------------------

COLUMNS = ["date", "open", "high", "low", "close", "volume", "enter_long", "__date_ts"]


def answer(pair, indices, *, close=101.0, forming=True):
    rows = [[iso(bar_ts(i)).replace("T", " ").replace("Z", "+00:00"), 100.0, 102.0, 98.0, close, 5.0, 0, bar_ts(i)]
            for i in indices]
    if forming:  # the bar still forming at "now" is always present in the engine's frame
        i = indices[-1] + 1
        rows.append([iso(bar_ts(i)), 100.0, 102.0, 98.0, 150.0, 1.0, 0, bar_ts(i)])
    return {"pair": pair, "timeframe": "1h", "columns": COLUMNS, "data": rows}


NOW = bar_ts(4) + 600_000  # bars 0..3 are closed; bar 4 is forming


def stub(answers: dict, calls: list | None = None):
    def fetch(url, params):
        if calls is not None:
            calls.append((url, dict(params)))
        value = answers[params["pair"]]
        if isinstance(value, Exception):
            raise value
        return value
    return fetch


@pytest.fixture
def out(tmp_path) -> Path:
    d = tmp_path / "tlos-paper" / "p3-evidence" / "engine-bars"
    d.mkdir(parents=True)
    return d / "run.jsonl"


def test_a_cycle_records_only_closed_bars_once_privately(out):
    calls = []
    answers = {p: answer(p, [0, 1, 2, 3]) for p in PAIRS}
    report = eb.record_cycle("http://127.0.0.1:8080", pairs=PAIRS, timeframe="1h", out=out,
                             fetch=stub(answers, calls), now_ms=NOW)
    assert report["result"] == dt.PASS and report["appended"] == 8 and report["revisions"] == 0
    assert all(url == "http://127.0.0.1:8080/api/v1/pair_candles" for url, _ in calls)
    assert [p["pair"] for _, p in calls] == PAIRS
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    lines = [json.loads(x) for x in out.read_text().splitlines()]
    assert {x["ts"] for x in lines} == {bar_ts(i) for i in range(4)}, "the forming bar is never recorded"
    assert all(x["source"] == eb.SOURCE and x["recorder_version"] == eb.RECORDER_VERSION for x in lines)
    again = eb.record_cycle("http://127.0.0.1:8080", pairs=PAIRS, timeframe="1h", out=out, fetch=stub(answers),
                            now_ms=NOW)
    assert again["appended"] == 0 and len(out.read_text().splitlines()) == 8


def test_a_revised_engine_bar_is_appended_and_the_comparator_reports_the_conflict(tmp_path, out):
    eb.record_cycle("http://x", pairs=["BTC/USDT"], timeframe="1h", out=out,
                    fetch=stub({"BTC/USDT": answer("BTC/USDT", [0, 1, 2, 3])}), now_ms=NOW)
    revised = answer("BTC/USDT", [0, 1, 2, 3])
    revised["data"][2][4] = 999.0
    report = eb.record_cycle("http://x", pairs=["BTC/USDT"], timeframe="1h", out=out,
                             fetch=stub({"BTC/USDT": revised}), now_ms=NOW)
    assert report["appended"] == 1 and report["revisions"] == 1
    live = dt.live_rows_from_input_ledger(build_lane(tmp_path, full([0, 1, 2, 3], pairs=["BTC/USDT"])), "BTC/USDT")
    compared = dt.compare_feeds(live, eb.engine_rows(out, "BTC/USDT", "1h"), pair="BTC/USDT", timeframe="1h")
    assert compared["result"] == dt.FAIL


def test_a_faithful_engine_recording_matches_the_live_input_exactly(tmp_path, out):
    eb.record_cycle("http://x", pairs=["BTC/USDT"], timeframe="1h", out=out,
                    fetch=stub({"BTC/USDT": answer("BTC/USDT", [0, 1, 2, 3])}), now_ms=NOW)
    lane = build_lane(tmp_path, full([0, 1, 2, 3], pairs=["BTC/USDT"]))
    live = dt.live_rows_from_input_ledger(lane, "BTC/USDT")
    report = dt.compare_feeds(live, eb.engine_rows(out, "BTC/USDT", "1h"), pair="BTC/USDT", timeframe="1h")
    assert report["result"] == dt.PASS, report["findings"]
    run = subprocess.run([sys.executable, str(REPO / "scripts" / "p3" / "data_truth.py"), "feed-compare",
                          "--evidence-dir", str(lane), "--pair", "BTC/USDT", "--timeframe", "1h",
                          "--engine-recording", str(out)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


@pytest.mark.parametrize("break_it,why", [
    (lambda a: a.update(columns=["date", "open"]), "columns"),
    (lambda a: a["data"][0].__setitem__(4, "x"), "non-numeric"),
    (lambda a: a["data"][0].__setitem__(7, bar_ts(0) + 1), "off the 1h grid"),
    (lambda a: a.update(pair="ETH/USDT"), "is for ETH/USDT"),
    (lambda a: a["data"].__setitem__(0, [1, 2]), "does not match the columns"),
])
def test_an_unreadable_answer_for_any_pair_records_nothing_for_the_cycle(out, break_it, why):
    bad = answer("ETH/USDT", [0, 1, 2, 3]) if why == "is for ETH/USDT" else answer("BTC/USDT", [0, 1, 2, 3])
    if why == "is for ETH/USDT":
        bad = answer("BTC/USDT", [0, 1, 2, 3])
    break_it(bad)
    answers = {"BTC/USDT": bad, "ETH/USDT": answer("ETH/USDT", [0, 1, 2, 3])}
    report = eb.record_cycle("http://x", pairs=["ETH/USDT", "BTC/USDT"], timeframe="1h", out=out,
                             fetch=stub(answers), now_ms=NOW)
    assert report["result"] == dt.UNPROVEN and why in report["detail"]
    assert out.read_text() == "", "atomic: the readable pair is not written either"


def test_an_api_error_records_nothing_and_a_naive_date_is_unreadable(out):
    report = eb.record_cycle("http://x", pairs=PAIRS, timeframe="1h", out=out,
                             fetch=stub({"BTC/USDT": answer("BTC/USDT", [0, 1]), "ETH/USDT": OSError("refused")}),
                             now_ms=NOW)
    assert report["result"] == dt.UNPROVEN and out.read_text() == ""
    naive = {"pair": "BTC/USDT", "timeframe": "1h", "columns": COLUMNS[:6],
             "data": [["2023-11-14 22:00:00", 1, 2, 0.5, 1, 1]]}
    with pytest.raises(eb.RecorderError, match="unreadable"):
        eb.closed_bars(naive, pair="BTC/USDT", timeframe="1h", now_ms=NOW)


def test_an_unreadable_existing_recording_is_not_extended(out):
    out.write_text("not json\n")
    report = eb.record_cycle("http://x", pairs=["BTC/USDT"], timeframe="1h", out=out,
                             fetch=stub({"BTC/USDT": answer("BTC/USDT", [0])}), now_ms=NOW)
    assert report["result"] == dt.UNPROVEN and out.read_text() == "not json\n"
    with pytest.raises(dt.DataTruthError, match="line 1 is unreadable"):
        eb.engine_rows(out, "BTC/USDT", "1h")


def test_the_recording_never_goes_into_a_lane_or_a_runtime_tree(tmp_path, monkeypatch):
    lane = tmp_path / "cohort" / "evidence"
    lane.mkdir(parents=True)
    with pytest.raises(eb.RecorderError, match="inside an evidence directory"):
        eb.check_output_path(lane / "bars.jsonl")
    runtime = tmp_path / "trading_lab_os_final"
    (runtime / "user_data").mkdir(parents=True)
    monkeypatch.setattr(eb, "FORBIDDEN_ROOTS", (runtime, REPO / "research" / "fp"))
    with pytest.raises(eb.RecorderError, match="stays outside lanes and runtime trees"):
        eb.check_output_path(runtime / "user_data" / "bars.jsonl")
    with pytest.raises(eb.RecorderError, match="stays outside"):
        eb.check_output_path(REPO / "research" / "fp" / "bars.jsonl")
    sneaky = tmp_path / "innocent"
    sneaky.symlink_to(lane)
    with pytest.raises(eb.RecorderError, match="inside an evidence directory"):
        eb.check_output_path(sneaky / "bars.jsonl")
    with pytest.raises(eb.RecorderError, match="does not exist"):
        eb.check_output_path(tmp_path / "nowhere" / "bars.jsonl")


def test_two_recorders_never_write_at_once(out):
    fd = os.open(out, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        with pytest.raises(eb.RecorderError, match="held by another recorder"):
            eb.record_cycle("http://x", pairs=["BTC/USDT"], timeframe="1h", out=out,
                            fetch=stub({"BTC/USDT": answer("BTC/USDT", [0])}), now_ms=NOW)
    finally:
        os.close(fd)


def test_the_http_fetcher_is_get_only_on_pair_candles_and_never_prints_the_secret(monkeypatch, out, capsys):
    seen = []

    class Response:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(request, timeout):
        seen.append((request.get_method(), request.full_url, request.get_header("Authorization")))
        pair = "BTC/USDT" if "BTC" in request.full_url else "ETH/USDT"
        return Response(json.dumps(answer(pair, [0, 1, 2, 3])).encode())
    monkeypatch.setattr(eb.urllib.request, "urlopen", fake_urlopen)
    fetch = eb.http_fetch("api-user", "s3cret-pass")
    with pytest.raises(eb.RecorderError, match="only the read-only pair_candles endpoint"):
        fetch("http://127.0.0.1:8080/api/v1/forcebuy", {})
    monkeypatch.setenv("FREQTRADE__API_SERVER__USERNAME", "api-user")
    monkeypatch.setenv("FREQTRADE__API_SERVER__PASSWORD", "s3cret-pass")
    import importlib.util
    spec = importlib.util.spec_from_file_location("eb_cli", REPO / "scripts" / "p3" / "engine_bars.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    code = cli.main(["--api", "http://127.0.0.1:8080", "--pair", "BTC/USDT", "--pair", "ETH/USDT",
                     "--timeframe", "1h", "--out", str(out)])
    printed = capsys.readouterr()
    assert code == 0 and "P3_ENGINE_BARS = PASS" in printed.out
    assert all(m == "GET" and "/api/v1/pair_candles?" in u and h and h.startswith("Basic ") for m, u, h in seen)
    assert "s3cret-pass" not in printed.out + printed.err + out.read_text()


def test_the_recorder_issues_no_mutating_call_anywhere_in_its_source():
    src = (REPO / "research" / "p3" / "engine_bars.py").read_text(encoding="utf-8")
    for verb in ('method="POST"', 'method="PUT"', 'method="DELETE"', 'method="PATCH"', "forcebuy", "forceexit",
                 "/api/v1/stop", "/api/v1/start", "reload_config"):
        assert verb not in src, verb
