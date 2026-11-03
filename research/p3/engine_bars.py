"""P3-PLN-07 G-3: record the engine's (Freqtrade's) bars through its read-only REST API.

Owner decision 2026-11-03 (docs/p3/PLN_07_DATA_TRUTH_COVERAGE.md §9): option (b). Each cycle reads
``GET /api/v1/pair_candles`` for each frozen pair and appends the **closed** bars to a separate host-side JSONL file.
The existing G-2 comparator (``data_truth.compare_feeds``) then compares them with the lane's captured input.

Boundaries, each enforced here and tested:
- **Read-only API.** Only ``GET`` on the ``pair_candles`` path is ever issued. No other endpoint, no other method.
- **Never into a lane.** The output must lie outside every evidence lane, the runtime checkout, the frozen FP tree
  (``RUNTIME_TREE``), the H1 lane and the operator ledger. A path with an ``evidence`` component is refused.
- **Fail closed, atomic per cycle.** A cycle that cannot read and parse every pair writes nothing and returns
  UNPROVEN. A bar seen again with identical values is not re-written. A bar seen again with different values is
  appended, so the comparator reports the conflict and never hides it.
- **One writer.** An exclusive flock on the output file refuses a concurrent recorder.
- **No secret is logged.** Credentials come from the environment and appear in no record or message.

It is BUILD_SMALL_MISSING_LAYER over REUSE_EXISTING parts: the bar format is the comparator's, and the grid and UTC
helpers are ``data_truth``'s. It needs a running paper engine, so it runs only inside an authorized window.
PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import base64
import fcntl
import json
import math
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from p3 import data_truth, health

RECORDER_VERSION = "P3_ENGINE_BAR_RECORDER_V1"
SOURCE = "freqtrade_api_pair_candles"
ENDPOINT = "/api/v1/pair_candles"
REPO_ROOT = Path(__file__).resolve().parents[2]
# Where the recording must never go: lanes and anything the runtime or the frozen tree owns.
FORBIDDEN_ROOTS = (health.RUNTIME_ROOT, REPO_ROOT / "research" / "fp", health.H1_LANE, health.OPERATOR_LEDGER.parent)

Fetch = Callable[[str, dict], dict]


class RecorderError(RuntimeError):
    pass


def check_output_path(path: Path) -> Path:
    """Refuse an output inside an evidence lane or a runtime-owned tree (resolved, so a symlink cannot smuggle it)."""
    resolved = Path(os.path.realpath(path))
    if "evidence" in resolved.parts:
        raise RecorderError(f"{path} is inside an evidence directory; the recording never goes into a lane")
    for root in FORBIDDEN_ROOTS:
        real_root = Path(os.path.realpath(root))
        if resolved == real_root or real_root in resolved.parents:
            raise RecorderError(f"{path} is inside {root}; the recording stays outside lanes and runtime trees")
    if not resolved.parent.is_dir():
        raise RecorderError(f"{resolved.parent} does not exist")
    return resolved


def http_fetch(username: str | None = None, password: str | None = None, timeout: float = 20.0) -> Fetch:
    """A GET-only fetcher with optional HTTP basic auth (the Freqtrade API server's own credentials)."""
    header = None
    if username is not None and password is not None:
        header = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()

    def fetch(url: str, params: dict) -> dict:
        if urllib.parse.urlsplit(url).path.rstrip("/").split("/api/v1")[-1] != "/pair_candles":
            raise RecorderError("only the read-only pair_candles endpoint may be called")
        request = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", method="GET")
        if header:
            request.add_header("Authorization", header)
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (localhost API)
            return json.loads(response.read().decode("utf-8"))
    return fetch


def _ts_of(row: dict) -> int | None:
    if isinstance(row.get("__date_ts"), (int, float)) and not isinstance(row.get("__date_ts"), bool):
        return int(row["__date_ts"])
    date = row.get("date")
    if isinstance(date, str):
        text = date.strip().replace(" ", "T", 1)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None  # a naive date is not proof of UTC: unreadable
        return int(parsed.timestamp() * 1000)
    return None


def closed_bars(payload: dict, *, pair: str, timeframe: str, now_ms: int) -> list[dict]:
    """The closed bars of one ``pair_candles`` answer, as comparator rows. Any unreadable row fails the pair."""
    if not isinstance(payload, dict) or not isinstance(payload.get("columns"), list) \
            or not isinstance(payload.get("data"), list):
        raise RecorderError(f"{pair}: the answer has no columns/data table")
    if payload.get("pair") not in (None, pair) or payload.get("timeframe") not in (None, timeframe):
        raise RecorderError(f"{pair}: the answer is for {payload.get('pair')} {payload.get('timeframe')}")
    columns = payload["columns"]
    missing = [c for c in data_truth.OHLCV if c not in columns]
    if missing:
        raise RecorderError(f"{pair}: columns {missing} absent")
    step = data_truth._step_ms(timeframe)
    out = []
    for index, values in enumerate(payload["data"]):
        if not isinstance(values, list) or len(values) != len(columns):
            raise RecorderError(f"{pair}: row {index} does not match the columns")
        row = dict(zip(columns, values))
        ts = _ts_of(row)
        try:
            ohlcv = {c: float(row[c]) for c in data_truth.OHLCV}
        except (TypeError, ValueError):
            raise RecorderError(f"{pair}: row {index} has a non-numeric OHLCV value") from None
        if ts is None or any(math.isnan(v) or math.isinf(v) for v in ohlcv.values()):
            raise RecorderError(f"{pair}: row {index} is unreadable")
        if ts % step:
            raise RecorderError(f"{pair}: row {index} is off the {timeframe} grid")
        if ts + step <= now_ms:  # only closed bars; the forming bar is never recorded
            out.append({"ts": ts, **ohlcv})
    return out


def _existing(path: Path) -> dict[tuple[str, str, int], tuple]:
    seen: dict[tuple[str, str, int], tuple] = {}
    if not path.exists():
        return seen
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            seen[(rec["pair"], rec["timeframe"], int(rec["ts"]))] = tuple(float(rec[c]) for c in data_truth.OHLCV)
        except (ValueError, KeyError, TypeError):
            raise RecorderError(f"{path} line {number} is unreadable; the recording is not extended") from None
    return seen


def record_cycle(api_base: str, *, pairs: list[str], timeframe: str, out: Path, fetch: Fetch,
                 now_ms: int | None = None, limit: int = 50) -> dict:
    """One recording cycle. Returns ``{"result": PASS|UNPROVEN, "appended": n, ...}``; writes nothing on UNPROVEN."""
    report = {"recorder_version": RECORDER_VERSION, "pairs": list(pairs), "timeframe": timeframe, "appended": 0,
              "revisions": 0, "result": data_truth.UNPROVEN, "detail": "", "real_money_authorized": False}
    if not pairs:
        report["detail"] = "no frozen pair named"
        return report
    out = check_output_path(out)
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    url = api_base.rstrip("/") + ENDPOINT
    fd = os.open(out, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RecorderError(f"{out} is held by another recorder") from None
        try:
            seen = _existing(out)
            lines, revisions = [], 0
            stamp = datetime.fromtimestamp(now_ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            for pair in pairs:
                bars = closed_bars(fetch(url, {"pair": pair, "timeframe": timeframe, "limit": limit}),
                                   pair=pair, timeframe=timeframe, now_ms=now_ms)
                for bar in bars:
                    key = (pair, timeframe, bar["ts"])
                    values = tuple(bar[c] for c in data_truth.OHLCV)
                    if seen.get(key) == values:
                        continue
                    revisions += key in seen
                    seen[key] = values
                    lines.append(json.dumps({"pair": pair, "timeframe": timeframe, **bar, "recorded_utc": stamp,
                                             "source": SOURCE, "recorder_version": RECORDER_VERSION}) + "\n")
        except (RecorderError, OSError, ValueError) as exc:
            report["detail"] = f"cycle not recorded: {str(exc)[:300]}"
            return report
        if lines:
            os.write(fd, "".join(lines).encode("utf-8"))
            os.fsync(fd)
    finally:
        os.close(fd)
    report.update(result=data_truth.PASS, appended=len(lines), revisions=revisions,
                  detail=f"{len(lines)} bar(s) appended ({revisions} revision(s) of an already-recorded bar)")
    return report


def engine_rows(path: Path, pair: str, timeframe: str) -> list[dict]:
    """The recorded engine bars of one pair, in the comparator's row format, every recorded copy kept (so a revised
    bar reaches compare_feeds as conflicting copies). An unreadable line makes the recording UNPROVEN."""
    rows = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            if rec["pair"] == pair and rec["timeframe"] == timeframe:
                rows.append({"ts": int(rec["ts"]), **{c: float(rec[c]) for c in data_truth.OHLCV}})
        except (ValueError, KeyError, TypeError):
            raise data_truth.DataTruthError(f"{path} line {number} is unreadable") from None
    return rows
