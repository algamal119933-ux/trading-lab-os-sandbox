"""Forward-paper (FP-BOOT-1 / FP-RUN) evidence lane.

This package implements the parts of the FP-BOOT-1 specification that can be
built and proven *without* a paper-admissible candidate and without private
market data: append-only evidence ledgers, the event-time replay reference, the
paper-admission evaluator, and the preflight gate.

Nothing here starts a trading process, and nothing here can create a cohort T0:
``preflight`` fails closed and ``admission`` refuses to return ``ADMITTED``
unless every condition in section 5 of the specification is independently
satisfied.
"""

FP_SPEC_VERSION = "FP-BOOT-1/FP-RUN v1.1 FINAL 2026-09-07"
