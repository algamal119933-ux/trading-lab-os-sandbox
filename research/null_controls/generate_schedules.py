#!/usr/bin/env python3
"""Generate the two deterministic null-control entry schedules (Research
Foundation Unit B). Pure computation over the calendar — no market data, no
network access, no dependency on any strategy's signal.

Re-running this script must reproduce byte-identical schedule files; that is
the whole point of freezing a seed. The committed
``null_*_schedule.json`` files are the frozen output; this script is kept so
the schedules are provably re-derivable, not just asserted.

    python3 research/null_controls/generate_schedules.py --check
        # recompute and diff against the committed files; exit 1 on mismatch
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEV_START = datetime(2021, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
DEV_END = datetime(2024, 12, 31, 23, 0, 0, tzinfo=timezone.utc)
HOLD_HOURS = 260
TARGET_N = 76
SEED_MATCHED = 20260929
SEED_BLOCK = 20260930
BLOCK_SIZE = 4

HERE = Path(__file__).resolve().parent


def _hours() -> int:
    return int((DEV_END - DEV_START).total_seconds() // 3600) + 1


def _stamp(i: int) -> str:
    return (DEV_START + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ")


def matched_frequency_schedule() -> dict:
    hours = _hours()
    rng = random.Random(SEED_MATCHED)
    occupied = [False] * hours
    chosen: list[int] = []
    attempts = 0
    while len(chosen) < TARGET_N and attempts < 200_000:
        attempts += 1
        i = rng.randrange(0, hours - HOLD_HOURS)
        if any(occupied[i : i + HOLD_HOURS + 1]):
            continue
        for k in range(i, i + HOLD_HOURS + 1):
            occupied[k] = True
        chosen.append(i)
    if len(chosen) != TARGET_N:
        raise RuntimeError(f"only placed {len(chosen)}/{TARGET_N} non-overlapping draws")
    chosen.sort()
    return {
        "method": "matched_frequency_random",
        "description": (
            f"{TARGET_N} uniformly random, non-overlapping candle-hour draws over the "
            "Dataset V2 Development window, each held HOLD_HOURS, with the matching exit "
            "candle precomputed here (entry + HOLD_HOURS) rather than decided at runtime. "
            "Deterministic given the seed; no market data informs the draw."
        ),
        "seed": SEED_MATCHED,
        "dev_window_start_utc": DEV_START.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dev_window_end_utc": DEV_END.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hold_hours": HOLD_HOURS,
        "target_n": TARGET_N,
        "entries_utc": [_stamp(i) for i in chosen],
        "exits_utc": [_stamp(i + HOLD_HOURS) for i in chosen],
    }


def block_shuffled_schedule() -> dict:
    hours = _hours()
    spacing = (hours - HOLD_HOURS) // TARGET_N
    base = [i * spacing for i in range(TARGET_N)]
    n_blocks = TARGET_N // BLOCK_SIZE
    if TARGET_N % BLOCK_SIZE:
        raise RuntimeError("BLOCK_SIZE must divide TARGET_N evenly")
    blocks_content = [base[b * BLOCK_SIZE : (b + 1) * BLOCK_SIZE] for b in range(n_blocks)]
    order = list(range(n_blocks))
    random.Random(SEED_BLOCK).shuffle(order)
    final = [None] * TARGET_N
    for slot_idx, content_block_idx in enumerate(order):
        content = blocks_content[content_block_idx]
        origin = base[slot_idx * BLOCK_SIZE]
        content_origin = content[0]
        for j, val in enumerate(content):
            final[slot_idx * BLOCK_SIZE + j] = origin + (val - content_origin)
    final.sort()
    return {
        "method": "block_shuffled",
        "description": (
            f"{TARGET_N} entries laid out as an evenly-spaced baseline schedule across "
            f"the Dataset V2 Development window, split into {n_blocks} blocks of "
            f"{BLOCK_SIZE}, with block ORDER permuted by a seeded Fisher-Yates shuffle and "
            "remapped onto the original block time-slots — preserving local clustering "
            "structure while destroying any link to calendar time. Each entry held "
            "HOLD_HOURS, with the matching exit candle precomputed here (entry + "
            "HOLD_HOURS) rather than decided at runtime. Deterministic given the seed; "
            "no market data informs the schedule, and this is not a shuffle of any "
            "strategy's own signal."
        ),
        "seed": SEED_BLOCK,
        "block_size": BLOCK_SIZE,
        "dev_window_start_utc": DEV_START.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dev_window_end_utc": DEV_END.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hold_hours": HOLD_HOURS,
        "target_n": TARGET_N,
        "entries_utc": [_stamp(i) for i in final],
        "exits_utc": [_stamp(i + HOLD_HOURS) for i in final],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="recompute and diff against the committed files instead of writing them")
    args = parser.parse_args()

    outputs = {
        "null_matched_frequency_schedule.json": matched_frequency_schedule(),
        "null_block_shuffled_schedule.json": block_shuffled_schedule(),
    }

    if args.check:
        mismatched = []
        for name, data in outputs.items():
            path = HERE / name
            current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            if current != data:
                mismatched.append(name)
        if mismatched:
            print(f"SCHEDULE_CHECK_FAIL: {mismatched} do not match a fresh recomputation")
            return 1
        print("SCHEDULE_CHECK_PASS: both schedules reproduce byte-identically")
        return 0

    for name, data in outputs.items():
        (HERE / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {name} ({len(data['entries_utc'])} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
