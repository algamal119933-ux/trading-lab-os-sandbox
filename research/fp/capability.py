"""The twelve operational-capability properties, in one place, once.

`PAPER_TRADING_OPERATIONAL_CAPABILITY = PROVEN` requires all twelve. They are
enumerated by the authority that first named them —
`docs/fp-boot-1/FP_CONTROL_1_ACTIVATION_PACK.md`, section A — and this module is
that list made executable so no schema, tool, test or document restates it.

The P2 contract originally described the split as "eight non-lifecycle" plus
"four lifecycle". That does not close: three of the twelve are lifecycle
properties (paper order/fill, position state, no duplicate execution), and
twelve minus three is nine. The fourth item in the old "four" was the completed
entry→fill→position→exit→realised-PnL chain, which the activation pack and the
registry schema both treat as a SEPARATE STATUS — `full_trade_lifecycle`, with
its own enum — and not as a thirteenth property.

So the model is:

    9 PRE_T0 qualifiable  +  3 POST_T0 lifecycle  =  12
    FULL_TRADE_LIFECYCLE is an AGGREGATE STATUS, outside the twelve

Keeping the aggregate outside the count is the load-bearing part. Folding it in
would let a cohort reach "12/12" while one genuine property went unevidenced,
because the aggregate would be standing in for it — and the aggregate is exactly
the thing a cohort can legitimately fail to observe in a quiet window without
any capability being missing. `P2 INCONCLUSIVE / INSUFFICIENT` exists for that
case, and it requires the two to be countable separately.
"""

from __future__ import annotations

from types import MappingProxyType

# The exact twelve, in the order the activation pack names them. The key is the
# stable machine name; the value is the pack's own wording, so a reader can
# check this list against the authority without interpreting anything.
PROPERTIES: MappingProxyType = MappingProxyType({
    "real_market_input": "real market input",
    "event_time_timestamp_knowability": "event-time/timestamp knowability",
    "paper_only_authority": "paper-only authority",
    "decision_logging": "decision logging",
    "risk_admission": "risk/admission",
    "paper_order_fill": "paper order/fill",
    "position_state": "position state",
    "persistence": "persistence",
    "restart_recovery": "restart recovery",
    "no_duplicate_execution": "no duplicate execution",
    "ledger_reconciliation": "ledger reconciliation",
    "data_integrity": "data integrity",
})

# Evidenceable on a pre-T0 qualification lane: none of them needs a trade to
# have happened. They are re-established during S3 at Mq, against the current P2
# source and runtime, because evidence is current only for the commit it was
# produced at.
PRE_T0_QUALIFIABLE: tuple[str, ...] = (
    "real_market_input",
    "event_time_timestamp_knowability",
    "paper_only_authority",
    "decision_logging",
    "risk_admission",
    "persistence",
    "restart_recovery",
    "ledger_reconciliation",
    "data_integrity",
)

# Cannot be evidenced without an execution: an order that filled, a position
# that existed, and an execution that was not recorded twice. Only credited L2
# records may establish these.
POST_T0_LIFECYCLE: tuple[str, ...] = (
    "paper_order_fill",
    "position_state",
    "no_duplicate_execution",
)

# NOT one of the twelve. The registry schema carries it as its own outcome field
# with its own enum (OBSERVED / NOT_YET_OBSERVED / NOT_OBSERVED /
# NOT_ESTABLISHED_BY_AVAILABLE_EVIDENCE), and the activation pack reports it
# separately from the capability verdict.
FULL_TRADE_LIFECYCLE = "full_trade_lifecycle"
FULL_TRADE_LIFECYCLE_DESCRIPTION = (
    "the completed entry→fill→position→exit→realised-PnL chain — an AGGREGATE "
    "STATUS reported alongside the twelve properties, never counted among them"
)

PROPERTY_COUNT = 12


def classify(name: str) -> str:
    """``PRE_T0`` or ``POST_T0`` for one property, or a hard failure.

    Raises on the aggregate by name, rather than returning a bucket for it: the
    whole point of keeping it outside is that it has no bucket.
    """
    if name == FULL_TRADE_LIFECYCLE:
        raise ValueError(
            f"{FULL_TRADE_LIFECYCLE} is an aggregate status, not one of the "
            f"{PROPERTY_COUNT} properties; it has no bucket"
        )
    if name in PRE_T0_QUALIFIABLE:
        return "PRE_T0"
    if name in POST_T0_LIFECYCLE:
        return "POST_T0"
    raise ValueError(f"{name!r} is not one of the {PROPERTY_COUNT} capability properties")
