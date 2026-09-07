# External benchmark sprint — preflight findings

Produced under directive v1.1 §7 and addendum v1.2 §7, which require pinning, license
status and a frozen claim snapshot **before** any candidate executes. The sprint itself is
still gated: §0 / addendum §1 require `1dfb6960…` merged to `main` with green merged-main
CI, and that is open in PR #3.

Everything below was established without running a single candidate, and none of it
depends on the gate. It changes what Wave 1 should do on day one.

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

## 2. EmaCross needs a longer warm-up than Dataset V2 has

`EmaCross` and `EmaCrossFunding` both declare `startup_candle_count = 1300`.

```
Dataset V2 warm-up available (2020-12-01 → 2021-01-01):   744 candles
BaselineEmaRegimeV1 requires:                             600   OK
EmaCross / EmaCrossFunding require:                      1300   short by 556 (23.2 days)
```

Freqtrade trims `startup_candle_count` candles from the start of the loaded data, so the
first scored bar would land at **2021-01-24**, twenty-three days inside Development. The
control and the candidate would then be scored on different windows, which breaks §14's
requirement to hold data constant, and makes any excess-return difference partly an
artifact of the start date.

The indicator itself is fine: `EmaCross.json` pins `ema_period = 600`, which converges
inside 744 candles. This is purely Freqtrade's declared-startup trimming, not
non-convergence — which is what makes the cheap fix legitimate rather than a fudge.

**Recommended fix — extend the warm-up, never the scored window.** Acquire
`2020-10-01 → 2020-12-01` as an additive, warm-up-only segment with its own lock entry.
It sits entirely *before* Development, so it cannot touch a scored bar, cannot alter any
existing candle, and cannot move any Dataset V2 fingerprint. Dataset V2 stays immutable
evidence, and both strategies then start scoring on 2021-01-01.

Rejected alternatives: lowering `startup_candle_count` edits upstream source and would
make the run no longer a reproduction of the pinned candidate; scoring from 2021-01-24
would require re-running the frozen control on a shortened window for a fair comparison.

---

## 3. `EmaCrossFunding` needs a funding series we cannot yet obtain

The strategy reads `research/webdata/funding.feather`, built upstream by
`research/fetch_onchain.py` from `https://fapi.binance.com/fapi/v1/fundingRate` (BTCUSDT,
from 2019-09-01).

That host is blocked from this sandbox, and during Dataset V2 acquisition Binance's
trading API returned **451** to GitHub-hosted runners — which is why Dataset V2 was
ultimately built from the public archive at `data.binance.vision` instead.

**The same archive publishes funding-rate history** under the UM futures path. Proving that
route is a prerequisite for H2 and should be the first CI job of Wave 1, because if it
fails, `EmaCrossFunding` cannot run at all and the H1/H2 split collapses to H1 alone.

**Do not substitute a different funding source.** A series with different settlement
semantics would silently change the feature and invalidate the ablation.

### FUNDING_TIMESTAMP_KNOWABILITY — preliminary PASS, must be re-asserted on real data

Directive §11 requires proof that each funding value was knowable at decision time.
Reading the pinned source rather than trusting the upstream comment:

```python
df["date"] = pd.to_datetime(df.fundingTime, unit="ms", utc=True)   # fetch_onchain.py
f = fr.reindex(idx, method="ffill")                                # EmaCrossFunding.py
```

- `fundingTime` is Binance's **settlement** timestamp — the instant the rate is applied
  and therefore known — not the start of the interval it accrued over. This is the
  distinction that decides the question: had the series been keyed on interval *start*,
  every value would leak up to eight hours.
- `method="ffill"` carries only the last already-settled value forward. Nothing indexes
  ahead.
- The derived features — `rolling(72).mean()` and `rolling(24*180).rank(pct=True)` — are
  both trailing windows over that already-lagged series.
- Freqtrade acts on a signal at the open of the candle *after* the one that produced it, so
  a value settled at 08:00 and used on the candle opening 08:00 is acted on at 09:00.

**Verdict: PRELIMINARY_PASS on source reading.** It is not yet evidence. Before any H2
result is recorded, assert empirically against the acquired series that every value's
timestamp precedes the decision bar, and run Freqtrade's own lookahead analysis. A
future-aligned value is an automatic FAIL under §11.

---

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

## 7. Ordering that follows from the above

1. Prove the `data.binance.vision` funding-rate route in CI. It gates H2 entirely.
2. Acquire the warm-up-only extension so the control and candidates share a scored window.
3. `EmaCross` (H1) native BTC-only reproduction — the cheapest real candidate, and
   btc-strategy-lab is BTC-native, so per §10 it is registered BTC-first rather than forced
   onto ETH.
4. `EmaCrossFunding` (H2) **as an ablation against H1**, never as a standalone ranking.
5. Postmortem negative control — cheap, and it calibrates everything after it.
6. GeneticEngineV1 claim challenge — cost and concentration gates first.
7. E0V1E native reconstruction — expected `NOT_ENOUGH_PUBLIC_INPUTS`.

Nothing in this list may start before the §0 gate passes.
