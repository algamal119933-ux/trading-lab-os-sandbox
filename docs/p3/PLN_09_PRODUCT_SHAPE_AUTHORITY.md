# P3-PLN-09 — Product-shape authority (identification record)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-09 and §6 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1). The master plan's §18.1 governs.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCH_AUTHORIZED = NO

The contract left PLN-09 **BLOCKED** until "the frozen product-shape reference (§18.1 'approved/frozen product shape') is identified", with the resolution "the Owner identifies or merges the product-shape authority".

On 2026-10-25 the Owner identified it by name and by the prototype's sha256 (directive "PRIORITIZE CONTROL ROOM"). This record brings the identified sources into the repository byte for byte, so that PLN-09 cites a reproducible artifact rather than a host path. **Merging this record is the Owner's act that unblocks PLN-09.** Until it merges, PLN-09 implementation stays on branches.

## 1. Sources: recovered, read directly, hash-verified
They were recovered from `~/Documents/TLOS-Owner-Input/` on hamza-workstation. Copies are in [`product_shape/`](product_shape/), with digests in [`product_shape/SOURCES.sha256`](product_shape/SOURCES.sha256).

| Role | File | sha256 | Verified against |
|---|---|---|---|
| **Frozen prototype** (Level-A §4) | `Trading_Lab_OS_Prototype_v0.2.5_FINAL.html` (181,633 B) | `e17d50dc9c8d0e6f6a629c4f215441ba4d00457d0e18a6eb5b45261c6651e3d9` | the Owner directive's expected hash ✓, and the Level-A record §4 ✓ (byte-identical to the AR_DESKTOP_PATCH candidate) |
| **Level-A freeze record** v1.0 (2026-09-26) | `Trading_Lab_OS_LEVEL_A_FREEZE_RECORD_v1.0.md` | `d38c39bd31f1d3ca5d5055e7abf78648b4562242ded62045b0085e5e415bbe58` | the prefix cited by the P3 planning drafts ✓ |
| **Approved visual direction** (2026-09-24) | `TLOS_Control_Room_Approved_Design.md` | `8a4fa4bd69ec94f97959ce87550aaa97670d1c4329107945020c8807da765b78` | Level-A §1 source 6 prefix ✓. The copy at `~/Downloads/Trading_Lab_OS_P3_Control_Room_Approved_Design.md` is byte-identical |
| **Final Master Product Shape Lock v1.2** (2026-09-25) | Appendix A of `Trading_Lab_OS_CLAUDE_NEW_SESSION_PACK_v1.0.md` (lines 1003 to end) | the pack: `2ddbe7720663cbd09e518f6be962f0426ab7862b8f662ae5ca0b68dbe3a17f95` | Level-A cites Shape Lock §14, §16.1, §42, §43, §59 and §63, all present ✓. No earlier record pins the pack's digest, so it is pinned here for the first time |

Authority chain:
```text
Shape Lock v1.2 (Owner product intent; self-labelled PRE-CANONICAL, freeze order in §63)
  → §63 gate executed: six-source reconciliation PASS · regression 1633/1633 · Owner walkthrough 15/15
  → LEVEL-A FREEZE RECORD v1.0: PRODUCT_SHAPE = CLOSED · NO_REOPEN_LAW = ACTIVE
  → frozen prototype v0.2.5 FINAL (e17d50dc…) = the shape (non-production, static mock data)
  → this record on main (Owner merge) = the §18.1 reference the frozen P3 contract requires
```

**Not authority:** the P3 planning drafts in `~/Documents/TLOS-Owner-Input/P3-Planning-Drafts/` (`P3_CONTROL_ROOM_SPEC.md` 8295289…, `P3_DESIGN_SYSTEM.md` 8e45d95…). Each declares itself "PLANNING DRAFT · EXTRACTION ONLY · NOT AUTHORITY". They are not committed. PLN-09 may use them only as an index into the prototype, and the prototype wins wherever they differ. `~/Downloads/final-product-shape.md` and the Manager Pack's `10_PRODUCT_CONTROL_ROOM.md` are later summaries and are not authority either.

## 2. Reconciliation with the frozen P3 contract
| Point | Frozen P3 contract / master plan | Product-shape authority | Verdict |
|---|---|---|---|
| Screen set | §18: 11 sections | Level-A §6.1: those 11 plus Settings = **12** | consistent. Settings is a platform page, not a new section |
| Purpose | PLN-09 realises the shape; it never reopens it (§18.1) | NO_REOPEN_LAW active (Level-A §6.2) | consistent |
| Evidence authority | the UI is never evidence authority (§23) | "The UI is an operator surface, not trading authority" (visual direction) | consistent |
| Language | Arabic/English | full RTL/LTR; Arabic glossary frozen; Operations = العمليات, Runtime = التشغيل (Level-A §5) | consistent. The canonical terms are Level-A's |
| Reuse | NEW_CONTROL_PLANE = NO (§10) | Level-C "live adapters, State Resolution" wait for P3 authority | consistent. Implement as a **read-only projection** of existing evidence, not a new control plane |
| Level-B schemas | — | "BIND IN PLN-02" (ProjectState, field authority, freshness) | **delta, not a conflict.** The contract's PLN-02 became the host state inventory, so the ProjectState binding moves into the PLN-09 adapter, with field authority per Shape Lock §32 |
| Stage display | P3 EXECUTING | the prototype's stage chip and ladder show P2 states (P3 "not authorized") | **delta, not a conflict.** The stage chip and Project-now chips are existing slots whose text is data, so live data fills them. No new slot |
| Visual fidelity | — | the third mockup image is not on the host (Level-A §6.3.4) | pixel fidelity to that image is not claimed. The prototype is the reference |

`REAL_CONFLICTS = 0` · `P0_GOVERNING_CONTRADICTIONS = 0`, so there is no basis to reopen anything.

## 3. Implementation rule for PLN-09 (binding on the implementing PRs)
- The frozen prototype's bytes are used **verbatim** as the component library and layout. A live build appends one adapter script that supplies a live scenario from verified evidence and re-declares only the data-bearing component functions, with the **same markup and classes**. No new screen, slot, navigation item or visual family.
- The build refuses to run if the prototype's sha256 is not `e17d50dc…`.
- It is offline and static (the prototype's CSP is kept: `connect-src 'none'`). The view carries its own observation time, and the existing stale-view treatment applies when it ages.
- Every displayed field traces to a repository tool or record. Anything unobserved is shown as unknown, never as healthy.
- The order follows the Owner directive: the **Command Center** first, then the remaining 11 screens.
