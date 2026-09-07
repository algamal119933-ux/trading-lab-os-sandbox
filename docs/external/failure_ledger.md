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

### F5 — The published funding threshold is not in the public sweep grid
**Status:** open (recorded, not resolved) · **Configuration:** `H2_EMACROSSFUNDING`

`research/sweep_funding.py` at the pinned commit sweeps
`funding_max_pct = [40, 50, 60, 70, 80, 90, 100]` and `ema_period = [500, 600, 700]`.
The published, executed value is **55**, which is not in that grid.

Upstream states the rationale — *"The filter is set to 55, not the best-performing 60.
Picking the exact peak of a sweep is how you fool yourself; 50, 55 and 60 all work, so take
the middle."* — so 55 is a documented midpoint between two swept values. But the sweep
evidence for 55 itself is not public.

```
EXECUTION_PARAMETER_PROVENANCE = VERIFIED               (the params file pins 55)
PARAMETER_SELECTION_PROVENANCE = PARTIALLY_DOCUMENTED   (55 was never swept publicly)
```

We execute the published 55 and record the gap. **We do not invent the missing sweep.**

### F6 — The upstream headline command has no end date
**Status:** open · **Configuration:** `H1_EMACROSS`, `H2_EMACROSSFUNDING`

The README's own invocation is:

```
freqtrade backtesting -c config.json -s EmaCrossFunding \
  --timeframe 1h --timerange 20191001- --fee 0.001
```

`--timerange 20191001-` is open-ended, so the +1,604% / +1,353% claims end on whatever date
upstream happened to run them — a date not published anywhere in the repository.

A present-day open-ended run therefore covers a **different, longer** period than the claim
did. Calling it an exact reproduction would be false. Split into
`CLAIM_SNAPSHOT_RECONSTRUCTION` (grade ceiling below EXACT until the cutoff can be proven)
and `CURRENT_NATIVE_REPLAY`.

Also note `--fee 0.001` is passed **by CLI**, not by config, which is why the execution
invocation is now part of the frozen identity.

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

### E5 — Evaluation lanes counted as if they were candidates
**Corrected in:** this revision

I listed native reproduction, Dataset V2 BTC, ETH generalization, `STRICT_1H_DELAY` and
`MATURE_FEATURE` alongside H1 and H2 as peer entries in the candidate list. They are
evaluation lanes and robustness analyses over **two** frozen configurations, not six
candidates.

Left uncorrected this would have inflated the candidate list and, worse, corrupted
multiple-testing accounting in the flattering direction — six "trials" where there are two,
while the real selection pressure sits upstream in a 42-strategy benchmark and a 21-point
sweep that our trial count cannot see. `LOCAL_TRIAL_COUNT`, `UPSTREAM_SELECTION_DEBT` and
`TOTAL_SELECTION_PROVENANCE` are now recorded separately, and no DSR or PBO figure may be
certified from the local count alone.

### E6 — Mature-feature comparison would have been unfair
**Corrected in:** this revision

The `MATURE_FEATURE` diagnostic truncates H2 to the interval where the funding percentile is
fully populated. I had not said to truncate H1 to the same interval, so the comparison would
have been a truncated H2 against a full-period H1 — and the interval difference would have
been read as an effect of the funding component. Both sides are now truncated to
`H1_MATURE_INTERVAL` vs `H2_MATURE_INTERVAL`.

---

## Lab calibration

`LAB_CALIBRATION = NOT_YET_ESTABLISHED` — no negative control has run.

If a known-bad negative control from the postmortem reproduces as *strong*, the verdict is
`LAB_CALIBRATION = SUSPECT` and no positive candidate is trusted until that is explained.
