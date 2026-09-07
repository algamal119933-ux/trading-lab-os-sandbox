# TL-FP-BOOT-1 v2.0 — adoption, corrections, and the activation block

**Directive:** `TRADING_LAB_OS_TL_FP_BOOT1_v2.0_FINAL_20260907.md`
**Branch:** `claude/new-session-pvkkbj` — the parked FP scaffold
**Classification (directive §1.3):** `FP-BOOT-1 PREPARATORY SCAFFOLD / PARKED / NON-AUTHORITATIVE UNTIL RECONCILED`

```text
TL_FP_BOOT_1 = BLOCKED — authoritative lineage not consolidated
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

## Activation status — §3.1

```text
BASELINE_CLOSURE_COMMIT   = 1dfb69604bb87856b75c8c90957f2acc8e1fab7f
ANCESTOR_OF_ORIGIN_MAIN   = NO
origin/main               = 9825541
```

§3.1: *"If this proof fails: `TL-FP-BOOT-1 = BLOCKED`."* It fails. Everything
downstream — benchmark execution, scaffold integration, entry-state
recomputation, admission, `T0` — is gated behind it.

The merge itself is ready and waiting, not blocked on any work:

* **PR #3** — [BASELINE-1 evaluation and Dataset V2 acquisition](https://github.com/algamal119933-ux/trading-lab-os-sandbox/pull/3)
* head `1dfb696`, base `9825541`, `mergeable_state: clean`, `main` is an ancestor
* CI green on `1dfb696` (run 34077889259)

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
  an authoritative `main` that does not yet exist.
* **Nothing on `claude/new-session-140zbb` was touched.**
* **No `T0`, no cohort, no admission.**

---

`PAPER / RESEARCH ONLY`
`REAL_MONEY_AUTHORIZED = NO`
