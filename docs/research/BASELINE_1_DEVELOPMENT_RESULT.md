# BASELINE-1 — Development result on Dataset V2

Evidence: GitHub Actions run
[34076735190](https://github.com/algamal119933-ux/trading-lab-os-sandbox/actions/runs/34076735190),
code commit `1a2514c`, strategy sha256 `8c0bc6c5…`, config example sha256
`d1d078c6…`, effective config sha256 `fc00865b…`, all frozen **before** the
evaluation ran.

Machine-readable record: `research/records/baseline1_development_datasetv2.json`.

## The two verdicts, kept apart

### `BASELINE_PROTOCOL_RESULT = PASS`

All seven pre-registered criteria are met on real, checksum-verified Binance
spot data:

| Criterion | Result |
| --- | --- |
| Dataset V2 integrity on real data | **PASS** — structural integrity clean, prices reconcile exactly |
| Code and config hashes frozen before evaluation | **PASS** |
| Backtest completes over the whole window with 5m detail, no config error | **PASS** |
| Lookahead analysis reports no bias | **PASS** — 20 signals, 0 biased entries, 0 biased exits, 0 biased indicators |
| Recursive analysis acceptable | **PASS** — no bias; drift at the strategy's 600 startup candles is 0.000 % (EMA50) and −0.003 % (EMA200) |
| Exposure, attribution and cost figures computed | **PASS** |
| No rule changed between spec freeze and evaluation | **PASS**, with one recorded correction |

The sixth criterion held this result at INCOMPLETE across five runs. The cause
was not in the research code: Freqtrade 2026.7 exports a backtest as
`backtest-result-<ts>.zip` and leaves only a small `.meta.json` beside it, while
the metrics step globbed for `*.json` and so found nothing substantive. The
summariser now reads either shape. Two earlier fixes on the way to that — a
heredoc terminator not at column 0, which makes bash exit 2 before running
anything, and capturing the step's own output to a file the job echoes — were
real bugs, but neither was the one that mattered.

The recorded correction: the committed config paired market order types with
`entry_pricing.price_side = "same"`, which the engine rejects — a market order
crosses the spread by definition. Both sides now use `"other"`, which is also
the more conservative fill assumption. The strategy logic did not change; the
Development backtest was re-run under the corrected config rather than reported
from the old one.

### `BASELINE_PERFORMANCE_CLASSIFICATION = NEUTRAL`

Against the pre-registered thresholds in
[`BASELINE_1_PROTOCOL.md`](BASELINE_1_PROTOCOL.md), fixed before any result
existed.

## Development backtest — 2021-01-01 → 2025-01-01

Engine-reported:

| Metric | Value |
| --- | --- |
| Trades | 211 (62 win / 149 loss, **29.4 %** win rate) |
| Total return | **+27.80 %** (+27.797 USDT on a 100 USDT wallet) |
| Average profit per trade | +1.32 % |
| Average trade duration | 7 days 3:02 |
| Profit factor | **1.51** |
| Max drawdown (wallet basis) | **11.67 %** (13.842 USDT) |
| Max drawdown (closed-trade basis) | 10.17 % (11.881 USDT) |
| Drawdown window | 2021-11-10 → 2023-01-03 (419 days) |
| Min / max wallet balance | 97.68 / 130.472 USDT |
| Max consecutive losses / wins | **12** / 3 |
| Sharpe — daily wallet balance / closed trades | **0.80** / 0.32 |
| Sortino — daily wallet balance / closed trades | **0.97** / 1.65 |
| Calmar — daily wallet balance / closed trades | **3.12** / 3.57 |
| Market change over the window | +291.90 % |
| Per-pair attribution | ETH/USDT **+18.70 %**, BTC/USDT **+9.10 %** |

Freqtrade reports Sharpe, Sortino and Calmar on two different bases. Both are
recorded rather than one being quietly chosen; the daily-wallet-balance figures
are the ones used for classification, because they account for capital sitting
idle rather than only for the trades that closed.

Computed by `research/summarize_backtest.py` from the exported trade list, which
is where every exposure figure comes from — Freqtrade reports none of them:

| Metric | Value |
| --- | --- |
| Time in market | **59.64 %** of the window |
| Average capital exposure | **10.13 %** of the wallet |
| Peak capital exposure | 19.96 % (2 concurrent trades, the configured maximum) |
| Return per unit of exposure | **+274 %** |
| Turnover | 4,150 USDT |
| Fees | ≈ 4.15 USDT |

Turnover and fees are approximations (entry plus exit notional at 2 × 0.1 %);
the engine exported no per-trade fee fields.

## Passive comparison — the number that matters

| Benchmark | Return |
| --- | --- |
| BTC/USDT buy-and-hold, net of fees | +222.08 % |
| ETH/USDT buy-and-hold, net of fees | +353.79 % |
| 50/50 fully invested | +287.94 % |
| Max-exposure-matched (20 % invested throughout) | +57.59 % |
| **Realised-exposure-matched (10.13 % average exposure)** | **+29.18 %** |
| **BASELINE-1** | **+27.80 %** |
| **Excess over realised-exposure-matched** | **−1.38 pp → NEUTRAL** |

Read against buy-and-hold, +27.8 % in a market that returned +292 % looks like a
failure. Read against the exposure it actually took — about a tenth of the
wallet at risk on average, and in the market only 60 % of the time — it is a
dead heat with passive, slightly behind, with a much shallower drawdown.

The two exposure numbers say different things and both matter. Time in market
of 59.6 % with average capital exposure of 10.1 % means the strategy was usually
holding *something*, but rarely much: with `max_open_trades = 2` and a 10 USDT
stake on a 100 USDT wallet, even both positions open is only 20 % of capital.
The cash drag is structural, a consequence of the sizing, not of the signal.

Neither reading makes it a good strategy. It is a **reference**, and the useful
result is the reference point itself: on Dataset V2's Development window, a
minimal EMA50/EMA200 regime rule earns roughly what passive would have earned on
the same average capital, with a 29.4 % win rate carried by a few long winners —
12 consecutive losses at the worst stretch, and ETH contributing twice BTC's
share. Any future candidate has to beat that, on the same window, under the same
frozen protocol.

## What this does not show

* Validation is untouched at the time of this result and must stay that way
  until the protocol is closed. It is then run once, unchanged.
* No forward-paper or prospective out-of-sample evidence exists.
* The exposure, turnover and fee figures are derived from the trade list, not
  reported by the engine. The arithmetic is tested
  (`tests/test_summarize_backtest.py`), but it is a model of the account, not
  the account itself.
* One window, one market regime pair, two pairs. A four-year sample containing
  one full bull-bear cycle is not evidence of robustness.
