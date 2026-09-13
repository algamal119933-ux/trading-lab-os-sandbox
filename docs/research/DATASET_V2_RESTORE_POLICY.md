# Dataset V2 — restore policy

```text
DATASET_V2_RESTORE_POLICY = LOCK_VERIFIED_RESTORATION_ALLOWED
```

Dataset V2's payload is not present on the native Ubuntu host: it was never in
Git, and the migration carried committed history only. This document records
what is permitted to put it back, and on what terms. **Nothing was downloaded to
write this policy, and this policy does not itself authorise a download run.**

## The distinction this policy rests on

| | |
| --- | --- |
| **Restoration** | putting back a payload whose identity is decided by the existing frozen lock. The lock is the judge; the restored files either match it or they are rejected. |
| **Reacquisition** | acquiring a dataset and freezing what comes back. This produces a second set of authoritative hashes and forks the provenance, which is the harm `TL_FP_BOOT_1_V2_ADOPTION.md` §1 prohibits. |

Restoration is allowed. Reacquisition is not, and the difference is not a matter
of intent: it is whether a lock is written at the end. Under this policy no lock
is written, so a restore cannot become an acquisition by accident.

## Conditions — all of them, every time

1. **The existing frozen lock is unchanged.**
   `research/datasets/dataset_v2.lock.json` is read-only for the whole
   operation. Its `status` stays `frozen`, its digests, coverage figures,
   integrity results and provenance are not edited, reordered or regenerated.
2. **No new freeze.** No lock file is written, no `--freeze`-style path is run,
   no fingerprint is transcribed into any lock. A restore produces data and a
   verdict, never a new authority.
3. **Canonical digests must match**, all four, exactly:
   `CANONICAL_CANDLE_V1` over BTC/USDT 1h, BTC/USDT 5m, ETH/USDT 1h, ETH/USDT 5m.
4. **Raw Feather hashes must match explicitly**, all four, and are checked and
   reported as their own result rather than folded into the canonical verdict.
5. **Immediate FAIL on any mismatch** — canonical or raw. A failing restore
   stops there: the mismatching files are not used, not partially accepted, not
   repaired, and no run proceeds against them. The mismatch is reported to the
   Owner for adjudication.

## One thing the current tooling does not do

`scripts/audit_data.py --gate lock` treats a raw-file-hash mismatch as a *note*
when the canonical digest still matches, on the stated reasoning that a PyArrow
version or compression change moves the file hash while the market data is
identical (the lock's own `integrity_contract.why` says the same).

Condition 4 above is **stricter** than that. Under this policy a raw mismatch is
a FAIL, not a note. That difference is recorded rather than resolved quietly:

* the gate as it stands does not enforce condition 4 on its own;
* so a restore run under this policy must check the four raw hashes explicitly
  and treat any mismatch as a stop, whether or not the gate prints `PASS`;
* changing the gate's behaviour is a separate, separately authorised change. It
  is **not** made here, and this policy does not silently reinterpret the lock's
  existing serialization clause.

## Verdict tokens

```text
DATASET_LOCK_GATE = PASS   only with 4/4 canonical and 4/4 raw hashes matching
DATASET_RESTORE   = FAIL   on any mismatch — stop, report, do not proceed
```

## Scope

This policy covers restoring an already-frozen dataset onto a host that lost its
copy. It authorises no new acquisition window, no change of pairs, timeframes or
date range, and no re-examination of the Development or Validation windows,
whose status in the lock is unchanged: Development closed, Validation spent.
