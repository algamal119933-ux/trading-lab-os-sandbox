# H1-WINDOW-AMENDMENT-1: a 30-day operational window

**Draft. Not adopted.** This record takes effect only when the Owner chooses the 30-day option on the H1 window
decision card and merges this record. Until then the frozen 180-day window in `PREREGISTRATION.md` §5.1 stands.
It does not edit the frozen H1 package. The package digest stays
`PACKAGE_MANIFEST.sha256 = ef9a3d0c5b5b9abe122faaa1bd4ef67feb0c3ec4437bed56cd6ef33d910bc43c`.

```text
DECISION    PENDING — Owner H1 window decision card, 2026-10-17 (recommended option: 30 days, operational)
CONTEXT     Owner, 2026-10-17T19:30Z: did not agree to the 180-day period; asked for a path to running within
            about 10 days. Owner, 2026-10-17T20:29Z: run the plan automatically to completion.
TIMING      before H1 T0, before any H1 paper result, before P2 (FP-CONTROL-3) reached a terminal state
SCOPE       H1-PAPER-COHORT-1 only. No other candidate, no P2 change. PAPER / RESEARCH ONLY.
            REAL_MONEY_AUTHORIZED = NO
```

## What it amends

`PREREGISTRATION.md` §5.1 (window) and §5.2 (B2), for H1-PAPER-COHORT-1.

```text
FROM  MAX_CALENDAR_DURATION = 180 days
      END_UTC              = ACTIVATION_UTC + 180 days
      B2 Lifecycles: at least 4 completed lifecycles (gated)

TO    MAX_CALENDAR_DURATION = 30 days
      END_UTC              = ACTIVATION_UTC + 30 days  (fixed; no automatic extension; no early stop for performance)
      B2 Lifecycles: reported, not gated. The count of completed lifecycles is recorded; zero is a lawful result
      VERDICT SCOPE         = OPERATIONAL. The cohort is classified on B1 signal fidelity, B3 drawdown envelope,
                              B4 cost treatment and B5 coverage, plus OPERATIONAL_CAPABILITY. EDGE_EVIDENCE is
                              NOT_EVALUATED: no claim of profitability or edge may be drawn from this window
```

## Why, and what it costs (recorded before T0)

At the package's historical cadence (6.4 / 9.4 / 11.3 lifecycles per 180 days at the lowest / mean / highest yearly
rate), 30 days gives an expected 1.07 / 1.57 / 1.88 completed lifecycles. Under the same Poisson approximation, the
probability of **no** completed lifecycle is about 0.34 / 0.21 / 0.15. The window therefore tests whether the
runtime, ledger, reconciliation, fees and replay fidelity work prospectively. It cannot settle edge, and the
180-day window could not either (§5.3).

## What it does not change

- The strategy, parameters, pair, timeframe, engine, config, benchmarks, freeze law (§6) and incident law (§7).
- Every H1 launch precondition in `PREREGISTRATION.md` §9 and both G6 amendments.
- P2 and FP-CONTROL-3, in any respect. Any later, longer H1 window is a new cohort under a new Owner decision.
