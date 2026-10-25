# P3-PLN-05 — Evidence Durability (execution record)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1).
**Acceptance (contract):**
- HOST_LOSS_REDUNDANCY = PROVEN by restoring from the independent host;
- every governed stop/start has an attributable record.

PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO

## Durability tiers today
| Tier | What | Status |
|---|---|---|
| 1 | sealed archives in `artifacts/` (same host, nvme) | 8 archives, ARCHIVE_VERIFIED |
| 2 | digests on GitHub (`evidence_digest_publication.json`) | published on main |
| same-host second device | WDC replicas, plus P3 backup sets `/mnt/tlos-wdc/tlos-backups/` (20261025T171416Z, 20261025T185052Z) | verified; restore drills PASS |
| **3** | **independent host** | **none exists. HOST_LOSS_REDUNDANCY = NOT_PROVEN** |

## Implemented
- `research/p3/offsite.py` and `scripts/p3/offsite.py`, reuse classification WRAP_EXISTING (rsync, sha256sum). They push a verified set to a local path or to `user@host:/path`, and verify it **on the destination**; for a remote target that means `sha256sum -c` over ssh. They are append-only: an existing copy is re-verified, never overwritten, and a divergent copy is reported as FAIL. An unverified source is never pushed. A remote PASS reports `host_loss_redundancy = CANDIDATE`. It becomes PROVEN only after a restore drill from that host.
- Tests: `tests/test_p3_offsite_and_units.py`.
- The attributable stop/start record is the operator ledger from PLN-08, merged in #76: hash-chained, with a reason required.

## Acceptance status
```text
ATTRIBUTABLE_STOP_START_RECORD   PASS (PLN-08 ledger; real drill recorded and verified)
HOST_LOSS_REDUNDANCY             NOT_PROVEN — needs an Owner-provided independent host (ssh-reachable
                                 user@host:/path with ~1 GB per set). Then: scripts/p3/offsite.py --set <newest>
                                 --dest <it>, and a restore drill from that host.
```
