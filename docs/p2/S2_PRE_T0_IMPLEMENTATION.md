# S2 — PRE-T0 IMPLEMENTATION

**Stage:** `P2 — PROSPECTIVE PAPER PROOF`, §13 stage S2.
**Authority:** [`P2_CONTRACT.md`](P2_CONTRACT.md). This record does not restate
it and does not extend it.

```text
CREATED   no T0 · no cohort · no cohort id · no prospective evidence
CHANGED   no strategy semantics · no risk semantics · no Dataset authority
TIER3_DESTINATION = OPEN_OWNER_DECISION
PAPER / RESEARCH ONLY        REAL_MONEY_AUTHORIZED = NO
```

S2 builds the mechanisms the later stages execute. Every one of them is built
and tested here; `freeze_t0` in particular is built, driven through every one of
its refusals, and **never run** — and nothing about that ordering is enforced by
a flag, because the thing it reads does not exist.

---

## 1. What was built

| | Mechanism | What it decides |
| --- | --- | --- |
| `research/fp/semantic_identity.py` | SEMANTIC_IDENTITY | whether two commits run the same system |
| `scripts/prove_semantic_equivalence.py` | the CLI for it | `EQUIVALENT` / `DIFFERENT` / `UNPROVEN` |
| `research/fp/registry_law.py` | RUNNING/T0 correspondence | the invariants a per-row schema cannot express |
| `research/fp/archive.py`, `scripts/archive_fp_lane.py` | Tier 1 | the whole lane moves, or nothing does |
| `scripts/publish_evidence_digest.py` | Tier 2 | what was sealed, never what it contained |
| `scripts/seal_pre_t0_qualification.py` | the S3 certificate | what a pre-T0 run established, sealed while it is live |
| `scripts/freeze_t0.py` | the T0 transaction | two files, seven values, or refusal |
| `scripts/validate_activation.py` | activation | the nine checks, and what the gap cost |
| `scripts/fp_watch.py` | continuity | wedged loop · stopped stack · silent corruption |
| `scripts/check_freeze_candidate.py` | the CI gate | a freeze candidate is the whole transaction or none of it |
| `scripts/tier3_discovery.py` | Tier 3, discovery only | what is already lawfully here |
| `research/fp/capability.py` | the property model | the twelve, their two buckets, and the aggregate outside them |

Two existing modules were corrected rather than extended:

```text
research/fp/reconcile.py    + registry_source_commit_equivalence
research/fp/preflight.py      check 5's unstamped-cohort case now names the records
research/fp/capture.py      + the activation_gap incident, recorded per missed bar
```

---

## 2. The three decisions that carry the most weight

### T0 authority is a merge, and the tool takes no token

`freeze_t0` reads `docs/p2/OWNER_T0_AUTHORIZATION.md` **from git at HEAD**, not
from the working tree. The distinction is the whole mechanism: a working-tree
read would make "the Owner authorized this" a claim anyone with write access to
this directory could manufacture. The file does not exist, and
`tests/test_p2_freeze_t0.py` plants one in the working tree and requires the
refusal to stand.

There is no authorization token and adding one would be a downgrade. A secret
can be guessed, leaked, copied out of a transcript, or supplied by whoever is at
the keyboard. A merge cannot.

### Equivalence is computed from git objects, not from a diff

`RUNTIME_TREE` is `{path: "mode:blob_id"}` — git's own content addresses, plus
the mode, because an executable bit is behaviour for a shell script. A textual
diff can be made to read as empty by a normalisation somewhere in the pipeline;
a blob id cannot.

**A defect found and fixed during this stage, recorded because it was
invisible.** The first implementation handed the contract's path rules to `git
ls-tree` as pathspecs. `ls-tree` treats a pathspec as a leading-directory
prefix and does not honour globs, so `research/fp/*.py` and `scripts/*.py`
matched **nothing** while the directory prefixes beside them matched normally.
Every module holding the runtime's own logic silently left the comparison — 8
files compared instead of 37 — and the report was populated and plausible. The
repair enumerates the whole tree and filters in Python, and refuses outright if
any declared rule matches no file: a rule that stops matching removes files from
the comparison without anyone deciding it should.

### A second defect, found because a refusal test is not a success test

Every freeze test written first proved a **refusal**. None proved the
transaction could **succeed**, and that gap hid a defect that would have
surfaced exactly once — the one time `freeze_t0` is ever run.

`scripts/verify_repo.py --fix` hashes each tracked file **as it stands in the
git index**, deliberately, so an unstaged edit cannot slip a hash into the
manifest for content that is never committed. `apply_freeze` regenerated the
manifest *before* staging the registry, so the manifest was rebuilt from the
pre-freeze registry, came out byte-identical to the committed one, and the
transaction then failed its own two-file check:

```text
the freeze staged ['research/fp/records/forward_paper_cohort_registry.json'],
not exactly ['MANIFEST.txt', 'research/fp/records/forward_paper_cohort_registry.json']
```

A freeze tool that can never succeed is a worse failure than one that fails
loudly. The order is now register → stage → regenerate → stage, the rollback
restores the index as well as the worktree, and six tests apply the real
transaction to a disposable clone of this repository at its own HEAD: exactly
two staged files, nothing unstaged, the seven values written, the FP-CONTROL-1
row byte-identical, `verify_repo` passing afterwards, and the resulting commit
passing the very CI gate it will face. The ordering was reverted once to confirm
those tests fail against the defect rather than passing for unrelated reasons.

### The whole lane moves, or nothing does

Archiving only `evidence/` would carry pre-T0 wallet and position state into a
post-T0 cohort through `tradesv3.sqlite`. The database is the leak, not the
ledgers, and it is the file a reasonable person forgets. `archive_lane` moves
the lane directory — evidence, logs, the database, `capture_runtime.json`, the
lock file, and anything else in there, including files this code has never heard
of, because an unanticipated file is the one most likely to carry state across.

It copies, re-reads every byte from the destination, hashes it against the
source, and only then removes the original. An archive nobody has read back is
an assumption, not a copy.

---

## 3. Durability — what each tier may truthfully claim

```text
TIER 1  SAME-HOST ARCHIVAL                                    IMPLEMENTED
  MAY      lanes cannot be commingled or cross-credited; no running container
           can reach an archived lane; operator error in the live lane cannot
           destroy archived evidence
  MAY NOT  survival of host loss, disk failure, filesystem corruption, or this
           machine being decommissioned

TIER 2  DIGEST PUBLICATION                                    IMPLEMENTED
  research/fp/records/evidence_digest_publication.json — tracked, empty, valid
  MAY      surviving evidence is provably the evidence that was sealed; a loss
           and its exact extent are provable rather than reconstructed
  MAY NOT  that anything is recoverable. A digest is not a backup.

TIER 3  INDEPENDENT-HOST SNAPSHOT                             DISCOVERY ONLY
  TIER3_DESTINATION = OPEN_OWNER_DECISION
```

A same-host copy is never described as host-loss redundancy, in any record, at
any time. That is a sentence rather than a code path, so
`tests/test_p2_contract_invariants.py` asserts it against the text every tool
emits.

### What Tier-3 discovery found on this host

Discovery ran. It provisioned nothing, contacted nothing, and created no
credential.

```text
/                          ext4     same device as the repository
/boot/efi                  vfat     a second partition, SAME failure domain
/run/media/hamza/…         ntfs3    a separate block device, ~924 GiB free
git remote origin                   off-host, and NOT an evidence destination

VERDICT = CANDIDATE_FOUND_INDEPENDENCE_UNPROVEN
```

One candidate exists and its independence is **unproven**. Whether a removable
volume mounted at this desk is outside this workstation's failure domain depends
on facts no tool can determine — whether it is a different physical disk, and
whether it ever leaves the desk. A second partition or a second disk in the same
machine is a different filesystem and the *same* failure domain: a theft, a
fire, a PSU failure or a decommission takes both.

The git remote is genuinely off-host and is deliberately **not** offered: the
evidence lane is gitignored by design, the worktree must stay clean for the
whole window, and committing evidence is precisely what the repository's own
integrity gate exists to prevent. Tier 2 already publishes digests through it,
and digests are not a backup.

---

## 4. Every mechanism refuses its own violation

Contract §13: *a gate that can only report `PASS` is not evidence.* Each
mechanism below has at least one test that drives it into refusal, and the
freeze tests additionally assert the registry and `MANIFEST.txt` are
byte-identical afterwards.

```text
semantic identity   a changed strategy · a changed research module · a changed
                    launcher · an executable bit · a widened max_open_trades ·
                    an unresolvable revision · an undeclared role · a rule that
                    matches nothing
                    and EQUIVALENT for image_digest, python_version and the
                    freeze transaction's own bookkeeping — which must be
                    excluded, or the proof the contract requires could never
                    hold for any real freeze
registry law        flag on with nothing running · flag off with a RUNNING row ·
                    a cohort id naming another instant · two RUNNING rows · a
                    NOT_STARTED row holding a T0 · a short commit · two rows
                    declaring one lane · real_money_authorized true
archival            a live writer holding the lock · an existing archive · a
                    destination inside a mounted lane · a lane containing a
                    symlink · a lane that does not exist
Tier 2              a mutated archive · a file added · a file removed · an
                    unsealed directory · a published digest rewritten in place
freeze_t0           absent authorization · one planted in the working tree ·
                    expired · wrong role · REAL_MONEY_AUTHORIZED = YES · a
                    missing field · a field declared twice · absent binding ·
                    a certificate the binding does not pin · a different Mq ·
                    a single-parent HEAD · a HEAD not on main · an Mq outside
                    the history · a dirty tree · non-equivalent commits ·
                    UNPROVEN equivalence · a non-empty lane · an already-started
                    row · an unlawful registry · a non-empty change_log ·
                    a back-dated T0 · a T0 a month out · a malformed T0
activation          a restarted lane · a broken chain · a foreign cohort id ·
                    a second source commit · a T0_NOT_FROZEN record · a
                    PRE_T0+LIVE record · a late first credited bar · a gap with
                    no incident recorded · a start beyond one candle period
freeze candidate    a freeze that also changes code · that also changes a doc ·
                    that forgets MANIFEST · that moves a risk field · that
                    leaves the flag false · that touches the closed row · a
                    cohort id that does not derive · two change_log entries ·
                    a non-equivalent declared commit · no declared commit
watch               a stalled heartbeat · a stalled decision stream · a RUNNING
                    row with no writer · silent chain corruption · and it is
                    asserted to write nothing into the lane
```

`UNPROVEN` blocks exactly as `FAIL` does, in all three gate families, and a test
asserts no override flag or override environment variable appears anywhere in
the S2 tool set.

---

## 5. Two values S2 had to choose, and one the contract must settle

### The maximum freeze→start interval — chosen

Contract §7 says the interval is **BOUNDED** without naming the bound. S2 sets
it to **one candle period** (`MAX_ACTIVATION_GAP_CANDLE_PERIODS = 1`, 3600s at
the frozen 1h timeframe), because that is the instant the gap becomes
evidentially visible: beyond one period, at least one bar that should have been
observed live closed while nothing was running. Any other number would be
arbitrary. `validate_activation` check 10 fails past it.

The stall threshold in `fp_watch` is deliberately **two** periods, for the
opposite reason: a one-period threshold would fire on the ordinary race between
a candle closing and the next poll, and an alarm that cries wolf every hour is
an alarm that is ignored on the day it matters.

### The maximum freeze→T0 distance — chosen

`freeze_t0` refuses a T0 more than **7 days** ahead. A T0 frozen far ahead is a
cohort whose identity is frozen against a system with time to move underneath it
before anything runs. `--t0` is required and never defaulted: only the Owner
knows when the freeze will be merged, and a guessed T0 buys an activation gap
nobody chose.

### The property model — resolved, and reduced to one statement

The contract's original split — *"eight non-lifecycle"* plus *"four
lifecycle"* — did not close, and the reason it did not close is that the
completed entry→fill→position→exit→realised-PnL chain was being counted as the
fourth lifecycle property.

The authority that first enumerated the twelve is
[`FP_CONTROL_1_ACTIVATION_PACK.md`](../fp-boot-1/FP_CONTROL_1_ACTIVATION_PACK.md)
section A, and it reports the chain **separately** from the capability verdict.
The registry schema agrees: `full_trade_lifecycle` is its own outcome field with
its own enum. The aggregate was always outside the twelve; P2's restatement put
it inside.

```text
PRE_T0 QUALIFIABLE   9   real market input · event-time/timestamp knowability ·
                         paper-only authority · decision logging ·
                         risk/admission · persistence · restart recovery ·
                         ledger reconciliation · data integrity
POST_T0 LIFECYCLE    3   paper order/fill · position state ·
                         no duplicate execution
                    ---
                     12

FULL_TRADE_LIFECYCLE     aggregate status, reported beside the twelve,
                         never counted among them
```

This is not a bookkeeping preference. Folding the aggregate into the count would
let a cohort reach `12/12` with a genuine property unevidenced and the aggregate
standing in for it. It would also collapse the distinction
`P2 INCONCLUSIVE / INSUFFICIENT` depends on: a quiet window can leave the
lifecycle unobserved while every capability is intact, and that outcome is only
expressible when the two are counted separately.

`research/fp/capability.py` is now the single source. The binding schema's enum
is derived from it, `seal_pre_t0_qualification` imports it rather than restating
it, and `tests/test_p2_capability_model.py` asserts the four invariants — twelve
unique properties, every one in exactly one bucket, the buckets summing to
twelve, and the aggregate unable to enter or leave the count — plus a parse of
the activation pack's own sentence that requires the twelve names to match it
exactly.

### The reconciliation finding count — P1 closed on 13, P2's law is 14

`registry_source_commit_equivalence` is a new check, so a reconciliation now
emits **fourteen** findings where P1's emitted thirteen.

Both numbers stand, about different things. `docs/p1/P1_CLOSURE.md` records
`13/13 findings, exit 0`; that describes what P1 observed at the commit it was
written for, it is evidence, and it is **not edited** to agree with a later
system. A test asserts the file is unmodified on this branch. The other
thirteens in the repository are unrelated counts — the S19 record's thirteen
required capture-loop test proofs, and CLOUD-0's thirteen inventory findings —
and are untouched.

What changes is the **expectation**. `reconcile.EXPECTED_FINDINGS` now names all
fourteen, every report carries `findings_complete`, `missing_findings` and
`unexpected_findings`, and an incomplete report is forced to `FAIL`. A check
that silently stops being emitted is a check that stopped running, and from
outside that is indistinguishable from it passing — `preflight.MECHANISM_KEYS`
exists for the same reason. `tests/test_p2_reconciliation_version.py` stops a
future P2 closure inheriting the stale number.

## 6. What S2 did not do

```text
no T0            no cohort           no cohort id        no lane was archived
no runtime was started or stopped    no registry value moved
freeze_t0 was never run              19d7d7e was not opened
no external storage, cloud service, credential, paid infrastructure or remote
host was provisioned, contacted or created
```

The L0 lane retained from P1 qualification still occupies
`freqtrade/user_data/fp-control-2/`. Archiving it is S3's first act, not S2's:
it is evidence, and moving it is a step in a stage that has not been authorized.

---

## 7. Where the next stages pick this up

```text
S3   archive L0 → create L1 → qualification run at Mq → seal the certificate
     WHILE L1 IS LIVE → stop → archive L1 → publish digests
S3b  commit research/fp/records/p2_qualification_binding.json — the certificate
     sha256, Mq, and the two class-O observations → CI → MERGE → M1
     then prove SEMANTIC_IDENTITY(Mq) == SEMANTIC_IDENTITY(M1)
S4   the Owner merges docs/p2/OWNER_T0_AUTHORIZATION.md               BLOCKING
```

`docs/p2/OWNER_T0_AUTHORIZATION.md` must declare, one occurrence each:

```text
ROLE = FP-CONTROL-2
QUALIFICATION_COMMIT = <Mq, 40 hex>
QUALIFICATION_CERTIFICATE_SHA256 = <64 hex, from the seal>
REAL_MONEY_AUTHORIZED = NO
EXPIRES_UTC = <YYYY-MM-DDTHH:MM:SSZ>
```

A file declaring any of these twice is refused rather than resolved: resolving
an ambiguity would mean choosing on the Owner's behalf.

```text
PAPER / RESEARCH ONLY
REAL_MONEY_AUTHORIZED = NO
```
