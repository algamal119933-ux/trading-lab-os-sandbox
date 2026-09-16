# P2 — PROSPECTIVE PAPER PROOF

**This file is the P2 single source of truth.** Every other document points here;
none of them restates what is written here. Where an older document disagrees
with this one about P2, this one governs.

**Authority:** the Owner's P2 Governance and Pre-T0 Build Contract, materialized
here and made authoritative by Owner merge. A document is not authority until it
is on `main` by a normal two-parent merge the Owner performed.

**Entry:** `P1 — HOST RECONSTITUTION`, `CLOSED / PASS`
([`../p1/P1_CLOSURE.md`](../p1/P1_CLOSURE.md)).

```text
PAPER / RESEARCH ONLY
REAL_MONEY_AUTHORIZED = NO
```

---

## 1. Execution model

```text
OWNER
 → Ubuntu terminal                    the operator surface
 → Claude Code                        the SOLE writer and executor
 → this contract + the frozen stage records
 → implementation / runtime
 → deterministic and adversarial gates
 → clean-checkout reproducibility
 → runtime and evidence provenance
 → branch → PR → GitHub CI
 → OWNER MERGE
 → re-ground on merged main → resume the SAME stage
 → P2 closure

CliDeck   role = NONE
Codex     role = NONE
```

No substitute AI verifier or orchestrator replaces either. P2's verification
basis is the same one P1 closed on: deterministic tests, adversarial negative
controls, clean-checkout parity, hash-chained runtime evidence and its replay,
reconciliation, schema conditionals, Dataset V2's lock gate, the paper guard,
`verify_repo` and `MANIFEST.txt` byte-identity, git ancestry proved with
`merge-base --is-ancestor` rather than asserted, and GitHub CI. Every one of
those is reproducible by a later reader without asking any model what it thought.

**Fail-closed is the default.** A gate that cannot establish its fact reports
`UNPROVEN`, and `UNPROVEN` blocks exactly as `FAIL` does. No override flag exists
anywhere in the gate set, and a test asserts that none appears.

---

## 2. Purpose, and the limit of what P2 can prove

```text
P2 = PROSPECTIVE PAPER PROOF
Proof target for FP-CONTROL-2:  PAPER_TRADING_OPERATIONAL_CAPABILITY
```

`FP-CONTROL-2` is a **control** — BASELINE-1 operated as an operational control.
It is not a candidate, not a survivor, and not candidate-quality evidence. That
is settled law in three places already on `main`: the activation pack's §0, the
S19 capture-loop record's §6, and the FP-CONTROL-1 closure record.

```text
For EVERY lawful P2 outcome:   PROSPECTIVE_PAPER_EDGE = NOT_EVALUATED
```

P2 measures a prospective window and records what it measures. It does not
convert those measurements into an edge claim, and no P2 outcome — favourable or
unfavourable — may be reported as one. A prospective edge requires an
`FP-CANDIDATE-*` row, which requires a paper-admissible survivor; `entry_state`
is `C` and `PAPER_ADMISSION` is `BLOCKED`.

**Not opened by this contract:** candidate research, the parked
`19d7d7e` strategy-source branch, FreqAI, Qlib, RD-Agent, Hummingbot, Condor,
NautilusTrader, operational hardening beyond the durability tiers of §8, Paper
Beta acceptance, controlled-live readiness, live trading, real money.

---

## 3. Operational-capability provenance

Twelve properties make `PAPER_TRADING_OPERATIONAL_CAPABILITY = PROVEN`:

```text
real market input · event-time/timestamp knowability · paper-only authority ·
decision logging · risk/admission · paper order/fill · position state ·
persistence · restart recovery · no duplicate execution · ledger reconciliation ·
data integrity
```

Nine of the twelve can be evidenced without a trade having happened; three
cannot. `research/fp/capability.py` is that split made executable, and it is the
only place the model is stated — every schema, tool, test and record derives
from it rather than restating it.

```text
S3, lane L1, pre-T0     the NINE pre-T0 qualifiable properties, at Mq
                        real market input · event-time/timestamp knowability ·
                        paper-only authority · decision logging · risk/admission ·
                        persistence · restart recovery · ledger reconciliation ·
                        data integrity
L2, post-T0, credited   the THREE lifecycle properties
                        paper order/fill · position state · no duplicate execution

P2 PASS requires the aggregate:  9 + 3 = 12 / 12
```

**`FULL_TRADE_LIFECYCLE` is not one of the twelve.** It is the completed
entry→fill→position→exit→realised-PnL chain, reported as its own status
alongside the capability verdict — the activation pack reports it separately and
the registry schema gives it its own enum. An earlier revision of this section
described the split as "eight non-lifecycle" plus "four lifecycle", counting the
aggregate as the fourth. That does not close: twelve minus three is nine, and
folding the aggregate into the count would let a cohort reach `12/12` while a
genuine property went unevidenced, with the aggregate standing in for it. It
would also collapse the one distinction `P2 INCONCLUSIVE / INSUFFICIENT`
depends on — a quiet window can leave the lifecycle unobserved with every
capability intact, and that outcome is only expressible if the two are counted
separately.

P1 evidenced the pre-T0 nine at commit `4543d4c3`. **That is not carried forward
as the sole current proof.** `main` has advanced since, and this contract will
advance it further. The nine are therefore **re-established during S3 against the
current P2 source and runtime**.

**No pre-T0 record may be presented as prospective lifecycle evidence.** L1
proves that the machinery works at the P2 commit. It proves nothing about a
forward window, and its records carry `t0_relation = T0_NOT_FROZEN` so they can
never be mistaken for records that do.

---

## 4. Lane model

The registry declares exactly one `evidence_dir` per role and the role enum is
closed, so all three lanes occupy `freqtrade/user_data/fp-control-2/` at
different times. Separation is by archival and by the identity stamped on every
record — never by path.

| | Lane | Purpose | Credited? |
| --- | --- | --- | --- |
| **L0** | retained P1 qualification lane | history | **never** |
| **L1** | fresh disposable pre-T0 qualification lane, S3 | prove the pre-T0 nine at Mq | **never** |
| **L2** | fresh authoritative post-T0 cohort lane | the cohort | **the only lane that may be** |

```text
ARCHIVE THE WHOLE LANE, always:  evidence/ · logs/ · tradesv3.sqlite ·
                                 capture_runtime.json · the lock file
DESTINATION                      artifacts/<name>/ — gitignored, and outside
                                 freqtrade/user_data/, which is the only host
                                 tree any container mounts
NEVER CARRIED BETWEEN LANES      wallet state · position state · the database ·
                                 ledgers · warm-up state · elapsed-time credit
```

Archiving only `evidence/` would carry pre-T0 wallet and position state into a
post-T0 cohort through `tradesv3.sqlite`. The whole lane moves, or nothing does.

### Why a record from one lane cannot be credited to another

1. Every record carries `role`, `cohort_id`, `source_commit`, `run_id`,
   `runtime_id`, `restart_counter` and `t0_relation`. L0 and L1 carry
   `cohort_id: null` and `T0_NOT_FROZEN`; L2 carries the frozen cohort id.
2. `research/fp/preflight.py` check 5 **fails** if the attached lane holds any
   cohort id the registry does not declare for that role. A stray L0 or L1
   record inside L2 is detected, not merely discouraged.
3. `research/fp/reconcile.py` fails on more than one stamped commit, and
   `record_role_binding` fails on any foreign role.
4. Archives live outside the only mounted host tree, and `lane.resolve_lane`
   refuses any lane root resolving outside canonical `user_data`, so an archive
   can never become a lane.
5. The archival tool refuses to return a lane that is not empty, and
   `freeze_t0` refuses if the declared `evidence_dir` holds any ledger record.

### Crediting law

```text
A record is PROSPECTIVELY CREDITED if and only if ALL of:
    lane L2 · role FP-CONTROL-2 · cohort_id == the frozen id ·
    source_commit == M2 · t0_relation == POST_T0 · bar_class == LIVE ·
    chain verifies from genesis · not an erratum

Anything failing any clause is CONTEXTUAL. Contextual evidence is never
credited and never deleted.
```

`bar_class` is decided by `capture.classify_bar`: `LIVE` only when the bar closed
within one candle period of the decision. A bar recovered by backfill is
`WARMUP`, and its admission is `WARMUP_NOT_EXECUTABLE`.

| `t0_relation` + `bar_class` | Meaning | Disposition |
| --- | --- | --- |
| `POST_T0` + `LIVE` | the cohort's prospective evidence | **credited** |
| `PRE_T0` + `WARMUP` | normal warm-up before T0 | contextual |
| `POST_T0` + `WARMUP` | a **continuity gap** — closed after T0, recovered by backfill rather than observed live | contextual, **counted and reported** |
| `PRE_T0` + `LIVE` | impossible on a fresh lane; asserted absent at activation | defect |
| `T0_NOT_FROZEN` + anything | an L0/L1 record; the lane was not fresh | defect |

---

## 5. Source-commit model

A commit cannot contain its own hash, so no model that declares *the commit the
runtime runs at* terminates. This one declares a commit that already exists and
then **proves** the runtime's commit equivalent to it.

```text
Mq   the commit at which the runtime-attached pre-T0 gates actually passed (S3)
M1   merged main carrying the S3b binding — the authoritative pre-freeze main
M2   merged main carrying the T0 freeze — the cohort's actual runtime commit
M3   merged main carrying the activation record, created while the cohort is
     already running at M2

DECLARED   runtime_identity.source_commit := M1      the frozen CODE identity
STAMPED    every L2 record carries M2, read from git HEAD by the launcher, which
           refuses to start on a dirty tree so the stamp cannot be false
REQUIRED   SEMANTIC_IDENTITY(Mq) == SEMANTIC_IDENTITY(M1) == SEMANTIC_IDENTITY(M2)
VERIFIED   reconcile --source-commit M2 --require-pass, plus the new finding
           registry_source_commit_equivalence
SCHEMA     unchanged. No runtime_commit field is added.
```

Declaring the merged main immediately preceding the freeze matches the
FP-CONTROL-1 precedent exactly — its `source_commit` `4b0d7f6` is the merge
commit whose registry still reads `NOT_STARTED / null / null`, and the freeze
commit `6d5d27c` is its child. What is new is that the declaration is now
**checked**. Until now nothing compared it to anything, which is the same class
of defect P1 closed one level down.

### SEMANTIC_IDENTITY

```text
SEMANTIC_IDENTITY(c) = ( RUNTIME_TREE(c), REGISTRY_SEMANTICS(c) )

RUNTIME_TREE(c)   git object ids at c — byte identity, not a textual diff — for:
                    freqtrade/user_data/strategies/
                    freqtrade/user_data/config.paper.json.example
                    research/fp/*.py            (research/fp/records/ EXCLUDED)
                    scripts/*.py  scripts/*.sh
                    docker-compose.yml  docker-compose.fp.yml
                    monitoring/exporter/

REGISTRY_SEMANTICS(c)  the FP-CONTROL-2 runtime_identity at c, excluding the
                  fields that are observations or freeze bookkeeping:
    EXCLUDED  source_commit · image_digest · python_version · t0_utc ·
              cohort_id · status · closed_utc · closure_reason · outcome ·
              change_log · registry_updated_utc · fp_run_active
    INCLUDED  candidate_family · strategy_sha256 · config_sha256 ·
              engine_version · pairs · timeframe · detail_timeframe ·
              fee_model · sizing · max_open_trades · order_policy ·
              feature_sources · paper_fill_model_version ·
              environment_variable_allowlist · bot_name · db_path · log_path ·
              evidence_dir · wallet
```

`image_digest` and `python_version` are observations of a runtime, not
instructions to one. Excluding them applies the existing model rather than
inventing a licence: FP-CONTROL-1's own first `change_log` entry binds exactly
those fields as class `O`, *"observability only — no trading semantics are
changed."*

---

## 6. The T0 Git transaction

### What the freeze candidate may change

```text
EXACTLY TWO FILES:
  research/fp/records/forward_paper_cohort_registry.json
  MANIFEST.txt

INSIDE THE REGISTRY, EXACTLY THESE SEVEN VALUES:
  instances[FP-CONTROL-2].t0_utc                          null → <T0>
  instances[FP-CONTROL-2].cohort_id                       null → FP-CONTROL-2-<stamp>
  instances[FP-CONTROL-2].status                          NOT_STARTED → RUNNING
  instances[FP-CONTROL-2].runtime_identity.source_commit  null → M1
  instances[FP-CONTROL-2].change_log                      [] → [ one class-O entry ]
  registry.fp_run_active                                  false → true
  registry.registry_updated_utc                           bumped

FORBIDDEN: any code, test, doc or CI file; any other registry field; any other
instance row. The FP-CONTROL-1 row must remain byte-identical.
```

Two files is not a stylistic preference. It makes the equivalence proof total
and reviewable in one line: `git diff --name-only M1 M2` must equal exactly that
pair.

```text
cohort_id = role + "-" + t0_utc with ":" and "-" removed
            precedent: 2026-09-08T12:15:13Z → FP-CONTROL-1-20260908T121513Z
            already an executable test, tests/test_fp_admission.py
```

### T0 authority is a merged record, never a secret

`freeze_t0` takes **no authorization token**. A secret is a thing that can be
guessed, leaked, copied out of a transcript, or supplied by whoever is at the
keyboard. Authority here is a merge, which only the Owner can perform.

```text
docs/p2/OWNER_T0_AUTHORIZATION.md

  DOES NOT EXIST YET. It is created by an Owner-merged PR at the moment the
  Owner grants T0 authority, and never before.

  freeze_t0 reads it FROM GIT at HEAD — not from the working tree, which anyone
  can write — and refuses unless ALL hold:
    · the file exists at HEAD, and HEAD is a merge commit on main
    · it names role                       FP-CONTROL-2
    · it names the qualification certificate sha256, matching the S3b binding
    · it names the qualification commit   Mq
    · it declares                         REAL_MONEY_AUTHORIZED = NO
    · it is not expired  (it carries an explicit expiry; an authorization that
      never expires is one that outlives the state it was granted against)
```

Its absence is the default, and the default is refusal.

### Sequence

```text
S3   qualification run at Mq on L1 → preflight 16/16 · reconcile PASS ·
     the pre-T0 nine · observe image_digest + python_version ·
     generate the certificate WHILE L1 IS LIVE · stop · seal · archive L1
S3b  PR: bind the observations and the certificate (class O)  → CI → MERGE → M1
     prove SEMANTIC_IDENTITY(Mq) == SEMANTIC_IDENTITY(M1)
S4   OWNER authorization merged                                        BLOCKING
S5a  create L2, fresh and empty
S5b  freeze_t0 writes the seven values, regenerates MANIFEST, commits, pushes
S5c  CI freeze-candidate gate: two files, seven values, equivalence, FP-CONTROL-1
     byte-identical
S5d  OWNER MERGE                                                       → M2
S5e  re-ground the runtime checkout to M2, worktree clean
S5f  start the cohort
S6   PR: activation record + archive digests → CI → MERGE               → M3
     from a SEPARATE worktree; the runtime checkout stays pinned at M2
```

---

## 7. Activation and continuity

The capture loop reads T0 **once**, at construction. A loop already running when
T0 is frozen will never see it, so the cohort requires a fresh process start
after the merge. This is how the code behaves, not a preference.

```text
VALIDATED AT ACTIVATION (scripts/validate_activation.py, exit 0/2)
  1 exactly one run_started, restart_counter 0
  2 all four chains verify from genesis, no erratum
  3 every record: role · cohort_id == frozen id · a SINGLE source_commit == M2
  4 no record carries T0_NOT_FROZEN                    — proves a fresh lane
  5 no record is both PRE_T0 and LIVE                  — warm-up never executable
  6 the first (POST_T0 ∧ LIVE) decision exists, on the first 1h boundary at or
    after t0_utc
  7 reconcile --source-commit M2 --require-pass        exit 0
  8 preflight --require-pass                           16/16, check 5 now PASSES
    because the stamped cohort id equals the declared one
  9 the activation-gap record is present
```

### The activation gap

The registry has four statuses. A cohort whose T0 is frozen but whose runtime
has not started cannot be `NOT_STARTED` (the schema forbids a T0 on it) and
cannot be `PAUSED` (a paused row is not executable). It must be `RUNNING`. So an
interval exists between the freeze and the first process start in which the
registry says `RUNNING` and nothing runs.

```text
BOUNDED   the contract sets a maximum freeze→start interval
VISIBLE   validate_activation writes t0_utc · first run_started_utc · elapsed ·
          the count of (POST_T0 ∧ WARMUP) decisions and the candles they cover;
          capture records an activation_gap incident when the count is non-zero
SAFE      the crediting law already refuses gap bars — they are POST_T0 ∧ WARMUP
```

A silently absent hour and a recorded one are different evidentiary objects.
Bars missed during any later stop return the same way: counted, never credited.

### Restart law

```text
SAME commit       continuity — restart_counter increments, chains continue,
                  reconcile's restart_continuity finding holds
DIFFERENT commit  NOT continuity — reconcile fails on a second stamped commit
```

Therefore the runtime checkout is **pinned at M2 for the cohort's whole life**,
and every P2 branch, commit and merge happens in a separate worktree.

Container crashes and host reboots are already covered: every service declares
`restart: unless-stopped`, and the Docker daemon is enabled at boot. What is not
covered without `scripts/fp_watch.py` is a wedged loop whose process is alive but
not advancing, a stack stopped and never restarted, and silent chain corruption
between reconciliation runs.

---

## 8. Durability

The two must never be conflated. The project has already paid for conflating
them once, under the closure reason `EVIDENCE_LANE_LOST_IN_HOST_MIGRATION`.

```text
TIER 1 — SAME-HOST ARCHIVAL                                        REQUIRED
  MAY CLAIM  lanes cannot be commingled or cross-credited; no running container
             can reach an archived lane; operator error in the live lane cannot
             destroy archived evidence
  MAY NOT CLAIM  survival of host loss, disk failure, filesystem corruption, or
             this machine being decommissioned

TIER 2 — DIGEST PUBLICATION                                        REQUIRED
  tracked: ledger tips, daily_pack_digest, record counts, per-file sha256.
  No evidence CONTENT leaves the host.
  MAY CLAIM  surviving evidence is provably the evidence that was sealed; a loss
             and its exact extent are provable rather than reconstructed
  MAY NOT CLAIM  that anything is recoverable. A digest is not a backup. It
             converts an unbounded loss into a bounded, documented one.

TIER 3 — INDEPENDENT-HOST / INDEPENDENT-STORAGE SNAPSHOT
  REQUIRED BEFORE T0 unless the Owner later changes this requirement.
  Evidence storage outside the active workstation's FAILURE DOMAIN.
  ONLY TIER 3 MAY CLAIM HOST-LOSS REDUNDANCY.
  Discovery only: what is already lawfully available on this host. No purchase,
  no provisioning, no credential creation without separate authority.
  If no lawful independent destination exists after S3b:
      STOP — OWNER_DECISION_REQUIRED BEFORE T0
```

A same-host copy is never described as host-loss redundancy, in any record, at
any time.

---

## 9. Conditional T0 authority

T0 is **not** authorized by this contract. It becomes executable only when every
one of these is true, and then only after a separate Owner confirmation:

```text
S1 merged                                    S3b merged
S2 merged                                    qualification certificate valid
S3 PASS                                       SEMANTIC_IDENTITY(Mq) == (M1)
fresh L2 exists and is empty                  Dataset lock PASS
Tier-3 durability gate satisfied              strategy/risk/Dataset authority unchanged
docs/p2/OWNER_T0_AUTHORIZATION.md merged      REAL_MONEY_AUTHORIZED = NO
```

When all are true, the report is `T0_PRECONDITIONS = PASS` and execution stops at
`OWNER_T0_EXECUTION_CONFIRMATION_REQUIRED`.

---

## 10. Authority

```text
OWNER ONLY
  every merge to main                     freezing a NEW T0, and opening a cohort
  roadmap / stage changes                 strategy semantic expansion
  risk semantic expansion                 Dataset authority / refreeze
  opening the parked 19d7d7e              live authorization / real money
  any class D or E change to a running cohort
  Tier-3 provisioning, purchase or credential creation

CLAUDE CODE, AUTONOMOUSLY, WITHIN THIS CONTRACT
  build and test every tool named here — including freeze_t0, but never run it
  run every gate, repeatedly, and diagnose failures
  start / stop / restart the runtime through the governed scripts at the frozen
    commit
  monitor the cohort, investigate incidents, run reconciliation
  fix ordinary bugs in tests, tooling and docs on a branch and open a PR
  produce evidence artifacts, digests and records
  re-ground on merged main and resume

RETURNS TO THE OWNER ONLY AT
  OWNER_MERGE_REQUIRED · Tier-3 unavailable · a genuine strategy/risk/Dataset
  authority conflict · T0_PRECONDITIONS = PASS
```

Ordinary implementation, test and runtime issues inside S1–S3b are not returns.

---

## 11. Defects after T0

| Class | Cohort | Runtime | Disposition | Autonomous? | Owner |
| --- | --- | --- | --- | --- | --- |
| **A** operational fault, no tracked change | **valid** | restart at the same commit | continues; incident recorded | yes | no |
| **B** repair needing a tracked runtime change | invalid | stop | CLOSED | build/test yes, merge no | yes |
| **C** corrupted or missing evidence | invalid | stop | CLOSED | investigate yes | yes |
| **D** strategy or risk semantic change | invalid | stop | CLOSED | **no** | yes |
| **E** Dataset authority change | invalid | stop | CLOSED | **no** | yes |
| **F** poor performance, evidence valid | **valid** | continues | runs to its end, closes on its own evidence | n/a | decision only |

```text
A cohort is invalidated ONLY by a technical defect in its evidence or identity.
It is NEVER invalidated by its result. Class F is the load-bearing row: a valid
unfavourable cohort is a RESULT, and re-running it to obtain a better one is the
behaviour every gate in this repository exists to prevent.
```

Replacement-T0 budget is **not granted** by this contract.

---

## 12. Closure law

```text
P2 CLOSED / PASS
  12/12 properties — the NINE from S3 at Mq, the THREE from credited L2 records;
  full_trade_lifecycle is reported beside them and is never counted among them ·
  reconciliation PASS · chains verify from genesis · one (commit, role, cohort,
  lane) identity throughout · equivalence proof holds · safe end-state ·
  archives sealed and digests published · closure record merged
    paper_trading_operational_capability = PROVEN
    full_trade_lifecycle                 = OBSERVED
    prospective_paper_edge               = NOT_EVALUATED
    measurable_post_t0_evidence          = AVAILABLE

P2 CLOSED / FAIL
  a safety or integrity gate failed and was not repairable within this contract ·
  paper-only authority breached · evidence proven unattributable or tampered.
  A FAIL is about the SYSTEM.

P2 INCONCLUSIVE / INSUFFICIENT
  evidence valid, chains intact, reconciliation PASS, no naturally-triggered
  closed trade in the window
    paper_trading_operational_capability = NOT_PROVEN
    full_trade_lifecycle                 = NOT_YET_OBSERVED
    measurable_post_t0_evidence          = AVAILABLE
  LEGITIMATE. The 48-hour window rule is explicit: no artificial trade may be
  generated to make the test pass; do not change the strategy, lower a threshold,
  or force an entry. The response is a longer window under the SAME frozen
  contract — never a changed one.
```

**P&L determines neither PASS nor FAIL.**

### What one completed trade lifecycle proves, and does not

```text
PROVES   a real signal from real closed candles reached a paper order; it filled
         under FREQTRADE_2026.7_DRYRUN_ORDERBOOK_V1; position state was created,
         persisted and recovered across a restart; an exit occurred and realised
         PnL was computed; all four ledgers agree; event-time replay reproduces
         the recorded decision; the executed entry was one the admission gate
         would have admitted; no duplicate execution occurred.
         This has NEVER been observed in this project: P1's trade ledger tip is
         0000000000000000 and FP-CONTROL-1's is unreadable.

DOES NOT PROVE   anything about edge, profitability or expectancy — n = 1.
         Anything about live fill quality: the fill model's own frozen text says
         these are "simulation semantics ... not evidence of live fill quality",
         with no slippage, latency, partial-fill or market-impact model.
         Anything about regimes other than the one observed. Paper Beta
         acceptance. Controlled-live readiness. Durability. And it does not
         convert a control into a candidate.
```

---

## 13. Stage scope

```text
S1   governance materialization — this file, CLAUDE.md's stage pointer,
     ROADMAP's supersession note, MANIFEST
S2   pre-T0 implementation — archive_fp_lane · prove_semantic_equivalence ·
     seal_pre_t0_qualification · freeze_t0 · validate_activation · fp_watch ·
     the registry_source_commit_equivalence reconciliation finding · the
     preflight correction · RUNNING/T0 correspondence tests · the CI
     freeze-candidate gate · activation and crediting negative controls ·
     Tier 1 · Tier 2 · Tier 3 discovery only
S3   live pre-T0 qualification at Mq on L1, and the certificate
S3b  class-O binding of the observations and the certificate → M1
```

Every authority-bearing mechanism built in S2 carries a **behavioural refusal
test**: the mechanism is shown to reject its own violation, and every refusal is
shown to leave the registry byte-identical. A gate that can only report `PASS` is
not evidence.

---

## 14. Pointers

Nothing below is restated here; each is the authority for its own subject.

```text
docs/p1/P1_CLOSURE.md                          P1 exit truth, verification basis
docs/NEXT_EXECUTION_PREREQUISITES_2026-09-14.md  prerequisite order, boundaries
docs/fp-boot-1/FP_PRE_T0_SUCCESSOR_CONTROL.md  the runnable pre-T0 instance
docs/fp-boot-1/FP_CONTROL_1_COHORT_CLOSURE.md  what a new cohort requires
docs/fp-boot-1/FP_CONTROL_1_ACTIVATION_PACK.md A1–A15, section B, S1–S19
                                               (A14 superseded — no runnable
                                               registry write remains)
docs/fp-boot-1/FP_S19_CAPTURE_LOOP.md          the evidence chain
docs/research/BASELINE_1_PROTOCOL.md           the frozen strategy's protocol
research/datasets/dataset_v2.lock.json         the dataset authority
research/schema/forward_paper_cohort_registry.schema.json
                                               the machine-enforced cohort law
```

```text
PAPER / RESEARCH ONLY
REAL_MONEY_AUTHORIZED = NO
```
