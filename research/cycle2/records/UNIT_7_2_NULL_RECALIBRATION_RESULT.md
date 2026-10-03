# CYCLE-2 UNIT 7.2 — null recalibration result

Summary of the two Cycle-2 null-calibration trials required by OFFLINE-RESEARCH-CYCLE-2-OPENING-1 §7.2 and
Master Plan §12. Both were judged by the frozen funnel law `research/cycle2/FUNNEL_LAW_1.md`
(sha256 `5ad00f5ad79a192aac9454e5eb8a90f3ce787fc332e3467fdd9ecf969800468a`). The ledger records named below
are the authoritative terminal states. This record restates their outcomes and changes none of them.

## Trials

| trial | run | head sha | ledger terminal | funnel_result | rejected_by | integrity gates | engine_fee_propagation |
|---|---|---|---|---|---|---|---|
| TRIAL-C2-NULL-MATCHFREQ-1 | [37032878568](https://github.com/algamal119933-ux/trading-lab-os-sandbox/actions/runs/37032878568) | `31c26b6` | **REJECTED**, seq 22 (`a77340a0…cf12`) | REJECTED | COST_STRESS, WALK_FORWARD | DATA_TRUTH, LOOKAHEAD, RECURSIVE, LEDGER_CHAIN = PASS | 6/6 PROVEN |
| TRIAL-C2-NULL-BLOCKSHUF-1 | [37038822799](https://github.com/algamal119933-ux/trading-lab-os-sandbox/actions/runs/37038822799) | `8654156` | **REJECTED**, seq 23 (`158bba77…6432`) | REJECTED | COST_STRESS, WALK_FORWARD | DATA_TRUTH, LOOKAHEAD, RECURSIVE, LEDGER_CHAIN = PASS | 6/6 PROVEN |

Both `funnel_result.json` files were reproduced locally byte-identical from the downloaded artifacts. Their durable
copies are `research/cycle2/records/<trial>_funnel_result.json`, and the full results are in `<trial>_RESULT.md`.

## Per-fold excess (base fee 0.001, EVAL folds)

| trial | fold | strategy % | passive (exposure-matched) % | excess % | trades |
|---|---|---|---|---|---|
| MATCHFREQ-1 | 1 (2023) | 7.510575 | 31.058557 | -23.547982 | 17 |
| MATCHFREQ-1 | 2 (2024) | 0.958608 | 23.973366 | -23.014758 | 19 |
| BLOCKSHUF-1 | 1 (2023) | 4.223123 | 31.058557 | -26.835435 | 19 |
| BLOCKSHUF-1 | 2 (2024) | 2.401404 | 23.973366 | -21.571962 | 18 |

Σ excess: MATCHFREQ-1 -46.562740 (stress fee 0.002: -47.082309) · BLOCKSHUF-1 -48.407396 (stress fee 0.002: -48.945878).
Sample evidence: SUFFICIENT for both.

## Verdict

**7.2 NULL_RECALIBRATION = PASS; funnel rejects the two existing no-edge controls in the 2023/2024 EVAL windows under FUNNEL_LAW_1**

Both nulls were REJECTED with every integrity gate PASS, so each per-trial calibration verdict = PASS and
cycle2_stop = NO.

PBO and DSR were NOT_EVALUABLE for both single-configuration nulls; the null controls do not validate PBO or DSR. Known benchmark bias (whole-window exposure) as disclosed in FUNNEL_LAW_1.

## Budget after 7.2

engine 12/120 · CAL 2/6 · SCI 0/12 · configs 0/24

## Authority

This record authorizes nothing. 7.3 (Trend lineage trials) needs its own Owner GO.
