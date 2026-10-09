# CONTINUOUS_EXECUTION_AUTHORITY_1 (CEA-1)

**Status:** ACTIVE on Owner merge. Auto-merge INACTIVE (§5).
**Authority:** Owner direction 2026-10-09: convert the accepted continuous-execution operating model into an
executable sequence. AUTH-1 is "Continuous Engineering + Commercial Charter", and "AUTH-1 itself is protected and
Owner-merged". Owner rule while GitHub platform enforcement is absent: `AUTO_IMPLEMENT = YES · AUTO_TEST = YES ·
AUTO_PR = YES · AUTO_MERGE = NO`.
**Classification:** GOVERNANCE + GATE TOOLING. NON-EXECUTING. This record runs nothing, dispatches nothing,
opens no research program and changes no runtime.
**Relationship to P2:** `docs/p2/P2_CONTRACT.md` is not modified. Its §10 ("OWNER ONLY: every merge to main")
stays in force for as long as P2 is open, which is why `p2_closed` is an activation condition (§5).
**Relationship to the Master Plan:** change record MP1-CR-002 (§22.1) records the §21 effect. The Master Plan
remains non-authorizing.

---

## §1 Scope

```text
IN SCOPE       engineering lane · commercial lane (through an ACTIVE charter under charters/)
               · research lane ONLY through an Owner-merged program charter (§12)
NEVER IN SCOPE P2 runtime and FP-CONTROL-3 · T0 / cohorts · P2 closure · P3 · paper admission ·
               real money · exchange keys · leverage / margin / futures / shorts · withdrawals
```

Anything not opened by an ACTIVE charter on `main` stays blocked. Charters live in `charters/` and are
validated by `.github/gates/check_charters.py` against `charters/charter.schema.json`.

## §2 Continuous execution and auto-advance

1. A unit may run only if an ACTIVE charter on `main` lists it **and** its prerequisites hold on `main`.
2. After a unit reaches a terminal result, the resolver (`.github/gates/resolve_next_unit.py`) selects the next
   eligible unit. Ordinary work never asks the Owner "continue?".
3. A blocker parks only its own lane. Each blocker carries a class:

```text
ENGINEERING           repair within §7 budget
SCIENTIFIC_NEGATIVE   follow the predefined edge (§12)
AUTHORITY             WAIT_FOR_OWNER — that lane only
SAFETY                stop that scope
EXTERNAL              backoff, then park until the next tick
```

4. The governing question at every resolution: *what authorized useful work remains unblocked?*

## §3 Protected verification paths

`.github/gates/protected_paths.txt` lists every path that judges, authorizes, guards, or defines acceptance. The
list is read from the PR's **base**, never from its head, and the list protects itself. A PR touching any listed
path is `OWNER_MERGE_REQUIRED`.

## §4 Base-policy merge law

> **A PR is judged only by policy and verifiers taken from the protected BASE (main) state. A PR that changes any
> protected verification path is never auto-merged.**

```text
AUTO_MERGE_ALLOWED(PR) =
      every §5 activation condition holds
  AND AUTONOMY_STATE(base) = ACTIVE
  AND author = the executor identity recorded in ACTIVATION.json
  AND the branch is auto/<charter>/<unit>, the charter is ACTIVE and the unit's merge_class = AUTO
  AND changed_paths ∩ protected_paths(BASE) = ∅
  AND changed_paths ⊆ charter(BASE).scope.paths ∪ {MANIFEST.txt}
  AND the branch is up to date with main (strict)
  AND required checks are green, where the merge-law check
        · runs from a workflow defined on BASE (pull_request_target), never the PR's copy
        · checks out BASE for policy, the protected list, and the gate itself
        · reads the HEAD only as data: changed paths, the ledger bytes, dependency files
        · runs with a read-only token and no secrets, and never executes PR-supplied code
  AND ledger diffs are append-only and TrialLedger(BASE code).verify() == []
  AND no new dependency outside charter(BASE).deps.allowlist
  AND no unresolved review thread
  AND merge method = merge commit (two-parent); never squash, never rebase
ELSE IF a protected path is touched → OWNER_MERGE_REQUIRED (lane-scoped; other lanes continue)
ELSE → repair within §7, else WAIT_FOR_OWNER(lane, reason)
```

The HEAD's product code is tested by the normal `ci.yml` run on the PR. The merge-law job never imports or runs it.

While AUTO_MERGE is INACTIVE, the merge-law job (`.github/workflows/merge-law.yml`) **fails on every PR by
design**: its verdict is "not auto-mergeable", which is true. That failure is not part of the CI-green
requirement for an Owner merge.

## §5 Activation matrix

```text
                 on Owner merge of CEA-1     after every condition below holds
AUTO_IMPLEMENT   YES                         YES
AUTO_TEST        YES                         YES
AUTO_PR          YES                         YES
AUTO_MERGE       NO                          YES, routine paths only (§4); protected paths → Owner
```

Conditions, each recorded in `.github/gates/ACTIVATION.json` by its own later Owner-merged PR:

| Flag | Holds when |
|---|---|
| `platform_enforcement` | The GitHub plan supports rulesets, and the ruleset on `main` requires a PR, the required checks (CI static + merge-law), strict up-to-date, merge commit only, with squash/rebase disabled and bypass = Owner only. |
| `executor_identity` | A non-admin write identity (machine user or GitHub App) exists; its login is recorded. |
| `executor_proven` | `DURABLE_EXECUTOR_CAPABILITY_PROVEN = YES` (§9). |
| `p2_closed` | `P2_CLOSED = YES` on `main`. P2_CONTRACT §10 is untouched, so every merge is the Owner's until then. |

Plus `AUTONOMY_STATE = ACTIVE`. This record sets every flag to `false` / `null`.

## §6 Serialized main mutation

```text
PARALLEL EXECUTION = YES       PARALLEL MAIN MUTATION = NO
1 at most ONE armed (auto-merge enabled) PR across all lanes
2 strict up-to-date: any change to main makes every other PR stale
3 stale PR → merge main into the branch (two-parent; never rebase/squash) → every check reruns on the new base,
  including the protected verifiers from the NEW base
4 MANIFEST.txt regenerated on the updated branch; conflicts → §7 repair
5 no stale-green merge: a check result belongs to the current head on the current base
6 order when several are ready: CLOSE records and ledger appends first, then charter priority
```

## §7 Bounded repair

```text
ENGINEERING          ≤ 2 repair loops (Master Plan §21), then WAIT_FOR_OWNER on that lane
SCIENTIFIC_NEGATIVE  follow the predefined edge; never retune, never rerun
AUTHORITY            WAIT_FOR_OWNER on that lane only
SAFETY               stop that scope
EXTERNAL             backoff 2 / 4 / 8 / 16 s, then park until the next tick
```

A failed precondition or a fact that does not reconcile is never "repaired". It stops the unit.

## §8 Kill / suspend

| Layer | Mechanism | Works if the executor is broken? |
|---|---|---|
| 1 Repo | `.github/gates/AUTONOMY_STATE.json` `{state: ACTIVE \| SUSPENDED, revoked_programs: [...]}`. merge-law refuses every PR unless ACTIVE; the resolver yields nothing. A revoked program's units are never eligible. Changing it is an Owner merge. | Yes, once platform enforcement exists |
| 2 Out-of-band | (a) disable the scheduled routine; (b) revoke the executor identity's write access; (c) turn off the repository's `allow_auto_merge` setting. Each is reachable from a phone. | **Always** |
| Runtime | P2 / paper governed scripts; later the P3 kill switch; for live, revoke the exchange key at the exchange. | Outside this record |

## §9 Durable executor

```text
WAKE → git fetch origin main (fail → exit) → read AUTONOMY_STATE (≠ ACTIVE → exit)
→ resolve_next_unit.py → {eligible, in_flight, blockers, owner_required}
→ each in-flight auto/<charter>/<unit> branch: base stale → merge main in (two-parent) → push;
  checks red → repair ≤ 2 loops on a fresh worktree; checks green → nothing (the platform merges, or the Owner)
→ nothing armed and a unit eligible → create branch auto/<charter>/<unit> (the name is the lease;
  existing branch ⇒ resume, never duplicate) → headless Claude Code for that one unit → push → PR
  (→ arm auto-merge only if §5 holds)
→ EXIT
```

- Stateless between ticks. State is rebuilt from `main` and GitHub each tick. No database, queue, daemon or
  framework. `EXECUTION_STATE` is derived, never committed, never authority.
- Never on the P2 host. Customer cases never run inside the cloud executor.
- **Capability probe authorized by this record, and nothing more:** one cloud Routine (fresh session per
  firing), fired once, with a read-only prompt: attach the repository, fetch main, read AUTONOMY_STATE, run
  `resolve_next_unit.py --dry-run`, report. Then a write probe, which is the branch push of the first real
  unit. Both PASS → a later Owner-merged PR sets `executor_proven = true`.
- Fallback if the probe fails: a non-P2 machine with a systemd timer running headless `claude -p` under the
  executor identity. The machine is an Owner purchase.

## §10 Executor identity

Never the Owner's account. Write access, never admin. Every auto PR is authored by it. Revoking it stops
everything (§8 layer 2).

## §11 CLOSE law

A record is CLOSE-auto-mergeable only if all of these hold:

1. its terminal facts derive from authoritative evidence;
2. a deterministic generator exists on BASE and is protected;
3. a BASE verifier re-runs the generator and the record is byte-identical;
4. it opens or widens no authority;
5. no other protected path changes in the same PR;
6. every §4 condition holds.

**No generator exists today ⇒ every CLOSE record is OWNER_MERGE_REQUIRED.**

## §12 Research

Research runs only through an Owner-merged program charter at `charters/programs/<PROGRAM_ID>.json` that
validates against `charters/research_program.schema.json` (`.github/gates/check_research_program.py`).

```text
FROZEN BEFORE THE FIRST RESULT  complete Experiment DAG · every prereg committed and hashed · N law · caps ·
                                holdout law · funnel / multiple-testing / N-law hashes
EDGES                           conditioned only on terminal states (REJECTED / SURVIVED / INCONCLUSIVE)
FORBIDDEN                       a node not in the charter · post-result hypothesis invention · changing grid,
                                thresholds, windows, funnel or holdout after any result · Hyperopt / sweeps ·
                                exceeding a cap · admitting a survivor to capital
NEW IDEA OUTSIDE THE DAG        → Owner amendment; research lane only; other lanes continue
```

Binding product constraint: qualified mechanism supply. **Today: `RESEARCH_LANE = NO_PROGRAM`.** Cycle 2 is closed
(`research/RESEARCH_CYCLE2_CLOSURE_1.md`), and no program is opened by this record.

## §13 Commercial value law

```text
CONTINUE = continue the highest-value AUTHORIZED unit whose PREREQUISITE EVIDENCE exists.
PRE-PAID      build only sample report + intake + minimum isolated runner.
AFTER EVIDENCE automate / generalise only what proved necessary.
```

Past PRE-PAID, no unit is created without an evidence ticket: a paid case id, measured manual minutes, a failing
case, or a demonstrated interface blocker. The first charter is `charters/COMMERCIAL-VERIFICATION-LANE-1.json`.

## §14 Owner-only boundaries

```text
AUTHORITY ACTS
  · this record and every later CEA / charter / program change · AUTH-2 content · AUTH-3 · AUTH-4
  · every PR touching protected_paths.txt (incl. generators and any driver/funnel generalisation)
  · P2 closure merge · any new T0 / cohort (P2 §9)
  · P3 workstream acceptance that is not machine-checkable
MONEY / RISK
  · real-money activation · capital/limit increases · leverage · withdrawals
  · live mechanism list · resume from hard HALT
EXTERNAL
  · GitHub plan and repository settings · executor identity · VPS/compute spend above cap
  · exchange keys · notification credentials · pricing · payment · client/legal terms · branding
  · business model change
KILL
  · suspend / revoke autonomy (always available, out-of-band)
```

## §15 No self-modification

No path lets a PR judge itself. The gate, the protected list, AUTONOMY_STATE, ACTIVATION, this record and every
charter are protected paths. Changing any of them is `OWNER_MERGE_REQUIRED` and is evaluated by the BASE policy.
After the Owner merges such a change, it becomes the base for every later PR.

## §16 Scope audit for charter branches

`tests/test_p2_scope_audit.py` audits a branch named `auto/<charter>/<unit>` against that charter's
`scope.paths` (plus `MANIFEST.txt`) instead of the hand-written `BRANCH_SCOPE`. A charter PR therefore never
edits the protected scope audit. Every live negative of that file still applies to it.

---

```text
CEA_1                     = ACTIVE_ON_OWNER_MERGE
AUTO_IMPLEMENT            = YES
AUTO_TEST                 = YES
AUTO_PR                   = YES
AUTO_MERGE                = INACTIVE (platform_enforcement = false · executor_identity = null ·
                            executor_proven = false · p2_closed = false)
RESEARCH_LANE             = NO_PROGRAM
ACTIVE_CHARTERS           = [COMMERCIAL-VERIFICATION-LANE-1]
P2_CONTRACT_MODIFIED      = NO
FP_CONTROL_3_TOUCHED      = NO
P3_STARTED                = NO
REAL_MONEY_AUTHORIZED     = NO
```
