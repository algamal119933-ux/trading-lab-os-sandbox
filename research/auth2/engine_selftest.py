#!/usr/bin/env python3
"""AUTH-2 engine self-test: the launcher's disclosed patches change no result.

    python research/auth2/engine_selftest.py --python python3 --work /tmp/auth2-selftest

Needs a Python with freqtrade==2026.7 (the pinned image's own interpreter, or a
local install). For A3 and A2 it generates one small no-edge synthetic world
(seed SELFTEST_SEED, used by no AUTH-2 node), runs the primary schedule through
the engine twice, with the defensive trade deep copy skipped (as every AUTH-2
run does) and kept (stock Freqtrade), and requires:

  * both runs succeed and pass replay parity (C1 thresholds);
  * identical daily equity marks;
  * every exported result file identical: feather files byte for byte, JSON
    files after dropping only backtest_run_start_ts / backtest_run_end_ts and
    writing the run's own directory as <run>.

It also runs each family once on a world whose data ends exactly at the window
end (END_AT_CLOSE, as the secondary window ends on Dataset V3) and requires
replay parity, one mark per day and the same final-day return as the replay
(|difference| <= END_AT_CLOSE_TOLERANCE).

Synthetic data only; it reads no market data and no AUTH-2 result.
PAPER / RESEARCH ONLY: backtesting only, dry_run true, keyless.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from auth2 import replay as RP  # noqa: E402
from auth2 import run_node as RN  # noqa: E402
from auth2 import synthetic as SY  # noqa: E402

SELFTEST_SEED = 4242
VOLATILE_KEYS = {"backtest_run_start_ts", "backtest_run_end_ts"}
END_AT_CLOSE_TOLERANCE = 1e-6
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}")


def _ms(y: int, mo: int = 1, d: int = 1) -> int:
    return int(datetime(y, mo, d, tzinfo=timezone.utc).timestamp() * 1000)


def _strip(obj):
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def exported(wd: Path) -> dict[str, object]:
    out: dict[str, object] = {}
    for zp in sorted((wd / "user_data" / "backtest_results").glob("*.zip")):
        with zipfile.ZipFile(zp) as z:
            for name in z.namelist():
                key = STAMP.sub("", name)  # drop the run-time stamp from member names
                body = z.read(name)
                if name.endswith(".json"):  # the run's own directory appears in its config: normalise it
                    out[key] = _strip(json.loads(body.decode().replace(str(wd.resolve()), "<run>")))
                else:
                    out[key] = body
    return out


def one(fam: str, python: str, work: Path) -> dict:
    w = SY.generate(fam, seed=SELFTEST_SEED, edge=0.0, start_ms=_ms(2019), end_ms=_ms(2020))
    m = w.market
    prices = RP.fill_like_freqtrade(m.times, {p: w.bars[p][:, :5] for p in m.pairs}, m.pairs)
    win = (_ms(2019, 3), _ms(2019, 7))
    run = {"name": "selftest", "config": "primary", "fee": 0.0015, "offset": 0, "window": "scored",
           "universe": "base"}
    recs = {}
    for label, keep in (("skip_copy", False), ("keep_copy", True)):
        d = work / fam / label
        shutil.rmtree(d, ignore_errors=True)
        recs[label] = RN.engine_run(run, fam, m, prices, w.bars, win, None, d, python, keep_trade_copy=keep)
        recs[label]["_dir"] = d / "runs" / "selftest"
    problems = []
    for label, r in recs.items():
        if r.get("status") != "OK":
            problems.append(f"{label}: engine {r.get('status')} (rc {r.get('returncode')})")
        elif r["parity"]["status"] != "PASS":
            problems.append(f"{label}: replay parity {r['parity']}")
    if not problems:
        a, b = recs["skip_copy"], recs["keep_copy"]
        if a["returns"] != b["returns"]:
            problems.append("daily returns differ")
        ea, eb = exported(a["_dir"]), exported(b["_dir"])
        if sorted(ea) != sorted(eb):
            problems.append(f"exported files differ: {sorted(ea)} vs {sorted(eb)}")
        else:
            problems += [f"exported {k} differs" for k in ea if ea[k] != eb[k]]
    return {"family": fam, "pairs": len(m.pairs), "status": "FAIL" if problems else "PASS", "problems": problems,
            "parity": {k: v.get("parity") for k, v in recs.items()}}


def end_at_close(fam: str, python: str, work: Path) -> dict:
    """One engine run on a world whose last bar closes at the window end (no bar opens there)."""
    import numpy as np

    win = (_ms(2019, 3), _ms(2019, 7))
    w = SY.generate(fam, seed=SELFTEST_SEED, edge=0.0, start_ms=_ms(2019), end_ms=win[1])
    m = w.market
    prices = RP.fill_like_freqtrade(m.times, {p: w.bars[p][:, :5] for p in m.pairs}, m.pairs)
    run = {"name": "selftest", "config": "primary", "fee": 0.0015, "offset": 0, "window": "scored",
           "universe": "base"}
    d = work / fam / "end_at_close"
    shutil.rmtree(d, ignore_errors=True)
    r = RN.engine_run(run, fam, m, prices, w.bars, win, None, d, python)
    problems = []
    if int(m.times[-1]) + RP.FOUR_H_MS != win[1]:
        problems.append("the world does not end at the window end")
    if r.get("status") != "OK":
        problems.append(f"engine {r.get('status')} (rc {r.get('returncode')})")
        return {"family": fam, "check": "end_at_close", "status": "FAIL", "problems": problems}
    if r["parity"]["status"] != "PASS":
        problems.append(f"replay parity {r['parity']}")
    days = (win[1] - win[0]) // RP.DAY_MS
    if len(r["returns"]) != days:
        problems.append(f"{len(r['returns'])} daily returns, want {days}")
    b = RN._bundle_for(run, fam, m, win, None)
    from auth2 import signals as S

    sched = RP.Schedule(b.exec_times, b.weights, S._forced(m, win[0], win[1]), b.extra_slippage, b.exempt)
    rm = RP.run(prices, sched, run["fee"], win[0], win[1], whitelist_order=list(np.argsort(m.pairs)))[0]
    diff = abs(float(r["returns"][-1]) - float(rm[-1] / rm[-2] - 1.0))
    if not diff <= END_AT_CLOSE_TOLERANCE:
        problems.append(f"final-day return differs from the replay by {diff}")
    return {"family": fam, "check": "end_at_close", "status": "FAIL" if problems else "PASS", "problems": problems,
            "final_day_return_diff": diff, "parity": r["parity"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--python", default=sys.executable, help="a Python with freqtrade==2026.7")
    ap.add_argument("--work", required=True)
    ap.add_argument("--families", nargs="+", default=["A3", "A2"])
    a = ap.parse_args(argv)
    res = [one(f, a.python, Path(a.work).resolve()) for f in a.families]
    res += [end_at_close(f, a.python, Path(a.work).resolve()) for f in a.families]
    print(json.dumps(res, indent=1, sort_keys=True, default=str))
    ok = all(r["status"] == "PASS" for r in res)
    print("AUTH2_ENGINE_SELFTEST = " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
