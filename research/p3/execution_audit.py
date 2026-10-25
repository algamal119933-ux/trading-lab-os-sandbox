"""P3-PLN-07 per-execution audit: every paper execution must be backed by an admitted decision.

P2 finding F-2: reconcile.py's ``execution_backed_by_decision`` is pair-level. It ignores bar timing
and the admission result, and it passed the ETH entry on a later BLOCKED decision. This audit is
the per-execution check that the closure record had to make by hand. It is an independent
verifier over the sealed or live ledgers, and it does not change reconcile.py, which belongs to the
frozen FP runtime tree.

Rule, for each paper execution (position_opened → enter_long, position_closed → exit_long):
there must be a decision on the same pair with that intended action, ``admission.result ==
ADMITTED``, ``POST_T0`` and ``LIVE``, whose candle closed at or before the fill and no more than one
timeframe before it. In other words, the fill belongs to the bar right after the decided candle,
which is how the capture loop and the engine act on a closed candle.

Read-only. PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

TIMEFRAME_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
ACTION_FOR_EVENT = {"position_opened": ("enter_long", "open_date_utc"),
                    "position_closed": ("exit_long", "close_date_utc")}


def _ms(text: str) -> int:
    text = text.replace("T", " ").rstrip("Z")
    return int(datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def _load(path: Path) -> list[dict]:
    return [json.loads(line)["payload"] for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def audit(evidence_dir: Path) -> dict:
    evidence_dir = Path(evidence_dir)
    decisions = _load(evidence_dir / "paper_decision_ledger.jsonl")
    trades = _load(evidence_dir / "paper_trade_ledger.jsonl")
    executions = []
    for trade in trades:
        if trade.get("event") not in ACTION_FOR_EVENT:
            continue
        action, when_field = ACTION_FOR_EVENT[trade["event"]]
        fill_ms = _ms(trade[when_field])
        backing, near = None, []
        for decision in decisions:
            if decision.get("pair") != trade["pair"] or decision.get("intended_action") != action:
                continue
            period = TIMEFRAME_MS.get(decision.get("timeframe", "1h"), 3_600_000)
            candle_close = int(decision["candle_ts"]) + period
            in_window = candle_close <= fill_ms < candle_close + period
            admitted = (decision.get("admission", {}).get("result") == "ADMITTED"
                        and decision.get("t0_relation") == "POST_T0" and decision.get("bar_class") == "LIVE")
            if abs(candle_close - fill_ms) <= 6 * period:
                near.append({"candle_close_utc": datetime.fromtimestamp(candle_close / 1000, timezone.utc)
                             .strftime("%Y-%m-%dT%H:%MZ"), "admission": decision.get("admission", {}).get("result"),
                             "in_window": in_window})
            if in_window and admitted:
                backing = near[-1] if near else {"candle_close_utc": str(candle_close)}
                break
        executions.append({"trade_id": trade.get("trade_id"), "pair": trade["pair"], "event": trade["event"],
                           "fill_utc": trade[when_field], "backed": backing is not None,
                           "backing_decision": backing, "nearby_decisions": near[:6]})
    unbacked = [e for e in executions if not e["backed"]]
    return {"audit_version": "P3_EXECUTION_AUDIT_V1", "evidence_dir": str(evidence_dir),
            "executions": executions, "unbacked": len(unbacked),
            "EXECUTION_BACKED_BY_ADMITTED_DECISION": "PASS" if not unbacked else "FAIL",
            "real_money_authorized": False}
