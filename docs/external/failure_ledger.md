# Failure ledger

Required by sprint v1.3 §27. Kronos Gauntlet is mined for exactly this discipline
(§16): preserve negative results, and correct your own published claims in the open
rather than quietly editing them.

Two kinds of entry. **Findings** are things discovered about candidates. **Errata** are
things this lab got wrong and corrected. Both are permanent; nothing here is deleted to
make a later result look cleaner.

Nothing has been executed yet — the activation gate is unmet — so every entry below comes
from reading pinned sources, not from a run.

---

## Findings

### F1 — E0V1E's published claim is not reproducible from public inputs
**Status:** open · **Candidate:** `E0V1E` (claim/method-reference track) · **Grade:** `NOT_ENOUGH_PUBLIC_INPUTS`

Found by reading the pinned config at `ebc58b1`, before running anything:

1. The config sets `dry_run_wallet = 70`, but the claim reports 4,963.744 USDT profit at
   496.37%, implying a wallet near 1,000. The published config cannot produce the published
   absolute figure.
2. `stake_currency = BUSD`, which Binance has since retired. The universe as it existed then
   is not reconstructible.
3. The pair universe is dynamic — `VolumePairList` + `AgeFilter` + `VolatilityFilter` with an
   empty static whitelist. Which pairs traded depended on run-time volume.

Plus no explicit `fee` and no `timeframe` in the config.

**Why it is recorded now, before any run:** so the result cannot later be written up as "we
tested E0V1E and it failed". The claim was never checkable. Those are different findings.

**Doubles as a failure case.** Item 3 is textbook pair survivorship, one of the §12 families
the lab must be able to detect. It is a live specimen, not a synthetic one.

### F2 — GeneticEngineV1's README contradicts itself on engine version
**Status:** open · **Candidate:** `GeneticEngineV1` (claim/method-reference track)

The benchmark table states Freqtrade **2026.4**; the Live Configuration section of the same
README states **2024.9**. The engine under which the claim was produced is ambiguous from
public inputs. Record which version we run; never assert the claim was made under ours.

### F3 — "Live Testing" is not real-money evidence
**Status:** closed (classified) · **Candidate:** `GeneticEngineV1`

Upstream labels the strategy "Active (Live Testing)" with no independently observable capital
or trade evidence. Classified `LIVE_MONEY=NO`, treated as `BACKTEST_CLAIM`. Same rule applied
to TrendRider, which uses "live performance" wording while stating no real money is at risk.

### F4 — A strategy file alone does not reproduce a claim
**Status:** closed (gate added) · **Candidate:** `EmaCrossFunding`

`EmaCrossFunding.py` defaults `funding_max_pct` to **90**; the README describes **55**;
`EmaCrossFunding.json`, which Freqtrade auto-loads, pins **55**.

A reproduction fetching only the `.py` would have tested a materially different rule and then
reported that the published claim did not hold — a false negative that would have looked like
a finding. Caught before any run. `V1_REPRODUCTION_IDENTITY` now requires every file the
engine loads, and §5 extends that to fee model, universe, timeframe and position semantics.

**This is the near-miss that justifies the whole identity gate.**

---

## Errata — this lab's own corrected errors

### E1 — Over-strict funding knowability
**Corrected in:** `2755994`

I framed same-hour funding as presumptively lookahead. Wrong: Freqtrade evaluates on candle
close and enters at the next open, so a value settled at `T` is already published when the
decision is taken at `T+1h`. Corrected to a per-observation proof of
`funding_available_at <= signal_decision_time`. Had it stood, it would have failed a valid
candidate for a timestamp coincidence.

### E2 — Over-generalized capital break-even
**Corrected in:** `2755994`, parked in v1.3 revision

I reported ~863 USDT as *the* break-even. It is one cell — proportional sizing on a dedicated
VPS, for BASELINE-1's trade profile. Break-even is 216 USDT on a shared box and there is no
opex hurdle at all on already-owned hardware, so the figure overstated the barrier roughly
fourfold in one common case and did not apply at all in another.

### E3 — Ordering that would have stalled the cheapest candidate
**Corrected in:** this revision

My Wave 1 ordering put the funding-archive probe first, ahead of H1. That would have blocked
the cheapest real candidate behind a network condition unrelated to it. Corrected to parallel
tracks per §9: H1 executable immediately, funding verification concurrent.

### E4 — Fail-closed applied too broadly
**Corrected in:** this revision

I made an unreachable funding API fail the whole gate, concluding H2 was `NOT_MEASURABLE` and
asking the owner for a manual API sample. Per §12.2 that discards usable evidence: an
inaccessible API blocks the *equivalence claim*, not the experiment. Corrected to a graded
verdict — `OFFICIAL_ARCHIVE_SURROGATE` at a lower reproduction grade. A *measured*
disagreement remains fatal; "could not check" and "checked and they disagree" are now
distinct verdicts, which is the part I had collapsed.

**The ask for a manual API sample is withdrawn** (§28).

---

## Lab calibration

`LAB_CALIBRATION = NOT_YET_ESTABLISHED` — no negative control has run.

If a known-bad negative control from the postmortem reproduces as *strong*, the verdict is
`LAB_CALIBRATION = SUSPECT` and no positive candidate is trusted until that is explained.
