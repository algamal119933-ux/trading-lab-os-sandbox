# Capital viability — is the edge economically meaningful?

Required by directive v1.1 §6, which asks for a **separate** economic view at 100, 500,
2,000 and 10,000 USDT, and insists on keeping `STATISTICAL_EDGE` apart from
`ECONOMICALLY_MEANINGFUL_EDGE`.

This is the framework plus the frozen control's row. Candidate rows are added as each one
clears its gates. Nothing here required running anything: every input is BASELINE-1's
immutable Development record.

## Inputs (all frozen evidence)

| | |
| --- | --- |
| Window | Dataset V2 Development, 2021-01-01 → 2024-12-31 (4 years) |
| Net return | **+27.80%** on a 100 USDT wallet |
| Trades | 211 |
| Turnover | 4,150 USDT — **41.5× capital** over four years |
| Fees paid | 4.15 USDT at 0.1% per side |
| Sizing as configured | fixed 10 USDT stake, max 2 open trades |
| Operating cost assumed | **$5/month VPS** — the postmortem's own figure, not invented here |

## The four tiers

Two sizing modes have to be shown separately, because BASELINE-1 is configured with a
**fixed** 10 USDT stake. Scale the wallet without scaling the stake and the strategy still
deploys at most 20 USDT, so absolute profit does not move at all.

| Wallet | Mode | Stake | Net profit (4y) | Fees | Opex (4y) | After opex |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 100 | proportional | 10 | 27.80 | 4.15 | 240 | **−212.20** |
| 100 | fixed stake | 10 | 27.80 | 4.15 | 240 | **−212.20** |
| 500 | proportional | 50 | 138.99 | 20.75 | 240 | **−101.01** |
| 500 | fixed stake | 10 | 27.80 | 4.15 | 240 | **−212.20** |
| 2,000 | proportional | 200 | 555.95 | 83.00 | 240 | +315.95 |
| 2,000 | fixed stake | 10 | 27.80 | 4.15 | 240 | **−212.20** |
| 10,000 | proportional | 1,000 | 2,779.74 | 415.00 | 240 | +2,539.74 |
| 10,000 | fixed stake | 10 | 27.80 | 4.15 | 240 | **−212.20** |

All stakes clear Binance spot's 5 USDT minimum notional, so order-size mechanics are not
the binding constraint here. Something else is.

## Finding 1 — operating cost, not strategy quality, decides small accounts

**A $5/month VPS costs 240 USDT over four years. BASELINE-1's entire four-year profit on a
100 USDT wallet is 27.80 USDT.** The hosting bill is roughly **nine times** the profit.

Breakeven against that single line item, scaling proportionally:

> **≈ 863 USDT.** Below that, a strategy performing exactly as BASELINE-1 did returns less
> than the cost of the machine it runs on.

That is before tax, before any exchange withdrawal fee, and before a single hour of the
operator's time is valued at anything.

This reframes the sprint's smallest tier. At 100 USDT the question "does this strategy have
an edge?" is not the operative one, because no edge of this magnitude survives the
overhead. It is worth knowing that before spending CI minutes discovering it.

## Finding 2 — the fixed-stake configuration does not scale at all

The frozen control deploys 10 USDT per trade with at most two positions open, so its
average capital exposure was 10.13% on a 100 USDT wallet. Move the wallet to 10,000 and
leave the sizing alone and exposure falls to about 0.2%: the same 27.80 USDT of profit
against a hundred times the capital.

So a capital-viability row is meaningless unless it states which mode it assumes. Any
future candidate row in this table must declare it. Proportional scaling is the only mode
in which "return %" means what a reader will assume it means.

## Finding 3 — low turnover is this design's real cost advantage

211 trades in four years is 41.5× turnover. Working backwards from the frozen figures, the
fee per side that would erase the entire net return is **≈ 0.77%** — nearly **eight times**
the 0.1% actually charged.

That headroom is the strongest thing in the control's economic profile, and it is worth
stating plainly because it is the exact opposite of what the external sources found
elsewhere: btc-strategy-lab records `EMASkipPump` making 5,953 trades and paying **1,191%
of capital** in fees, and 21 of 22 5m strategies unprofitable with a median of −95.6%.

**Implication for Wave 1 ordering.** `GeneticEngineV1` is a 5m strategy claiming 183 trades
in three months. Its fee headroom should be computed *before* its return is discussed — the
cost gate (V6) is cheap, and on this evidence it is where 5m candidates are most likely to
die.

## Finding 4 — the control has no economically meaningful edge at any tier

The tiers above use **raw return**, which flatters the picture. The frozen classification is
`E = −1.38 pp` on Development and `+1.97 pp` on Validation against the
exposure-matched passive line: the control roughly reproduces the return of the exposure it
takes.

So the 27.80 USDT is not edge. It is market exposure, obtainable by holding, without the
VPS. Combining that with Finding 1:

```
STATISTICAL_EDGE            = NOT PROVEN  (E within the NEUTRAL band, both windows)
ECONOMICALLY_MEANINGFUL_EDGE = NO         (at every tier, for the frozen control)
```

That is not a criticism of BASELINE-1, which was built as a reference and passed its
protocol. It is the correct reading of a NEUTRAL result, and it sets the bar the external
sprint has to clear: **a candidate must beat exposure-matched passive by enough to cover
its own operating cost at the account size it is meant for.** A candidate that wins on
excess return but only at 10,000 USDT is a real finding, and so is one that wins nowhere.

## What this file must not be used for

- Not a projection. These are four-year historical figures on one frozen window.
- Not a recommendation to trade at any size. `REAL_MONEY_AUTHORIZED=NO`.
- Not a slippage model. None is applied anywhere in Dataset V2; a strategy whose edge is
  thinner than the spread would not be caught by anything in this table, which is why
  slippage sensitivity stays a separate Wave 2 stress test.
