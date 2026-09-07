"""Event-time replay reference (FP-BOOT-1 sections 9, 10).

Section 9.1 makes event-time replay the *primary parity gate*: replay the frozen
logic against the contemporaneously captured ``paper_input_ledger`` and ask
whether it reproduces the decision the runtime actually took. Section 9.2 adds a
diagnostic replay against later canonical data, whose disagreement is classified
as ``SOURCE_REVISION_DRIFT`` rather than as strategy nondeterminism.

Two design choices matter here.

**The replay parameters are read out of the frozen strategy file, not copied.**
``BaselineEmaRegimeV1`` imports ``talib`` and ``freqtrade``, neither of which is
installed in the research environment, so the periods are lifted by AST the way
``tests/test_baseline_strategy.py`` does. Copying the numbers would let the
strategy and its replay reference drift apart silently, which is precisely the
failure this gate exists to detect.

**The EMA is a declared re-implementation, not TA-Lib.** It follows TA-Lib's
seeding convention: output is undefined for the first ``period - 1`` bars, the
bar at index ``period - 1`` is the simple mean of the first ``period`` closes,
and each later bar is ``prev + k * (close - prev)`` with ``k = 2 / (period + 1)``.
That equivalence is an *assertion until it is executed against TA-Lib itself*.
``ema_parity_vectors()`` emits the deterministic series that CI feeds to TA-Lib
inside the pinned Freqtrade image; until that check has run,
``EMA_PARITY_STATUS`` below is the honest status of the claim.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_PATH = REPO_ROOT / "freqtrade" / "user_data" / "strategies" / "BaselineEmaRegimeV1.py"

# Set to "VERIFIED_IN_CI" only by evidence from the TA-Lib parity job, never by
# assertion. See .github/workflows/ci.yml, job `freqtrade-load`.
EMA_PARITY_STATUS = "ASSERTED_PENDING_TALIB_EXECUTION"

REPLAY_ENGINE_VERSION = "FP_EVENT_TIME_REPLAY_V1"

SIGNAL_LONG = "long"
SIGNAL_FLAT = "flat"

ACTION_ENTER_LONG = "enter_long"
ACTION_EXIT_LONG = "exit_long"
ACTION_HOLD = "hold"


class ReplayError(RuntimeError):
    """Raised when replay inputs are unusable."""


# --------------------------------------------------------------------------
# Frozen strategy parameters, read from the strategy source
# --------------------------------------------------------------------------


def strategy_constants(path: Path | None = None) -> dict[str, int]:
    """Module-level integer constants of the frozen strategy, via AST.

    Importing the strategy would require talib and freqtrade. Parsing it keeps
    the replay reference bound to the same file the engine loads.
    """
    source = (path or STRATEGY_PATH).read_text(encoding="utf-8")
    tree = ast.parse(source)
    constants: dict[str, int] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target = stmt.targets[0]
            if isinstance(target, ast.Name):
                try:
                    value = ast.literal_eval(stmt.value)
                except ValueError:
                    continue
                if isinstance(value, int):
                    constants[target.id] = value
    for required in ("EMA_FAST_PERIOD", "EMA_SLOW_PERIOD"):
        if required not in constants:
            raise ReplayError(f"{required} not found in {path or STRATEGY_PATH}")
    return constants


# --------------------------------------------------------------------------
# EMA
# --------------------------------------------------------------------------


def ema(values: list[float], period: int) -> list[float | None]:
    """TA-Lib-convention exponential moving average.

    ``None`` for the first ``period - 1`` positions, SMA seed at ``period - 1``.
    """
    if period < 1:
        raise ReplayError(f"period must be >= 1, got {period}")
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1.0)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    previous = seed
    for index in range(period, len(values)):
        previous = previous + k * (values[index] - previous)
        out[index] = previous
    return out


def ema_parity_vectors() -> dict[str, list[float]]:
    """Deterministic closes used by the CI TA-Lib parity check.

    A plain arithmetic series would let a wrong smoothing constant still look
    right, so this mixes a trend, a cycle and a step discontinuity. It is
    generated from integers only: the same values appear bit-for-bit on any
    platform, which is what makes the CI comparison meaningful.
    """
    closes: list[float] = []
    for i in range(600):
        trend = 20000.0 + 25.0 * i
        cycle = 900.0 * (((i * 37) % 101) - 50) / 50.0
        step = 5000.0 if i >= 400 else 0.0
        closes.append(round(trend + cycle + step, 8))
    return {"close": closes}


# --------------------------------------------------------------------------
# Decision derivation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayDecision:
    index: int
    candle_ts: int
    pair: str
    ema_fast: float | None
    ema_slow: float | None
    signal_state: str
    intended_action: str
    no_action_reason: str | None


def derive_decisions(candles: list[dict], pair: str, constants: dict[str, int] | None = None) -> list[ReplayDecision]:
    """Reproduce BASELINE-1's signal for each closed candle.

    Mirrors ``populate_entry_trend`` / ``populate_exit_trend`` exactly: entry
    when EMA-fast crosses strictly above EMA-slow relative to the previous bar,
    exit when it crosses strictly below. Both use only the current and previous
    bar, so no future value can enter the decision.

    ``signal_state`` is the position the frozen logic implies after the bar;
    ``intended_action`` is what the runtime should have done on that bar.
    """
    consts = constants or strategy_constants()
    fast_period = consts["EMA_FAST_PERIOD"]
    slow_period = consts["EMA_SLOW_PERIOD"]

    timestamps = [int(c["ts"]) for c in candles]
    if timestamps != sorted(timestamps):
        raise ReplayError(f"{pair}: input candles are not in ascending timestamp order")
    if len(set(timestamps)) != len(timestamps):
        raise ReplayError(f"{pair}: input candles contain duplicate timestamps")

    closes = [float(c["close"]) for c in candles]
    fast = ema(closes, fast_period)
    slow = ema(closes, slow_period)

    decisions: list[ReplayDecision] = []
    state = SIGNAL_FLAT
    for index in range(len(candles)):
        f_now, s_now = fast[index], slow[index]
        f_prev, s_prev = (fast[index - 1], slow[index - 1]) if index else (None, None)

        action = ACTION_HOLD
        reason: str | None = None
        if None in (f_now, s_now, f_prev, s_prev):
            reason = "indicators_not_converged"
        elif f_now > s_now and f_prev <= s_prev:
            if state == SIGNAL_LONG:
                reason = "already_long"
            else:
                action = ACTION_ENTER_LONG
                state = SIGNAL_LONG
        elif f_now < s_now and f_prev >= s_prev:
            if state == SIGNAL_FLAT:
                reason = "already_flat"
            else:
                action = ACTION_EXIT_LONG
                state = SIGNAL_FLAT
        else:
            reason = "no_regime_cross"

        decisions.append(
            ReplayDecision(
                index=index,
                candle_ts=timestamps[index],
                pair=pair,
                ema_fast=f_now,
                ema_slow=s_now,
                signal_state=state,
                intended_action=action,
                no_action_reason=reason,
            )
        )
    return decisions


# --------------------------------------------------------------------------
# Replay comparison
# --------------------------------------------------------------------------

MATCH = "MATCH"
DECISION_MISMATCH = "DECISION_MISMATCH"
SOURCE_REVISION_DRIFT = "SOURCE_REVISION_DRIFT"
MISSING_DECISION = "MISSING_DECISION"


def candles_from_input_ledger(records, pair: str) -> list[dict]:
    """Extract one pair's captured candles from ``paper_input_ledger`` records."""
    candles = []
    for record in records:
        payload = record.payload
        if payload.get("erratum"):
            continue
        if payload.get("pair") != pair:
            continue
        candle = payload.get("candle")
        if not isinstance(candle, dict) or "ts" not in candle or "close" not in candle:
            raise ReplayError(f"input record seq {record.seq} has no usable candle payload")
        candles.append(candle)
    return candles


def event_time_replay(input_records, decision_records, pair: str, constants: dict[str, int] | None = None) -> dict:
    """Section 9.1 — the primary parity gate.

    Compares each recorded runtime decision against the decision the frozen
    logic derives from the inputs captured at that time. Returns a report; the
    caller decides the gate. ``status`` is ``PASS`` only when every compared bar
    matches and no recorded decision is unaccounted for.
    """
    candles = candles_from_input_ledger(input_records, pair)
    expected = {d.candle_ts: d for d in derive_decisions(candles, pair, constants)}

    compared = 0
    mismatches: list[dict] = []
    unmatched: list[int] = []

    for record in decision_records:
        payload = record.payload
        if payload.get("erratum") or payload.get("pair") != pair:
            continue
        ts = int(payload["candle_ts"])
        reference = expected.get(ts)
        if reference is None:
            unmatched.append(ts)
            continue
        compared += 1
        if (
            payload.get("intended_action") != reference.intended_action
            or payload.get("signal_state") != reference.signal_state
        ):
            mismatches.append(
                {
                    "candle_ts": ts,
                    "decision_seq": record.seq,
                    "runtime_action": payload.get("intended_action"),
                    "replay_action": reference.intended_action,
                    "runtime_state": payload.get("signal_state"),
                    "replay_state": reference.signal_state,
                }
            )

    problems = list(mismatches)
    status = "PASS" if not problems and not unmatched else "FAIL"
    return {
        "replay_engine_version": REPLAY_ENGINE_VERSION,
        "ema_parity_status": EMA_PARITY_STATUS,
        "pair": pair,
        "candles_replayed": len(candles),
        "decisions_compared": compared,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "decisions_without_captured_input": unmatched,
        "classification": MATCH if status == "PASS" else DECISION_MISMATCH,
        "status": status,
    }


def canonical_later_diagnostic(
    input_records, canonical_candles: list[dict], pair: str, event_time_status: str
) -> dict:
    """Section 9.2 — did the upstream source revise history after the decision?

    This is a diagnostic, never a parity gate. When event-time replay passed but
    a later canonical download disagrees with what was captured, the finding is
    ``SOURCE_REVISION_DRIFT`` — a property of the data source, not evidence of
    strategy nondeterminism.
    """
    captured = {int(c["ts"]): c for c in candles_from_input_ledger(input_records, pair)}
    later = {int(c["ts"]): c for c in canonical_candles}

    revised: list[dict] = []
    for ts in sorted(set(captured) & set(later)):
        fields = {}
        for field in ("open", "high", "low", "close", "volume"):
            if field in captured[ts] and field in later[ts]:
                if float(captured[ts][field]) != float(later[ts][field]):
                    fields[field] = {"as_seen": captured[ts][field], "canonical_later": later[ts][field]}
        if fields:
            revised.append({"candle_ts": ts, "fields": fields})

    classification = "NO_REVISION"
    if revised:
        classification = SOURCE_REVISION_DRIFT if event_time_status == "PASS" else DECISION_MISMATCH

    return {
        "pair": pair,
        "candles_compared": len(set(captured) & set(later)),
        "only_as_seen": sorted(set(captured) - set(later)),
        "only_canonical_later": sorted(set(later) - set(captured)),
        "revised_candles": revised,
        "revision_count": len(revised),
        "event_time_replay_status": event_time_status,
        "classification": classification,
    }
