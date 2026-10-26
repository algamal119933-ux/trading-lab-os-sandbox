# A1B-PREREGISTRATION-1 — A1b, TSMOM-VT with a no-trade band

**Status:** FROZEN, pending Owner authority. The machine-readable spec is [`a1b_prereg.json`](a1b_prereg.json), and its
sha256 is in [`SHA256SUMS`](SHA256SUMS). Where this text and the JSON differ, the JSON wins, and the difference is a defect
to be fixed before any evaluation.

**Authority:** none until the Owner merges the authority record
[`research/OWNER_RESEARCH_AUTHORIZATION_A1B_1.md`](../OWNER_RESEARCH_AUTHORIZATION_A1B_1.md) (branch
`owner/research-authorization-a1b`). That record must merge before this one. Evaluation additionally needs an Owner-merged
program charter at `charters/programs/A1B-QUALIFICATION-1.json` that binds this spec's sha256 (CEA-1 §12). This
preregistration does not create that charter.

**Verification law:** [`research/PROFITABILITY_VERIFICATION_LAW_1.md`](../PROFITABILITY_VERIFICATION_LAW_1.md), prepared in
parallel on branch `claude/research-verification-law-1`. The law as merged on `main` governs. Where the law and this file give
different numbers for the same test, the stricter applies. No evaluation may run before the law is merged.

PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCH_AUTHORIZED = NO · PAPER_LAUNCH_AUTHORIZED = NO ·
dry_run = true · hyperopt = 0 · no leverage, margin, futures, shorts or exchange keys.

## 1. Why A1b exists

A1 (TSMOM-VT, [`research/auth2/prereg/A1.json`](../auth2/prereg/A1.json)) survived the FCS-1 commercial screen on
2026-10-17:

| Measure | A1 | Matched benchmark |
|---|---|---|
| Net return, 2019–2024, 0.15%/side | +260.5% | +362.1% |
| Sharpe | 1.39 | 1.19 |
| Max drawdown | 18.8% | 43.8% |

A1 then failed the frozen pre-paper gate on G3 execution feasibility. Only **30.6%** of its fills were at or above 5 USDT at a
1,000 USDT wallet, because it re-sizes six sleeves every day. Any repair is a post-result change, so the repair has to be a
**new, preregistered candidate**. That candidate is A1b, option V of the 2026-10-21 Master Map. Option V is a no-trade band and
a minimum-order floor, counted as a new trial.

The literature supports the family:
- Liu, Tsyvinski & Wu (JF 2022) and Liu & Tsyvinski (RFS 2021) find time-series momentum in crypto over 1–4 week horizons.
- Han, Kang & Ryu find long-only TSMOM keeps a higher Sharpe than the market after 15 bp costs, with a much lower drawdown.

Its value is **lower risk, not higher return**. A1 earned less than always-long.

## 2. Hypothesis

Long-only time-series momentum with per-sleeve volatility targeting, on the most liquid point-in-time Binance USDT spot assets,
has a higher risk-adjusted net return than the same book held always long. It also stays executable at retail size once
trades below a minimum-order floor are suppressed by a declared no-trade band.

## 3. Frozen specification

```text
SIGNAL        research/auth2/signals.py a1_weights, UNCHANGED (sha256 pinned in the JSON)
              score = mean of 20/60/120-day trailing returns of the daily close; long if score > 0, else cash
              sleeve size = min(1, 0.25 / realised 30-day annualised vol) / sleeves
              decided at each UTC day boundary from closes known then; engine timeframe 4h; exec offset 0
UNIVERSE      FUNNEL-LAW-2 point-in-time U6 (frozen membership_u6.json), ranks 1..4 only → sleeves = 4
              USDT spot, long only, gross exposure ≤ 1, delisted members force-exited at their last kline
BAND          entry  flat→long only if target notional ≥ min_order_floor, else stay flat
              exit   long→flat always, as a full close
              resize long→long only if |target_w − current_w| ≥ max(0.25 × target_w, min_order_floor / equity)
              min_order_floor = 2 × min_notional_usdt
COSTS         base 0.15%/side (0.10% fee + 0.05% slippage allowance, as A1) · x2 0.30% · x3 0.45% (report)
              BNB-discounted 0.125% (report only) · latency +1 engine bar
WALLETS       1,000 USDT primary (the frozen G3 wallet) · 100 USDT report-only
```

The only declared changes from A1 are:
1. the rank cap (4 instead of 6), for retail-size feasibility;
2. the band with its minimum-order floor.

Lookbacks, vol target, vol window, decision time, data, costs and engine are A1's.

### Open input (never chosen from a result)
`min_notional_usdt` is not written here, because it was not observed in this environment. It is the maximum, over every symbol
that is ever a U6 member, of the `NOTIONAL` / `MIN_NOTIONAL` filter `minNotional`. It comes from **one** `GET /api/v3/exchangeInfo`
snapshot captured on the Owner host, with its bytes sha256-recorded in the data-preparation PR, before any A1b evaluation.
Without it every evaluation step refuses to run (`INCONCLUSIVE_INPUT_MISSING`).

### Variants (all four count toward N)
| ID | Role | Rank cap / sleeves | Band | Decisions |
|---|---|---|---|---|
| V1 | **primary**, the only possible candidate | 4 / 4 | 0.25 | daily |
| V2 | reject-only perturbation | 4 / 4 | 0.50 | daily |
| V3 | reject-only perturbation | 4 / 4 | 0.25 | weekly (Monday 00:00 UTC) |
| V4 | reject-only perturbation | 6 / 6 | 0.25 | daily |

No variant is ever substituted for V1. There is no other parameter search and no Hyperopt.

### Baselines
- `A1B_BENCH`: the matched benchmark. Same universe, sizing and band as V1, but always long.
- `BTC_HOLD`: BTC/USDT held throughout.
- `NO_TRADE`: cash.
- `EXPOSURE_MATCHED_PASSIVE`: report only.

## 4. Data and windows

**Data.** Dataset V3 ([`dataset_v3.lock.json`](../datasets/dataset_v3.lock.json)), built from data.binance.vision. Every zip is
verified against its published `.CHECKSUM`. Membership is point-in-time and delisted symbols are retained, so the universe is
free of survivorship bias by construction.

**Holdout data.** The holdout needs data past V3's end (2026-08-31). It comes from a **separate extension lock**, built by the
same route only after 2027-01-01T00:00Z and checksum-verified. Building it is the data preparation the Owner record authorizes.

| Window (UTC) | Range | Evidence class |
|---|---|---|
| Development | 2019-01-01 → 2025-01-01 | **HISTORICAL_EXPLORATORY**. A1 was screened on it and smoke-tested before AUTH-2 |
| Validation | 2025-01-01 → 2026-09-01 | **HISTORICAL_EXPLORATORY**. A1's secondary window was seen in FCS-1 R6 |
| Locked holdout | 2026-09-01 → 2027-01-01 | **HISTORICAL_UNSEEN** for every A1-family configuration, per repository and Lane A records. Opened exactly once, after E0–E10. If any prior exposure is found it is BURNED |
| Prospective | forward paper, separate Owner authority | the only class that can support a profitability claim, judged by the verification law |

## 5. Evaluation plan (frozen gates)

Every gate below is **material** unless marked report-only.

| Gate | Rule |
|---|---|
| E0 Data | The V3 lock and the holdout extension lock verify. The `min_notional_usdt` snapshot is recorded |
| E1 Causality | `signals.lookahead_check` (20 cuts) and `recursive_check` (shifts 30/90, warm-up 400 d) on the V1 and A1B_BENCH generators: 0 failures. Freqtrade `lookahead-analysis` and `recursive-analysis` on the engine strategy: 0 flagged |
| E2 Parity | Freqtrade 2026.7 against the frozen replay (V1@base, development): daily correlation ≥ 0.999 and \|Δ total return\| ≤ 0.25 pp |
| E3 Feasibility (G3 re-applied) | ≥ 95% of V1@base development fills ≥ max(5 USDT, `min_notional_usdt`) at 1,000 USDT. Report-only: the 100 USDT share. The live-vs-replay 30-day match is NOT_YET_EVALUABLE until paper |
| E4 Paper guard | `engine_io.guard_config` passes and `dry_run = true` |
| E5 Screen | Development, V1: R1 net > 0 and Sharpe > 0; R2 net > 0 at x2; R3 net > 0 at +1 bar; R4 Sharpe − A1B_BENCH Sharpe > 0; R5 max DD ≤ 0.50. R6, on validation and reject-only: NOT (net ≤ 0 AND ΔSharpe ≤ 0) |
| E6 Robustness | Reject V1 if 2 or more of V2–V4 have development Sharpe ≤ 0 or ΔSharpe against their own matched bench ≤ 0 |
| E7 Overfitting | PBO by CSCV (S = 16) over daily net returns, development plus validation, for {A1 primary, A1 P1–P5, V1–V4}: **PBO ≤ 0.10** |
| E8 Deflated Sharpe | V1 daily net returns, development plus validation: **DSR ≥ 0.95** with N = max(39, the law's N_eff). 39 is lifetime TLOS 35 (OD-C5) plus the 4 A1b variants |
| E9 Exposure | ΔSharpe against A1B_BENCH > 0 (material). Sharpe, CAGR and max DD against BTC_HOLD, NO_TRADE and EXPOSURE_MATCHED_PASSIVE are reported. Reduced exposure is never called alpha |
| E10 Sample period and drawdown | ΔSharpe against A1B_BENCH > 0 in ≥ 4 of the 7 calendar years 2019–2025, and no single year contributes > 60% of summed yearly log return. Realised vol and max-DD/vol are reported. **TOO_GOOD flag**: max DD < 0.5 × bench max DD and CAGR ≥ bench CAGR → Owner review before any paper step |
| E11 Holdout (once) | Reject-only: REJECTED if V1 net ≤ 0 and ΔSharpe ≤ 0. Otherwise UNDERPOWERED, because about 4 months cannot confirm an edge |

**Multiple testing.** Holm with m = 1 inside the program, since only V1 is tested. Across concurrent candidates, the verification
law's correction applies.

**Drawdown sanity.** A1's 18.8% max DD is low against published long-only TSMOM, about 60% (Han, Kang & Ryu). Per-sleeve caps of
1/sleeves plus a 25% vol target make low portfolio vol plausible by construction. E10 must **show** that with measured vol, not
assume it.

**Selection debt.**
- A1's family N is 21; lifetime TLOS N is 35.
- A1's results were seen before this file.
- The band and the rank cap respond to G3, which is a post-result choice. That is why development and validation are exploratory
  and the DSR uses N ≥ 39.

## 6. Terminal states, kill rules and stop rules

**Terminal states**

| State | Meaning |
|---|---|
| `PREPAPER_CANDIDATE` | Every material gate passes. V1 may then be **proposed** to a separate Owner paper-admission decision, and nothing more |
| `REJECTED` | A material gate clearly fails |
| `INCONCLUSIVE` | A gate cannot be established honestly, for example a missing input or insufficient coverage |
| `INVALID_RUN` | An integrity or causality failure. One technical retry is allowed, then STOP |

**Stop and burn rules**
- Any frozen value, window, threshold or variant is changed after any A1b result: the program is BURNED.
- The holdout is opened before E0–E10: BURNED.
- The data lock does not match: STOP.
- A new idea needs a new preregistration.

**Caps.** 4 configurations, ≤ 24 engine invocations, 0 Hyperopt, 0 LLM tokens.

## 7. Ledger

`research/trial_ledger.py` defines a `PREREGISTERED` record. Precedent (AUTH-2, `make_preregs.py --append-ledger`) appends it
in a commit after the program charter. So `TRIAL-A1B-1` is **not** appended here. It is appended once, in the charter PR,
binding this spec's sha256, before any evaluation.

## 8. Non-claims

- No profitability is claimed. Historical results are exploratory evidence only.
- `PREPAPER_CANDIDATE` is not paper admission and not a survivor decision.
- Nothing here authorizes execution, data download, a paper worker, live trading, exchange keys or capital.

## Citations

- Liu, Tsyvinski & Wu (2022), *Common Risk Factors in Cryptocurrency*, Journal of Finance.
- Liu & Tsyvinski (2021), *Risks and Returns of Cryptocurrency*, Review of Financial Studies.
- Han, Kang & Ryu, *Time-Series and Cross-Sectional Momentum in the Cryptocurrency Market* (working paper, 2013–2023 sample).
- Moskowitz, Ooi & Pedersen (2012), *Time Series Momentum*, Journal of Financial Economics.
- Bailey & López de Prado (2014), *The Deflated Sharpe Ratio*, Journal of Portfolio Management.
- Bailey, Borwein, López de Prado & Zhu (2017), *The Probability of Backtest Overfitting*, Journal of Computational Finance.
