#!/usr/bin/env python3
"""Prove the replay EMA equals TA-Lib's (FP-BOOT-1 section 9.1).

``fp.replay.ema`` is a pure-Python re-implementation, because the research
environment has neither TA-Lib nor pandas. Event-time replay is the primary
parity gate, so "my EMA is the same as the engine's EMA" cannot stay an
assertion in a docstring — a silent difference in seeding would make every
replay report meaningless.

This script runs **inside the pinned Freqtrade image**, where TA-Lib is the same
build the strategy uses, and compares the two implementations over the
deterministic vectors in ``fp.replay.ema_parity_vectors()`` for both of
BASELINE-1's periods. It compares through ``talib.abstract`` on a DataFrame, the
exact call shape ``BaselineEmaRegimeV1.populate_indicators`` uses.

Exit codes: 0 identical within tolerance, 2 divergent.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "research"))

from fp.replay import ema, ema_parity_vectors, strategy_constants  # noqa: E402

# TA-Lib works in float64 and accumulates the same recursion, so agreement is
# expected to a handful of ULPs rather than exactly. A tolerance any looser than
# this would hide a genuine seeding difference.
RELATIVE_TOLERANCE = 1e-12


def main() -> int:
    import pandas as pd  # noqa: PLC0415
    import talib.abstract as ta  # noqa: PLC0415

    vectors = ema_parity_vectors()
    frame = pd.DataFrame({"close": vectors["close"]})
    constants = strategy_constants()

    failures: list[str] = []
    for label in ("EMA_FAST_PERIOD", "EMA_SLOW_PERIOD"):
        period = constants[label]
        reference = ema(vectors["close"], period)
        engine = ta.EMA(frame, timeperiod=period)

        for index, (mine, theirs) in enumerate(zip(reference, engine)):
            theirs_is_nan = theirs != theirs  # NaN is the only value unequal to itself
            if mine is None:
                if not theirs_is_nan:
                    failures.append(f"{label}={period} index {index}: replay None, TA-Lib {theirs!r}")
                continue
            if theirs_is_nan:
                failures.append(f"{label}={period} index {index}: replay {mine!r}, TA-Lib NaN")
                continue
            if abs(mine - theirs) > RELATIVE_TOLERANCE * max(1.0, abs(theirs)):
                failures.append(f"{label}={period} index {index}: replay {mine!r} vs TA-Lib {theirs!r}")

        if len(reference) != len(engine):
            failures.append(f"{label}={period}: length {len(reference)} vs {len(engine)}")

        seeded = next((i for i, v in enumerate(reference) if v is not None), None)
        if seeded != period - 1:
            failures.append(f"{label}={period}: replay seeds at index {seeded}, expected {period - 1}")

    if failures:
        print(f"EMA_PARITY = FAIL ({len(failures)} divergences)", file=sys.stderr)
        for item in failures[:20]:
            print(f"  {item}", file=sys.stderr)
        return 2

    print(
        f"EMA_PARITY = PASS — {len(vectors['close'])} bars, periods "
        f"{constants['EMA_FAST_PERIOD']} and {constants['EMA_SLOW_PERIOD']}, "
        f"max relative difference within {RELATIVE_TOLERANCE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
