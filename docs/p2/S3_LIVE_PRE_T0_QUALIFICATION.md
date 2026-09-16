# S3 / S3b — LIVE PRE-T0 QUALIFICATION AT Mq, AND THE BINDING

**Stage:** `P2 — PROSPECTIVE PAPER PROOF`, §13 stages S3 and S3b.
**Authority:** [`P2_CONTRACT.md`](P2_CONTRACT.md). This record does not restate
it and does not extend it.

```text
Mq                      af17c3b80dad535b524e5ffbe40bef0785b3f605
CERTIFICATE_SHA256      9780df85a8d05b7534d7cc46f9ea0114a325f668a185011edf1a26092211f915
SEMANTIC_IDENTITY(Mq)   4e0c48359c312efb06993b4d3f9972e10abfd84368f23a0c949da1deffa43f34

CREATED                 no T0 · no cohort · no cohort id · no prospective evidence
CHANGED                 no strategy semantics · no risk semantics · no Dataset authority
SECOND_PHYSICAL_DEVICE  AVAILABLE       HOST_LOSS_REDUNDANCY = NOT_PROVEN
PAPER / RESEARCH ONLY                   REAL_MONEY_AUTHORIZED = NO
```

S3 re-established the nine pre-T0 qualifiable properties against the current P2
source and runtime, on a lane created fresh for the purpose and destroyed into an
archive afterwards. S3b binds what that run observed and the certificate it
produced. Neither stage freezes anything, and the certificate authorizes
nothing: it is the value the Owner's authorization will have to name.

---

## 1. The three lanes, in the order they were handled

| Archive | What it is | Credited |
| --- | --- | --- |
| `p1-l0-qualification-4543d4c3` | L0 — P1's retained qualification lane | **never** |
| `l1-attempt-9ba714fd` | a superseded L1 attempt, §5 below | **never** |
| `l1-qualification-af17c3b8` | L1 — the qualification lane this record is about | **never** |

All three live under `artifacts/`, outside `freqtrade/user_data/`, which is the
only host tree any container mounts.

### L0 was verified before it was moved

P1's closure record states L0's fingerprints, so the lane was reconciled against
them first rather than archived on the assumption that it was what it claimed:

```text
input     1998   tip 566e86c8bb7f83eb      decision  1998   tip 27f95df081f7db22
incident     3   tip 762de6ee71656968      trade        0   tip 0000000000000000
daily_pack_digest fa347aa5d9084777c311cc93f9c29ae04815aea26b22e867422cc5fa1bada1d0
```

Every value matches `docs/p1/P1_CLOSURE.md`. Reconciliation as a whole reads
**FAIL**, on exactly one finding:

```text
record_source_commit FAIL
  evidence claims commit(s) ['4543d4c3'] but the repository is on 04b36ebd:
  the runtime that ran is not the source being verified
```

That is contract §3 working as written rather than a defect. P1's proof of the
nine at `4543d4c3` is not carried forward, and the lane's own refusal to be read
as current is the mechanism that stops it being carried forward. The nine are
re-established below, at Mq, and nothing from L0 contributes to that.

The whole lane moved — `evidence/`, `logs/`, `tradesv3.sqlite`,
`capture_runtime.json`, the capture lock, and a stray zero-byte `x.jsonl` this
code had never heard of. The database is the file that would carry pre-T0 wallet
and position state into a post-T0 cohort, and the unanticipated file is the one
most likely to carry state across; `archive_lane` copies, re-reads every byte
from the destination, hashes it against the source, and only then removes the
original.

---

## 2. What the qualification run did

```text
start  → 1998 backfilled candles (999 × BTC/USDT, ETH/USDT) at 1h
stop   → start  the restart drill, same commit, tracked tree clean, nothing committed between
wait   → the 16:00–17:00 candle closed and was captured LIVE by the RESTARTED run
gates  → runtime-attached preflight · reconciliation
seal   → the certificate, generated WHILE THE LANE WAS LIVE
stop   → archive the whole lane → publish digests → replicate to the second device
```

The restart came before the boundary deliberately. A restart followed by no
further live bar leaves `restart_recovery` half-proved: it shows the process
came back, not that it resumed observing. The lane ends with two live bars in
the first run and two in the second.

```text
input      2000   tip 26859dfe637a8e9b4f59c89b8544b1adc7c67c37ff486170d5dcbae2f8d1742a
decision   2000   tip 70904c288eaaaa89605f5e191a9baf97961ea73cc36f68477ba0020b97db2852
incident      3   tip bfb858e1d22379abfaac3b0bc041e06d77a3dacce699185000c4c581d1ed01c7
trade         0   tip 0000000000000000000000000000000000000000000000000000000000000000
daily_pack_digest da31ba3f27c6890a90a98868f0c8387658e33b9ff9894da7e94ae04d15c54f6c

runs            2 (run_started restart_counter 0, then 1), 2 distinct run ids
bar_class       1996 WARMUP + 4 LIVE; the 4 LIVE split 2 / 2 across the restart
t0_relation     T0_NOT_FROZEN on all 2000 decisions
cohort_id       null on all 2000 records
source_commit   af17c3b8 on all 2000 records, and on no other value
uniqueness      2000 distinct (pair, candle) decisions out of 2000
chains          all four verify from genesis, before and after the restart
```

`trade 0` is not an omission. The strategy signalled `hold` on every live bar it
saw, and contract §7's prohibition is absolute: nothing may be done to make a
trade happen. The three lifecycle properties are not S3's to evidence.

### The gates, at Mq

```text
preflight   16/16 PASS   --require-pass exit 0
            T0_PERMITTED = YES · FP_RUNTIME_READINESS = PASS
            FP_INFRASTRUCTURE_SCAFFOLD_VALIDATION = PASS
            all five mechanism verdicts PASS
reconcile   14/14 PASS   --require-pass exit 0
            findings_complete true · missing [] · unexpected []
            including registry_source_commit_equivalence, the P2 finding
dataset     DATASET_LOCK_GATE = PASS (content matches the frozen lock), exit 0
repo        REPO_CHECK_PASS · PAPER_GUARD_PASS · tests 1010 passed, 8 skipped
```

`preflight` says `T0_PERMITTED = YES`. S3 does not take it, for the same reason
P1 did not: freezing a T0 is an Owner act, and qualification evidence is not a
cohort.

Two notes on the dataset gate, because the acquisition verdict printed beside it
reads `FAIL` and that is the expected output for a frozen dataset. The
acquisition gate defaults to a zero missing-candle ratio, and Dataset V2's own
lock records nine gap clusters per pair caused by Binance halting trading —
candles absent from Binance's own archive. The lock also records
`price_reconciliation_5m_to_1h = PASS` with zero OHLC mismatches over 50 374
buckets, which is reproduced here exactly; the four volume differences observed
fall in the incomplete fine buckets the lock already excludes. The question a
frozen dataset needs answered on every later run is whether it is still the same
data, the canonical digests answer it exactly, and that is the gate that is
binding.

### The nine properties, and what evidenced each

```text
real_market_input                 2000 candles from binance:spot:public-rest:klines,
                                  2 of 2 public hosts reachable, every input
                                  exchange-sourced
event_time_timestamp_knowability  every record carries source and receive
                                  timestamps; every decision is at or after its
                                  candle's close; clock skew +408 ms measured
                                  against the exchange
paper_only_authority              dry_run exactly true, spot, no exchange
                                  credential in the engine environment, no record
                                  claiming a live execution, PAPER_GUARD_PASS
decision_logging                  2000 append-only decisions, one per (pair, bar),
                                  chain verifying from genesis
risk_admission                    every decision carries its admission verdict,
                                  stake 10, max_open_trades 2, wallet 100
persistence                       reopened from disk by fresh readers and
                                  re-verified; the daily pack digest binds the tips
restart_recovery                  stopped and restarted at the same commit;
                                  counters [0, 1]; nothing re-captured, nothing
                                  re-decided, no execution re-recorded; the
                                  restarted run went on to observe live bars
ledger_reconciliation             14/14, including event-time replay reproducing
                                  every recorded decision and detecting a single
                                  flipped action
data_integrity                    altering a captured candle is detected;
                                  DATASET_LOCK_GATE = PASS
```

These nine are what the certificate carries. The three lifecycle properties —
paper order/fill, position state, no duplicate execution — are absent from it by
construction, and `full_trade_lifecycle` is not among the twelve at all.

---

## 3. Durability

```text
TIER 1   three whole-lane archives, each byte re-read from the destination and
         hashed against the source before the original was removed
TIER 2   research/fp/records/evidence_digest_publication.json — three entries,
         counts, ledger tips, pack digests and every per-file hash
SECOND   /run/media/hamza/New Volume on sda (WDC WD10EZEX-00B): all three
DEVICE   archives replicated and then re-verified from the device
         SAME_HOST_SECOND_DEVICE = YES     HOST_LOSS_REDUNDANCY = NOT_PROVEN
```

The replication is append-only by refusal rather than by filesystem attribute,
and a repeat run re-verifies rather than rewrites. All three replicas were
re-read from the device after the last archive landed, so the earlier ones are
known to have survived the later ones — which is the only claim Tier 2 and a
second device jointly support.

The certificate is not in Git and is not replicated as a lane: it is a runtime
artifact under `artifacts/p2-s3-qualification/`, and the tracked thing is its
sha256, pinned in the binding record. That is deliberate, and it is what lets a
merge-gated authorization refer to it. No ungoverned copy of it was made.

---

## 4. S3b — the binding

`research/fp/records/p2_qualification_binding.json` pins Mq, the certificate's
sha256, `SEMANTIC_IDENTITY(Mq)`, and the two class-O observations
(`image_digest`, `python_version`) taken from the engine while it ran. It binds;
it does not authorize.

Two of its three pinned values would otherwise be only as good as whoever typed
them, so `tests/test_p2_qualification_binding.py` **recomputes** them:

```text
qualification_commit      must be a real commit and an ancestor of HEAD
semantic_identity_digest  recomputed from git objects at that commit and
                          required to match — a binding that named another
                          commit, or altered one hex digit, fails
certificate_sha256        cannot be recomputed from Git by design; where the
                          artifact is still on the host its bytes are required
                          to hash to the pinned value, and freeze_t0 is what
                          compares the pin against the Owner's authorization
```

Both refusals were driven: one flipped digit and a substituted Mq, each rejected
with the recomputed value named.

The observations are class O — observations *of* a runtime, never instructions
*to* one — which is why they are excluded from `REGISTRY_SEMANTICS`, and the test
asserts that exclusion still holds rather than assuming it. That exclusion is
what lets the equivalence proof survive S3b at all.

```text
image_digest    sha256:da3428fde0f7f9f976eaafba8abc7eba42bf978f23e4808347e15d476ad9a643
python_version  3.14.6
engine_version  freqtradeorg/freqtrade:2026.7
```

Both observed values are byte-identical to the ones FP-CONTROL-1 bound, which is
a coincidence worth stating rather than relying on: the digest was read from the
running container, not copied from the registry row.

### Semantic identity across this branch

```text
SEMANTIC_IDENTITY(2b96dbd) vs SEMANTIC_IDENTITY(Mq)   DIFFERENT — one file:
    scripts/seal_pre_t0_qualification.py              the repair in §5
SEMANTIC_IDENTITY(Mq) vs SEMANTIC_IDENTITY(this branch head)   EQUIVALENT
```

Everything committed after Mq is outside `RUNTIME_TREE`: the binding and the
publication record are under `research/fp/records/`, which the model excludes;
the rest is `docs/p2/`, `tests/` and `MANIFEST.txt`, which it never included.
`SEMANTIC_IDENTITY(Mq) == SEMANTIC_IDENTITY(M1)` is therefore expected to hold
on the merge, but it is **not** claimed here: M1 does not exist until the Owner
merges, and it is proved against M1 or not at all.

---

## 5. Three defects, each found by running the system

### The seal could never produce a certificate

`seal_pre_t0_qualification` built its own preflight `RuntimeContext` carrying
only an evidence directory and a role. Three of the sixteen checks are
statements about a system running right now — real market-data ingestion,
monitoring liveness, clock tolerance against the exchange — and with no
endpoints and no market route they answer `UNPROVEN`, which blocks exactly as
`FAIL` does. Against a live lane whose own gates were green, preflight 16/16 and
reconciliation 14/14 run by hand:

```text
QUALIFICATION_SEAL_REFUSED: preflight is BLOCKED; not PASS:
['real market-data ingestion works', 'monitoring is alive',
 'clock/timestamp handling is within tolerance']
```

Every seal test proved a refusal and none proved the tool could reach its
output. That is exactly the gap S2 recorded for `freeze_t0` and repaired there,
one level down; the lesson did not generalise on its own, and a mechanism driven
only into its refusals is a mechanism whose success path runs for the first time
on the day it matters.

The repair threads the live instance's endpoints through, under the same flag
names and environment defaults as `preflight`'s own CLI. The lane and the role
are overwritten with the ones the seal validated, so a caller supplies endpoints
and can never redirect the gates at another lane. Absent wiring is now a refusal
that names the wiring, and it is placed **after** the refusals about the evidence
itself — an operator sealing the wrong lane should hear that first. The
certificate records which URLs were probed, so `PASS 16/16` can be told apart
from `PASS 16/16 with three checks excused`; credentials are never recorded.

Because the repair changes `RUNTIME_TREE`, Mq moved. The lane that had already
run could not be reused at the new commit — its records are stamped with the old
one — so it was archived as `l1-attempt-9ba714fd` with its digests published,
and a fresh L1 was created. It is contextual evidence: never credited, never
deleted.

### The scope audit could not survive its own merge

The S2 scope audit asked what the branch changes against main. On a branch that
is the right question; afterwards it is unanswerable. The moment PR #17 merged,
the diff emptied, all forty map entries read as stale, and CI on merged main
failed on the audit that had just passed on the PR — run `35120550355`, two
failures, both in that file. Each closed stage is now pinned to its own merge
range, whose two named commits cannot decay, and the in-flight stage keeps the
same audit against the merge base.

### Four Tier-2 tests described the day they were written

They seeded themselves from a verbatim copy of the committed publication record
and asserted that record was empty — indistinguishable from correct while Tier 2
had never been used, and wrong the first time it was. They now start from an
empty document that still borrows the real record's shape and claims, and the
committed-record test asserts what is durable: it validates, every entry carries
per-file hashes, no entry carries evidence content, and it keeps saying a digest
is not a backup.

All three defects have the same shape. A check whose subject was the present
moment, written down as though it were a law.

---

## 6. What S3 and S3b did not do

```text
no T0                    no cohort            no cohort id
no registry value moved  freeze_t0 not run    19d7d7e not opened
no strategy, risk, admission or Dataset change
no artificial trade, threshold change, forced entry or exit
no external storage, cloud service, credential, paid infrastructure or remote
host provisioned, contacted or created
```

The FP-CONTROL-1 row is byte-identical, and the registry file is untouched by
this branch: the only branch permitted to write it is the freeze candidate.

---

## 7. T0 preconditions — contract §9

```text
S1 merged                                      YES
S2 merged                                      YES
S3 PASS                                        YES — this record
S3b merged                                     NO  — this PR
qualification certificate valid                YES — 9780df85…, sealed while live
SEMANTIC_IDENTITY(Mq) == (M1)                  NOT YET PROVABLE — M1 does not exist
fresh L2 exists and is empty                   NOT YET — L2 is created at S5a;
                                               the lane is currently empty
Dataset lock PASS                              YES
Tier 1 + Tier 2 satisfied                      YES
second device used when available/healthy      YES — available, used, re-verified
strategy/risk/Dataset authority unchanged      YES
REAL_MONEY_AUTHORIZED = NO                     YES
docs/p2/OWNER_T0_AUTHORIZATION.md merged       NO  — Owner only, stage S4

T0_PRECONDITIONS = NOT_YET
```

`T0_PRECONDITIONS = PASS` is not reported and must not be inferred from the
gates above. Three of the twelve are open, and two of them are the Owner's:
merging S3b, then granting authorization. Independent-host storage is not among
the twelve and is not a blocker.

---

## 8. What this record does not claim

No prospective edge. No profitability. No forward-paper result. No lifecycle
evidence of any kind. No Paper Beta acceptance. No controlled-live readiness. No
host-loss redundancy.

S3 says one thing: at `af17c3b8`, on this host, a pre-T0 qualification instance
can be started, restarted, proven, sealed and stopped, with every record
attributable to exactly one commit, one role and one lane — and with the nine
pre-T0 properties re-established against the current source rather than
inherited from P1.

```text
PAPER / RESEARCH ONLY
REAL_MONEY_AUTHORIZED = NO
PROSPECTIVE_PAPER_EDGE = NOT_EVALUATED
```
