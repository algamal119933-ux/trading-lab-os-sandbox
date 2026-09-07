# TL-FP-BOOT-1 v2.0 — adoption, corrections, and the activation block

**Directive:** `TRADING_LAB_OS_TL_FP_BOOT1_v2.0_FINAL_20260907.md`
**Branch:** `claude/new-session-pvkkbj` — the parked FP scaffold
**Classification (directive §1.3):** `FP-BOOT-1 PREPARATORY SCAFFOLD / PARKED / NON-AUTHORITATIVE UNTIL RECONCILED`

```text
TL_FP_BOOT_1 = BLOCKED — section 3.1 DONE, section 3.2 outstanding
BASELINE_CLOSURE_ANCESTOR = YES (1dfb696 -> origin/main 07f957c)
BENCHMARK_CLOSURE_MERGED  = NO
ENTRY_STATE = NOT_AUTHORITATIVE
FP_INFRASTRUCTURE_SCAFFOLD_VALIDATION = PASS
FP_RUNTIME_READINESS = NOT_PROVEN
DATASET_V2_REACQUIRED = NO
REAL_MONEY_AUTHORIZED = NO
```

## What v2.0 supersedes

For the next stage only, v2.0 supersedes
`TRADING_LAB_OS_FP_BOOT1_AND_FP_RUN_v1.1_FINAL_2026-09-07.md`, which is what
[`FP_BOOT_1_ENTRY_STATE.md`](FP_BOOT_1_ENTRY_STATE.md) and
[`FP_BOOT_1_CLOSURE.md`](FP_BOOT_1_CLOSURE.md) were written against. Those two
documents are kept as the record of what was determined under v1.1 and are
**not** rewritten to look like they always agreed with v2.0; the corrections are
recorded here instead.

## Three corrections v2.0 forces

### 1. Dataset V2 was already acquired and frozen. Do not reacquire it.

The v1.1 closure recommended, as the one next step needing no owner decision,
*"acquire Dataset V2 via the existing dataset-v2.yml workflow."*

**That was wrong, and v2.0 §2 prohibits it outright:** `DO NOT REACQUIRE
DATASET V2`, and specifically *"do not run `dataset-v2.yml` merely because a
stale branch says `pending_acquisition`."*

The `pending_acquisition` lock on this branch is the pre-acquisition stub
inherited from `main` at `9825541`. The authoritative lock lives in the
BASELINE-1 closure lineage and is fully frozen:

| | |
| --- | --- |
| `status` | `frozen` |
| Content digests | 4 × `CANONICAL_CANDLE_V1` + 4 raw Feather hashes, BTC/ETH at 1h and 5m |
| Structural integrity | `PASS` — 0 duplicates, 0 off-grid timestamps, 0 NaN cells, 0 invalid OHLC rows |
| 5m → 1h reconciliation | `PASS` — 50,374 buckets, 0 mismatches |
| Development window | closed — protocol `PASS`, performance `NEUTRAL` |
| Validation window | **spent** — run once on 2026-09-07, unchanged, not reusable for tuning |

Running the acquisition workflow would have produced a second set of
authoritative hashes and a provenance fork, which is exactly the harm §2 names.
The recommendation is withdrawn.

Consequence for tooling: `research/fp/admission.py` read fingerprints only from
a `files` key, which the authoritative lock does not use — it keys them
`canonical_hashes` and `raw_file_hashes`. Left alone, the evaluator would have
reported a fully audited, frozen dataset as having **zero** fingerprints and
blocked on real evidence. `dataset_v2_fingerprints()` now reads all three
layouts, preferring the canonical digests, and is verified against both the
authoritative lock (4 fingerprints) and the stub (0).

### 2. BASELINE-1 has run. The v1.1 entry-state document says otherwise.

`FP_BOOT_1_ENTRY_STATE.md` states that BASELINE-1 "has never been run". That was
true of `main` and of this branch, and false of the project. In the closure
lineage BASELINE-1 completed **both** protocol windows:

| Window | Return | Exposure-matched passive | Excess | Max DD | Trades |
| --- | --- | --- | --- | --- | --- |
| Development `20210101-20250101` | +27.80 % | +29.18 % | **−1.38 pp** | 11.67 % | 211 |
| Validation `20250101-20260901` | −0.07 % | −2.03 % | **+1.97 pp** | 9.41 % | 96 |

Lookahead analysis: no bias over 20 signals. Recursive analysis: no bias, drift
0.000 % / −0.003 % at 600 startup candles. Classification
`BASELINE_PROTOCOL = PASS`, `BASELINE_PERFORMANCE = NEUTRAL`,
`DURABLE_ALPHA = NOT_PROVEN` — the reference roughly reproduces the return of
the exposure it takes, which is a legitimate result for a reference point.

None of this changes the admission verdict, because none of it is a *survivor*.

### 3. This branch's `ENTRY_STATE = C` is not authoritative.

v2.0 §7: *"Do not inherit the earlier scaffold branch's temporary
`ENTRY_STATE=C`. Recompute from actual benchmark closure."*

The evaluator no longer emits a bare `C`. While the BASELINE-1 lineage is
unmerged it emits `NOT_AUTHORITATIVE`, and it flips by itself once the merge
lands, because the ancestry is checked with `git merge-base --is-ancestor`
rather than asserted.

## §3.1 — BASELINE lineage merge: COMPLETE

Merged on owner authorisation.
[PR #3](https://github.com/algamal119933-ux/trading-lab-os-sandbox/pull/3) —
*BASELINE-1 evaluation and Dataset V2 acquisition*.

All seven steps of §3.1 verified, not assumed:

| § | Step | Evidence |
| --- | --- | --- |
| 3.1.1 | merged into `main` with a normal merge commit | `07f957c`, two parents |
| 3.1.2 | not squashed | parents are `9825541` **and** `1dfb696`; a squash has one |
| 3.1.3 | not rebased | `1dfb696` retains its original SHA as the second parent |
| 3.1.4 | `1dfb696…` not rewritten | present verbatim in `git log origin/main` |
| 3.1.5 | ancestry proof | `git merge-base --is-ancestor 1dfb696 origin/main` → **exit 0** |
| 3.1.6 | merged-main CI green | run 34108300025 on `07f957c` — **success** |
| 3.1.7 | frozen artifacts unchanged | every blob hash identical across the merge (below) |

Step 7 was checked by comparing git blob object IDs before and after the merge,
which is a byte-identity test rather than a diff of rendered content:

```text
05c72ab  research/datasets/dataset_v2.lock.json
33ce9e4  research/datasets/dataset_v1.lock.json
2a95e5e  research/records/baseline1_development_datasetv2.json
d17b72e  research/records/baseline1_validation_datasetv2.json
1082eb0  freqtrade/user_data/strategies/BaselineEmaRegimeV1.py
922d651  freqtrade/user_data/config.paper.json.example
ARTIFACT_INTEGRITY = PASS
```

Dataset V2 Validation is now **spent** on authoritative `main` and must never
again be described as pristine OOS.

## §3.2 — benchmark closure: OUTSTANDING

`main` carries no `research/external/` artifacts, so
`BENCHMARK_CLOSURE = NOT_MERGED`. §3 is explicit that *"only that merged main is
authoritative for FP-BOOT entry-state determination"*, so passing §3.1 alone
does **not** make any entry state binding.

The evaluator models this rather than collapsing it. `benchmark_closure_state()`
distinguishes three states, because reading a pre-registered scorecard as a
closed one would let an unexecuted sprint satisfy §3.2:

| State | Meaning |
| --- | --- |
| `NOT_MERGED` | the sprint's artifacts are not on `main` at all — **current state** |
| `MERGED_NOT_EXECUTED` | registry present, scorecard carries no experiment rows |
| `CLOSED` | scorecard carries at least one row |

`entry_state` stays `NOT_AUTHORITATIVE` until §3.1 **and** §3.2 are both on
`main`. Both are checked with git, so each flips by itself when its merge lands
— condition 18 already did exactly that when PR #3 merged, with no edit to any
committed record.

## What changed in the scaffold under v2.0

| Area | v1.1 | v2.0 | Effect here |
| --- | --- | --- | --- |
| Admission gate | 14 conditions (§5) | **18** conditions (§9) | leverage / futures / margin / shorts split into four rows with distinct evidence; condition 18 "no unresolved P0 project-integrity issue" added |
| Condition 18 | — | new | implemented as a real `git merge-base --is-ancestor` check; currently `FAIL` |
| Preflight | 12 checks (§12) | **16** checks (§16) | dry-run split from Spot; clock tolerance, evidence persistence and a pre-T0 restart drill added |
| Input ledger check | "works" | "works **on real incoming data**" | demoted `PASS` → `UNPROVEN`: every candle in the sample is synthetic |
| Replay check | "bounded sample" | "bounded **real-data** sample" | demoted `PASS` → `UNPROVEN`, same reason |
| Verdicts reported | one | two (§1.3) | `FP_INFRASTRUCTURE_SCAFFOLD_VALIDATION` kept separate from `FP_RUNTIME_READINESS` |
| EMA parity meaning | stated in prose | bounded (§14) | `EMA_PARITY_MEANING` / `EMA_PARITY_DOES_NOT_PROVE` are now module constants the report must carry |
| Override flags | grep of the source | behavioural | the four named flags are rejected through the CLI, and six environment variables are proven unable to flip the verdict |

Two checks that previously reported `PASS` now report `UNPROVEN`. That is the
point: v2.0 §1.3 says the scaffold's evidence *"is useful infrastructure
evidence, not project-state authority"*, and a synthetic candle cannot satisfy a
requirement that says real.

The scaffold mechanisms are still validated, and each now reports its own
verdict instead of having one inferred from its prose:

```text
mechanism_input_ledger       = PASS
mechanism_decision_ledger    = PASS
mechanism_event_time_replay  = PASS
mechanism_persistence        = PASS      (ledgers reopened from disk by fresh readers)
mechanism_restart            = PASS      (restarted writer resumes the chain, no duplicate decision)
```

## What was deliberately not done

* **`dataset-v2.yml` was not run**, per §2. `DATASET_V2_REACQUISITION_AUTHORIZED = NO`.
* **No conflict in `MANIFEST.txt`, `tests/conftest.py` or `.github/workflows/ci.yml`
  was resolved**, per §4: resolving them against a stale `main` would mean
  solving them twice against different project truths.
* **`claude/fp-boot-1-integration` was not created**, per §4: it must be cut from
  a `main` that carries **both** BASELINE-1 and benchmark closure. It now carries
  only the first.
* **`main` was not merged into this branch.** §4 defers that until the benchmark
  lineage is authoritative, so the scaffold stays behind `main` on purpose. The
  CI anti-fork guard was changed to compare the Dataset V2 lock against the
  *merge base* rather than main's tip, so being behind reads as behind and only
  an independent edit reads as a fork.
* **Nothing on `claude/new-session-140zbb` was touched.**
* **No `T0`, no cohort, no admission.**

---

`PAPER / RESEARCH ONLY`
`REAL_MONEY_AUTHORIZED = NO`
