# BASELINE-1 — Development result on Dataset V2

Evidence: GitHub Actions run
[34064987322](https://github.com/algamal119933-ux/trading-lab-os-sandbox/actions/runs/34064987322),
code commit `94753fe`, strategy sha256 `8c0bc6c5…`, effective config sha256
`7941da97…`, all frozen **before** the evaluation ran.

Machine-readable record: `research/records/baseline1_development_datasetv2.json`.

## The two verdicts, kept apart

### `BASELINE_PROTOCOL_RESULT = INCOMPLETE`

Six of the seven pre-registered criteria are met on real, checksum-verified
Binance data:

| Criterion | Result |
| --- | --- |
| Dataset V2 integrity on real data | **PASS** — structural integrity clean, prices reconcile exactly |
| Code and config hashes frozen before evaluation | **PASS** |
| Backtest completes over the whole window with 5m detail, no config error | **PASS** |
| Lookahead analysis reports no bias | **PASS** — 20 signals, 0 biased entries, 0 biased exits, 0 biased indicators |
| Recursive analysis acceptable | **PASS** — no bias; drift at the strategy's 600 startup candles is 0.000 % (EMA50) and −0.003 % (EMA200) |
| Exposure, attribution and cost figures computed | **NOT MET** — see below |
| No rule changed between spec freeze and evaluation | **PASS**, with one recorded correction |

The seventh fails and that is why the protocol result is not a PASS: the metrics
step never ran to completion. Its cause was found by extracting the step and
running it locally — a heredoc whose terminator is not at column 0 once nested,
which makes bash exit 2 before executing anything, producing the instant,
output-free failure seen in CI. The step has been rewritten without heredocs and
both its success and failure paths verified locally, but **the confirming CI run
has not completed**: it stalled in the backtest step for over an hour, against
35-53 seconds in the two runs that produced the evidence above, and was
cancelled. So the fix is committed and locally proven, and the metrics remain
uncomputed in CI. Capital exposure, turnover and fees
below are therefore **derived** from the engine's own trade count, average
duration and fixed stake — arithmetic, but not engine output. **Per-pair
attribution and time-in-market are simply not available**, and the protocol
requires them.

The recorded correction: the committed config paired market order types with
`entry_pricing.price_side = "same"`, which the engine rejects — a market order
crosses the spread by definition. Both sides now use `"other"`. The strategy
logic did not change; the Development backtest was re-run under the corrected
config rather than reported from the old one.

### `BASELINE_PERFORMANCE_CLASSIFICATION = NEUTRAL`

Against the pre-registered thresholds in
[`BASELINE_1_PROTOCOL.md`](BASELINE_1_PROTOCOL.md), fixed before any result
existed.

## Development backtest — 2021-01-01 → 2025-01-01

| Metric | Value |
| --- | --- |
| Trades | 211 (62 win / 149 loss, **29.4 %** win rate) |
| Total return | **+27.80 %** (+27.797 USDT on a 100 USDT wallet) |
| Average profit per trade | +1.32 % |
| Average trade duration | 7 days 3:02 |
| Max drawdown (account underwater) | **11.67 %** (13.842 USDT) |
| Relative drawdown | 10.17 % (11.881 USDT) |
| Drawdown window | 2021-11-10 → 2023-01-03 (419 days) |
| Min / max wallet balance | 97.68 / 130.472 USDT |
| Sharpe (daily wallet balance) | **0.80** |
| Sortino | **0.97** |
| Calmar | **3.12** |

Derived (see caveat above): average capital exposure **10.29 %**, return per
unit of exposure **+270 %**, turnover 4,220 USDT, fees ≈ 4.22 USDT.

## Passive comparison — the number that matters

| Benchmark | Return |
| --- | --- |
| BTC/USDT buy-and-hold, net of fees | +222.08 % |
| ETH/USDT buy-and-hold, net of fees | +353.79 % |
| 50/50 fully invested | +287.94 % |
| Max-exposure-matched (20 % invested throughout) | +57.59 % |
| **Realised-exposure-matched (10.29 % average exposure)** | **+29.63 %** |
| **BASELINE-1** | **+27.80 %** |
| **Excess over realised-exposure-matched** | **−1.83 pp → NEUTRAL** |

Read against buy-and-hold, +27.8 % in a market that returned +288 % looks like a
failure. Read against the exposure it actually took — about a tenth of the
wallet at risk on average — it is a dead heat with passive, with a much smaller
drawdown (11.67 % versus the 50/50 line's far deeper one).

Neither reading makes it a good strategy. It is a **reference**, and the useful
result is the reference point itself: on Dataset V2's Development window, a
minimal EMA50/EMA200 regime rule earns roughly what passive would have earned on
the same average capital, with a 29.4 % win rate carried by a few long winners.
Any future candidate has to beat that, on the same window, under the same
frozen protocol.

## What this does not show

* Validation is untouched and must stay that way until the protocol is closed.
* No forward-paper or prospective out-of-sample evidence exists.
* Per-pair attribution and time-in-market are missing.
* Dataset V2's four fingerprints are computed and verified, but two are not yet
  transcribed into the lock, so the lock is not marked frozen.
