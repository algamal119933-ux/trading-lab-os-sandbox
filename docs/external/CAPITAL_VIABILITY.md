# Capital viability — operating economics, kept separate from alpha

Required by directive v1.1 §6, revised under the pre-Wave-1 review correction. The
correction replaced a single proportional break-even with a **scenario matrix**, because
one break-even number silently assumed one sizing mode and one hosting arrangement, and
neither is a given.

Two things are reported separately throughout and must never be merged:

```
STATISTICAL_ALPHA    - is there excess return over exposure-matched passive?
OPERATING_ECONOMICS  - does what remains survive fees and running costs at this size?
```

A candidate can pass one and fail the other. Conflating them is how a strategy with no
edge gets sold on its gross return, and how a real edge gets dismissed because someone
priced it against a dedicated server it never needed.

This is the framework plus the frozen control's row. Candidate rows are added as each
clears its gates. Every input is BASELINE-1's immutable Development record; nothing here
required a run.

## Inputs (frozen evidence)

| | |
| --- | --- |
| Window | Dataset V2 Development, 2021-01-01 → 2024-12-31 (4 years) |
| Net return | +27.80% on a 100 USDT wallet |
| Trades / turnover | 211 trades, 4,150 USDT — **41.5× capital** |
| Fees paid | 4.15 USDT at 0.1% per side |
| Sizing as configured | **fixed** 10 USDT stake, max 2 open trades |
| Binance spot min notional | 5 USDT — every stake below clears it |

## Sizing scenarios

**Fixed stake** is what BASELINE-1 actually declares: 10 USDT per trade, at most two open.
Absolute profit is then capped by the stake and does not respond to wallet size at all.

**Proportional stake** scales the stake with the wallet, holding percentage exposure
constant. Only in this mode does "return %" mean what a reader assumes.

The gap between them is the single largest effect in this document — larger than any
hosting choice:

| Wallet | Sizing | Net profit (4y) | Fees |
| ---: | --- | ---: | ---: |
| 100 | either | 27.80 | 4.15 |
| 500 | proportional | 138.99 | 20.75 |
| 500 | fixed | 27.80 | 4.15 |
| 2,000 | proportional | 555.95 | 83.00 |
| 2,000 | fixed | 27.80 | 4.15 |
| 10,000 | proportional | 2,779.74 | 415.00 |
| 10,000 | fixed | **27.80** | 4.15 |

At 10,000 USDT under the configured fixed stake, average capital exposure falls to roughly
0.2% and the strategy returns the same 27.80 USDT it returned on 100. **Any capital row
that does not name its sizing mode is not interpretable.**

## Infrastructure scenarios

| Infrastructure | Opex (4y) | Break-even wallet, proportional |
| --- | ---: | ---: |
| Dedicated VPS ($5/mo) | 240 USDT | **863 USDT** |
| Shared VPS, 1 of 4 strategies ($1.25/mo) | 60 USDT | **216 USDT** |
| Existing / local hardware | 0 | **0 — no opex hurdle** |

The $5/month figure is the postmortem's own, not invented here. The shared row assumes one
box already running four strategies; the marginal cost of the fourth is what should be
charged to it. The third row is the common retail reality — a machine that is already on
and already paid for, where the marginal cost of one more Freqtrade process is
approximately nothing.

## Full matrix, after operating cost

| Wallet | Sizing | Dedicated VPS | Shared VPS | Existing hardware |
| ---: | --- | ---: | ---: | ---: |
| 100 | proportional | −212.20 | −32.20 | **+27.80** |
| 100 | fixed | −212.20 | −32.20 | **+27.80** |
| 500 | proportional | −101.01 | **+78.99** | **+138.99** |
| 500 | fixed | −212.20 | −32.20 | **+27.80** |
| 2,000 | proportional | **+315.95** | **+495.95** | **+555.95** |
| 2,000 | fixed | −212.20 | −32.20 | **+27.80** |
| 10,000 | proportional | **+2,539.74** | **+2,719.74** | **+2,779.74** |
| 10,000 | fixed | −212.20 | −32.20 | **+27.80** |

### What the matrix corrects

The earlier single break-even of ~863 USDT was real but over-general. It is the break-even
for **one** cell — proportional sizing on a dedicated VPS. Read as *the* break-even it
overstates the hurdle by about 4× against a shared box, and it does not apply at all to
someone running on hardware they already own.

The honest summary is narrower and more useful:

- **Hosting choice, not account size, decides the small tiers.** At 100 USDT the control
  is under water on a dedicated VPS and profitable on existing hardware. Same strategy,
  same trades, opposite economics.
- **Fixed stake is the binding constraint above ~500 USDT**, and no hosting choice rescues
  it. It never clears a dedicated VPS at any wallet size tested.

## Fee headroom — this design's real strength

211 trades in four years is 41.5× turnover. Working back from the frozen figures, the fee
per side that would erase the whole net return is **≈ 0.77%** — nearly **eight times** the
0.1% charged. Fees are 13.0% of gross profit.

That inverts what the external sources found elsewhere: btc-strategy-lab records
`EMASkipPump` paying **1,191% of capital** in fees over 5,953 trades, and 21 of 22 5m
strategies unprofitable at a median of −95.6%.

**Ordering consequence for Wave 1.** Compute a high-frequency candidate's fee headroom
*before* discussing its return. On this evidence the cost gate (V6) is where 5m candidates
are most likely to die, and it is cheap to run.

## The control's verdict

Every figure above uses **raw return**, which flatters. The frozen classification is
`E = −1.38 pp` on Development and `+1.97 pp` on Validation against exposure-matched
passive.

```
STATISTICAL_ALPHA    = NOT PROVEN  (E inside the NEUTRAL band on both windows)
OPERATING_ECONOMICS  = VIABLE only on shared or already-owned infrastructure,
                       and only under proportional sizing
```

So the 27.80 USDT is exposure, not edge — obtainable by holding, without the machine. That
is not a criticism of a reference that passed its protocol; it is what NEUTRAL means, and
it sets the bar for the sprint: **a candidate must beat exposure-matched passive by enough
to cover its own operating cost, in the sizing mode and on the infrastructure it is
actually meant for.** A candidate that wins only at 10,000 USDT is a real finding. So is
one that wins nowhere.

## Limits

- Four-year historical figures on one frozen window. Not a projection.
- No slippage is modelled anywhere in Dataset V2. A strategy whose edge is thinner than the
  spread would not be caught by anything here, which is why slippage sensitivity stays a
  separate Wave 2 stress test.
- Tax is excluded entirely, and it is not small in most jurisdictions.
- `REAL_MONEY_AUTHORIZED=NO`. Nothing here is a recommendation to trade at any size.
