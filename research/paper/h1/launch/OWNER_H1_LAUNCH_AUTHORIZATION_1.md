# OWNER H1 LAUNCH AUTHORIZATION 1 — H1-PAPER-COHORT-1 (prepared; NOT GRANTED)

**State: PREPARED, NOT GRANTED.** This file is the record through which the Owner may later grant
`H1_LAUNCH_AUTHORIZATION` ([`H1_LAUNCH_BINDER.md`](H1_LAUNCH_BINDER.md) §5 step 7). It was prepared
on the Owner directive of 2026-10-26 "PRIORITY 4 — H1 PAPER AUTHORIZATION", which says: *"Do not
interpret preparation or PR merge as permission to launch. H1_LAUNCH_AUTHORIZED remains NO until
explicitly and independently granted."*

**Merging this record does NOT authorize launch.** Launch requires a separate, explicit Owner grant
that changes `H1_LAUNCH_AUTHORIZED` to `YES` in its own Owner PR. That grant is valid only after a
`READY_FOR_OWNER_AUTHORIZATION` card (`h1_launch_card.py`) dated within `CARD_MAX_AGE_HOURS` of the
grant merge, whose JSON path and sha256 the grant names. Until then the binder's default stands:
**DENY.** No launch tool reads this file. It authorizes nothing by being present.

PAPER / DRY-RUN ONLY · H1 is not a P3 dependency (P3 contract §1 and the PLN-00 reconciliation) and
this record is not P3 scope.

## The record

```text
AUTHORIZATION            = H1_LAUNCH_AUTHORIZATION
H1_LAUNCH_AUTHORIZED     = NO
PACKAGE                  = H1-PAPER-COHORT-PACKAGE-1 v1.0.0
PACKAGE_MANIFEST_SHA256  = ef9a3d0c5b5b9abe122faaa1bd4ef67feb0c3ec4437bed56cd6ef33d910bc43c
COHORT_ID                = H1-PAPER-COHORT-1
CANDIDATE                = H1_EMACROSS
MODE                     = PAPER / DRY-RUN ONLY · Binance spot BTC/USDT 1h long-only · 100 USDT simulated wallet
HOST                     = hamza-workstation
PLACEMENT                = HOST_PLACEMENT = PASS required (no P2 container running); no same-host exception record
LANE_DIR                 = /home/hamza/tlos-paper/h1-paper-cohort-1
SECOND_EVIDENCE_STORE    = <SET AT GRANT: Owner-named directory on a different device from LANE_DIR>
LAUNCH_CARD_JSON         = <SET AT GRANT: path of a READY_FOR_OWNER_AUTHORIZATION card JSON>
LAUNCH_CARD_SHA256       = <SET AT GRANT: sha256 of that card JSON>
CARD_MAX_AGE_HOURS       = 24
T0_RULE                  = PAPER_T0 is the recorded_utc of the lane's first COHORT_START incident; nothing before T0 is prospective evidence
WINDOW                   = ACTIVATION_UTC + 10 days (H1-WINDOW-AMENDMENT-1); no extension, no early stop for performance
EDGE_EVIDENCE            = NOT_EVALUATED
EXPIRES_UTC              = <SET AT GRANT: an unused grant lapses at this time>
REAL_MONEY_AUTHORIZED    = NO
```

Each field appears exactly once (the precedent of `docs/p3/OWNER_P3_EXECUTION_AUTHORIZATION.md`).
`tests/test_h1_launch_authorization_record.py` enforces the shape. While `H1_LAUNCH_AUTHORIZED = NO`
the not-a-grant clause above must be present. A `YES` without a concrete card path, a 64-hex card
sha256, a concrete second store and a concrete `EXPIRES_UTC` fails the test, so a half-filled grant
cannot merge through CI.

## Readiness evidence at preparation (2026-10-26)

Repository-only rows, run in the cloud at `main` `8f673eb448b3490710a90c0caedabbd30d561e24`:

| Card row | Result |
|---|---|
| P2_TERMINAL_STATUS / P2_CLOSURE_DIGEST | PASS · `H1_ENTRY_ELIGIBLE` · CLOSED / PASS · closure `f5b45013…f198a0` |
| G11_RECORDS_PR_STATUS | PASS (MERGED) |
| H1_WINDOW_AMENDMENT | PASS (ADOPTED) |
| H1_PACKAGE_DIGEST | PASS · `h1_paper.py verify` = PASS · `ef9a3d0c…bc43c` |
| PAPER_GUARD / DRY_RUN | PASS / `true` |
| REAL_MONEY_AUTHORIZED | NO |

Host rows, which cannot be observed from the cloud and so are **not claimed**: `SOURCE_SHA256_STATUS`,
`MATERIALISATION_PREFLIGHT` (including ≥ 20 GB free on the lane's filesystem), `HOST_PLACEMENT`,
`SECOND_EVIDENCE_STORE`. The last host card (P2 closure report, 2026-10-24) was 11/12, failing only
`MATERIALISATION_PREFLIGHT` on capacity. Root has since been reported at 163 GiB free (Owner-run `df`,
2026-10-26). The card must be re-run on the host before any grant.

## What a grant requires, in order

1. The host card re-run reads `READY_FOR_OWNER_AUTHORIZATION`, at a commit whose card code equals `main`.
2. The Owner names `SECOND_EVIDENCE_STORE`.
3. A separate Owner PR sets `H1_LAUNCH_AUTHORIZED = YES` and fills the four `SET AT GRANT` fields, and
   the Owner merges it (normal two-parent merge).
4. Only then does the binder's §5 launch sequence run, step by step, stopping at any unexpected verdict.

No real order, exchange key or money is involved at any step.
