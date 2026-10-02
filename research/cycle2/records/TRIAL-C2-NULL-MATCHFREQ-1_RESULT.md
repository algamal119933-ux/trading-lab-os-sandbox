# TRIAL-C2-NULL-MATCHFREQ-1 — result record (CYCLE-2 UNIT 7.2 B1)

Durable copy of a GitHub Actions run whose artifact expires. Derived from the run's artifacts; the ledger record at seq 22 (digest `a77340a0560c7c3ca73e04f417b2b2e2cc816fbdadd5a105523dcd6e3757cf12`) is the authoritative terminal state.

## Run

| field | value |
|---|---|
| run | [37032878568](https://github.com/algamal119933-ux/trading-lab-os-sandbox/actions/runs/37032878568) |
| workflow | `.github/workflows/cycle2_research.yml` (workflow_dispatch, conclusion success) |
| head sha | `31c26b6be55ad009bc0c81fec607f3ff20a34273` |
| preregistration | `research/cycle2/prereg/TRIAL-C2-NULL-MATCHFREQ-1.json` (sha256 `37123d5bcfcef808378440f0976c27294aba2b602db51b2cf5bba7637421ede8`) |
| funnel law | `research/cycle2/FUNNEL_LAW_1.md` (sha256 `5ad00f5ad79a192aac9454e5eb8a90f3ce787fc332e3467fdd9ecf969800468a`) |
| artifact | `cycle2-NullControlMatchedFrequency` (zip digest `sha256:2ea9b3ce0ccd92780300582bea45c13fd0af304468930ae66a74b5ce31ef3a4d`), expires 2026-11-01T16:20:01Z |
| ledger before / after | 22 records / 23 records, terminal at seq 22, verify() == [] |

## Verdict (per the frozen law)

| item | value |
|---|---|
| funnel_result | REJECTED |
| ledger state appended | REJECTED (mapping: funnel REJECTED → REJECTED) |
| calibration verdict | PASS |
| rejected_by | COST_STRESS, WALK_FORWARD |
| integrity gates ≠ PASS | none |
| cycle2_stop | NO |
| sample evidence | SUFFICIENT |
| local reproduction of funnel_result.json | BYTE_IDENTICAL (sha256 860cc994010a2a29b0b8972735708220fa217610c95b1c25d527fc64bf515e29) |

## Engine invocations (6/6 executed, 6/6 engine_fee_propagation PROVEN)

| # | fold | phase | timerange | fee/side | engine_fee_propagation | status | return % | trades | max DD % |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | train_selection | 20210101-20221231 | 0.001 | PROVEN | OK | 1.234845 | 40 | 6.8435 |
| 2 | 1 | eval | 20230101-20231231 | 0.001 | PROVEN | OK | 7.510575 | 17 | 1.6655 |
| 3 | 1 | cost_stress_eval | 20230101-20231231 | 0.002 | PROVEN | OK | 7.165632 | 17 | 1.7414 |
| 4 | 2 | train_selection | 20210101-20231231 | 0.001 | PROVEN | OK | 8.942096 | 57 | 6.8435 |
| 5 | 2 | eval | 20240101-20241231 | 0.001 | PROVEN | OK | 0.958608 | 19 | 3.0667 |
| 6 | 2 | cost_stress_eval | 20240101-20241231 | 0.002 | PROVEN | OK | 0.593824 | 19 | 3.2541 |

selected config by fold: {"1": "CFG1", "2": "CFG1"} (single configuration CFG1).

## Walk-forward (L1/L2, base fee 0.001, EVAL folds)

| fold | strategy return % | passive (exposure-matched) % | excess % | trades | sample |
|---|---|---|---|---|---|
| 1 | 7.510575 | 31.058557 | -23.547982 | 17 | SUFFICIENT |
| 2 | 0.958608 | 23.973366 | -23.014758 | 19 | SUFFICIENT |

Σ excess = -46.562740 % → WALK_FORWARD = FAIL (excess over the exposure-matched passive < 0 in ALL folds → REJECTED).

Passive methodology: 20.00 of a 100.00 wallet invested for the whole window (20.00 each across 1 leg(s)), 80.00 held in cash; invested fraction 0.2000 = max_open_trades(2) x stake(10.0) capped at the wallet.

## Cost stress (L3)

| fee/side | Σ excess % | non-positive | fold-1 passive % | fold-2 passive % |
|---|---|---|---|---|
| 0.001 (base) | -46.562740 | True | 31.058557 | 23.973366 |
| 0.002 | -47.082309 | True | 30.956389 | 23.885375 |

COST_STRESS = FAIL (a stress fee level makes Σ excess <= 0).

## Every gate

| gate | state | reason |
|---|---|---|
| COST_STRESS | FAIL | a stress fee level makes Σ excess <= 0 |
| DATA_TRUTH | PASS | DATASET_LOCK_GATE = PASS and WARMUP_OVERLAY_JOIN = PASS |
| LEDGER_CHAIN | PASS | ledger verifies and the preregistration is BOUND |
| LOOKAHEAD | PASS | lookahead-analysis has_bias = No |
| MULTIPLE_TESTING | NOT_EVALUABLE | a multiple-testing statistic is NOT_EVALUABLE (never PASS) |
| PARAMETER_ROBUSTNESS | NOT_APPLICABLE | lineage_kind NULL_CALIBRATION has no parameters |
| RECURSIVE | PASS | no recursive variance and no indicator lookahead bias |
| WALK_FORWARD | FAIL | excess over the exposure-matched passive < 0 in ALL folds → REJECTED |

## Multiple testing

| statistic | status | value | threshold | N / effective trials | reason |
|---|---|---|---|---|---|
| DSR | NOT_EVALUABLE | null | 0.95 | N = 2 (effective_trials 2) | cross-trial Sharpe variance is not estimable (fewer than 2 trial Sharpes, or all equal) while effective_trials=2 |
| PBO | NOT_EVALUABLE | null | 0.05 | effective_trials 1 | too few configurations for CSCV: 1 < 2 |

**PBO = NOT_EVALUABLE (single configuration); not a PBO validation.** PBO is NOT_EVALUABLE with a single configuration. This trial does not validate PBO; PBO's first real exercise is a multi-configuration trial.

MULTIPLE_TESTING = NOT_EVALUABLE (a multiple-testing statistic is NOT_EVALUABLE (never PASS)). It is not a FAIL and did not drive the verdict; the REJECTED result comes from WALK_FORWARD and COST_STRESS.

## Budget after this record

| budget | consumed by closed trials | cap |
|---|---|---|
| engine invocations | 6 | 120 |
| calibration trial IDs | 2 | 6 |
| scientific trial IDs | 0 | 12 |
| scientific configurations | 0 | 24 |

The run's own budget block reports engine `consumed_after = 12`: that is this trial's 6 plus 6 *reserved* for the still-open TRIAL-C2-NULL-BLOCKSHUF-1, not 12 executed. Calibration trial IDs count both preregistered nulls.

## Artifact sha256 (every downloaded file)

| file | sha256 |
|---|---|
| `benchmarks/fold1_fee0.001.json` | `9a80360677e184e4c83357bd2ebe14c216d3e2d28e721ac8a18701024dbbc438` |
| `benchmarks/fold1_fee0.001.log` | `e66f5d3bb193be0b767f2f28626d6fd8ca74e459259ed8205ef238eb05f2b1fd` |
| `benchmarks/fold1_fee0.002.json` | `dfa72361014672f90baea8afc2ed632c246581215c7dd227c28aceb03b9adbb8` |
| `benchmarks/fold1_fee0.002.log` | `175a1ef4032fd336b82468a1350d06e7b5453a650f9edac646ac7dd795603a37` |
| `benchmarks/fold2_fee0.001.json` | `d082ec2435dd20f53f0a0c927b2c9fb1f321cf7ef8772d78a0901d1ff7fa0b37` |
| `benchmarks/fold2_fee0.001.log` | `c5d63f28338e4c2c6eb89d3535c1d4166ac6b39267b165b31447dc6d7724ac6e` |
| `benchmarks/fold2_fee0.002.json` | `71543e12454aeae80978aafd9b7918e22637970fb09865aedbdfb9fc52f0be63` |
| `benchmarks/fold2_fee0.002.log` | `d6f09b0c0941f014c73c894e0dff8c1c837bd42e39a35e7dcfb3af2ab57e44ca` |
| `cycle2/backtest_fold1_cost_stress_eval_SELECTED_fee0.002.log` | `aa6fb0d45f831f480f44289145aeac013d17283a04142c4d0ecd4b8303523d53` |
| `cycle2/backtest_fold1_eval_SELECTED_fee0.001.log` | `caa16a29c493c8052337c516f3b1896e9cbeb7b8fb8f1dcc1cfcfa910e008844` |
| `cycle2/backtest_fold1_train_CFG1_fee0.001.log` | `5509a9d01123ecb8756488bc3d3a162202b34bd7d397b5ef6a57eeccd0f39346` |
| `cycle2/backtest_fold2_cost_stress_eval_SELECTED_fee0.002.log` | `3ee4edc707dc37b878c77ddd9aae806b514764c4828c72212042f30a47b0c35d` |
| `cycle2/backtest_fold2_eval_SELECTED_fee0.001.log` | `37edd6b675a88fd3e37eb14e2e6e8911f5dc49780d2026d5352c6afdc73fabe3` |
| `cycle2/backtest_fold2_train_CFG1_fee0.001.log` | `9363141cb8510b491debb03ac348e76e8f64d43673a535f54f7d3204c48b65bd` |
| `cycle2/backtest_results/fold1_cost_stress_eval_SELECTED_fee0.002.zip` | `390b2a90324c248f06adf9018ddd3860146e1347b2007dbe18b520c2e9ed8ccb` |
| `cycle2/backtest_results/fold1_eval_SELECTED_fee0.001.zip` | `df03462985179d17d5dc89018da1d7b7f55798edfe29e741c5533d6ac6e1cae9` |
| `cycle2/backtest_results/fold1_train_CFG1_fee0.001.zip` | `af6a6376b82fad5d4b68fd150fff85b3eac5b57b852c1b610d14592ce21c4cc8` |
| `cycle2/backtest_results/fold2_cost_stress_eval_SELECTED_fee0.002.zip` | `0544321d6aee0aaa962428fc8c9023bc68414798c364014ab33703ad2227728e` |
| `cycle2/backtest_results/fold2_eval_SELECTED_fee0.001.zip` | `b2e4b0a187391fdc35e29c16304496f8a6289567e05c8cf3b6b48ed69ed32232` |
| `cycle2/backtest_results/fold2_train_CFG1_fee0.001.zip` | `67d66ecf6427becc0169a7ab235d2e54d721d43493d71a5642fbf7c01773a2b6` |
| `cycle2/cycle2_run_summary.json` | `fa057f69801511f5b6b7dd65b4ca8e37acccee0d5b7951829365728dfc73da8d` |
| `cycle2/invocation_fold1_cost_stress_eval_SELECTED_fee0.002.json` | `5dd6ac50accd0b89a5a7137fcd50d91f61c7ce6c72ea9804fa52ade607f6d57d` |
| `cycle2/invocation_fold1_eval_SELECTED_fee0.001.json` | `d088648d0026410a6a33300a71407d67ab70e8c239cc60aa3f50b25630e5f288` |
| `cycle2/invocation_fold1_train_CFG1_fee0.001.json` | `9fd6e1958438c35b5e8ff36764f69563bd283a755e6e8afd61da219d5a90928e` |
| `cycle2/invocation_fold2_cost_stress_eval_SELECTED_fee0.002.json` | `b37e7fb04d35c933d1c80d3e405b7c2eca2b340d1ff900dfa24cbf93ff99a3f2` |
| `cycle2/invocation_fold2_eval_SELECTED_fee0.001.json` | `87883d4b877c9ccc5229eacfdac1d8dc0d4e256a73bd7286f5031b7f496f3b1f` |
| `cycle2/invocation_fold2_train_CFG1_fee0.001.json` | `9dd981a951ea0009a781addf7c72d094adfd0206c6294fe857c0cb1c1421e497` |
| `cycle2/metrics_fold1_cost_stress_eval_SELECTED_fee0.002.json` | `5f24e1a59bdfb89c2c35f63b37acbcf349d6f291c8a8d58a9ea301033a04bd78` |
| `cycle2/metrics_fold1_cost_stress_eval_SELECTED_fee0.002.md` | `5cbf62215eb09fc3b592819abcef895a6c0b77032fcbdd109538e6de509abccf` |
| `cycle2/metrics_fold1_eval_SELECTED_fee0.001.json` | `e3b45a539aa08dad877bbe06bb104dc899e803030464abaa4b6e7af668b431db` |
| `cycle2/metrics_fold1_eval_SELECTED_fee0.001.md` | `e79ee6eaef92f9a585a8a618edbc014cbaf91e4fff8e8f5d62ddce8681b70eff` |
| `cycle2/metrics_fold1_train_CFG1_fee0.001.json` | `ef075f02ac8296c7a48738f43976952c53fa6723a618592b356d52ae8572ced4` |
| `cycle2/metrics_fold1_train_CFG1_fee0.001.md` | `bee822873f34f80e06b99ac7d4ef24f7e201dcfbb42d171904250aa1fac00cac` |
| `cycle2/metrics_fold2_cost_stress_eval_SELECTED_fee0.002.json` | `8fe259b6b9a3c921f5d5e868351c51c50559863ce44e2901d41230859f271967` |
| `cycle2/metrics_fold2_cost_stress_eval_SELECTED_fee0.002.md` | `6c105b556e90ea89ec0c998aaefc9d29229e88655945e0e42ec90470a11e2158` |
| `cycle2/metrics_fold2_eval_SELECTED_fee0.001.json` | `530a01ab03a69cb62c199dd95edf0c2d0391d6f11c7eb139a1d10c3b41663fbf` |
| `cycle2/metrics_fold2_eval_SELECTED_fee0.001.md` | `46af51bad620511d1f77220d213d940fe7f8bb098e256595cbf84a00027dd894` |
| `cycle2/metrics_fold2_train_CFG1_fee0.001.json` | `729ca59910ae58f0bba1ed25405d14d5088a950e84e97214f98dc2a193605f02` |
| `cycle2/metrics_fold2_train_CFG1_fee0.001.md` | `9423ef12ed30a1149a08c46b3005e6237e6403afeb7a8f09fd8fabf8f683a468` |
| `cycle2_eval_windows.json` | `59eca09ffd7d81c5659f6c7d4e149131a5b75850e3d99a229b72fbe17dc9cd80` |
| `driver.log` | `013b1b5df519739315d5fbc7693623c42103ccf7fe9d566ed6aafdf7b5dad09c` |
| `funnel.log` | `70583c2231ad90dbf8cd28d9cbf5aeadc3e027225ed238e57fa676999b6c1626` |
| `funnel_result.json` | `860cc994010a2a29b0b8972735708220fa217610c95b1c25d527fc64bf515e29` |
| `lookahead_development.log` | `d17108406f90d53c036350fa0391baac7b7ee752bedf3cfe5328052343bcb8aa` |
| `paper_guard_with_candidate.log` | `c8954b8dc871639fe91265b5ad69b0ea2083a173193a5cef74a1045fcf57fdc8` |
| `recursive_development.log` | `d91dfb24c7961f23b096bb660603323439f91b8bcd8a50e1dd7f755c4fe257af` |
| `reproduction_identity.json` | `d2e52a108aaf1cc4430fd9b0e17239fab5d879f1a119c10370a11387a5aaf933` |
| `v4_dataset_lock_check.log` | `ce64a061c217d3caf78c27f9e062ef74d7ce664a982ab74a66f29036aec8b3b7` |
| `v7_warmup_join.json` | `a01311a5ebb27603b6d2c5ad01c00992c5043177822436809bfe4b7c6aa40765` |
| `v7_warmup_join.log` | `3e6dc5f7d3588e63ef748fee856599d01c93907380e0d99c622dd64d4d405f1a` |

