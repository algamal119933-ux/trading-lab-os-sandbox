# COMMERCIAL-VERIFICATION-LANE-1: Freqtrade Strategy Verification

**Status:** ACTIVE on Owner merge, under `docs/governance/CONTINUOUS_EXECUTION_AUTHORITY_1.md` (CEA-1).
**Machine-readable charter:** `charters/COMMERCIAL-VERIFICATION-LANE-1.json`. It governs execution, and this
record governs interpretation. Changing either is an Owner merge (both are protected).

## Product

One paid product: **Freqtrade Strategy Verification**. Intake and triage are free, and the service runs concierge
first: a human runs each case.

**Not built:** SaaS, dashboard, database, agent framework, generic workflow engine.

## Where it lives

- Code lives in `verification/**`, with its tests in `tests/test_verification_*.py`. These are outside RUNTIME_TREE
  and outside every protected path (`.github/gates/check_charters.py` proves it).
- Customer code and customer data are never committed. They never enter a cloud executor and never touch the P2
  host. A case runs only on a non-P2 machine, launched by a human.
- A unit's PR may change only those paths plus `MANIFEST.txt`.

## Governing principle

```text
PRE-PAID:        build only sample report + intake + minimum isolated runner.
AFTER EVIDENCE:  automate / generalise only what proved necessary.
```

## Units

| Unit | What | Merge | Eligible when |
|---|---|---|---|
| CV-01 | Sample report on a licence-clean public Freqtrade strategy | AUTO | immediately after AUTH-1 |
| CV-02 | Minimum intake / triage (form, checklist, rubric) | AUTO | immediately after AUTH-1 |
| CV-03 | Minimum isolated runner | AUTO | immediately after AUTH-1 |
| CV-03P | Protected driver/funnel generalisation | **OWNER** | only on evidence (below) |
| CV-1x | Automate a step with recorded manual minutes in a paid case | AUTO | ≥ 1 paid + a manual-minutes ticket |
| CV-MVP | One-command case | AUTO | ≥ 3 paid tickets, if demand supports it |

"AUTO" means the unit may be auto-merged once CEA-1 §5 holds. Until then every merge is the Owner's.

**CV-03 requirements.** It sandboxes the execution of a customer or public strategy. Untrusted strategy code gets
no network. The engine and container are pinned. No customer code or data is committed. It uses the existing
repository capabilities and interfaces **as-is**, and it does **not** modify `research/cycle2/**`.

**CV-03P** is **not** a prerequisite for CV-03 and is **not** opened automatically before paid demand. It becomes
eligible only when an evidence ticket shows one of these:

```text
EXISTING_INTERFACE_BLOCKER   demonstrated by the minimum runner
OR
PAID_CASE_MANUAL_WORK        repeated work in paid cases (≥ 2 manual-minutes tickets, each tied to a paid case)
                             that the generalisation removes
```

It stays protected because it touches `research/cycle2/**`. The scientific engine is never generalised merely
because it may eventually be useful.

## Value gates

| Stage | Allowed | Exit gate |
|---|---|---|
| PRE-PAID | CV-01, CV-02, CV-03 | ≥ 1 paid ticket |
| AFTER FIRST PAID | CV-1x: automate only steps with recorded manual minutes in a paid case | ≥ 3 paid tickets |
| AFTER 3–5 PAID | CV-MVP, only if recorded demand supports it | — |

## Stop law (frozen market test)

```text
WINDOW            14 days from the Owner's first logged outreach          (OWNER MAY EDIT BEFORE MERGE)
MINIMUM CONTACTS  25 logged contacts                                       (OWNER MAY EDIT BEFORE MERGE)
0 PAID AT END     STOP commercial building. A pivot needs a charter amendment merged by the Owner.
```

## Evidence tickets

Tickets live at `charters/tickets/COMMERCIAL-VERIFICATION-LANE-1/<id>.json` and follow `charters/ticket.schema.json`.

- Fields: kind (`paid` · `manual_minutes` · `failing_case` · `existing_interface_blocker`), case id, minutes,
  date and a short summary.
- A ticket has no field for a customer's name, contact, code or data.
- A `manual_minutes` ticket must name the case id of a `paid` ticket.

## Owner only

Price · payment account · client / legal terms · branding · outreach identity and outreach itself · spend above cap
· scope expansion · the CV-03P merge.
