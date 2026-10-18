# H1-WINDOW-AMENDMENT-1: a 10-day operational window

**Adopted by the Owner, effective only once this record is Owner-merged.** Until the merge, the frozen 180-day window
in `PREREGISTRATION.md` §5.1 stands and the launch card denies. It does not edit the frozen H1 package. The package
digest stays `PACKAGE_MANIFEST.sha256 = ef9a3d0c5b5b9abe122faaa1bd4ef67feb0c3ec4437bed56cd6ef33d910bc43c`.

```text
DECISION    Owner, 2026-10-17T20:44:51Z (user_01H7pPnm6dL1F2scmKs6u5jk): "لا 10 ايام" ("no, 10 days"), in answer
            to the H1 window decision card (options 30 / 180 / 90 days, recommended 30)
CONTEXT     Owner, 2026-10-17T19:30Z: did not agree to the 180-day period; asked for a path to running within
            about 10 days. Owner, 2026-10-17T20:29Z: run the plan automatically to completion
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

TO    MAX_CALENDAR_DURATION = 10 days
      END_UTC              = ACTIVATION_UTC + 10 days  (fixed; no automatic extension; no early stop for performance)
      B2 Lifecycles: reported, not gated. The count of completed lifecycles is recorded; zero is a lawful result
      VERDICT SCOPE         = OPERATIONAL. The cohort is classified on B1 signal fidelity, B3 drawdown envelope,
                              B4 cost treatment and B5 coverage, plus OPERATIONAL_CAPABILITY. EDGE_EVIDENCE is
                              NOT_EVALUATED: no claim of profitability or edge may be drawn from this window
```

## What it costs (recorded before T0)

At the package's historical cadence (6.4 / 9.4 / 11.3 lifecycles per 180 days at the lowest / mean / highest yearly
rate), 10 days gives an expected 0.36 / 0.52 / 0.63 completed lifecycles. Under the same Poisson approximation, the
probability of **no** completed lifecycle is about 0.70 / 0.59 / 0.53. The most likely outcome is therefore a window
with no trade: it proves the runtime, ledger, coverage and P2 isolation prospectively, and, more likely than not, it
does not observe a full paper trade lifecycle. B1 with no entry and no replay entry is satisfied vacuously, and is
reported as such. The window cannot settle edge; the 180-day window could not either (§5.3).

## What it does not change

- The strategy, parameters, pair, timeframe, engine, config, benchmarks, freeze law (§6) and incident law (§7).
- Every H1 launch precondition in `PREREGISTRATION.md` §9 and both G6 amendments.
- P2 and FP-CONTROL-3, in any respect. Any later, longer H1 window is a new cohort under a new Owner decision.
