# P3-PLN-11 — Execution pack structure (DRAFT / NOT FROZEN)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-11 and §8 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1).
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCH_AUTHORIZED = NO

**Contract acceptance:** the closure record is merged by the Owner, and the pack is reproducible from Git plus digests.

**Status: preparation only.** This record and `research/p3/exec_pack.py` define the pack's structure and how it is
generated. The pack is **not frozen**, P3 is **not closed**, and nothing here claims PASS. The freeze happens only after
the PLN-10 run is accepted by the Owner, at the commit that run used.

## 1. Pack contents
The generator writes one directory per build. Every JSON file carries `"status": "DRAFT_NOT_FROZEN"` and the commit it
was built from.

| File | Content | Source |
|---|---|---|
| `version_inventory.json` | Container images declared in the compose files (an overridable default is shown with its variable). Pinned Python packages (`==`) from the requirement files. A list of images with no tag or `:latest` | `docker-compose.yml`, `docker-compose.fp.yml`, `scripts/p3/ops/docker-compose.p3-ops.yml`, `requirements*.txt` |
| `source_digests.json` | Git object id (tree or blob) of each governed path at the commit. A missing path is recorded as `MISSING`, never skipped | `GOVERNED_PATHS` in the generator |
| `runbook_index.json` | Every `docs/p3` document whose name or title marks it as a runbook, procedure, program or checklist, with its blob id | `docs/p3/*.md` |
| `evidence_index.json` | Every `docs/p3/PLN_*` execution record, with the status lines it declares | `docs/p3/PLN_*.md` |
| `acceptance_mapping.json` | Every PLN-10 acceptance criterion, as `PENDING_EVIDENCE` until the run's records exist. If the program is absent at the commit, the whole mapping is `PENDING` | `research/p3/acceptance.py` (PLN-10 draft) |
| `POST_BETA_HANDOFF_TEMPLATE.md` | The handoff skeleton. Every field stays `TBD` until the closure record is merged. It grants nothing | the generator |
| `PACK_MANIFEST.json` | sha256 of each file, plus `frozen: false`, `p3_closed: false` and `real_money_authorized: false` | the generator |

**Reproducibility:** the generator reads Git objects (`git show <commit>:<path>`), never the working tree. Two builds of
the same commit therefore produce identical file digests, and a test enforces this. It refuses to write into a non-empty
directory, so a pack is never written over.

## 2. Governed paths (initial set)
- `CLAUDE.md`
- `docs/p3`
- the master plan
- `research/p3`
- `scripts/p3`
- `scripts/paper_guard.py`
- the paper config example
- the FP cohort registry
- `docker-compose.yml`
- `docker-compose.fp.yml`

Changing this set is a reviewed change to `GOVERNED_PATHS`.

## 3. How to build a draft
This can run in any clone, and it runs nothing on the host:
```bash
python3 -c "import sys; sys.path.insert(0,'research'); from p3 import exec_pack; print(exec_pack.build('.', 'origin/main', '/tmp/tlos-pack-draft'))"
```

## 4. Freeze rule (later, not now)
The pack becomes `FROZEN` only through a separate Owner-merged PR, and only when all of these hold:
1. The PLN-10 run verdict is `CANDIDATE_FOR_OWNER_ACCEPTANCE`, and the Owner's acceptance record is merged.
2. The pack is built at the PLN-10 run commit. Its `acceptance_mapping` cites the run's evidence records, with no `PENDING_EVIDENCE` left.
3. `unpinned_images` is empty, or each entry is accepted by the Owner in writing.
4. No governed path is `MISSING`.
5. The P3 closure record (contract §8) cites the frozen pack's manifest digest.

## 5. Not claimed
No freeze, no PASS, no P3 closure, no POST-BETA authority, no real money.
