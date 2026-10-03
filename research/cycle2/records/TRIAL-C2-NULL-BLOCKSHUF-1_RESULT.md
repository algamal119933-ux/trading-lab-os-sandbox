# TRIAL-C2-NULL-BLOCKSHUF-1 — result record (CYCLE-2 UNIT 7.2 B2)

Durable copy of a GitHub Actions run whose artifact expires. Derived from the run's artifacts; the ledger record at seq 23 (digest `158bba771790e5e6b72941566d9e8a16b670341825f8f249ce3be27d9d036432`) is the authoritative terminal state.

## Run

| field | value |
|---|---|
| run | [37038822799](https://github.com/algamal119933-ux/trading-lab-os-sandbox/actions/runs/37038822799) |
| workflow | `.github/workflows/cycle2_research.yml` (workflow_dispatch, conclusion success) |
| head sha | `8654156db8bcbc8c38c1606b31d0121ac1035c1e` |
| preregistration | `research/cycle2/prereg/TRIAL-C2-NULL-BLOCKSHUF-1.json` (sha256 `9f8ceca4b0c750c6a1391b78e682d6a7e131b65e8766b75862721bcf4030f30f`) |
| funnel law | `research/cycle2/FUNNEL_LAW_1.md` (sha256 `5ad00f5ad79a192aac9454e5eb8a90f3ce787fc332e3467fdd9ecf969800468a`) |
| artifact | `cycle2-NullControlBlockShuffled` (zip digest `sha256:321f0cfd7c8258f8ccf1b2b0fb9cc0aeee17df04b433621354b251775d6fb72e`), expires 2026-11-01T17:12:29Z |
| ledger before / after | 23 records / 24 records, terminal at seq 23, verify() == [] |

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
| local reproduction of funnel_result.json | BYTE_IDENTICAL (sha256 cb2f602879a983ca0b9bd9f988bdc0188a240a41e7fc7b8ffa55dbf678c92ed7) |

## Engine invocations (6/6 executed, 6/6 engine_fee_propagation PROVEN)

| # | fold | phase | timerange | fee/side | engine_fee_propagation | status | return % | trades | max DD % |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | train_selection | 20210101-20221231 | 0.001 | PROVEN | OK | 3.386325 | 39 | 3.7770 |
| 2 | 1 | eval | 20230101-20231231 | 0.001 | PROVEN | OK | 4.223123 | 19 | 2.1106 |
| 3 | 1 | cost_stress_eval | 20230101-20231231 | 0.002 | PROVEN | OK | 3.844788 | 19 | 2.1876 |
| 4 | 2 | train_selection | 20210101-20231231 | 0.001 | PROVEN | OK | 7.737868 | 58 | 3.6574 |
| 5 | 2 | eval | 20240101-20241231 | 0.001 | PROVEN | OK | 2.401404 | 18 | 2.3293 |
| 6 | 2 | cost_stress_eval | 20240101-20241231 | 0.002 | PROVEN | OK | 2.051099 | 18 | 2.5013 |

selected config by fold: {"1": "CFG1", "2": "CFG1"} (single configuration CFG1).

## Walk-forward (L1/L2, base fee 0.001, EVAL folds)

| fold | strategy return % | passive (exposure-matched) % | excess % | trades | sample |
|---|---|---|---|---|---|
| 1 | 4.223123 | 31.058557 | -26.835435 | 19 | SUFFICIENT |
| 2 | 2.401404 | 23.973366 | -21.571962 | 18 | SUFFICIENT |

Σ excess = -48.407396 % → WALK_FORWARD = FAIL (excess over the exposure-matched passive < 0 in ALL folds → REJECTED).

Passive methodology: 20.00 of a 100.00 wallet invested for the whole window (20.00 each across 1 leg(s)), 80.00 held in cash; invested fraction 0.2000 = max_open_trades(2) x stake(10.0) capped at the wallet.

## Cost stress (L3)

| fee/side | Σ excess % | non-positive | fold-1 passive % | fold-2 passive % |
|---|---|---|---|---|
| 0.001 (base) | -48.407396 | True | 31.058557 | 23.973366 |
| 0.002 | -48.945878 | True | 30.956389 | 23.885375 |

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
| DSR | NOT_EVALUABLE | None | 0.95 | N = 2 (effective_trials 2) | cross-trial Sharpe variance is not estimable (fewer than 2 trial Sharpes, or all equal) while effective_trials=2 |
| PBO | NOT_EVALUABLE | None | 0.05 | effective_trials 1 | too few configurations for CSCV: 1 < 2 |

**PBO = NOT_EVALUABLE (single configuration); not a PBO validation.** PBO is NOT_EVALUABLE with a single configuration. This trial does not validate PBO; PBO's first real exercise is a multi-configuration trial.

MULTIPLE_TESTING = NOT_EVALUABLE (a multiple-testing statistic is NOT_EVALUABLE (never PASS)). It is not a FAIL and did not drive the verdict; the REJECTED result comes from WALK_FORWARD and COST_STRESS.

## Budget after this record

| budget | consumed by closed trials | cap |
|---|---|---|
| engine invocations | 12 | 120 |
| calibration trial IDs | 2 | 6 |
| scientific trial IDs | 0 | 12 |
| scientific configurations | 0 | 24 |

The run's own budget block reports engine `consumed_before = 6` (TRIAL-C2-NULL-MATCHFREQ-1, seq 22) and `consumed_after = 12` (that 6 plus this trial's 6, all executed; no open trial reserves anything). Calibration trial IDs count both preregistered nulls.

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
| `cycle2/backtest_fold1_cost_stress_eval_SELECTED_fee0.002.log` | `a032649cbd6815a8bd78eda855c1d5e183ed12761652f1004ac0372d7e7ed8f3` |
| `cycle2/backtest_fold1_eval_SELECTED_fee0.001.log` | `e18ea5aa8a71c8ee658ed671d1075458ef32ac14e5de4ef52e0335aa3656f4d8` |
| `cycle2/backtest_fold1_train_CFG1_fee0.001.log` | `f96522c8b7e63cff130797111c37dd84a656d4ffa5fe08ba17fd03560653bddb` |
| `cycle2/backtest_fold2_cost_stress_eval_SELECTED_fee0.002.log` | `8a10d7b403f14d7a51fa88d3f1a1b6d248e4bc697963f357efb2c567365d5769` |
| `cycle2/backtest_fold2_eval_SELECTED_fee0.001.log` | `84390ff19bead9633d1496e9920b4938cd87a1b16b126cd6414a6149e8ef182a` |
| `cycle2/backtest_fold2_train_CFG1_fee0.001.log` | `62c13642983ddc1f2b72b80c3bf9af463ec4021bfec6d396dc93ea549be2ca29` |
| `cycle2/backtest_results/fold1_cost_stress_eval_SELECTED_fee0.002.zip` | `ba740a3bccc2ff4f8ab1e378e646c507c6a9473921459115244f5550c230ae91` |
| `cycle2/backtest_results/fold1_eval_SELECTED_fee0.001.zip` | `40b2c846b844c25d515c6cfec78fb6de95f86f6701795a3b9ad3228252e06264` |
| `cycle2/backtest_results/fold1_train_CFG1_fee0.001.zip` | `3b15e9d1104923da7ce27e3b4645266e4590a0675de1bb74e4d8e6fec55521b0` |
| `cycle2/backtest_results/fold2_cost_stress_eval_SELECTED_fee0.002.zip` | `1d2da879e309bc5594f862cc009d5842187440d90d55ff8b0c4e5a29796b6a68` |
| `cycle2/backtest_results/fold2_eval_SELECTED_fee0.001.zip` | `6d41828a5c3749b970b499f228ba2ef509718c876166467a7bb1633071f6727b` |
| `cycle2/backtest_results/fold2_train_CFG1_fee0.001.zip` | `76fdffe5c43f8fcbda4e77481425f4e5bc5acd869bcda73eafa53aa7e0c00fb1` |
| `cycle2/cycle2_run_summary.json` | `35e4155a26db0610b7042045e1c3eefe508824630d112220ab81b2eefddcd2af` |
| `cycle2/invocation_fold1_cost_stress_eval_SELECTED_fee0.002.json` | `c437078627dc3b348e18570086fbee504d80852413b0639398df5cff324e67a3` |
| `cycle2/invocation_fold1_eval_SELECTED_fee0.001.json` | `4928c5de2fcca0f063b6160dbf2bfd9414486d57ace03730ab1e342ee1caee5c` |
| `cycle2/invocation_fold1_train_CFG1_fee0.001.json` | `2c4d9c2e2078a51cb066cf655b4fac6a33947ce31f082e59c168df5d982150e2` |
| `cycle2/invocation_fold2_cost_stress_eval_SELECTED_fee0.002.json` | `4733e64d145063d48c92e48fa476a2cca9106f815798159aa943adf0359150f2` |
| `cycle2/invocation_fold2_eval_SELECTED_fee0.001.json` | `bcd8b6e2ce53684a2ebbed37363a96c9937e190c3aea90aa6e5ca226ba6b7254` |
| `cycle2/invocation_fold2_train_CFG1_fee0.001.json` | `e3b975f97c8ccb4e2ce605ce2f64875536fd558e9356353be1d4dc73e765ff68` |
| `cycle2/metrics_fold1_cost_stress_eval_SELECTED_fee0.002.json` | `3e7ceeae906aa70a66c80918f485c1b4b46905bb0e9703d3b2700244202b03fe` |
| `cycle2/metrics_fold1_cost_stress_eval_SELECTED_fee0.002.md` | `27fbe9d2f7d25e04cbceb7b145bbc6fb9d9a82ebee054c934801bf34129941f0` |
| `cycle2/metrics_fold1_eval_SELECTED_fee0.001.json` | `14b4049e86d27dd29b8a9ec512b36beb28db6c306b2489c763f41f089b93d1a7` |
| `cycle2/metrics_fold1_eval_SELECTED_fee0.001.md` | `4020db890e33ee86dcd273e2db08f6d550f739ad9d9318b486fe61a5098f76a9` |
| `cycle2/metrics_fold1_train_CFG1_fee0.001.json` | `f48539fa117249a6cdb98ee748733fc10e51331adef0092fabb79bf5a646017f` |
| `cycle2/metrics_fold1_train_CFG1_fee0.001.md` | `62745ea3fb055b572e730a2b317ae0dbe63af167b0938221d9eab29346824293` |
| `cycle2/metrics_fold2_cost_stress_eval_SELECTED_fee0.002.json` | `af43ce66f14ec54c712aa3279ec7d44c61c7e7694abceb76ec22644d3383cb11` |
| `cycle2/metrics_fold2_cost_stress_eval_SELECTED_fee0.002.md` | `17cbf9ed8de7be118914088e333d72276e93e4159b297f420dc2e10b584c9f88` |
| `cycle2/metrics_fold2_eval_SELECTED_fee0.001.json` | `34c64094cfb1d793e62759cc4115448fcd258b62f41ae93d420a87632f0c0409` |
| `cycle2/metrics_fold2_eval_SELECTED_fee0.001.md` | `93a47cf6c218e0e48e7070d762f4be42c4dc7ce452e5752ea6ed5c843d3791bf` |
| `cycle2/metrics_fold2_train_CFG1_fee0.001.json` | `a838ac09ecf1eeb3aa5c57b53958fe675b30f6b2c5e487a6dfb8bd65a0eb6309` |
| `cycle2/metrics_fold2_train_CFG1_fee0.001.md` | `d84743cf794a12f0133ad6d62a204efbc84ddd4e1c7b9d6fffc3ef40e905e3f1` |
| `cycle2_eval_windows.json` | `59eca09ffd7d81c5659f6c7d4e149131a5b75850e3d99a229b72fbe17dc9cd80` |
| `driver.log` | `3e71fa0a9d6a477331c553a9186f6ddb1415d02f5e80eafaeec3c32fb20d0b94` |
| `funnel.log` | `189e449170dbfc347ff30170bb270860dea5d0e5adc2c0c1493559eaa054fc5e` |
| `funnel_result.json` | `cb2f602879a983ca0b9bd9f988bdc0188a240a41e7fc7b8ffa55dbf678c92ed7` |
| `lookahead_development.log` | `c8f29421b000e22ae9c9e68ada3938b56519c40f89aaee26be47c5f13dd1bc5c` |
| `paper_guard_with_candidate.log` | `c8954b8dc871639fe91265b5ad69b0ea2083a173193a5cef74a1045fcf57fdc8` |
| `recursive_development.log` | `06b3ecc1961cd195027981b0003663e0aa171493d6e86a83be7c7aba6ed7e7e0` |
| `reproduction_identity.json` | `fa0bcc21f6777c44e6b7b6aea807bb811ad3203ba1c42b1abf2d3192fd1af0c0` |
| `v4_dataset_lock_check.log` | `ce64a061c217d3caf78c27f9e062ef74d7ce664a982ab74a66f29036aec8b3b7` |
| `v7_warmup_join.json` | `a01311a5ebb27603b6d2c5ad01c00992c5043177822436809bfe4b7c6aa40765` |
| `v7_warmup_join.log` | `3e6dc5f7d3588e63ef748fee856599d01c93907380e0d99c622dd64d4d405f1a` |

