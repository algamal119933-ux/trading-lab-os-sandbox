# AUTH2-GOVERNANCE-CLOSURE-1 — AUTH-2 Governance Closure Record

**Authority:** Owner decision "AUTH-2 CLOSURE AND SUCCESSOR READINESS", 2026-10-12T23:14:33Z, Gate 1
`OWNER_CLOSURE_REVIEW`, on the review "AUTH-2 Closure and Successor Readiness Review" (section 6). That review
answered the Owner decision "OPTION A — CLOSE + SUCCESSOR, WITH SEPARATE GOVERNANCE AND ENGINEERING GATES"
(2026-10-12T22:14:10Z). This record binds when the Owner merges the PR that adds this folder. `docs/governance/**`
is a protected path, so that merge is `OWNER_MERGE_REQUIRED` (CEA-1 §3).

The Owner's Gate-1 decisions, verbatim:

```text
OD-C1 = APPROVED AS RECOMMENDED
Use docs/governance/records/AUTH2-GOVERNANCE-CLOSURE-1/. Do not append synthetic terminal records to the scientific trial ledger. Corrections are append-only errata.
OD-C2 = APPROVED AS RECOMMENDED
Classification is OPERATIONAL_EXHAUSTION, scientific outcome NONE; D0 is CLOSED_NOT_EVALUATED; the remaining 13 trials are CLOSED_NOT_RUN.
OD-C3 = APPROVED AS RECOMMENDED
Set the AUTH-2 charter status to CLOSED in the closure PR while preserving the as-run charter hash in the closure evidence.
OD-C4 = APPROVED AS RECOMMENDED
Add the explicit fail-closed refusal of every AUTH-2 dispatch when the charter is not ACTIVE, in the separate operator PR specified by the review.
OD-C5 = APPROVED AS RECOMMENDED
Do not count AUTH-2's 16 configurations in N-law accounting. Lifetime remains 35; A1/A2/A3 remain 21/6/4.
OD-C6 = APPROVED
The six run artifacts and available job logs must be preserved before 2027-01-10. Identify the exact Owner-side download actions where this session cannot retrieve them.
OD-C7 = APPROVED
Prepare the governance closure implementation PR. It must append nothing to the scientific ledger and dispatch nothing. Stop at the Owner merge gate.
```

**This is a governance record, not a research unit.** No AUTH-2 node, guard or closure workflow was dispatched
for it, nothing was appended to the trial ledger, and no preregistration, law, code pin, threshold, dataset,
strategy or risk setting changed. Outside this folder the only change is one value in the program charter:
`status` `ACTIVE` → `CLOSED` (OD-C3).

---

## A — Closure

```text
PROGRAM                 = AUTH-2-DISCOVERY-QUALIFICATION-1
EVIDENCE_COMMIT         = main 8013e216075fcdfdf1068ef1b43b52aea5747d78 (PR #63 merge)
TERMINAL                = OPERATIONAL_EXHAUSTION
SCIENTIFIC_OUTCOME      = NONE: 0 hypotheses evaluated, 0 node results, 0 engine invocations
TRIAL-AUTH2-D0          = CLOSED_NOT_EVALUATED (no result after its one technical retry)
OTHER 13 TRIAL IDS      = CLOSED_NOT_RUN (never reached: D0 produced no result)
CHARTER                 = charters/programs/AUTH-2-DISCOVERY-QUALIFICATION-1.json, status CLOSED
CHARTER_AS_RUN_SHA256   = d6c057789fd8410aba39bebdacd2053c7893e14f4ed97fc38427b7ba65387a40 (status ACTIVE)
CHARTER_CLOSED_SHA256   = 1472916afc5101ccf5e7c8d161684e4bd5a98e6f18aa275fab5cfc6b70d84ba6 (only "status" differs)
FUNNEL_LAW_2_SHA256     = 8aa91f5ec18cca488fdf3b4051f24fb41c11070faddafe5f866631d0c3234da5 (unchanged)
TRIAL_LEDGER            = unchanged: 40 records, tip 87c8b0499bbaf9f51089cb04560cf045a37e55d378df701964d21f394fcce363,
                          sha256 9da92ae40d6b3aded94806c270e1b4f4ad737c606a6fd960d05615e0230616da
AUTH2_LEDGER_RECORDS    = 14 PREREGISTERED (seq 26–39), 0 terminal; they stay open and are never registered again
N_LAW                   = AUTH-2's 16 configurations are not counted: lifetime 35, A1/A2/A3 21/6/4 (OD-C5)
COMPUTE                 = 157 of 4,000 minutes (node runs 152, guard runs 5, closure runs 0); 0 of 240 invocations
REAL_MONEY_AUTHORIZED   = NO · dry_run = true
```

The closure is evidence neither for nor against A1, A2 or A3. It is not a scientific hypothesis failure, which
is a node result that ends a family under the law (REJECTED, INCONCLUSIVE, LAW_INVALID,
INCONCLUSIVE_UNDERPOWERED, DATA_LIMITED). It is not the charter's STOP_PROGRAM either, which is a C1 integrity
failure (INVALID_RUN) whose one retry is spent. D0 never reached a comparison, so it produced neither.

N-law (OD-C5): `FUNNEL_LAW_2.md` §MULTIPLE_TESTING_LAW discloses 19 configurations before AUTH-2 plus its 16, a
lifetime of 35, and `research/auth2/families.py` `FAMILY_N` gives A1 21, A2 6 and A3 4. AUTH-2's 16 saw no data
and are not counted again; counting them would have made the lifetime 51 and A1/A2/A3 27/12/8.

## B — Why AUTH-2 stopped

D0 part 1 ran twice, its attempt limit, and ended both times without a result:

| Run | Commit | End | Billed min | Cause |
|---|---|---|---|---|
| 38273417548 | `410418e3` | failure in the node step's first second | 1 | the program check refused: a one-commit checkout made every PREREGISTERED record look older than the program (fixed by PR #63, merged as `8013e216`) |
| 38286502721 | `8013e216` | cancelled by the 150-minute job timeout | 151 | `dataset_v3.build` fetched the archive (27,898 files) one file at a time, and the archive cache restore found nothing. Inferred from the step timings and the code path, because the job log could not be read |

The pinned guard now refuses D0 (`ATTEMPTS: D0 part 1 already ran 2 time(s); the retry is spent`), no other node
can run before D0 ends, and the pinned `research/auth2/closure.py` refuses both of its paths:

```text
normal        AUTH2_NODE_REFUSED: the DAG is not exhausted: next [('D0', 1)], retry []
stop_program  AUTH2_NODE_REFUSED: STOP_PROGRAM needs a node whose last result is INVALID_RUN
```

## C — Why the closure is outside the trial ledger

All 14 trial-ledger terminal records would pass the ledger's schema, but none can be produced under the frozen law:

- `FUNNEL_LAW_2.md` §DAG_OPERATIONS LEDGER maps D0 to COMPLETED with its terminal state, FAILED on INVALID_RUN, or
  ABORTED NOT_RUN if never reached. D0 has no result and no INVALID_RUN, and it was reached twice.
- §DAG_OPERATIONS CLOSURE has `research/auth2/closure.py` write the closure record, and it refuses this state (§B).
- `research/auth2/IMPLEMENTATION_NOTES.md`, Ledger: terminal records are appended at closure only, mapped as
  §DAG_OPERATIONS states.

`trial_ledger_option.check.json` is the rejected option, checked: the 14 terminal records appended to a temporary
copy of the ledger, never to the repository's.

Two findings go to the successor, AUTH-2-DISCOVERY-QUALIFICATION-2:

- **Law gap.** RETRY covers a job that ends without a result, but STOP_PROGRAM needs an INVALID_RUN result, so a
  retry spent without a result has no terminal. The successor's TECHNICAL_EXHAUSTION terminal closes it (OD-S6).
- **Compute proof.** §COMPUTE_CAP_PROOF counted node timeouts only. Counting the guard and closure jobs, and the
  minute a job can bill past its timeout (run 38286502721 billed 151 minutes on a 150-minute timeout), the
  review's worst case is 4,448 minutes against the 4,000 cap. AUTH-2 used 157. The successor's proof counts every
  job (OD-S7).

## D — Trials

| Trial ID | Ledger seq | Kind | Node | Governance status |
|---|---|---|---|---|
| TRIAL-AUTH2-D0 | 26 | DATA_LOCK | D0 | CLOSED_NOT_EVALUATED |
| TRIAL-AUTH2-CAL-A1 | 27 | CALIBRATION_STAT | CAL-A1 | CLOSED_NOT_RUN |
| TRIAL-AUTH2-CAL-A2 | 28 | CALIBRATION_STAT | CAL-A2 | CLOSED_NOT_RUN |
| TRIAL-AUTH2-CAL-A3 | 29 | CALIBRATION_STAT | CAL-A3 | CLOSED_NOT_RUN |
| TRIAL-AUTH2-PC-A1 | 30 | POSITIVE_CONTROL | PC-A1 | CLOSED_NOT_RUN |
| TRIAL-AUTH2-PC-A2 | 31 | POSITIVE_CONTROL | PC-A2 | CLOSED_NOT_RUN |
| TRIAL-AUTH2-PC-A3 | 32 | POSITIVE_CONTROL | PC-A3 | CLOSED_NOT_RUN |
| TRIAL-AUTH2-N-A1 | 33 | NULL_CALIBRATION | N-A1 | CLOSED_NOT_RUN |
| TRIAL-AUTH2-N-A2 | 34 | NULL_CALIBRATION | N-A2 | CLOSED_NOT_RUN |
| TRIAL-AUTH2-N-A3 | 35 | NULL_CALIBRATION | N-A3 | CLOSED_NOT_RUN |
| TRIAL-AUTH2-A1 | 36 | SCIENTIFIC | A1 (and SC-A1) | CLOSED_NOT_RUN |
| TRIAL-AUTH2-A2 | 37 | SCIENTIFIC | A2 (and SC-A2) | CLOSED_NOT_RUN |
| TRIAL-AUTH2-A3 | 38 | SCIENTIFIC | A3 (and SC-A3) | CLOSED_NOT_RUN |
| TRIAL-AUTH2-HOLM | 39 | HOLM | HOLM | CLOSED_NOT_RUN |

The trial ledger refuses a second PREREGISTERED record for a trial ID, so none of these 14 is ever registered
again. A successor registers its own trial IDs and cites this record.

## E — Files

| File | sha256 | What it is |
|---|---|---|
| `evidence.json` | `bbece74c7757c4c8030293b34c1c7e74615997d7d3bbd13b2cd0c1dc98394c3f` | Snapshot of every AUTH-2 run (`auth2.yml`, `auth2-guard.yml`, `auth2-closure.yml`) from the Actions API at 2026-10-12T22:29:19Z, with jobs, steps, billed minutes and decoded guard records, and the repository state at main `8013e216` |
| `governance_closure.proposed.json` | `accc6ed0f9f3ce248b8227d4774fe1ce8da93e88e8227a61719a18008f0c71c2` | The closure record, as approved under OD-C2. Its status line reads "PROPOSED: binding only after the Owner merges it"; the merge that adds this folder is that merge |
| `trial_ledger_option.check.json` | `ab501540c200ef283960eac5234cad25b4719a397a5b4f3baf88b688f37047d5` | The rejected trial-ledger option, checked (§C) |
| `SHA256SUMS` | `fee39e08980907b156cce6d33c5c30a073e921892cd8283b8df78ff8d81cc89c` | Hashes of the three files above |
| `closure_proposal.py` | `0c7cb7c1ca286d5279e69d0c17737c709b490190b104ec9eaae7cb8dc9a4608a` | The generator. It sits here and not under `research/auth2/`, because `run_node.code_sha256` hashes every `research/auth2/*.py` and a new file there would break all 17 preregistration pins |

These five files are byte-identical to the bundle the Owner approved.

**Append-only.** No file in this folder changes after the merge; `tests/test_auth2_governance_closure.py` pins
the sha256 of each one, this README included. A correction is a new file, `ERRATA_<n>.md`, in the form of
`research/RESEARCH_CYCLE2_CLOSURE_1_ERRATA_1.md`, merged by the Owner.

## F — Reproduce

```bash
git -C <clone> worktree add --detach /tmp/auth2-closure 8013e216075fcdfdf1068ef1b43b52aea5747d78
cd <clone>/docs/governance/records/AUTH2-GOVERNANCE-CLOSURE-1
python3 closure_proposal.py verify --repo /tmp/auth2-closure --evidence evidence.json --out-dir .
#   CLOSURE_PROPOSAL_VERIFY = PASS
python3 closure_proposal.py check-live --repo /tmp/auth2-closure \
    --slug algamal119933-ux/trading-lab-os-sandbox --evidence evidence.json
#   EVIDENCE_MATCHES_LIVE = YES   (read-only repository endpoints through gh api)
```

`verify` needs no network: it rebuilds the record from `evidence.json` and the checkout and requires every output
to be byte-identical, with the trial ledger and the worktree unchanged. The generator refuses a checkout that no
longer matches the evidence, so it runs against main `8013e216` and not against a later commit (this record's own
commit changes the charter). `tests/test_auth2_governance_closure.py` runs `verify` the same way.

Checked before the PR: `verify` passed against a clean checkout of `8013e216`, and `check-live` reported
`EVIDENCE_MATCHES_LIVE = YES` at 2026-10-12T23:22:19Z.

## G — Evidence preservation (OD-C6): Owner action, not yet done

The six run artifacts and the seven job logs expire under the repository's retention. The executor's session can
list them but not download them: GitHub redirects each download to its artifact storage host, which that
session's network policy refuses (HTTP 403). The Owner downloads them once, unchanged, into the evidence store
Cycle 2 used (`RESEARCH_CYCLE2_CLOSURE_1.md` §G).

| Artifact | Name | Run | Bytes | sha256 GitHub lists (its digest) | Expires (UTC) |
|---|---|---|---|---|---|
| 11720410128 | auth2guard-D0-p1 | 38184895792 (guard) | 519 | `bedd0b10b8bbc6274bbf8965ed1847f2e09738d95e75a323c1ccb73f21a36313` | 2027-01-10T00:02:20Z |
| 11734002265 | auth2guard-D0-p1 | 38220977904 (guard) | 1164 | `f38bd5bf1cacd2d831843e13f5397effd7696cd595fcda99a090c559068a5e37` | 2027-01-10T08:00:29Z |
| 11756579518 | auth2guard-D0-p1 | 38272303141 (guard) | 961 | `4c3b93e56acb959f9bb7ae1bcd6907d01c9163ce008544825250d601222b3bc4` | 2027-01-10T15:43:22Z |
| 11757732325 | auth2-D0-p1 | 38273417548 (D0) | 1351 | `6dc2be09a1fd612fbd2f9a57cd88882eb3c6a0987505328676dfdb6ee029f958` | 2027-01-10T15:52:46Z |
| 11764090440 | auth2guard-D0-p1 | 38286343057 (guard) | 968 | `477854baf09a2a8891f681728071e9d819e6c4faab7c210bfe1af5953e6b9dc6` | 2027-01-10T17:45:36Z |
| 11771162818 | auth2-D0-p1 | 38286502721 (D0) | 1127 | `b803f09d6ba9d222d44e5153590b09473d7d0cbc1d9b97110610dad358c587f8` | 2027-01-10T17:47:01Z |

| Run | Attempt | Job |
|---|---|---|
| 38184895792 | 1 | 114605009837 |
| 38184895792 | 2 | 114609831877 |
| 38220977904 | 1 | 114716894081 |
| 38272303141 | 1 | 114889282026 |
| 38273417548 | 1 | 114892991064 |
| 38286343057 | 1 | 114935526670 |
| 38286502721 | 1 | 114936047670 |

Do it by 2027-01-08. Run 38184895792 started 2026-10-11T23:36Z, so its logs can expire before its artifact does.
On the Owner's host, with `gh` signed in as the repository owner:

```bash
R=algamal119933-ux/trading-lab-os-sandbox
D=~/Documents/TLOS-Evidence/trading-research/AUTH2
mkdir -p "$D/artifacts" "$D/logs"

# 1. the six run artifacts, as the zip GitHub serves
for p in 38184895792:11720410128 38220977904:11734002265 38272303141:11756579518 \
         38273417548:11757732325 38286343057:11764090440 38286502721:11771162818; do
  gh api "repos/$R/actions/artifacts/${p#*:}/zip" > "$D/artifacts/${p%%:*}-${p#*:}.zip"
done

# 2. each job's log as text (seven jobs; run 38184895792 ran twice)
for p in 38184895792-1:114605009837 38184895792-2:114609831877 38220977904-1:114716894081 \
         38272303141-1:114889282026 38273417548-1:114892991064 38286343057-1:114935526670 \
         38286502721-1:114936047670; do
  gh api "repos/$R/actions/jobs/${p#*:}/logs" > "$D/logs/${p%%:*}-job-${p#*:}.txt"
done

# 3. each run attempt's full log archive
for p in 38184895792/1 38184895792/2 38220977904/1 38272303141/1 38273417548/1 38286343057/1 38286502721/1; do
  gh api "repos/$R/actions/runs/${p%%/*}/attempts/${p#*/}/logs" > "$D/logs/${p%%/*}-attempt-${p#*/}.zip"
done

# 4. check against GitHub's digests, then index
sha256sum "$D"/artifacts/*.zip
cd "$D" && find . -type f | LC_ALL=C sort | xargs sha256sum > ../AUTH2_CLOSURE_SHA256SUMS.txt
sha256sum ../AUTH2_CLOSURE_SHA256SUMS.txt
```

Each artifact's sha256 should equal the digest in the table. The zip and log archives stay in the evidence store:
`scripts/verify_repo.py` forbids committing archives. A later append-only file in this folder,
`PRESERVATION_1.md`, records the index and its sha256, as `RESEARCH_CYCLE2_CLOSURE_1.md` §G did for Cycle 2.

## H — Order from here

The Owner's decision fixes the order:

1. This closure, merged by the Owner. AUTH-2 is CLOSED from that merge.
2. The readiness tooling PR, stopped at the Owner merge gate. The OD-C4 operator refusal is its own PR.
3. RT-0 to RT-11, each dispatched by the Owner individually, against a readiness ledger capped at 300 billed
   minutes (OD-S4).
4. After INFRA_READINESS = PASS at one named commit: the successor's law, preregistrations, measured compute proof
   and snapshot identity, stopped for Owner review (OD-S8).
5. No successor scientific trial runs before that later Owner merge.

Until the OD-C4 PR merges, AUTH-2 stays blocked by its own pinned rules (§B).

## Final status block

```text
AUTH2_STATUS            = CLOSED from the Owner's merge of this record
CLOSURE_RECORD          = AUTH2-GOVERNANCE-CLOSURE-1, outside the trial ledger
TERMINAL                = OPERATIONAL_EXHAUSTION · SCIENTIFIC_OUTCOME = NONE
NODES_EXECUTED          = D0 part 1 twice (38273417548 failure, 38286502721 cancelled); no result
INVOCATIONS_USED        = 0 of 240
MINUTES_LEDGER          = 157 of 4,000
TRIAL_LEDGER_CHANGE     = NONE
DISPATCHES_FOR_CLOSURE  = NONE
EVIDENCE_PRESERVATION   = OWNER ACTION PENDING (§G), by 2027-01-08
REAL_MONEY_AUTHORIZED   = NO
```

PAPER / RESEARCH ONLY. dry_run stays true; no real-money authority is created or implied.
