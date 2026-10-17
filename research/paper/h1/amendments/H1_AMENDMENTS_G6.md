# H1 amendments adopted under Owner decision G6

**Two amendments, recorded beside AUTH-3.** Neither edits the frozen H1 package. The package digest stays
`PACKAGE_MANIFEST.sha256 = ef9a3d0c5b5b9abe122faaa1bd4ef67feb0c3ec4437bed56cd6ef33d910bc43c`.

```text
DECISION    Owner decision card G6, option "both", 2026-10-17T17:59:55Z (user_01H7pPnm6dL1F2scmKs6u5jk);
            restated with the full eligibility list in the Owner directive
            "PREPARE NEXT H1 PHASE NOW", 2026-10-17T18:09:02Z
TIMING      adopted before H1 T0, before any H1 paper result, and before P2 (FP-CONTROL-3) reached a terminal state
BASIS       G5_HOST_CHECK.md (H1_H2_BYTE_IDENTICAL_COPY = RECOVERED)
SCOPE       H1-PAPER-COHORT-1 only. No other candidate, no H2, no P2 change. PAPER / RESEARCH ONLY.
            REAL_MONEY_AUTHORIZED = NO
```

## H1-P2-CONDITION-AMENDMENT-1 (G.2-a)

It amends PAPER_R1_RULE (1), "H1 paper launch (Owner item 11)".

```text
FROM  (1) P2 reaches its required CLOSED PASS state and the P2 closure is Owner-merged

TO    (1) P2 reaches a terminal state, recorded in an Owner-merged P2 closure record, that is EITHER

            A. CLOSED / PASS

          OR

            B. INCONCLUSIVE / INSUFFICIENT, and only when ALL of these hold:
               - the closure evidence is valid
               - the evidence chains are intact
               - reconciliation = PASS
               - no unresolved integrity defect
               - no unresolved technical defect
               - no safety failure
               - the Owner has merged the P2 closure record

          P2 CLOSED / FAIL blocks H1.

          At H1 T0 no P2 cohort may be running on the H1 host, unless a separate, explicit
          Owner decision ISOLATED_SAME_HOST_AFTER_OWNER_APPROVAL exists. This amendment does not grant it.
```

**Risk accepted by the Owner.** Under branch B, H1 would prove paper behaviour without P2 having observed a full
trade lifecycle (P2_CONTRACT §12: `full_trade_lifecycle = NOT_YET_OBSERVED`).

## H1-MATERIALISATION-AMENDMENT-1 (G.2-b)

It replaces H1 launch precondition 5 (`research/paper/h1/package/PREREGISTRATION.md` §9). The upstream GitHub
repository returns 404, so `pin_upstream.py --verify --materialize` can no longer succeed.

```text
FROM  5. pin_upstream.py --verify --materialize <W>, then copy exactly EmaCross.py, EmaCross.json and LICENSE

TO    5. from the recovered local source
           /home/hamza/projects/trading/tlos-control/.upstream-cache/btc_strategy_lab/
         copy exactly these three files, into a fresh workspace, in a credential-free environment (env -i):

           user_data/strategies/EmaCross.py     387cf39f58d266bb63d06865a0784bc2e08676edf54f4610c7d7709bb2a95f24
           user_data/strategies/EmaCross.json   9209a90e5092216af166fd10b9e7415690ab16af0fb3010c7e94e162c027e3ee
           LICENSE                              3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986

         - verify every pinned sha256, before and after the copy; any mismatch fails closed
         - record the source path and the three sha256 in COHORT_START
         - no repin, no reconstruction, no substitution, no source modification
         - the GPL-3.0 source is never committed to, or vendored into, TLOS
```

## What these amendments do not change

- Every other H1 launch precondition in `PREREGISTRATION.md` §9: the Owner launch authorization naming the
  package digest, the second durable evidence copy, the placement decision, `verify`, `preflight`, start, and
  `COHORT_START` as PAPER_T0.
- The strategy, the parameters, the pair, the timeframe, the engine, the config, the benchmarks and the terminal law.
- H2. Its placement is a separate, untaken Owner decision.
- P2 and FP-CONTROL-3, in any respect.
