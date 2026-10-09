# TRIAL-C2-TREND-DONCHIAN-1 — result record (CYCLE-2 UNIT 7.3)

Durable copy of a GitHub Actions run whose artifact expires. Derived from the run's artifacts; the ledger record at seq 25 (digest `b258ec2b05d422b849484acd490371befa07fe828ddaa58fa3d7acbe0aeaa071`) is the authoritative terminal state.

## Run

| field | value |
|---|---|
| run | [37155789386](https://github.com/algamal119933-ux/trading-lab-os-sandbox/actions/runs/37155789386) |
| workflow | `.github/workflows/cycle2_research.yml` (workflow_dispatch, conclusion success) |
| head sha | `efe6e77187992fb06f9ddadd470b20d04e583eca` |
| preregistration | `research/cycle2/prereg/TRIAL-C2-TREND-DONCHIAN-1.json` (sha256 `98f5b6c9d9b39c0779adf23bd497760fdfaa316a332fd10b0046b0ed98a07d80`) |
| preregistration record | `research/trend_breakout/PREREGISTRATION.md` (sha256 `5a05b74872b92884abd6164a6a0dfd3ebb56a54193edad022fc4715a82609474`) |
| funnel law | `research/cycle2/FUNNEL_LAW_1.md` (sha256 `5ad00f5ad79a192aac9454e5eb8a90f3ce787fc332e3467fdd9ecf969800468a`) |
| strategy | `research/trend_breakout/DonchianBreakoutV1.py` (sha256 `375dd3dbf65f472fd640bae970abf492fdc7808d757bb2ea1c114bf8ac0bf1cc`) |
| artifact | `cycle2-DonchianBreakoutV1` (zip digest `sha256:b8fc2b3651e805c73480586134444d28a3c26f61145a3075f535c642262da173`), expires 2026-11-02T21:48:48Z |
| ledger before / after | 25 records / 26 records, terminal at seq 25, verify() == [] |

## Verdict (per the frozen law)

| item | value |
|---|---|
| funnel_result | REJECTED |
| ledger state appended | REJECTED (mapping: funnel REJECTED → REJECTED) |
| rejected_by | COST_STRESS, MULTIPLE_TESTING, PARAMETER_ROBUSTNESS, WALK_FORWARD |
| integrity gates ≠ PASS | none |
| cycle2_stop | NO |
| sample evidence | SUFFICIENT |
| local reproduction of funnel_result.json | BYTE_IDENTICAL (sha256 a15fbfdcf40a2751d06d4970a4041db9672308c9ceb6f440121c9d9ad3021ce5) |

PREREGISTRATION.md "Outcomes and what follows", the REJECTED row, verbatim:

```text
REJECTED      any gate FAIL. Terminal; the lineage is not modified, re-tuned or rerun. With
              MR not approved (OPENING-1 §2.2), Cycle 2 proceeds to its closure record (7.5).
```

## Engine invocations (22/22 executed, 22/22 engine_fee_propagation PROVEN)

| # | lane | fold | phase | config | timerange | fee/side | engine_fee_propagation | status | return % | trades | max DD % |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | walk_forward | 1 | train_selection | E168_X72 | 20210101-20221231 | 0.001 | PROVEN | OK | 6.318343 | 79 | 3.8575 |
| 2 | walk_forward | 1 | train_selection | E168_X168 | 20210101-20221231 | 0.001 | PROVEN | OK | 9.862113 | 53 | 8.8284 |
| 3 | walk_forward | 1 | train_selection | E336_X72 | 20210101-20221231 | 0.001 | PROVEN | OK | 7.054239 | 58 | 3.1261 |
| 4 | walk_forward | 1 | train_selection | E336_X168 | 20210101-20221231 | 0.001 | PROVEN | OK | 12.341516 | 38 | 5.3987 |
| 5 | walk_forward | 1 | train_selection | E480_X72 | 20210101-20221231 | 0.001 | PROVEN | OK | 3.954191 | 50 | 5.4949 |
| 6 | walk_forward | 1 | train_selection | E480_X168 | 20210101-20221231 | 0.001 | PROVEN | OK | 11.029501 | 30 | 7.3164 |
| 7 | walk_forward | 1 | eval | E336_X168 | 20230101-20231231 | 0.001 | PROVEN | OK | 7.990000 | 19 | 3.0806 |
| 8 | walk_forward | 1 | cost_stress_eval | E336_X168 | 20230101-20231231 | 0.002 | PROVEN | OK | 7.606752 | 19 | 3.2479 |
| 9 | walk_forward | 2 | train_selection | E168_X72 | 20210101-20231231 | 0.001 | PROVEN | OK | 14.013377 | 116 | 3.8575 |
| 10 | walk_forward | 2 | train_selection | E168_X168 | 20210101-20231231 | 0.001 | PROVEN | OK | 21.650258 | 78 | 8.8284 |
| 11 | walk_forward | 2 | train_selection | E336_X72 | 20210101-20231231 | 0.001 | PROVEN | OK | 13.229337 | 84 | 3.6245 |
| 12 | walk_forward | 2 | train_selection | E336_X168 | 20210101-20231231 | 0.001 | PROVEN | OK | 20.331516 | 57 | 5.3987 |
| 13 | walk_forward | 2 | train_selection | E480_X72 | 20210101-20231231 | 0.001 | PROVEN | OK | 10.620575 | 73 | 5.4949 |
| 14 | walk_forward | 2 | train_selection | E480_X168 | 20210101-20231231 | 0.001 | PROVEN | OK | 20.262064 | 46 | 7.3164 |
| 15 | walk_forward | 2 | eval | E336_X168 | 20240101-20241231 | 0.001 | PROVEN | OK | 8.565228 | 22 | 4.0082 |
| 16 | walk_forward | 2 | cost_stress_eval | E336_X168 | 20240101-20241231 | 0.002 | PROVEN | OK | 8.128267 | 22 | 4.2593 |
| 17 | robustness | — | robustness | E168_X72 | 20210101-20241231 | 0.001 | PROVEN | OK | 25.988294 | 156 | 3.8575 |
| 18 | robustness | — | robustness | E168_X168 | 20210101-20241231 | 0.001 | PROVEN | OK | 34.735612 | 104 | 8.8284 |
| 19 | robustness | — | robustness | E336_X72 | 20210101-20241231 | 0.001 | PROVEN | OK | 22.920986 | 112 | 3.6245 |
| 20 | robustness | — | robustness | E336_X168 | 20210101-20241231 | 0.001 | PROVEN | OK | 28.914638 | 78 | 5.3987 |
| 21 | robustness | — | robustness | E480_X72 | 20210101-20241231 | 0.001 | PROVEN | OK | 20.611254 | 96 | 5.4949 |
| 22 | robustness | — | robustness | E480_X168 | 20210101-20241231 | 0.001 | PROVEN | OK | 28.951223 | 64 | 7.3164 |

selected config by fold (TRAIN selection, preregistered selection_metric `return_over_drawdown`): {"1": "E336_X168", "2": "E336_X168"}.

## Walk-forward (L1/L2, base fee 0.001, EVAL folds)

| fold | config | strategy return % | passive (exposure-matched) % | excess % | trades | sample |
|---|---|---|---|---|---|---|
| 1 | E336_X168 | 7.990000 | 24.600777 | -16.610777 | 19 | SUFFICIENT |
| 2 | E336_X168 | 8.565228 | 16.498089 | -7.932861 | 22 | SUFFICIENT |

Σ excess = -24.543639 % → WALK_FORWARD = FAIL (excess over the exposure-matched passive < 0 in ALL folds → REJECTED).

Passive methodology: 20.00 of a 100.00 wallet invested for the whole window (10.00 each across 2 leg(s)), 80.00 held in cash; invested fraction 0.2000 = max_open_trades(2) x stake(10.0) capped at the wallet.

## Cost stress (L3)

| fee/side | Σ excess % | non-positive | fold-1 passive % | fold-2 passive % |
|---|---|---|---|---|
| 0.001 (base) | -24.543639 | True | 24.600777 | 16.498089 |
| 0.002 | -25.201568 | True | 24.511531 | 16.425056 |

COST_STRESS = FAIL (a stress fee level makes Σ excess <= 0).

## Parameter robustness (L4, GRID_EXCESS_OVER_EXPOSURE_MATCHED, robustness window 20210101-20241231, fee 0.001)

Passive (exposure-matched) over the window: 57.587104 % (`robustness_fee0.001.json`, sha256 `abe3b78b44d7300a2303ca9756e0729ea2176f65f7a001cef9ced09467ca5f61`).

| config | strategy return % | excess % | positive | trades |
|---|---|---|---|---|
| E168_X72 | 25.988294 | -31.598811 | False | 156 |
| E168_X168 | 34.735612 | -22.851492 | False | 104 |
| E336_X72 | 22.920986 | -34.666118 | False | 112 |
| E336_X168 | 28.914638 | -28.672466 | False | 78 |
| E480_X72 | 20.611254 | -36.975850 | False | 96 |
| E480_X168 | 28.951223 | -28.635881 | False | 64 |

positive configurations: 0 of 6 (minimum 4); selected configurations: E336_X168. PARAMETER_ROBUSTNESS = FAIL (0 of 6 configurations positive over the exposure-matched passive < 4).

## Every gate

| gate | state | reason |
|---|---|---|
| COST_STRESS | FAIL | a stress fee level makes Σ excess <= 0 |
| DATA_TRUTH | PASS | DATASET_LOCK_GATE = PASS and WARMUP_OVERLAY_JOIN = PASS |
| LEDGER_CHAIN | PASS | ledger verifies and the preregistration is BOUND |
| LOOKAHEAD | PASS | lookahead-analysis has_bias = No |
| MULTIPLE_TESTING | FAIL | a multiple-testing statistic FAILED its preregistered threshold |
| PARAMETER_ROBUSTNESS | FAIL | 0 of 6 configurations positive over the exposure-matched passive < 4 |
| RECURSIVE | PASS | no recursive variance and no indicator lookahead bias |
| WALK_FORWARD | FAIL | excess over the exposure-matched passive < 0 in ALL folds → REJECTED |

## Multiple testing

| statistic | status | value | threshold | N / effective trials | observations | reason |
|---|---|---|---|---|---|---|
| DSR | PASS | 0.9551601423331788 | 0.95 | N = 15 (effective_trials 15) | 17544 | DSR >= threshold |
| PBO | FAIL | 0.6142857142857143 | 0.05 | effective_trials 6 | 26280 | PBO > threshold |

MULTIPLE_TESTING = FAIL (a multiple-testing statistic FAILED its preregistered threshold). PBO evaluated over the preregistered grid's last-fold TRAIN series.

N derivation: Cycle-1 H1 configurations 9 (from `research/RESEARCH_CYCLE1_CLOSURE_1.md`, identities not resolved) + this trial's 6 distinct N-LAW identities = 15; the Cycle-2 trial-ID count (4) is not N.

**Selection-debt disclosure (stated beside every DSR/PBO figure).** Trend family (OPENING-1 §2.1: inherits the trend family's Cycle-1 count and the H1 upstream selection debt). N = family_configuration_N of BTSL_EMA_REGIME under the N LAW (research/cycle2/config_n.py): Cycle-1 H1's 9 configurations (1 frozen centre + 8 sensitivity neighbours) plus this trial's 6 = 15, not a trial-ID count. The H1 upstream debt (a 42-strategy benchmark winner, a 21-point public sweep, an undocumented midpoint choice) is disclosed verbatim from research/external/candidate_registry.json multiple_testing_accounting beside every DSR/PBO figure; it cannot be observed, so it is not folded into N. This lineage's own selection context (three canonical breakout designs considered, none executed) is in research/trend_breakout/PREREGISTRATION.md.

Verbatim from `research/external/candidate_registry.json → multiple_testing_accounting`:

- LOCAL_TRIAL_COUNT = 2 (H1_EMACROSS and H2_EMACROSSFUNDING - the frozen configurations this lab selects and tests; excluded: evaluation lanes and robustness analyses; re-evaluating one frozen configuration is not an additional trial).
- UPSTREAM_SELECTION_DEBT = substantial and only partly quantified: EmaCross was selected as the winner of a 42-strategy benchmark (33 lost money outright); the funding rule was then added to that already-selected winner - upstream names both selection steps itself; the public grid sweeps 3 ema_period x 7 funding_max_pct = 21 combinations; the published funding_max_pct=55 is not in that grid, so at least one further selection step is undocumented; upstream discarded a prior strategy at PBO 1.00 before arriving at this one.
- TOTAL_SELECTION_PROVENANCE (PARTIALLY_DOCUMENTED): A low LOCAL_TRIAL_COUNT does not make the family lightly-tested. The configurations we run arrive pre-selected from a 42-way benchmark plus a 21-point sweep plus an undocumented midpoint choice, and that history is not reset by our re-evaluating them. Hard rule: Do NOT claim DSR or PBO certification from LOCAL_TRIAL_COUNT alone. Any deflated-Sharpe or PBO figure must state which trial count it used and acknowledge the upstream selection debt it cannot observe.

The DSR figure above used N = 15 and cannot observe the upstream debt; it is not a DSR certification.

## Regime / session diagnostic (OPENING-1 §6.4; diagnostic only, never gating)

**NOT PRODUCED.** `research/cycle2/regime_session.py` takes its regime rule and session table only from a preregistered spec and has no defaults. Neither `research/cycle2/prereg/TRIAL-C2-TREND-DONCHIAN-1.json` nor `research/trend_breakout/PREREGISTRATION.md` preregisters one. Writing a spec after this result would be a post-result choice, and this unit forbids new preregistration content. The regime labels would also need the Dataset V2 OHLCV under its lock, which the run artifact does not include. The diagnostic never gates, so leaving it out changes no gate and not the verdict. The funnel order (OPENING-1 §4: multiple-testing control → regime/session diagnostics → FREEZE) puts it after gates this trial already FAILED. The EVAL trade lists it would read are preserved below by sha256 (`cycle2/backtest_results/fold{1,2}_eval_SELECTED_fee0.001.zip`), so the diagnostic can still be produced later if the Owner preregisters a spec.

## Budget after this record

| budget | consumed by closed trials | cap |
|---|---|---|
| engine invocations | 34 | 120 |
| scientific trial IDs | 1 | 12 |
| calibration trial IDs | 2 | 6 |
| scientific configurations | 6 | 24 |

The run's own budget block reports engine `consumed_before = 12` (the two Cycle-2 nulls, seq 22 and 23) and `consumed_after = 34` (that plus this trial's 22, all executed). Scientific trial ID and configurations count from the preregistration at seq 24, so they are already 1 and 6 before the run. Remaining: engine 86 · SCI 11 · CAL 4 · configs 18.

## Artifact sha256 (every downloaded file)

| file | sha256 |
|---|---|
| `benchmarks/fold1_fee0.001.json` | `d27fa719e04203a20ce38f3888cca5ce9160f79c85588477138c3206cbc64585` |
| `benchmarks/fold1_fee0.001.log` | `13ea8f14661853a778ce2634368dcdf12bb6b820ddb0651ee9ef198565ac541e` |
| `benchmarks/fold1_fee0.002.json` | `5d425e660043438211796afc620b8dabe7cc4be54e216bdcf5ad97d2be4c069c` |
| `benchmarks/fold1_fee0.002.log` | `d8e4cfc800237910ce51da21914003edd2ef1d6fa22694ad8b2b5c0e0c2b1f2f` |
| `benchmarks/fold2_fee0.001.json` | `b5a0a50871f97a9fa52f537f1c40803bdb1e5c159a698baf4f7e472a5f4242ee` |
| `benchmarks/fold2_fee0.001.log` | `ef49ad4021887345663175831a3f13997703427f12a17c6f7bf5e1a08e18739e` |
| `benchmarks/fold2_fee0.002.json` | `40eaca476b0071f1073745951e02cf97ae6d3cbc27bad4c30e652ebaaf3cfd13` |
| `benchmarks/fold2_fee0.002.log` | `421e215aaec09d3ac3de374d1ce9195de04c8daa3e479e052f73ada1af0a4253` |
| `benchmarks/robustness_fee0.001.json` | `abe3b78b44d7300a2303ca9756e0729ea2176f65f7a001cef9ced09467ca5f61` |
| `benchmarks/robustness_fee0.001.log` | `d6a200d8dd52cb16037e6f2ec2333a45d6d04e991dde9e2d44643172fae9dba9` |
| `cycle2/backtest_fold1_cost_stress_eval_SELECTED_fee0.002.log` | `73ad821e9eb542d4ec0ea64a78d9c5583945ca548e06c0be07b225fc03408c21` |
| `cycle2/backtest_fold1_eval_SELECTED_fee0.001.log` | `d8c92d6404582bf04a6da98d3441ee4c9129236eb30669becda69435d74c77c5` |
| `cycle2/backtest_fold1_train_E168_X168_fee0.001.log` | `ab38e1e4e6195d2d71b4ba675d7dd40886922c9e1ee0539f9189e7d3ca512d12` |
| `cycle2/backtest_fold1_train_E168_X72_fee0.001.log` | `bbdbb097e256b9f822030117bb4dbd80f5b7e0a3162171006de762c23dfc648a` |
| `cycle2/backtest_fold1_train_E336_X168_fee0.001.log` | `7e3a1e81420017fcb7313ec3d9480ed2eed59219e800d0b64d19341b6a30c779` |
| `cycle2/backtest_fold1_train_E336_X72_fee0.001.log` | `d2ec8e67c6fc2229cfa58b60af2147b2860b68c9f6ba0a66f469ad8c6ba9a864` |
| `cycle2/backtest_fold1_train_E480_X168_fee0.001.log` | `7138cd085be3d4572f2be2afa767748d46c31af520a0b36befcdc75497ea8952` |
| `cycle2/backtest_fold1_train_E480_X72_fee0.001.log` | `62e2357d79982def11aae4174c4a3314f4a5e158f2bce6ca0c80a331c81c1604` |
| `cycle2/backtest_fold2_cost_stress_eval_SELECTED_fee0.002.log` | `0fb971718c3dc93dd0e16c0ef92fd342283bdec1226f4dde83f5cf32afceb84d` |
| `cycle2/backtest_fold2_eval_SELECTED_fee0.001.log` | `e62aaa2f18098e3a4474167f346f68fd341c78c024119a072f228289230ba488` |
| `cycle2/backtest_fold2_train_E168_X168_fee0.001.log` | `32b98535619d8b0b77de63b0c9dfc9aaa8dbcbae512bc931dad321e100c2b270` |
| `cycle2/backtest_fold2_train_E168_X72_fee0.001.log` | `9e4b1149ad706edf42328f212191c3d35cc8c5a7c50402b26f2229c82eb84c82` |
| `cycle2/backtest_fold2_train_E336_X168_fee0.001.log` | `280f7b5813cd610ea23c24b46118bf430b65220a12abf4967b3ee0cdbb974cb3` |
| `cycle2/backtest_fold2_train_E336_X72_fee0.001.log` | `123cefe7f2b5c16f6b92d661d100fb8d3aa3d546a73aac92de3ff3d78ad00650` |
| `cycle2/backtest_fold2_train_E480_X168_fee0.001.log` | `1f0d06e43f6ebd2d8f8119f7da2d739ebe9e9b4a0efcad3948488def3485fd21` |
| `cycle2/backtest_fold2_train_E480_X72_fee0.001.log` | `435c121264dcd484ad01302312365f36f1ca061875674c9f417b8a81cb59b804` |
| `cycle2/backtest_results/fold1_cost_stress_eval_SELECTED_fee0.002.zip` | `b6319ea8bdc0dae7f6c1e9f3c2dc12ab9a119bf0da8dd7f8c22f9ea28b83843a` |
| `cycle2/backtest_results/fold1_eval_SELECTED_fee0.001.zip` | `09981d7e5f1cb4914f1b2fa433d4288f4173d014abb99d1d872100d20766712d` |
| `cycle2/backtest_results/fold1_train_E168_X168_fee0.001.zip` | `e18e766f42a1258b203153fb46d3ce0c0b56d5a466153a1c4825380f55995f14` |
| `cycle2/backtest_results/fold1_train_E168_X72_fee0.001.zip` | `99fe517e2fb15976b9d190d9f8372b28464b008e305fc0883b8b088e3b8c18bd` |
| `cycle2/backtest_results/fold1_train_E336_X168_fee0.001.zip` | `ab7475292d52a147f2634b7a8684c169b23b2b7357c6b18c6929ba6cfed4931c` |
| `cycle2/backtest_results/fold1_train_E336_X72_fee0.001.zip` | `2df40ce1ce3d791166a14dec49cbb6ea41383bc7b3bc7d0e0501a8f6a153ce51` |
| `cycle2/backtest_results/fold1_train_E480_X168_fee0.001.zip` | `eb496cf1674f6376fe04bc590635ef59a248c7d405805fc2567ac7a8ecd2ae9e` |
| `cycle2/backtest_results/fold1_train_E480_X72_fee0.001.zip` | `f043f13ab8fb47aa7171dc451bbad51e85eec9c208c5bb5b149a772232665a94` |
| `cycle2/backtest_results/fold2_cost_stress_eval_SELECTED_fee0.002.zip` | `5488864398c7fc9975d414e2adcbb269a202045f3e6d14648245a6771f5f304a` |
| `cycle2/backtest_results/fold2_eval_SELECTED_fee0.001.zip` | `08786b47c4b9cd2543f4b643da7a9d08fbbc8fe60f0352a8415f64d3ef9653b2` |
| `cycle2/backtest_results/fold2_train_E168_X168_fee0.001.zip` | `5c6f2ce84463bfe59102b904968a6e17d0bc922deba159d590903721cff8a870` |
| `cycle2/backtest_results/fold2_train_E168_X72_fee0.001.zip` | `913f9c32164298639693f2db181dc7590d1eee3ba927a016061d2e7efcfcd1a9` |
| `cycle2/backtest_results/fold2_train_E336_X168_fee0.001.zip` | `c84b393079e03f4057d263ad6cd693dbeef85031b7a8f2da73365d8e520c4ecf` |
| `cycle2/backtest_results/fold2_train_E336_X72_fee0.001.zip` | `f5f4ceb213899c2a2d24571dad69acc47da65133eb95bc88c0e2f345c86b3ca1` |
| `cycle2/backtest_results/fold2_train_E480_X168_fee0.001.zip` | `e1726f46f655b80da2148c165f1b7d0382c8082a34c840d154d228017890cfc5` |
| `cycle2/backtest_results/fold2_train_E480_X72_fee0.001.zip` | `ba16a2047b2c2b3ce3fc17c648045a9b5fc1ecf08a585df46acde663659091f3` |
| `cycle2/backtest_results/robustness_E168_X168_fee0.001.zip` | `175db2da103d161f166f26a447eb3f5678dbd5faed7332d4e4f07f2d80333a5c` |
| `cycle2/backtest_results/robustness_E168_X72_fee0.001.zip` | `41c2968b381d836f0dc6247396bca8edfa227c53ded03a985a0ae310b46f227f` |
| `cycle2/backtest_results/robustness_E336_X168_fee0.001.zip` | `7a5cbdfadc62129e47356b4d8f8f38abbbe95121ca42ddbb0eb36f149209cdb8` |
| `cycle2/backtest_results/robustness_E336_X72_fee0.001.zip` | `39d24326b91984ec969edb499ed496521df4ebad388551ec584c22ca1e0d7575` |
| `cycle2/backtest_results/robustness_E480_X168_fee0.001.zip` | `9262a6aad759c706b4878f5b637df57b8b47f9e5a0cdc008beb8d4174fbbe0b0` |
| `cycle2/backtest_results/robustness_E480_X72_fee0.001.zip` | `981b6bc047804c0cf96d016e2b15dc502365cade0ae393f38fbcd2c5e249449a` |
| `cycle2/backtest_robustness_E168_X168_fee0.001.log` | `8c0155b3d0481e8f20dba7130fbd9f3d20197d3f7aee526ccc4692027523bb80` |
| `cycle2/backtest_robustness_E168_X72_fee0.001.log` | `61321e3c297303bb89d2ab8c64c7fc709c3328ac13e86ffebb2df09eddf4549c` |
| `cycle2/backtest_robustness_E336_X168_fee0.001.log` | `568937849eb1694c1457ec65a41dce2ce0a6326426cacff0941684f169175a59` |
| `cycle2/backtest_robustness_E336_X72_fee0.001.log` | `10900fc4609b8c1e5577db7a87b14b5a5009a054d82b83d8c54bde46a229b9bc` |
| `cycle2/backtest_robustness_E480_X168_fee0.001.log` | `18b320b6e545cb8f1328938ba9040efc9b9523e68af75b9a2d726fb7c1b932ca` |
| `cycle2/backtest_robustness_E480_X72_fee0.001.log` | `0ae1984af81a8687f38a219bd09c5dcb92a7f8067217e3419c3645eb7ca8e596` |
| `cycle2/cycle2_run_summary.json` | `048ff83f112c44b87ef5d11888859a7c5d114cce9bda896c30ff4b41a0f17583` |
| `cycle2/invocation_fold1_cost_stress_eval_SELECTED_fee0.002.json` | `f3d7f8b2c83faa7c492a8bfc8f1c85568ecc44be4b7ab0b6907656ce94fa9dff` |
| `cycle2/invocation_fold1_eval_SELECTED_fee0.001.json` | `ac9a36aed0fcecb7eb1425733e92cb3572107e9f5a33fbff9632bb80b417eeef` |
| `cycle2/invocation_fold1_train_E168_X168_fee0.001.json` | `d7d8e9a5a5c0d45d7f78822b5e9130c245916e6e2ea76c3cfe493f75d8e7b533` |
| `cycle2/invocation_fold1_train_E168_X72_fee0.001.json` | `33ce6ef68fdb12ddcfbf3795ff66a4e4d70d0f751c9f80d791de521f4e106c2a` |
| `cycle2/invocation_fold1_train_E336_X168_fee0.001.json` | `ea9d8a7844277401d8e72b9331322b23fb5324d3fd999c916975cfbc786e2042` |
| `cycle2/invocation_fold1_train_E336_X72_fee0.001.json` | `d3dc1cee802564c9cf379de934a6c873b911319f143a2bef40b892a5b7e3abb7` |
| `cycle2/invocation_fold1_train_E480_X168_fee0.001.json` | `dde6c564a448c6f79e982e8ba031124aaba46f980a9b6996e05d022ea8f86845` |
| `cycle2/invocation_fold1_train_E480_X72_fee0.001.json` | `b85218e8f8dbbeaf35e154aa8735d72a18e232bfa82b843f851f86fa0fcb484f` |
| `cycle2/invocation_fold2_cost_stress_eval_SELECTED_fee0.002.json` | `688d2af14b588b564a31b9355e32de9b305e28487dc9d6f1aa6a2f36612e4df1` |
| `cycle2/invocation_fold2_eval_SELECTED_fee0.001.json` | `61ef9071f92a2577be2800a653e268a17966e808dc995808602a59cfd23212e2` |
| `cycle2/invocation_fold2_train_E168_X168_fee0.001.json` | `0763fb32deee623368e1fac0fe2c2e7c9477d07d0a41b459ac12daf97d555344` |
| `cycle2/invocation_fold2_train_E168_X72_fee0.001.json` | `94185d5ba23e0b96cbb75428cf15729f1101964305fede2f18c0079356c946b1` |
| `cycle2/invocation_fold2_train_E336_X168_fee0.001.json` | `2f5436fd3f1880db5752ebba4d3fe73f2bb22104433a1da76c00c7d7c68ff87c` |
| `cycle2/invocation_fold2_train_E336_X72_fee0.001.json` | `01f696a3b1a06013392006e2f279f0ae498732f9fcaf99da16e99b1a54ff1790` |
| `cycle2/invocation_fold2_train_E480_X168_fee0.001.json` | `05401bd7ba1e0618dd5185c3b57d01976451e8dba26c4e0245515d7a1116f9dd` |
| `cycle2/invocation_fold2_train_E480_X72_fee0.001.json` | `22d1473cfebb59f2c56192a216c96446ac255e9b0ace2d4368dbe1ba4c4b5812` |
| `cycle2/invocation_robustness_E168_X168_fee0.001.json` | `30efefc2e42850e5f3d8ef5becc421fbdc704e77a4b5fa65c7dfadef08ebd131` |
| `cycle2/invocation_robustness_E168_X72_fee0.001.json` | `a324950f251b47312905f3fce2a37b6e684c9e8cb6a75153d053dee8c1e62f9d` |
| `cycle2/invocation_robustness_E336_X168_fee0.001.json` | `a1c373ce1482963c589931b0203347763f988250b4648ca62124480494a42c58` |
| `cycle2/invocation_robustness_E336_X72_fee0.001.json` | `fdb727b0c2b3055411f6f649d8558b973b5abd8d13f2b79e8bc6b56692f0fe5d` |
| `cycle2/invocation_robustness_E480_X168_fee0.001.json` | `a71e5a66351a65f607b25e35049dabad3526f684517f5369920f164cc70ad3e7` |
| `cycle2/invocation_robustness_E480_X72_fee0.001.json` | `dcd06c0f41063e3b8992ca3786e0a0b83e8a6256e6c11a975ebd8e3caa2904d3` |
| `cycle2/metrics_fold1_cost_stress_eval_SELECTED_fee0.002.json` | `840f25982b71be234c68cc41dd8c2d893528f246bb2394482ca2c1f5a3c7953a` |
| `cycle2/metrics_fold1_cost_stress_eval_SELECTED_fee0.002.md` | `eee2f5629a24d12b59bb07b26405178d3a09332c8b84b20896f0ef202adf5011` |
| `cycle2/metrics_fold1_eval_SELECTED_fee0.001.json` | `8d66a55713ae9f3b0c9076b429d3f353ff646b1b240bd49ebab2118063ae5bb2` |
| `cycle2/metrics_fold1_eval_SELECTED_fee0.001.md` | `a95a13795e27353cfd78ea27bfc2a0c9e7472f475ca4b90864b4bf37a3cb7d4f` |
| `cycle2/metrics_fold1_train_E168_X168_fee0.001.json` | `969e481a24eb9070eb43fee0794ebaebac1967d1b5482b0bb0f921bd20f4d69b` |
| `cycle2/metrics_fold1_train_E168_X168_fee0.001.md` | `40086fc57da7fc5a59a11be6f82fa4f7518109521d715fce4f9d39c66cba08b8` |
| `cycle2/metrics_fold1_train_E168_X72_fee0.001.json` | `cb2a9e3691acf3ba597fa1fd18a29214c773a5d5f73c0088e3725111a10b6a88` |
| `cycle2/metrics_fold1_train_E168_X72_fee0.001.md` | `91c29086c50bf15fb0a0bbbfa5c589a592d5ba7fb19ce09eb3027c60fe9de0bb` |
| `cycle2/metrics_fold1_train_E336_X168_fee0.001.json` | `55aea34c5f6df07fa49dd30e1a76e6f40bcc18bc0c27a17e59cd39fe8886ff81` |
| `cycle2/metrics_fold1_train_E336_X168_fee0.001.md` | `dac1ba22634b3351724fbe8b15da29b0e317106a6f086cee4dc8833158426cbf` |
| `cycle2/metrics_fold1_train_E336_X72_fee0.001.json` | `8f4e2b5945a06a8e518cec9fb129325116bffe7cfa4c195dc8879867585bf352` |
| `cycle2/metrics_fold1_train_E336_X72_fee0.001.md` | `2779d0fb3cc12832a5b98f605fec623459d9f3ea66d8316de56096cdf941c978` |
| `cycle2/metrics_fold1_train_E480_X168_fee0.001.json` | `e55069a5c80c691052ab5aa7c79ed6a4ee29f4c3b9e034eab1b0e4c70cb02439` |
| `cycle2/metrics_fold1_train_E480_X168_fee0.001.md` | `d3117b6734c17d39dc9995488723cd2376fc2af1d80ab2d4a642efb35bac7ebb` |
| `cycle2/metrics_fold1_train_E480_X72_fee0.001.json` | `8031bce4f05404b137672b44b85998878ae96ad0b1df080dad23981db6ab366b` |
| `cycle2/metrics_fold1_train_E480_X72_fee0.001.md` | `cb426908a3dff53dba545a0663df6815ec16e2f2bbd41cbe2fe336c0a2c4bf75` |
| `cycle2/metrics_fold2_cost_stress_eval_SELECTED_fee0.002.json` | `e7b559884f5effb1f14b4c3d192e2ed715b2e27abef52f223291ce4ecb223a96` |
| `cycle2/metrics_fold2_cost_stress_eval_SELECTED_fee0.002.md` | `48fa292c981ad9db1628024c0ccb3ebc498c03adcf7e3dc3e137e4f7f583eb6b` |
| `cycle2/metrics_fold2_eval_SELECTED_fee0.001.json` | `6508165d7442a7481ba5527416a0dbb0dd11cfd5481d0192b0bdd308739260fc` |
| `cycle2/metrics_fold2_eval_SELECTED_fee0.001.md` | `aec2972f0f73c2fbe2158a010ce20241568b9acaad164bbe0e18faf0c9d48ff4` |
| `cycle2/metrics_fold2_train_E168_X168_fee0.001.json` | `dfca48c880d9c8a265e72c1dfb78d18164caeb478763389c9c6644838a728513` |
| `cycle2/metrics_fold2_train_E168_X168_fee0.001.md` | `7dbe5cfe3aaa409997aaa0ecdcf25b022aa32bae1e233bc676e82d0e21589a78` |
| `cycle2/metrics_fold2_train_E168_X72_fee0.001.json` | `6ad844391462ace6019ced77eb0a4b8d26906c6379ac74b744cee70858d847a9` |
| `cycle2/metrics_fold2_train_E168_X72_fee0.001.md` | `9725baa56bb6be5bb48692559211ba498625bb665e10861790f3973a36121532` |
| `cycle2/metrics_fold2_train_E336_X168_fee0.001.json` | `04d03dc8fbead433ef9fbe62d5d9c7942455983872217d181174b4f0137e064d` |
| `cycle2/metrics_fold2_train_E336_X168_fee0.001.md` | `dbbf930c5b2bd948a0025fb5d72d3970ae7bc39592ba32d6e57a82d88b9d4069` |
| `cycle2/metrics_fold2_train_E336_X72_fee0.001.json` | `8debad35a8ace97e207c8c50eca3f60814779520233ad192442143d0fbfde9f8` |
| `cycle2/metrics_fold2_train_E336_X72_fee0.001.md` | `1f108efc964f3c46a80904aeac6cffd3e3d6e900bb0a000809d0b0a35e05f66f` |
| `cycle2/metrics_fold2_train_E480_X168_fee0.001.json` | `35688f111fb1420d00ada8353c76ce7777f06fb935eca752f6fa88120a558814` |
| `cycle2/metrics_fold2_train_E480_X168_fee0.001.md` | `795bd114ed016e1e298cbac92747a20e3a521de6a4f1438609362e7212aa4c5e` |
| `cycle2/metrics_fold2_train_E480_X72_fee0.001.json` | `27e13d62d57857af7fe333ced4cf8fd2a56481c5952f8bb9040e5a459b6fad65` |
| `cycle2/metrics_fold2_train_E480_X72_fee0.001.md` | `09664868df652a795748b74f1b6c1bd13b72485fa199799f8343773d8b45adec` |
| `cycle2/metrics_robustness_E168_X168_fee0.001.json` | `77ddbb09e27ed5b7f60cfc6710cb7ea8eda0660f84dd63c636b9ee11abed9e70` |
| `cycle2/metrics_robustness_E168_X168_fee0.001.md` | `7e97a8763e00933bd2dd2884dfca71f79746f9560bb5bd0ffe252b0cf1c7d4b6` |
| `cycle2/metrics_robustness_E168_X72_fee0.001.json` | `a37d5b43165ccffbe4d90e7f3d8ee411d0343ce185e8169d29764fa7bc9df758` |
| `cycle2/metrics_robustness_E168_X72_fee0.001.md` | `462462a5aea0f53282b4e554981c4151c6ff2a61a38460e49e7c7b062e584f40` |
| `cycle2/metrics_robustness_E336_X168_fee0.001.json` | `7a2355089e0b45b9c7dbf5899fcd44bdc971fda615db6045e5229c4681571952` |
| `cycle2/metrics_robustness_E336_X168_fee0.001.md` | `f626b3bf38527e6828956666b84f470ddff7118646d499500949593c9c185d41` |
| `cycle2/metrics_robustness_E336_X72_fee0.001.json` | `410e871af054a0b5fc5998eef46ce72edaa5fc943d12594c2134efd45002705c` |
| `cycle2/metrics_robustness_E336_X72_fee0.001.md` | `73fcc85a0a115dc633ea0933a90e90a988d67885e8909feae1cf461b9e5331c6` |
| `cycle2/metrics_robustness_E480_X168_fee0.001.json` | `da7c5edd5b8ee22f7fec707d1967648c92e73ac76871626c8fcec8e9fdf1bfee` |
| `cycle2/metrics_robustness_E480_X168_fee0.001.md` | `01800b7d5aff5ab9bdbf815ed9d4df7fc8665aae11b44477d64a4a29095bbe35` |
| `cycle2/metrics_robustness_E480_X72_fee0.001.json` | `8816d911f86fd886142016f13cc8146c92717276f7b40f9af17bd043f9383926` |
| `cycle2/metrics_robustness_E480_X72_fee0.001.md` | `ff2708c5cdf2de8f3ea58952369b70113ad8d0ee0795a269c1fd7f1dd7d48836` |
| `cycle2_eval_windows.json` | `81b994be0e9f590e9980c7311271260d3a7be760fc2e151b3652c054547ce2a4` |
| `driver.log` | `26ddca3558255de30d80d1a91b7c7c13af13ef4ef575805865567a562383b8ba` |
| `funnel.log` | `7f4d6df26e2bdeec921bc22b6c5845f69b82336364626e27ba3ec8f314b91657` |
| `funnel_result.json` | `a15fbfdcf40a2751d06d4970a4041db9672308c9ceb6f440121c9d9ad3021ce5` |
| `lookahead_development.log` | `6678ebe19b2cbec29a2d7ded15c735473a81f03068261941e2c9926edcddee47` |
| `paper_guard_with_candidate.log` | `c8954b8dc871639fe91265b5ad69b0ea2083a173193a5cef74a1045fcf57fdc8` |
| `recursive_development.log` | `1d99d935d55bd8cd643f1d064c38c1c07052ee0dceb7c8c2b7e56b72cea850cb` |
| `reproduction_identity.json` | `5640576229ce9b736c21abbb877f623bb9eab6f7e8559145111664cc4223333a` |
| `v4_dataset_lock_check.log` | `ce64a061c217d3caf78c27f9e062ef74d7ce664a982ab74a66f29036aec8b3b7` |
| `v7_warmup_join.json` | `a01311a5ebb27603b6d2c5ad01c00992c5043177822436809bfe4b7c6aa40765` |
| `v7_warmup_join.log` | `3e6dc5f7d3588e63ef748fee856599d01c93907380e0d99c622dd64d4d405f1a` |
