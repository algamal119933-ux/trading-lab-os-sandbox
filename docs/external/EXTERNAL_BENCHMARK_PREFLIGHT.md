# External benchmark sprint — preflight findings

Produced under directive v1.1 §7 and addendum v1.2 §7, which require pinning, license
status and a frozen claim snapshot **before** any candidate executes. The sprint itself is
still gated: §0 / addendum §1 require `1dfb6960…` merged to `main` with green merged-main
CI, and that is open in PR #3.

Everything below was established without running a single candidate, and none of it
depends on the gate. It changes what Wave 1 should do on day one.

**Revision v2** applies the pre-Wave-1 review correction. Sections 2, 3 and 7 are
superseded by it: the warm-up fix is now an immutable overlay with a canonical-identity
proof, funding knowability is a per-observation proof obligation rather than a
same-hour presumption, and the executable ordering is decided by execution rights.

---

## 1. The sandbox cannot execute any candidate. CI must.

| Capability | State |
| --- | --- |
| Freqtrade, Docker, pandas | absent |
| Dataset V2 market data | not in the repository, by design |
| `api.binance.com`, `fapi.binance.com` | blocked |
| `github.com`, `codeload.github.com` | **403** — no clone, no tarball |
| `raw.githubusercontent.com` | reachable — single blobs at a pinned commit |
| `api.github.com` | this repository only |

So every candidate run is a GitHub Actions job, exactly as BASELINE-1 was, and upstream
code arrives as hash-verified individual files rather than a checkout. `dataset-v2.yml`
already proves the pattern works end to end.

**Consequence for planning:** Wave 1 is six candidates × (acquire → verify → backtest →
lookahead → recursive → metrics). Budget it as CI minutes, not as a local loop, and reuse
one parameterised workflow rather than one workflow per candidate.

---

## 2. EmaCross needs 1300 valid startup candles, supplied by an overlay

`EmaCross` and `EmaCrossFunding` both declare `startup_candle_count = 1300`.

```
Dataset V2 warm-up available (2020-12-01 -> 2021-01-01):   744 candles
BaselineEmaRegimeV1 requires:                              600   OK
EmaCross / EmaCrossFunding require:                       1300   short by 556 (23.2 days)
```

Freqtrade trims `startup_candle_count` candles from the start of the loaded data, so the
first scored bar would land at **2021-01-24**, twenty-three days inside Development. The
control and the candidate would then be scored on different bars, which breaks §14's
requirement to hold data constant.

### The fix: a separate immutable overlay, never a mutation

**Dataset V2 is not touched.** The warm-up comes from a distinct artifact with its own
lock, and the two are combined only at load time:

| | |
| --- | --- |
| Overlay range | 2020-10-01 → 2020-11-30T23:00Z |
| Overlay candles (1h) | 1,464 |
| Plus Dataset V2's own warm-up | 744 |
| **Total before first scored bar** | **2,208 ≥ 1300** ✓ |
| Lock | `research/datasets/warmup_overlay.lock.json`, separate from Dataset V2's |
| Scored? | **Never.** The overlay ends before Development begins. |

Three properties make this safe, and each is asserted rather than assumed:

1. **Disjoint.** The overlay ends at 2020-11-30T23:00Z; Dataset V2 begins at
   2020-12-01T00:00Z. No candle exists in both, so no value can be overwritten.
2. **Canonical-identity preserved.** After the overlay is joined, every Dataset V2 candle
   must still hash to its frozen `CANONICAL_CANDLE_V1` digest. This is run as a gate, not
   asserted in prose: a joined series that moves any scored candle fails and the run stops.
3. **Never scored.** The overlay lies entirely before the Development window, so it
   contributes indicator history and nothing else.

The overlay must itself pass the full acquisition audit — coverage, cadence, duplicates,
gaps, NaN, OHLC validity, monotonic timestamps, completed-candle boundaries — so that
"1300 startup candles" means 1300 *valid completed* candles, not merely 1300 rows.

### What is explicitly not done

**`startup_candle_count` is not lowered.** Editing it would make the run a reproduction of
a different strategy than the one pinned, and V1_REPRODUCTION_IDENTITY would fail it.

**The warm-up is not arbitrarily extended to 180 days** to force the funding percentile to
maturity. The percentile's immaturity is real but is handled as a reported sensitivity —
see §3 — not by inflating the startup window until it disappears.

## 3. Funding: acquisition must be verified, and knowability proved per observation

The strategy reads `research/webdata/funding.feather`, built upstream by
`research/fetch_onchain.py` from `https://fapi.binance.com/fapi/v1/fundingRate`.

`fapi.binance.com` is blocked from this sandbox and returned **451** to GitHub-hosted
runners during Dataset V2 acquisition. `data.binance.vision` is the route that worked for
candles — and it too is blocked from the sandbox (403 to CONNECT, confirmed), so the probe
runs in CI. `scripts/fetch_binance_funding.py` implements it.

### Nothing about the archive is trusted by default

Before the series may be used, all of the following must pass; any failure is fatal:

| Check | What it establishes |
| --- | --- |
| Coverage | every requested month present, spanning the range |
| Schema | columns are a recognised shape — an unknown header **fails closed**, never guesses |
| Checksum | each archive matches its published `.CHECKSUM` |
| Ordering / dedup | timestamps strictly increasing, no duplicates |
| **Semantics** | every timestamp on the 00:00/08:00/16:00 UTC settlement grid |
| Continuity | exactly one settlement per 8-hour slot, no gaps |
| **API equivalence** | overlapping samples agree with the upstream API representation |

The last two carry the argument. The archive names its columns `calc_time` /
`last_funding_rate`; the API names them `fundingTime` / `fundingRate`. **That these denote
the same instant is an assumption until measured**, and getting it wrong shifts every value
by up to eight hours.

So if the API cannot be reached, equivalence is `UNESTABLISHED` and the gate **fails
closed** — "could not check" must never read as "checked". A unit test pins exactly that
behaviour, because it is the one place a well-meaning fix would quietly turn a blocker into
a pass.

**Consequence worth stating plainly:** `fapi.binance.com` is refused from both networks
available to this project. If no API sample can be obtained from a network Binance does not
refuse, equivalence cannot be established and **H2 is `NOT_MEASURABLE`**. That is the
correct outcome under the directive, not a problem to engineer around. A single small API
sample from an unblocked network would discharge it.

### FUNDING_TIMESTAMP_KNOWABILITY — a proof obligation, not a same-hour presumption

**Corrected.** Same-hour funding is *not* automatically lookahead. Freqtrade evaluates
signals on candle close and enters at the next candle open, so for a candle opening at `T`
the decision is taken at `T+1h`. A value settled at `T` is already published by then.

The gate is discharged by proving, per observation:

```
funding_available_at <= signal_decision_time
```

and not by treating a shared timestamp as guilt. Reading the pinned source supports the
mapping — `fetch_onchain.py` keys the series on `fundingTime`, the settlement instant, and
`EmaCrossFunding.py` carries it forward with `reindex(..., method="ffill")`, so nothing
indexes ahead — but source reading gives `PRELIMINARY_PASS` only. The empirical
per-observation assertion is required before any H2 result is recorded, and a value whose
availability cannot be established is a FAIL.

### Two sensitivities, recorded separately from the native run

- **`STRICT_1H_DELAY`** — re-run with every funding value held back a further full hour
  beyond native availability. Robustness against residual uncertainty in publication
  timing. Native timing remains *the* reproduction; a disagreement between them is
  reported, not resolved by preferring one.
- **`MATURE_FEATURE`** — the percentile uses `rolling(24*180, min_periods=24*30)`, so early
  bars are built on a 30-day window where the rule intends 180. Report H2 restricted to
  bars where the percentile is fully populated, *alongside* the unrestricted native run.
  Diagnostic evidence; it does not replace the native run.

## 4. Reproducing a claim means loading its parameter files

`EmaCrossFunding.py` declares `funding_max_pct` **default 90**. The README describes rule 4
as skipping the top 45% of the trailing range — a threshold of **55**. These disagree.

`user_data/strategies/EmaCrossFunding.json` resolves it: `funding_max_pct = 55`,
`ema_period = 600`, `exit_threshold = 2.0`, matching the README exactly. Freqtrade
auto-loads `<Strategy>.json`, so upstream's published run used 55.

A reproduction that fetched only the `.py` would have tested a materially different rule
and then reported that the published claim did not hold. Both params files are pinned for
this reason, and **no candidate is executed without its params file**.

This generalises into a Wave 1 cheap gate: *source identity means every file the engine
loads, not just the strategy module.*

---

## 5. E0V1E's claim is very likely not reproducible, and we already know why

Three independent obstacles, all found by reading the pinned config rather than by running
anything:

1. **The wallet does not match the claim.** The config sets `dry_run_wallet = 70`. The
   claim reports 4,963.744 USDT of profit at 496.37%, which implies a wallet near 1,000.
   The published config cannot produce the published absolute figure.
2. **The stake currency is retired.** `stake_currency = BUSD`, which Binance has since
   wound down. The universe as it existed then is not reconstructible.
3. **The pair universe is dynamic.** `VolumePairList` + `AgeFilter` + `VolatilityFilter`
   with an empty static whitelist. Which pairs traded depended on run-time volume. This is
   textbook pair survivorship — and it is already on the §12 failure-case list, so E0V1E
   doubles as a live specimen for `failure_cases/`.

Plus no explicit `fee` and no `timeframe` in the config.

`NOT_ENOUGH_PUBLIC_INPUTS` is the predeclared verdict and is very likely the honest one.
Recording it early, before running, is the point of §7: it stops the result being written
as "we tested E0V1E and it failed" when the truth is "the claim was never checkable."

Per addendum §5 this must not be quietly normalised onto BTC/ETH Dataset V2 and then used
to call the public claim false. That is registered separately as
`E0V1E_NORMALIZED_LAB_CHALLENGE`.

---

## 6. What the sources already agree on, before we test anything

btc-strategy-lab, the postmortem and Kronos reached the same two conclusions
independently, on different data, with different methods:

- **The cost floor kills most retail crypto strategies.** 21 of 22 5m strategies
  unprofitable, median −95.6%; one paid 1,191% of capital in fees. Kronos: no slice clears
  a ~0.3% round-trip wall.
- **A high win rate predicts nothing.** `Strategy001` won 88.6% of trades and finished at
  −98.6%. The postmortem's worst pair showed 100% win rate on ROI exits and 0% on signal
  exits, the latter bleeding more than the former captured.

`GeneticEngineV1`'s headline — 98.9% win rate, 1.65% drawdown, profit factor marked "90+"
by estimate — sits exactly on that failure shape. That is why it is registered as an
adversarial claim challenge, and it tells us which gates to run first: fee load,
concentration, and leakage, before anyone looks at the return.

It also sets an expectation for §12: if our lab reproduces every one of these as
*profitable*, the lab is wrong. `LAB_CALIBRATION=SUSPECT` is the correct verdict in that
case.

---

## 7. Ordering — two parallel tracks, rights decide the lane

**Corrected twice.** Rights decide which lane a candidate is in (`V3B_EXECUTION_RIGHTS`);
a no-license source leaves the executable track for the claim/method-reference track, which
is a rights finding and never a quality judgement. And per sprint v1.3 §9, **H1 does not
wait on funding** — my earlier ordering put the funding probe first, which would have
stalled the cheapest real candidate behind a network condition that has nothing to do with
it.

**Track A — executable immediately**

1. Acquire and lock the warm-up overlay; prove Dataset V2 canonical identity and lock-file
   byte identity are preserved.
2. **`H1_NATIVE_REPRODUCTION`** — the published claim on its own terms, against
   `BTSL_NATIVE_DATASET_v1`, never silently against Dataset V2.
3. **`H1_DATASET_V2_DEVELOPMENT`** — the same frozen identity on Development, BTC only,
   against BTC-appropriate controls.
4. **`H1_ETH_GENERALIZATION_CHALLENGE`** — only after the BTC candidate is frozen. ETH
   failure classifies the candidate `BTC_SPECIALIST`; it does not kill it.

**Track B — concurrent, non-blocking**

The `data.binance.vision` funding archive probe. Its outcome grades H2's reproduction, and
under §12.2 an unreachable API downgrades H2 to an official-archive surrogate rather than
making it unmeasurable.

**Then**

`H2` if admissible → H1-vs-H2 ablation → licensed negative control → cheap survivor
decision → NFI native qualification (timeboxed) → deep validation for 2–3 survivors only.

**Parallel non-blocking lane.** Method and evidence mining (Passivbot, TrendRider, Kronos,
Hummingbot) runs throughout and must not block executable testing.

Nothing in either track may start before the activation gate passes.
