#!/usr/bin/env python3
"""Join the benchmark warm-up overlay to Dataset V2 at load time (sprint v1.3 §8.2).

`EmaCross` and `EmaCrossFunding` declare ``startup_candle_count = 1300``. Dataset
V2's own pre-Development warm-up supplies 744 hourly candles, so Freqtrade would
trim 1300 candles from the start of the loaded data and score its first bar
around 2021-01-24 — twenty-three days inside Development, on different bars from
the control. That breaks window parity (gate ``V7_WINDOW_PARITY``).

The fix is an overlay, never a mutation. Dataset V2 keeps every byte and every
canonical digest it was frozen with; a separate, separately-locked series covering
2020-10-01 → 2020-11-30T23:00Z is concatenated in front of it, in the runner's
ephemeral data directory only.

Three properties are gates here, not prose:

1. **Disjoint.** The overlay must end strictly before Dataset V2 begins. If any
   timestamp is shared, the Dataset V2 candle wins unconditionally
   (``overlap_policy.on_overlap``) and the collision is reported.
2. **Canonical identity preserved.** After the join, the Dataset V2 slice of the
   combined series must still hash to the ``CANONICAL_CANDLE_V1`` digest recorded
   in ``dataset_v2.lock.json``. A join that moves any scored candle fails and the
   run stops. This is the property that makes "overlay, not mutation" checkable
   rather than merely asserted.
3. **Enough VALID candles.** The gate is
   ``VALID_COMPLETED_1H_CANDLES >= startup_candle_count`` strictly before the
   first scored candle — valid completed candles, not merely rows, so a series
   padded with NaN or duplicate rows cannot satisfy it.

Exit codes: 0 all gates pass, 2 a gate failed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from audit_data import CANONICAL_DIGEST_VERSION, canonical_digest  # noqa: E402

HOUR_MS = 3_600_000


def parse_utc(text: str) -> int:
    return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000)


def load_candles(path: Path) -> list[tuple]:
    import pandas as pd  # noqa: PLC0415 - heavy, only needed for feather

    frame = pd.read_feather(path)
    cols = {c.lower(): c for c in frame.columns}
    date_col = cols.get("date") or cols.get("timestamp") or frame.columns[0]
    stamps = pd.to_datetime(frame[date_col], utc=True).astype("int64") // 1_000_000
    out = []
    for ts, o, h, low, c, v in zip(
        stamps, frame[cols["open"]], frame[cols["high"]], frame[cols["low"]],
        frame[cols["close"]], frame[cols["volume"]],
    ):
        out.append((int(ts), float(o), float(h), float(low), float(c), float(v)))
    return sorted(out, key=lambda r: r[0])


def write_candles(path: Path, candles: list[tuple]) -> None:
    import pandas as pd  # noqa: PLC0415

    frame = pd.DataFrame(candles, columns=["date", "open", "high", "low", "close", "volume"])
    frame["date"] = pd.to_datetime(frame["date"], unit="ms", utc=True)
    frame.to_feather(path, compression="lz4")


def valid_completed(candles: list[tuple], before_ms: int, step_ms: int = HOUR_MS) -> tuple[int, list[str]]:
    """Count candles strictly before ``before_ms`` that are usable as warm-up.

    A candle counts only if it is on the cadence grid, carries finite positive
    prices, satisfies low <= min(open, close) <= max(open, close) <= high, and is
    not a duplicate of a timestamp already counted.
    """
    problems: list[str] = []
    seen: set[int] = set()
    count = 0
    for ts, o, h, low, c, v in candles:
        if ts >= before_ms:
            continue
        if ts % step_ms:
            problems.append(f"off-grid timestamp {ts}")
            continue
        if ts in seen:
            problems.append(f"duplicate timestamp {ts}")
            continue
        seen.add(ts)
        values = (o, h, low, c)
        if any(x != x or x in (float("inf"), float("-inf")) for x in values) or v != v:
            problems.append(f"non-finite cell at {ts}")
            continue
        if any(x <= 0 for x in values) or v < 0:
            problems.append(f"non-positive price or negative volume at {ts}")
            continue
        if not (low <= min(o, c) and max(o, c) <= h):
            problems.append(f"invalid OHLC at {ts}")
            continue
        count += 1
    return count, problems


def join_pair(
    dataset_path: Path,
    overlay_path: Path,
    frozen_digest: str,
    first_scored_ms: int,
    required_candles: int,
) -> dict:
    return join_series(
        load_candles(dataset_path),
        load_candles(overlay_path),
        frozen_digest,
        first_scored_ms,
        required_candles,
        name=dataset_path.name,
    )


def join_series(
    dataset: list[tuple],
    overlay: list[tuple],
    frozen_digest: str,
    first_scored_ms: int,
    required_candles: int,
    name: str = "<series>",
) -> dict:
    """The gates themselves, over candle lists.

    Kept free of file and pandas access so the gates can be tested directly; the
    research environment has no pandas, and a gate that can only be exercised
    inside CI is a gate nobody checks.
    """
    report: dict = {
        "pair_file": name,
        "dataset_candles": len(dataset),
        "overlay_candles": len(overlay),
        "problems": [],
    }

    dataset_stamps = {row[0] for row in dataset}
    dataset_start = min(dataset_stamps)
    collisions = sorted(ts for ts in (row[0] for row in overlay) if ts in dataset_stamps)
    report["disjoint"] = not collisions
    report["collisions"] = len(collisions)
    if collisions:
        # overlap_policy.on_overlap: the Dataset V2 candle wins unconditionally.
        overlay = [row for row in overlay if row[0] not in dataset_stamps]
        report["problems"].append(
            f"{len(collisions)} overlay candle(s) collided with Dataset V2 and were discarded; "
            "Dataset V2 wins unconditionally"
        )
    ahead = [row[0] for row in overlay if row[0] >= dataset_start]
    if ahead:
        report["problems"].append(f"{len(ahead)} overlay candle(s) are not strictly before Dataset V2")

    joined = sorted(overlay + dataset, key=lambda r: r[0])

    # Gate 2: the Dataset V2 slice of the joined series must be byte-for-byte the
    # frozen series. Recomputed from the joined data, not from the input.
    slice_v2 = [row for row in joined if row[0] >= dataset_start]
    rejoined_digest = canonical_digest(slice_v2)
    report["canonical_digest_version"] = CANONICAL_DIGEST_VERSION
    report["frozen_digest"] = frozen_digest
    report["rejoined_digest"] = rejoined_digest
    report["canonical_identity_preserved"] = rejoined_digest == frozen_digest
    if not report["canonical_identity_preserved"]:
        report["problems"].append(
            "CANONICAL IDENTITY FAILED: joining moved a Dataset V2 candle. The joined series is discarded."
        )
        return report

    # Gate 3: enough VALID completed candles before the first scored bar.
    count, invalid = valid_completed(joined, first_scored_ms)
    report["valid_completed_before_first_scored"] = count
    report["required"] = required_candles
    report["warmup_sufficient"] = count >= required_candles
    if invalid:
        report["invalid_warmup_candles"] = invalid[:10]
    if not report["warmup_sufficient"]:
        report["problems"].append(
            f"only {count} valid completed candles before the first scored bar, need {required_candles}"
        )
    report["joined_candles"] = len(joined)
    report["joined"] = joined
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--data-dir",
        required=True,
        help=(
            "Working copy of the Dataset V2 feather directory. MUTATED IN PLACE: pass a per-run copy, "
            "never the pristine acquisition. Joining is a load-time operation; a joined series that "
            "outlives its run will fail the frozen-digest gate on the next one, which is how this "
            "requirement was discovered."
        ),
    )
    parser.add_argument("--overlay-dir", required=True, help="overlay feather directory")
    parser.add_argument("--lock", required=True, help="dataset_v2.lock.json")
    parser.add_argument("--pair", action="append", required=True, help="e.g. BTC/USDT (repeatable)")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--first-scored-utc", required=True, help="first Development candle, e.g. 2021-01-01T00:00:00Z")
    parser.add_argument("--required-candles", type=int, required=True)
    parser.add_argument("--out", default=None, help="write the JSON report here")
    parser.add_argument("--dry-run", action="store_true", help="run every gate but do not write the joined series")
    args = parser.parse_args(argv)

    lock = json.loads(Path(args.lock).read_text(encoding="utf-8"))
    frozen = lock.get("canonical_hashes") or {}
    first_scored_ms = parse_utc(args.first_scored_utc)

    reports = []
    failed = False
    for pair in args.pair:
        stem = f"{pair.replace('/', '_')}-{args.timeframe}.feather"
        dataset_path = Path(args.data_dir) / stem
        overlay_path = Path(args.overlay_dir) / stem
        key = f"{pair} {args.timeframe}"
        if key not in frozen:
            print(f"JOIN_FAIL: no frozen canonical digest for {key}", file=sys.stderr)
            failed = True
            continue
        if not dataset_path.exists() or not overlay_path.exists():
            missing = dataset_path if not dataset_path.exists() else overlay_path
            print(f"JOIN_FAIL: missing {missing}", file=sys.stderr)
            failed = True
            continue

        report = join_pair(dataset_path, overlay_path, frozen[key], first_scored_ms, args.required_candles)
        joined = report.pop("joined", None)
        reports.append(report)
        if report["problems"]:
            failed = True
            for problem in report["problems"]:
                print(f"JOIN_FAIL [{key}]: {problem}", file=sys.stderr)
        elif not args.dry_run and joined is not None:
            write_candles(dataset_path, joined)
            print(
                f"joined {key}: {report['overlay_candles']} overlay + {report['dataset_candles']} dataset "
                f"= {report['joined_candles']} candles; "
                f"{report['valid_completed_before_first_scored']} valid warm-up candles "
                f"(need {args.required_candles}); canonical identity preserved"
            )
        else:
            print(f"dry-run {key}: all gates pass, nothing written")

    summary = {
        "gate": "WARMUP_OVERLAY_JOIN",
        "result": "FAIL" if failed else "PASS",
        "dry_run": args.dry_run,
        "first_scored_utc": args.first_scored_utc,
        "required_candles": args.required_candles,
        "pairs": reports,
    }
    if args.out:
        Path(args.out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"WARMUP_OVERLAY_JOIN = {summary['result']}")
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
