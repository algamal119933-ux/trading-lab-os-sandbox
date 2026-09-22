# S8 — FRESH PRE-T0 QUALIFICATION OF FP-CONTROL-3, AND THE BINDING

**Stage:** `P2 — PROSPECTIVE PAPER PROOF`.
**Authority:** [`P2_CONTRACT.md`](P2_CONTRACT.md) §6 and §9, and the merged
[`OWNER_REPLACEMENT_AUTHORIZATION.md`](OWNER_REPLACEMENT_AUTHORIZATION.md).
This record does not restate either and does not extend either.

```text
Mq                      909bf5fa551e9cb4351de6eb40cc42f9cbe28cbd
CERTIFICATE_SHA256      b339c995943649dd3cbfead74cbef92a6cb103517ad1eae4485b8bdbde31e8ec
SEMANTIC_IDENTITY(Mq)   04578497dc515a87c404e10fac61e9c451ff35f4097667eadb549da303f7dfba

CREATED                 no T0 · no cohort · no cohort id · no prospective evidence
CHANGED                 no strategy semantics · no risk semantics · no Dataset authority
SECOND_PHYSICAL_DEVICE  NOT AVAILABLE   HOST_LOSS_REDUNDANCY = NOT_PROVEN
PAPER / RESEARCH ONLY                   REAL_MONEY_AUTHORIZED = NO
```

S8 re-establishes the nine pre-T0 qualifiable properties for the successor
control, against the **repaired** tooling merged by the recovery transaction, on
a lane created fresh for the purpose and destroyed into an archive afterwards.
It binds what that run observed and the certificate it produced, and it carries
the Owner's T0 authorization for the successor. Nothing here freezes anything.

---

## 1. Why this qualification exists, and why nothing was reused

`FP-CONTROL-2` is `CLOSED` under §11 class B. Its activation could not be
certified because the frozen activation contract was internally unsatisfiable,
and the repair lived inside `RUNTIME_TREE`, which a frozen cohort cannot consume.
The recovery transaction repaired it. This stage qualifies the successor against
that repair.

Nothing from the predecessor is carried across, and the crediting law is what
refuses it rather than a promise made here:

```text
Mq              af17c3b8 → 909bf5fa   a different system: the repair is in it
certificate     9780df85 → b339c995   the product of this run, not that one
lane            fp-control-2 → fp-control-3   fresh, created empty, archived whole
T0 / cohort_id  not created by this stage at all
credit          zero records inherited; no FP-CONTROL-1 or FP-CONTROL-2 record
                may be credited to FP-CONTROL-3, on cohort_id alone
```

## 2. What the qualification run did

```text
start  → 1998 backfilled candles (999 × BTC/USDT, ETH/USDT) at 1h
stop   → start  the restart drill, same commit, tracked tree clean, nothing committed between
wait   → the 17:00–18:00 candle closed and was captured LIVE by the RESTARTED run
gates  → runtime-attached preflight · reconciliation
seal   → the certificate, generated WHILE THE LANE WAS LIVE
stop   → archive the whole lane → publish digests
```

The restart came before the boundary deliberately, for the reason S3 recorded: a
restart followed by no further live bar leaves `restart_recovery` half-proved —
it shows the process came back, not that it resumed observing. The lane ends
with two live bars in the first run and two in the second.

```text
input      2000   tip 5fbfad293a974a0b
decision   2000   tip b3788f08bf7ed8d1
incident      3   tip 3db2c078b0aa4c85
trade         0   tip 0000000000000000
daily_pack_digest 11c877ed76b175a9f26634f4ea2c257066755927e6ea5c3f83be91c4001217eb

runs            2 (run_started restart_counter 0, then 1), 2 distinct run ids
bar_class       1996 WARMUP + 4 LIVE; the 4 LIVE split 2 / 2 across the restart
t0_relation     T0_NOT_FROZEN on all 2000 decisions
cohort_id       null on all 2000 records
source_commit   909bf5fa on all 2000 records, and on no other value
uniqueness      2000 distinct (pair, candle) decisions out of 2000
chains          all four verify from genesis, before and after the restart
```

The third incident is a `freqtrade_api_unreachable` observation recorded at
`2026-09-22T17:30:37Z`, while the restarted engine was still coming up and the
capture loop polled it. It is a truthful record of a transient startup state,
not a defect, and it is kept rather than tidied away.

`trade 0` is not an omission. The strategy signalled `hold` on every live bar it
saw, and §7's prohibition is absolute: nothing may be done to make a trade
happen. The three lifecycle properties are not this stage's to evidence.

### The gates, at Mq

```text
preflight   16/16 PASS   --require-pass exit 0
            T0_PERMITTED = YES · FP_RUNTIME_READINESS = PASS
            FP_INFRASTRUCTURE_SCAFFOLD_VALIDATION = PASS
reconcile   14/14 PASS   --require-pass exit 0
            including registry_source_commit_equivalence, the P2 finding
dataset     DATASET_LOCK_GATE = PASS (content matches the frozen lock), exit 0
repo        REPO_CHECK_PASS · PAPER_GUARD_PASS
```

The acquisition verdict printed beside the dataset gate reads `FAIL`, which is
the expected output for a frozen dataset and is documented in
[`S3_LIVE_PRE_T0_QUALIFICATION.md`](S3_LIVE_PRE_T0_QUALIFICATION.md) §2. The
binding question — is this still the same data — is `DATASET_LOCK_GATE`, and it
passes.

### The nine properties

The certificate carries exactly the nine pre-T0 qualifiable properties and none
of the three post-T0 lifecycle ones. `full_trade_lifecycle` is not among the
twelve at all and does not appear.

## 3. Durability, and what is different from S3

```text
TIER 1   artifacts/l1-qualification-909bf5fa — the whole lane, 7 files,
         each byte re-read from the destination and hashed against the source
         before the original was removed
TIER 2   research/fp/records/evidence_digest_publication.json — six entries now,
         counts, ledger tips, pack digests and every per-file hash
SECOND   SAME_HOST_SECOND_DEVICE = NO. scripts/second_device_discovery.py finds
DEVICE   no second physical device on this host: the repository is on nvme0n1
         and nothing else is mounted.
```

**This differs from S3, and it is recorded rather than worked around.** S3
replicated its archives to a WDC drive that is not attached to this host. §8 of
the contract makes Tier 1 and Tier 2 unconditional and the second device
conditional — *"an unavailable second device is NOT a return: it is recorded and
the cohort proceeds with Tier 1 and Tier 2"* — so this does not block the
freeze. `HOST_LOSS_REDUNDANCY` remains `NOT_PROVEN`, as it was when the device
was present: only a Tier-3 independent-host snapshot could change that, and that
is P3 scope.

The certificate is not in Git and is not replicated as a lane: it is a runtime
artifact under `artifacts/p2-s8-qualification/`, and the tracked thing is its
sha256, pinned in the binding. That is what lets a merge-gated authorization
refer to it. The superseded `artifacts/p2-s3-qualification/certificate.json` is
untouched: it is the predecessor's history, and the binding test now names this
qualification's artifact so that a stale certificate is never hashed against a
current pin.

## 4. The binding, and the repairs this stage made

`research/fp/records/p2_qualification_binding.json` pins Mq, the certificate's
sha256, `SEMANTIC_IDENTITY(Mq)` and the two class-O observations
(`image_digest`, `python_version`) taken from the engine while it ran. It binds;
it does not authorize. `tests/test_p2_qualification_binding.py` recomputes Mq's
reachability and the semantic identity from git objects rather than trusting
them.

Two ordinary defects were repaired here rather than raised as questions, both of
the same class the recovery transaction addressed — a constant that named one
cohort and therefore decayed at the first successor:

```text
research/schema/p2_qualification_binding.schema.json
    the role enum could not express FP-CONTROL-3, so the successor's own
    binding was unrepresentable

.github/gates/check_t0_authority.py
    ROLE was hardcoded to FP-CONTROL-2. The gate would have gone on auditing a
    CLOSED row's immutable T0 while the row actually under authorization moved
    unwatched. It now resolves the role it must judge — the Owner's merged
    authorization where one exists, otherwise the single row that has not
    closed — and never falls back to a CLOSED row, whose T0 no later branch can
    have created.
```

## 5. What this stage does not establish

```text
NOT an activation                nothing has been activated; that is a later gate
NOT a T0                         no T0, no cohort id, no RUNNING row
NOT prospective evidence         PROSPECTIVE_PAPER_EDGE = NOT_EVALUATED
NOT a lifecycle claim            full_trade_lifecycle is not evidenced here
NOT host-loss redundancy         Tier 1 + Tier 2 only, second device absent
NOT a candidate                  FP-CONTROL-3 is a CONTROL
```

```text
PAPER / RESEARCH ONLY
REAL_MONEY_AUTHORIZED = NO
P3 NOT STARTED · NOT AUTHORIZED
```
