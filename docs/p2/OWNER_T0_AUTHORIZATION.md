# OWNER T0 AUTHORIZATION — FP-CONTROL-2

**Granted by:** the Owner, and by no one else. This file exists only because the
Owner decided it should; it is created by an Owner-merged PR at the moment
authority is granted, and never before.

**Authority:** [`P2_CONTRACT.md`](P2_CONTRACT.md) §6 and §9. This record does not
restate the contract and does not extend it.

This is **PAPER-ONLY** authority. It authorizes one act: freezing the T0 of the
`FP-CONTROL-2` control cohort, under the frozen P2 contract, against the
qualification run named below. It authorizes nothing else — no real money, no
strategy change, no risk change, no Dataset change, no candidate, no live
trading, and no P3 scope.

---

## The authorization

```text
ROLE = FP-CONTROL-2
QUALIFICATION_COMMIT = af17c3b80dad535b524e5ffbe40bef0785b3f605
QUALIFICATION_CERTIFICATE_SHA256 = 9780df85a8d05b7534d7cc46f9ea0114a325f668a185011edf1a26092211f915
EXPIRES_UTC = 2026-09-23T18:00:00Z
REAL_MONEY_AUTHORIZED = NO
```

Each field appears exactly once, by requirement: a file that says two things
about one field is not an authorization but an ambiguity, and resolving it would
mean choosing on the Owner's behalf.

---

## What each value is, and what checks it

`scripts/freeze_t0.py` reads this file with `git show HEAD:` — from Git, never
from the working tree. A working-tree read would make "the Owner authorized
this" a claim anyone with write access to the checkout could manufacture, which
is the entire distinction between a merge and a file.

| Field | Value | Checked against |
| --- | --- | --- |
| role | the control cohort this authorizes | the registry row, and the S3b binding |
| qualification commit | `af17c3b8`, the commit at which the pre-T0 gates actually passed | must be an ancestor of HEAD, and must equal the commit the merged S3b binding records |
| certificate sha256 | `9780df85…`, the S3 qualification certificate | must equal the sha256 pinned by the merged S3b binding — the Owner authorizes one qualification run, not any run |
| expiry | `2026-09-23T18:00:00Z` | must be in the future when the freeze runs |
| real money | `NO` | the only admissible value in this repository |

The expiry is not a formality. An authorization that never expires is one that
outlives the state it was granted against: the qualification it names was taken
on a particular host, at a particular commit, with a particular runtime
observed, and none of those facts stay true indefinitely. If it lapses before
the freeze is executed, the Owner grants a new one against a fresh
qualification — nothing here may be extended in place.

---

## What this file does not do

```text
it does not freeze a T0          freeze_t0 does that, and only when run
it does not create a cohort      no cohort id exists until the freeze transaction merges
it does not create or start L2   S5a and S5f, both after this
it does not write the registry   the freeze candidate is the only branch permitted to
it does not authorize real money the project is PAPER / RESEARCH ONLY
it does not convert a control    FP-CONTROL-2 is a CONTROL, not a candidate
it does not open 19d7d7e, P3, or any candidate research
```

Merging this file changes no runtime, strategy, risk, Dataset, registry,
qualification, evidence or admission semantics. After it is merged the registry
still reads `NOT_STARTED`, with a null T0 and a null cohort id, and the freeze
remains a separate Owner-reviewed transaction of exactly two files and exactly
seven values, gated in CI by `scripts/check_freeze_candidate.py`.

The prospective paper edge of this cohort is not evaluated by this file, by the
freeze, or by any lawful P2 outcome.

```text
PAPER / RESEARCH ONLY
```
