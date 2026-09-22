# OWNER T0 AUTHORIZATION — FP-CONTROL-3

**Granted by:** the Owner, and by no one else. This file exists only because the
Owner decided it should; it is created by an Owner-merged PR at the moment
authority is granted, and never before.

**Authority:** [`P2_CONTRACT.md`](P2_CONTRACT.md) §6 and §9, together with the
merged [`OWNER_REPLACEMENT_AUTHORIZATION.md`](OWNER_REPLACEMENT_AUTHORIZATION.md),
which is what permits a successor cohort to exist at all. This record does not
restate either and does not extend either.

This is **PAPER-ONLY** authority. It authorizes one act: freezing the T0 of the
`FP-CONTROL-3` control cohort, under the frozen P2 contract, against the
qualification run named below. It authorizes nothing else — no real money, no
strategy change, no risk change, no Dataset change, no candidate, no live
trading, and no P3 scope.

---

## The authorization

```text
ROLE = FP-CONTROL-3
QUALIFICATION_COMMIT = 909bf5fa551e9cb4351de6eb40cc42f9cbe28cbd
QUALIFICATION_CERTIFICATE_SHA256 = b339c995943649dd3cbfead74cbef92a6cb103517ad1eae4485b8bdbde31e8ec
EXPIRES_UTC = 2026-09-25T00:00:00Z
REAL_MONEY_AUTHORIZED = NO
```

Each field appears exactly once, by requirement: a file that says two things
about one field is not an authorization but an ambiguity, and resolving it would
mean choosing on the Owner's behalf.

---

## Why this authorization is not the previous one

The authorization this file replaces named `FP-CONTROL-2`, qualification commit
`af17c3b8` and certificate `9780df85…`. That cohort is `CLOSED` under §11 class
B, and its closure record is
[`FP_CONTROL_2_COHORT_CLOSURE.md`](FP_CONTROL_2_COHORT_CLOSURE.md). None of its
values may be carried across:

```text
its T0            2026-09-20T12:00:00Z    spent, immutable, never reused
its cohort_id     FP-CONTROL-2-20260920…  spent, immutable, never reused
its Mq            af17c3b8                a commit whose activation tooling was
                                          the defect; superseded by the repair
its certificate   9780df85…               the product of that run, not this one
its lane          fp-control-2            archived whole and sealed
```

A replacement that reused any of them would be the same cohort wearing a new
name, and the crediting law exists precisely to refuse that.

## What each value is, and what checks it

`scripts/freeze_t0.py` reads this file with `git show HEAD:` — from Git, never
from the working tree. A working-tree read would make "the Owner authorized
this" a claim anyone with write access to the checkout could manufacture, which
is the entire distinction between a merge and a file.

| Field | Value | Checked against |
| --- | --- | --- |
| role | the successor control cohort this authorizes | the registry row, and the merged binding |
| qualification commit | `909bf5fa`, the commit at which the runtime-attached pre-T0 gates actually passed | must be an ancestor of HEAD, and must equal the commit the merged binding records |
| certificate sha256 | `b339c995…`, the fresh qualification certificate | must equal the sha256 pinned by the merged binding — the Owner authorizes one qualification run, not any run |
| expiry | `2026-09-25T00:00:00Z` | must be in the future when the freeze runs |
| real money | `NO` | the only admissible value in this repository |

The expiry is not a formality. An authorization that never expires is one that
outlives the state it was granted against: the qualification it names was taken
on a particular host, at a particular commit, with a particular runtime
observed, and none of those facts stay true indefinitely. It is set to span the
freeze transaction, its review and the activation that follows, and no more. If
it lapses before the freeze is executed, the Owner grants a new one against a
fresh qualification — nothing here may be extended in place.

---

## What this file does not do

```text
it does not freeze a T0          freeze_t0 does that, and only when run
it does not create a cohort      no cohort id exists until the freeze transaction merges
it does not create or start L2   later transactions, both after this
it does not write the registry   the freeze candidate is the only branch permitted to
it does not authorize real money the project is PAPER / RESEARCH ONLY
it does not convert a control    FP-CONTROL-3 is a CONTROL, not a candidate, and a
                                 favourable result would not make it one
it does not grant a replacement  that is OWNER_REPLACEMENT_AUTHORIZATION.md, budget 1,
                                 already consumed by this successor when it is frozen
it does not open 19d7d7e, P3, or any candidate research
```

Merging this file changes no runtime, strategy, risk, Dataset, registry,
qualification, evidence or admission semantics. After it is merged the registry
still reads `NOT_STARTED` for `FP-CONTROL-3`, with a null T0 and a null cohort
id, and the freeze remains a separate Owner-reviewed transaction of exactly two
files and exactly seven values, gated in CI by
`scripts/check_freeze_candidate.py`.

The prospective paper edge of this cohort is not evaluated by this file, by the
freeze, or by any lawful P2 outcome.

```text
PAPER / RESEARCH ONLY
```

The paper-only trailer deliberately does not repeat `REAL_MONEY_AUTHORIZED`.
The parser matches that key on any line of this file and refuses a second
occurrence as an ambiguity, so the authorization states it exactly once, above.
