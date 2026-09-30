# Trading Lab OS — Master Execution, Parallel Research & Monitoring Plan
## SSOT Governance Document

**Document ID:** `TRADING-LAB-OS-MASTER-PLAN-1`  
**Status:** `APPROVED / MASTER PLANNING SSOT / NON-AUTHORIZING BY ITSELF`  
**Version:** `1.1`  
**Date:** `2026-09-29`  
**Scope:** Trading Lab OS — P2 → P3 → POST-BETA, including deferred research/AOS lanes  
**Purpose:** Prevent scope drift, stage drift, authority drift, duplicated systems, premature execution, and loss of evidence.

**Critical authority note:** This document consolidates the plan. It does **not** grant execution authority that a current merged stage contract, registry, runtime authority record, or explicit Owner gate does not grant.

---

# 0. GOVERNING LAW

This document is the **master planning SSOT** for how the project fits together.

It is **not** the highest authority for every field.

Field-specific authority order:

```text
CURRENT VERIFIED RUNTIME / EVIDENCE
        ↓
CURRENT MERGED STAGE CONTRACT / REGISTRY / AUTHORITY RECORD
        ↓
THIS MASTER PLANNING SSOT
        ↓
CURRENT P3 BLUEPRINT / FROZEN PRODUCT-SHAPE REFERENCES
        ↓
REFERENCE / HANDOFF
        ↓
HISTORICAL REPORTS / CHAT MEMORY
```

The exact winner remains **field-specific**. For example:

```text
runtime liveness          → live runtime/evidence
P2 permissions            → current merged P2 contract / registry
P3 execution authority    → frozen/merged P3 contract + Owner gate
product shape             → frozen product-shape authority
planning placement        → this master plan unless a higher authority conflicts
```

Therefore:

```text
THIS FILE CANNOT OPEN A BLOCKED ACTION.
THIS FILE CANNOT START P3.
THIS FILE CANNOT AUTHORIZE A NEW T0.
THIS FILE CANNOT AUTHORIZE REAL MONEY.
THIS FILE CANNOT MERGE A PARKED RESEARCH BRANCH.
```

If this plan conflicts with a higher field-specific authority:

```text
HIGHER AUTHORITY WINS
MASTER_PLAN_STATE = NEEDS_RECONCILIATION
```

Core laws:

```text
Canonical evidence > dashboard/UI
Verified current state > historical status claims
Authority > technical possibility
Preparation ≠ execution authorization
Planning ≠ runtime start
Backtest result ≠ proven edge
Research result ≠ execution authority
Candidate ≠ survivor
Paper result ≠ real-money authority
More bots ≠ more independent evidence
More configurations ≠ more independent hypotheses
P&L alone ≠ sufficient evidence
LLM / Agent ≠ trading authority
Executor ≠ final verifier
```

No finding, tool, repository, model, strategy, framework, dashboard, or research idea may silently create a new stage or reorder the roadmap.

---

# 1. OFFICIAL CRITICAL PATH

The locked roadmap is:

```text
P1 — Host Reconstitution
    ↓
P2 — Prospective Paper Proof
    ↓
P3 — Paper Beta Release
    ↓
POST-BETA — Controlled-Live Readiness
    ↓
Separate Owner Live Authorization
```

Rules:

```text
NEW_STAGES = NONE
P3_IS_ONE_STAGE = YES
```

`AOS-OSS-AND-ASYMMETRIC-OUTCOME-SPACE-1` is **not a new stage** and is **not automatically inserted into the critical path**.

Its correct placement is:

```text
POST-P3 / POST-BETA RESEARCH-QUALIFICATION LANE
```

It may be opened by explicit Owner authority after P3, but it does not automatically gate or authorize `Controlled-Live Readiness`.

Current governing P2 shape, when P2 is verified active:

```text
P2
→ canonical FP control
→ Evidence
→ Monitoring
→ Reconciliation
→ A15
→ governed P2 closure transaction
```

No research finding creates a new major stage.

---

# 2. CURRENT-STATE RULE

This document intentionally separates **plan truth** from **live runtime truth**.

The following may be used only as a historical baseline until live-verified:

```text
P2 = ACTIVE
FP-CONTROL-3 = RUNNING
REAL_MONEY_AUTHORIZED = NO
P3_STARTED = NO
```

Every session that needs current operational truth must verify from:

```text
authoritative repo
current worktree
runtime
Docker
canonical evidence
registries
logs
reconciliation records
```

Never promote a stale chat/status report to current truth.


## 2.1 Dynamic State Must Not Be Frozen Into This Plan

This master plan must not be edited every time a counter, container ID, trade count, or live status changes.

Dynamic truth belongs in:

```text
current stage contract / registry
runtime evidence
incident/reconciliation records
current-state report
```

This document stores the **rules and placement**, not live counters.

A session must never infer:

```text
P2 still active
FP control still running
A15 still open
P3 still not started
```

without re-verification.


---

# 3. FOUR EXECUTION LANES

Trading Lab OS is governed as four distinct lanes.

## LANE A — P2 LIVE RUNTIME

Purpose:

```text
prove runtime / evidence / continuity / reconciliation
```

Primary object:

```text
FP-CONTROL-3
```

Allowed:

```text
observe
monitor
collect canonical evidence
reconcile
document incidents
verify continuity
progress toward A15
```

Forbidden during the active canonical P2 control unless separately authorized:

```text
strategy change
threshold change
pair-universe change
risk change
forced entry
forced exit
T0 change
cohort change
experimental contamination
candidate substitution
real-money activation
```

Legitimate terminal outcomes include:

```text
PASS
INCONCLUSIVE
INSUFFICIENT EVIDENCE
TRUTHFUL STOP
```

Activity must never be manufactured just to produce trades.

---

## LANE B — PARALLEL OFFLINE RESEARCH PREPARATION

Purpose:

```text
use P2 waiting time productively
without contaminating P2
and without pretending preparation is strategy execution
```

Target shape:

```text
P2 remains untouched
+
research preparation stays isolated and non-authoritative
+
candidate execution requires a separate authority gate
```

**Authority rule:** this master plan does not itself authorize new research during an active P2. At the last verified reconciliation, the merged P2 governance blocked parallel candidate research, backtests, new research dependencies, and new paper workers pending a fresh Owner directive.

Existing research-preparation artifacts may be preserved as a parked/reference package. Any new preparation, merge, dependency installation, backtest, candidate execution, or paper admission must first pass the current merged authority.

Target shape:

```text
KEEP FP-CONTROL-3 UNTOUCHED
        +
OFFLINE RESEARCH PREPARATION
        +
ONLY FUTURE SURVIVORS BECOME PAPER CANDIDATES
```

### Parked Research Package Law

The previously prepared research package/branch is not automatically canonical.

Last verified state included:

```text
research-prep branch = PARKED / UNMERGED
candidate execution = NOT AUTHORIZED
main merge = DEFERRED pending the governing gate
```

Every session must re-verify this against the current repository before acting.

No merge is authorized merely because the package exists or its tests pass.

### Research-preparation work — allowed only when current authority permits

```text
source discovery
source acquisition into isolated workspace
source locking
commit/hash capture
license review
provenance recovery
strategy-family mapping
lineage mapping
semantic duplicate detection
candidate registry
data dependency mapping
compatibility analysis
benchmark-contract design
research-priority design
H1 provenance recovery
trial-accounting design
pre-registration schema design
null/negative-control design
data-truth audit design
trialgate audit
arch audit
reuse/build matrix
resource-isolation assessment
monitoring schema design
```

### Not authorized merely because preparation exists

```text
new candidate backtests
Hyperopt
parameter sweeps
candidate strategy execution
new paper workers
promotion to P2
replacement of FP-CONTROL-3
live trading
```

Research authority states must be explicit:

```text
BLOCKED
PLANNING_ONLY
PREPARATION_AUTHORIZED
EXECUTION_AUTHORIZED
PAPER_ADMISSION_AUTHORIZED
```

Never infer one state from another.


Preparation and execution must remain explicit, separate states.

---

## LANE C — P3 PLANNING / READINESS

P3 planning may proceed in parallel with P2.

P3 implementation/runtime activation must wait for the governing P2 closure gate.

P3 planning includes:

```text
Backup design
Restore design
Restart/Reboot Recovery
Evidence Durability
Monitoring Continuity
Operational Hardening
Failure/Recovery Matrix
Operator Controls
Kill Switch
Control Room architecture
Arabic/English UX
Paper Beta Acceptance
P3 execution map
```

Required state distinction:

```text
P3_PLANNING = ALLOWED
P3_EXECUTION = AFTER P2 CLOSURE / AUTHORITY GATE
```

---

## LANE D — POST-P3 AOS RESEARCH

`AOS-OSS-AND-ASYMMETRIC-OUTCOME-SPACE-1` is not the same as the lightweight parallel research-preparation lane.

AOS remains Post-P3:

```text
AOS-0 — OSS Capability Qualification
AOS-1 — Outcome-Space Simulation
AOS-2 — Adversarial / Independent Validation
AOS-3 — Prospective Paper Candidate
AOS-4 — Verified Outcome
```

AOS must not mutate current P2/P3 scope.

It must not create a new core architecture automatically.

---

# 4. CROSS-CUTTING MONITORING LAYER

Monitoring is a horizontal layer over every lane.

```text
                    MONITORING / OBSERVABILITY
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
     LANE A                LANE B                LANE C
   P2 Runtime          Research Prep           P3 Planning
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                         LANE D later
```

Monitoring is not authority.

```text
Canonical Evidence
        ↓
Resolved State
        ↓
Control Room / Grafana
```

If UI state conflicts with canonical evidence:

```text
CANONICAL EVIDENCE WINS
```

---

# 5. P2 MONITORING CONTRACT

Track at minimum:

```text
FP_CONTROL_3_STATE
FP_RUN_ACTIVE
T0
COHORT_ID
HARD_CAP

container health
container identity
restart count
uptime
exchange connectivity

input_event_count
decision_event_count
trade_count
open_trade_count
closed_trade_count

latest_input_timestamp
latest_decision_timestamp
latest_intended_action

evidence continuity
database continuity
digest continuity
cohort continuity

incidents
DNS failures
API failures
market-data gaps
decision gaps
rate-limit events
writer conflicts
```

Critical alerts:

```text
FP stopped unexpectedly
unexpected writer
strategy/config hash change
T0 change
cohort change
paper guard failure
evidence-chain break
canonical DB corruption
unexplained data replacement
real-money state detected
```

---

# 6. PARALLEL RESEARCH MONITORING CONTRACT

Track:

```text
research workspace health

source repos
├── source captured
├── pinned commit
├── file hash
├── license
└── upstream changed?

candidate registry
├── total candidates
├── family count
├── lineage count
├── independent candidate count
└── OUR_RESULT

H1 provenance
├── strategy
├── config
├── engine
├── dataset
├── data hashes
├── result artifact
└── trade list

governance-prep
├── prereg schema
├── trial ledger design
├── benchmark contract
├── null-control design
└── data manifest design
```

The UI/report must distinguish:

```text
SOURCE CLAIM
OUR RESULT
VERIFIED RESULT
```

No source-reported profit number may be represented as a verified Trading Lab OS result.


Licensing is also a gate:

```text
GPL / copyleft source identified
→ record it
→ do not import into the main product merely because it is technically compatible
→ Owner/legal/project licensing decision before incorporation
```

Reference or clean-room comparison is different from copying code.

---

# 7. ISOLATION MONITOR

Parallel preparation must not degrade or contaminate P2.

Track:

```text
LIVE_WORKTREE_CHANGED_BY_RESEARCH
SHARED_DB
SHARED_WRITE_PATH
SHARED_CONTAINER
SHARED_PORT_CONFLICT

CPU contention
RAM contention
disk I/O contention
storage pressure
network contention
exchange/IP rate-limit contention
API-limit contention
shared cache risk
shared credential risk
```

Governing priority:

```text
IF research activity threatens canonical P2
→ throttle/stop research lane
→ preserve P2
```

P2 always wins.

---

# 8. H1 ROLE AND EVIDENCE PRESERVATION

H1 is not accepted as a proven edge.

Its first role is:

```text
REPRODUCIBILITY FIXTURE
```

Recover and preserve:

```text
strategy source
strategy hash
config
config hash
Freqtrade version
relevant dependencies
data files
data hashes
exchange
trading mode
pair universe
timeframe
timerange
fees
slippage assumptions
funding assumptions
mark-data assumptions
backtest command
backtest result
trade list
recorded metrics
CI artifacts
```

Classify each field:

```text
FOUND
MISSING
AMBIGUOUS
CONTRADICTED
```

Final H1 reproducibility classification:

```text
TRUE_REPRODUCTION_AVAILABLE
or
CONTROLLED_RE_DERIVATION_REQUIRED
or
BLOCKED
```

Exact reproduction target, **only when the original trade list and required original artifacts are recoverable**:

```text
identical trade-list hash
```

If the original trade list is not recoverable, do not call a reconstructed run an exact reproduction. The path must be classified as:

```text
CONTROLLED_RE_DERIVATION_REQUIRED
```

unless a later explicit project policy resolves the current reproducibility disagreement differently.

A merely similar aggregate return is not sufficient.

### Time-sensitive H1 evidence item — re-verify before claiming closed

At the latest verified reconciliation:

```text
GitHub Actions run = 34126570635
artifact expiry    = 2026-10-07
archive status     = NOT YET PROVEN CLOSED
```

The artifact contained the non-summary H1 evidence behind the reported result. It must be archived to durable storage before expiry if this has not already been done.

Evidence that can expire or be lost must be archived before expiry.

---

# 9. RESEARCH GOVERNANCE SCHEMA

Future research must distinguish:

```text
FAMILY
↓
LINEAGE
↓
CANDIDATE
↓
CONFIG
↓
EXPERIMENT
↓
RUN
↓
TRIAL
↓
PAPER ADMISSION
```

Trial accounting law:

```text
100 parameter configurations
=
100 selection attempts

BUT

100 configurations
≠
100 independent hypotheses
```

Research records must preserve:

```text
pre-registration
trial count
source provenance
data version/hash
engine version/hash
result artifacts
result hash
decision record
holdout state
paper-admission state
```

MLflow may later be a view/tracker.

It is not the sole authority for trial counts.

---

# 10. REUSE-BEFORE-BUILD LAW

Default position:

```text
do not build what already exists and passes audit
```

Evaluate components as:

```text
REUSE_EXISTING
WRAP_EXISTING
AUDIT_BEFORE_USE
BUILD_SMALL_MISSING_LAYER
DEFER
DO_NOT_BUILD
```

Core retained stack:

```text
Freqtrade
Git
Docker
Prometheus
Grafana
existing evidence/reconciliation infrastructure
```

Potential later components:

```text
trialgate
arch
MLflow
Hummingbot
NautilusTrader
DVC/lakeFS
VectorBT
skfolio
Jesse
LEAN
Qlib
FinRL
```

Their existence does not justify installation.

No new trading engine, database, control plane, monitoring stack, or orchestrator is added without demonstrated need.

---

# 11. TRIALGATE / ARCH POLICY

## trialgate

Status:

```text
AUDIT / ADOPT-CANDIDATE
NOT A CURRENT DEPENDENCY
```

Audit activity itself must obey the current research-authority boundary.

Potential reuse:

```text
hash-chained registry
PBO
DSR
holdout lock
cost checks
```

Required before adoption:

```text
source audit
license verification
version/hash pinning
reference-value tests
threshold configurability check
determinism check
dependency-risk assessment
```

## arch

Status:

```text
AUDIT / ADOPT-CANDIDATE
NOT A CURRENT DEPENDENCY
```

Audit activity itself must obey the current research-authority boundary.

Potential use:

```text
SPA
StepM
MCS
multiple-candidate statistical analysis
```

Do not build a custom statistical framework while reusable audited tools are sufficient.

---

# 12. NULL / NEGATIVE CONTROL LAW

Before trusting the validation funnel, test the funnel itself.

Use a no-edge fixture such as:

```text
random entries
shuffled signals
permuted signals
```

Expected result:

```text
VALIDATION FUNNEL → REJECT
```

If the funnel accepts noise:

```text
STOP
```

No real candidate should be trusted until the validation system rejects known-no-edge controls.

---

# 13. DATA-TRUTH CONTRACT

Research cannot be trusted without data truth.

Investigate and control:

```text
point-in-time universe
inactive pairs
delisted pairs
survivorship bias
missing candles
duplicate candles
timezone consistency
partial datasets
silent redownload
mixed data versions
symbol changes
funding timestamp alignment
mark-price alignment
cache contamination
```

Data truth must be explicit and reproducible.

Silent dataset replacement is prohibited.

---

# 14. FUTURE VALIDATION FUNNEL

When candidate execution is separately authorized, the default validation sequence is:

```text
PRE-REGISTER
↓
PROVENANCE
↓
LOOKAHEAD CHECK
↓
RECURSIVE / WARM-UP CHECK
↓
DEVELOPMENT TESTING
↓
WALK-FORWARD
↓
PARAMETER ROBUSTNESS
↓
FEES / FUNDING / SLIPPAGE STRESS
↓
MULTIPLE-TESTING CONTROL
↓
REGIME / SESSION DIAGNOSTICS
↓
FREEZE
↓
LOCKED HOLDOUT — OPEN ONCE
↓
PASS / REJECT
↓
ISOLATED FORWARD PAPER
```

The locked holdout is not development data.

After the holdout is opened, tuning against it is prohibited.

---

# 15. FUTURE RESEARCH EXECUTION — SEPARATE AUTHORITY REQUIRED

A15 or P2 closure does **not by itself** authorize candidate research execution.

Research execution may start only when current governance explicitly opens it, for example through an Owner-approved merged amendment/sibling contract or equivalent current authority.

Required rule:

```text
P2/A15 closure
≠
research execution authorization
```

Once research execution is separately authorized, the intended sequence is:

```text
H1 exact reproduction
or controlled re-derivation
        ↓
null calibration
        ↓
existing-family mapping
        ↓
candidate harvesting
        ↓
cheap elimination gates
        ↓
walk-forward
        ↓
robustness
        ↓
cost stress
        ↓
multiple-testing control
        ↓
locked holdout
        ↓
SURVIVORS ONLY
        ↓
separately admitted isolated paper workers
```

A15 may remove a timing conflict. It does not replace research authority.

It is acceptable for all candidates to be rejected.

Scientific failure of a hypothesis is a valid result.

---

# 16. FUTURE PAPER-WORKER CONTRACT

Only validated survivors may become paper workers.

Each future worker must have its own:

```text
candidate ID
cohort ID
config/hash
database
logs
evidence
incident history
terminal result
```

No survivor may reuse the canonical P2 cohort identity.

No paper worker may silently become real-money enabled.

---

# 17. P3 CONTRACT / ENTRY LAW

P3 is one stage and has exactly twelve locked planning workstreams:

```text
P3-PLN-00  Final P2 → P3 Reconciliation
P3-PLN-01  Contract & Acceptance
P3-PLN-02  State & Recovery Inventory
P3-PLN-03  Backup & Restore
P3-PLN-04  Restart / Reboot / Host Recovery
P3-PLN-05  Evidence Durability
P3-PLN-06  Monitoring & Operational Hardening
P3-PLN-07  Failure & Recovery Verification
P3-PLN-08  Operator Controls & Kill Switch
P3-PLN-09  Control Room UX / UI
P3-PLN-10  Paper Beta Acceptance Program
P3-PLN-11  Final Freeze & Execution Pack

P3_WORKSTREAM_COUNT = 12
P3_IS_ONE_STAGE = YES
WORKSTREAM_13 = FORBIDDEN
```

A finding enters an existing workstream, `POST-BETA`, or `REFERENCE / DEFERRED`. It does not create P3A/P3B/P3.5/P4.

## 17.1 P3 does not start merely because P2 ends

Required entry sequence:

```text
P2 terminal condition
  → A15 final evidence
  → governed shutdown
  → archive / seal / digest
  → P2 closure transaction
  → OWNER MERGE
  → merged-main verification
  → P2_CLOSED = YES
  → P2 terminal outcome reviewed
  → P3-PLN-00 Final P2 → P3 Reconciliation   [planning]
  → P3_ENTRY_TRUTH = RECONCILED
  → P3-PLN-01 contract review / freeze        [planning]
  → OWNER_AUTHORIZES_P3_EXECUTION
  → P3_STARTED = YES
  → P3 production implementation
```

Neither `PLN-00` nor `PLN-01` planning is P3 execution.

Outcome law:

```text
P2 PASS
→ still requires PLN-00 + PLN-01 + Owner P3 execution authorization

P2 INCONCLUSIVE / INSUFFICIENT
→ no automatic P3 start; Owner chooses the lawful governed path

P2 FAIL
→ failure authority is resolved first; no automatic P3 start
```

## 17.2 P3 planning vs authority

P3 planning/design may proceed during P2 where current authority allows.

P3 production implementation does not.

A P3 planning draft does not become runtime authority merely because it is complete. The P3 contract becomes binding only through its required freeze/merge/Owner authority process.

## 17.3 P3 purpose

P3 work covers:

```text
backup / restore proof
restart / reboot / host recovery
evidence durability
monitoring continuity
operational hardening
failure / recovery verification
operator controls
kill switch
Control Room implementation of the frozen product shape
Paper Beta acceptance
final freeze / execution pack
```

P3 is not:

```text
a new strategy stage
an edge-discovery stage
a real-money stage
a redesign stage
```

---

# 18. CONTROL ROOM INFORMATION ARCHITECTURE

Use one unified surface instead of one dashboard per bot.

Target sections:

```text
COMMAND CENTER
PROJECT & CONTINUITY
MARKET WORKSPACE
DECISIONS
TRADES & POSITIONS
RISK & AUTHORITY
EVIDENCE & RECONCILIATION
INCIDENTS
OPERATIONS
SYSTEM
HISTORY
```

Future research/paper components should map into this common schema.


No dashboard proliferation.

## 18.1 Product-shape no-reopen law

The approved/frozen product shape is implemented in P3; it is not redesigned in P3.

```text
LEVEL_A / PRODUCT_SHAPE = FROZEN where current product authority says frozen
PLN-09 = REALISE THE SHAPE
PLN-09 ≠ REOPEN THE SHAPE
```

Reopening requires a proven higher-authority governing contradiction, not a feature request.

## 18.2 Current implementation must be verified

Do not assume the Control Room is already live.

At the latest reconciliation, the live operator surface was Grafana and the Control Room itself was not proven present as a live connected system.

Therefore:

```text
Control Room target architecture = APPROVED PLANNING
Control Room live implementation = VERIFY CURRENTLY
new adapters/state-resolution implementation = WAIT FOR THE CORRECT P3 AUTHORITY
```

Existing Prometheus/Grafana may continue to serve operational monitoring where already lawful and present.

---

# 19. ALERT SEVERITY MODEL


## INFO

Examples:

```text
source captured
research-prep test completed
candidate classified
artifact archived
planning document updated
```

## WARNING

Examples:

```text
research disk > threshold
API/rate limit approaching
H1 provenance incomplete
upstream source changed
research-prep test failure
resource contention rising
```

## CRITICAL

Examples:

```text
FP-CONTROL stopped
paper guard failure
unexpected writer
strategy/config hash changed
T0/cohort changed
evidence chain broken
DB corruption
real-money enabled
unauthorized execution
```

Critical alerts require immediate Owner attention.

---

# 20. GOVERNANCE / SCOPE-DRIFT MONITOR

Monitoring must detect project drift, not only system crashes.

Continuously evaluate:

```text
CURRENT_STAGE
AUTHORIZED_ACTIONS
FORBIDDEN_ACTIONS

P2 mutated?
new candidate executed?
new dependency installed?
new bot started?
P3 started early?
AOS started early?
new stage invented?
real money enabled?
```

Any mismatch becomes an incident.

---

# 21. EXECUTION-GOVERNANCE MODEL

The preferred execution model remains:

```text
Owner freezes stage contract
        ↓
Claude = sole writer/executor
        ↓
deterministic + adversarial gates
        ↓
Codex = fresh independent read-only verifier
        ↓
FAIL → Claude repair → re-run gates → fresh verifier
        ↓
PASS
        ↓
Git / PR / CI / runtime closure
```

Governed Git discipline for stage transactions:

```text
branch
→ commit
→ post-commit gates
→ push
→ PR
→ mandatory CI
→ OWNER MERGE [normal two-parent where governing contract requires]
→ re-ground on merged main
→ continue
```

No direct push to main, no self-merge, no history rewriting, and no squash/rebase where the governing stage contract requires a normal merge.

Rules:

```text
one writer
fail closed
no silent authority expansion
no stage invention
max two automatic repair loops before Owner escalation
Owner required for true authority gates
```

CliDeck, if used, remains an operator UI, not an orchestrator or authority.

DevGuard-style isolation / one-writer / fail-closed rules remain desirable governance controls.

---

# 22. CHANGE-CONTROL LAW FOR THIS PLAN

This file must not be silently edited to match convenience.

Any material change must record:

```text
CHANGE_ID
DATE
OWNER_DECISION
REASON
AFFECTED_SECTION
OLD_RULE
NEW_RULE
EVIDENCE / DRIVER
```

Material changes include:

```text
stage reordering
P2 mutation rights
research-execution authority
P3 entry criteria
AOS timing
real-money authority
strategy/risk semantics
new engine
new database
new control plane
holdout policy
trial accounting
monitoring authority
```

If no Owner-approved change record exists and no higher field-specific authority has changed:

```text
THIS PLAN REMAINS THE PLANNING SSOT
```

If a newer merged contract/registry legitimately changes a field:

```text
HIGHER AUTHORITY WINS FOR THAT FIELD
THIS FILE MUST BE RECONCILED
```

Do not use this file to block a valid higher-authority transaction, and do not use a chat message to bypass the required transaction.

---

# 23. ABSOLUTE PROHIBITIONS

Unless separately and explicitly authorized:

```text
NO real money
NO strategy mutation in canonical P2
NO risk mutation in canonical P2
NO T0/cohort mutation
NO forced activity
NO unauthorized backtests
NO unauthorized Hyperopt
NO unauthorized paper bots
NO new stage taxonomy
NO new core architecture
NO silent dataset replacement
NO trial deletion/relabeling to improve results
NO holdout reuse as development data
NO UI becoming evidence authority
NO research workload allowed to endanger P2
NO merge of parked research-prep merely because it exists
NO unified Control Room production implementation before its P3 authority
NO AOS treated as a stage or automatic Controlled-Live prerequisite
```

---

# 24. CONCURRENT WORK MODEL — AUTHORITY-AWARE

The intended concurrency is:

```text
LANE A
P2 canonical runtime
→ evidence / monitoring / reconciliation / A15
```

In parallel, only what current authority actually permits:

```text
LANE C
P3 planning / readiness
→ explicitly allowed as planning while P2 runs
```

For research:

```text
LANE B
existing isolated research-prep package
→ preserve / inspect / reconcile as permitted
→ remain parked/non-authoritative until admitted

NEW research preparation or execution
→ NOT opened by this master file
→ follow current merged P2 contract + explicit Owner directive
```

And:

```text
LANE D
AOS
→ POST-P3 / POST-BETA research lane
→ no automatic start
→ no new stage
```

The project goal remains to avoid wasting P2 waiting time, but **productivity never outranks authority**.

---

# 25. COMPACT GOVERNING STATUS

```text
OFFICIAL_ROADMAP                 = P1 → P2 → P3 → POST-BETA
NEW_STAGES                       = NONE
P3_IS_ONE_STAGE                  = YES
P3_WORKSTREAM_COUNT              = 12

P2_IF_ACTIVE                     = CONTINUE UNTOUCHED
P2_MONITORING                    = HIGHEST OPERATIONAL PRIORITY

P3_PLANNING_DURING_P2            = ALLOWED WHERE CURRENT AUTHORITY SAYS SO
P3_EXECUTION                     = REQUIRES ENTRY LAW + EXPLICIT OWNER AUTHORITY

PARALLEL_RESEARCH_PREP           = NOT AUTHORIZED BY THIS FILE
LAST VERIFIED P2 RESEARCH STATE  = BLOCKED PENDING FRESH OWNER DIRECTIVE
EXISTING_RESEARCH_PREP_PACKAGE   = PARKED / REFERENCE UNTIL CURRENT AUTHORITY ADMITS IT
PARALLEL_CANDIDATE_EXECUTION     = NO
PARALLEL_NEW_PAPER_BOTS          = NO

H1_EVIDENCE_PRESERVATION         = REQUIRED
H1_REPRODUCTION_CLASSIFICATION   = REVERIFY; DISAGREEMENT EXISTS
H1_CI_ARTIFACT                   = TIME-SENSITIVE UNTIL DURABLE ARCHIVE IS PROVEN

TRIALGATE / ARCH                 = AUDIT CANDIDATES, NOT CURRENT DEPENDENCIES
NEW_ENGINE_REQUIRED_BY_PLAN      = NO
NEW_DATABASE_REQUIRED_BY_PLAN    = NO
NEW_CONTROL_PLANE_REQUIRED       = NO
NEW_MONITORING_PLATFORM          = NO
PROMETHEUS_GRAFANA               = REUSE WHERE PRESENT

MONITORING                       = CROSS-CUTTING REQUIREMENT
CANONICAL_EVIDENCE               = AUTHORITY FOR EVIDENCE FIELDS
CONTROL_ROOM                     = PROJECTION / OPERATOR SURFACE
CONTROL_ROOM_LIVE_STATUS         = VERIFY; DO NOT ASSUME

AOS                              = POST-P3 / POST-BETA RESEARCH LANE
AOS_IS_STAGE                     = NO
AOS_BLOCKS_CONTROLLED_LIVE       = NO, unless a later Owner-approved authority explicitly says so

REAL_MONEY_AUTHORIZED_BY_PLAN    = NO
```

---

# 26. SESSION START CHECK

Every new Claude/Codex session working on Trading Lab OS should start by reading this document and answering:

```text
1. What is the current verified stage?
2. Which lane is this task in?
3. Is the requested action preparation, execution, or authority change?
4. Does it mutate canonical P2?
5. Does it create a new stage/tool/engine/database unnecessarily?
6. Does it require Owner authority?
7. What canonical evidence will prove completion?
8. What monitoring/incident impact can it have?
9. What higher field-specific authority governs this action?
10. Is the relevant contract/registry current and merged?
11. Is a parked/reference branch being mistaken for current authority?
```

If the action conflicts with this plan:

```text
STOP
→ identify contradiction
→ surface Owner decision
```

Do not silently reinterpret the plan.

---

# 27. FINAL GOVERNING MAP

```text
                           TRADING LAB OS
                                  │
                                  ▼
                    P1 — Host Reconstitution
                                  │
                                  ▼
                 P2 — Prospective Paper Proof
                                  │
                      canonical control / evidence
                      monitoring / reconciliation
                                  │
                         A15 + governed closure
                                  │
                                  ▼
                    P3-PLN-00 Reconciliation
                                  │
                    P3-PLN-01 Contract Freeze
                                  │
                     OWNER AUTHORIZES P3
                                  │
                                  ▼
                     P3 — Paper Beta Release
                                  │
                        12 locked workstreams
                                  │
                      Paper Beta acceptance
                                  │
                       governed P3 closure
                                  │
                                  ▼
                             POST-BETA
                         ┌────────┴────────┐
                         │                 │
                         ▼                 ▼
              Controlled-Live        Research /
                 Readiness            Qualification
                         │             AOS lane
                         │                 │
                 separate Owner       separate Owner
                  authorization        authority
                         │                 │
                         └──────┬──────────┘
                                │
                  NO AUTOMATIC REAL-MONEY AUTHORITY
```

Important:

```text
AOS is not P4.
AOS is not automatically before Controlled-Live.
AOS does not authorize Controlled-Live.
Controlled-Live does not authorize real money.
Every consequential transition remains separately governed.
```

Across all lanes:

```text
MONITORING
+
EVIDENCE
+
RECONCILIATION
+
GOVERNANCE
+
FIELD-SPECIFIC AUTHORITY
+
NO REAL MONEY WITHOUT SEPARATE OWNER AUTHORITY
```

---

# 28. SUPERSESSION / RECONCILIATION RULE

This document is formally superseded as a whole only by an explicitly named later Owner-approved version.

Valid whole-document supersession should say:

```text
SUPERSEDES:
TRADING-LAB-OS-MASTER-PLAN-1

NEW DOCUMENT ID:
...

OWNER APPROVAL:
...

DATE:
...
```

However, field-specific authority may change through a valid higher-authority merged contract/registry/runtime transaction before this file is revised.

In that case:

```text
higher field-specific authority wins
this document becomes NEEDS_RECONCILIATION for that field
```

The following do **not** silently supersede or authorize anything:

```text
chat repetition
tool suggestion
research finding
source repository
new framework
implementation convenience
unmerged branch
passing local tests
```

---

# 29. OPEN P0 / RECONCILIATION ITEMS SNAPSHOT — 2026-09-29

These are not permanent plan laws. They are a dated snapshot that must be re-verified.

At the latest reconciliation, open items included:

```text
1. reconcile the 2026-09-28 restart / DNS incident record
2. archive H1 CI artifact run 34126570635 before 2026-10-07 if not already archived
3. resolve H1 exact-reproduction vs controlled-re-derivation policy disagreement
4. resolve/merge the authority for any new research direction before execution
5. clarify branch-local / unverified research-family and trial-count claims
6. keep stale clones from being mistaken for authority
```

Do not mark any item closed without evidence.

---

# 30. FINAL ANTI-DRIFT ASSERTIONS

```text
MASTER_PLAN_ROLE                  = PLANNING SSOT
MASTER_PLAN_EXECUTION_AUTHORITY   = NO
AUTHORITY_MODEL                   = FIELD-SPECIFIC

ROADMAP                           = P1 → P2 → P3 → POST-BETA
NEW_STAGES                        = NONE

P2_MUTATION_BY_THIS_PLAN          = NO
P3_AUTO_START_AFTER_P2            = NO
P3_WORKSTREAM_COUNT               = 12

RESEARCH_EXECUTION_BY_THIS_PLAN   = NO
PARKED_RESEARCH_AUTO_MERGE        = NO

AOS_IS_STAGE                      = NO
AOS_AUTO_BLOCKS_CONTROLLED_LIVE   = NO

MONITORING                        = CROSS-CUTTING
CONTROL_ROOM_AUTHORITY            = NO

REAL_MONEY_AUTHORIZED             = NO
SCOPE_DRIFT_POLICY                = FAIL CLOSED
```

# END

```text
MASTER_PLAN_STATUS = GOVERNING
CRITICAL_PATH = P2 → P3 → POST-BETA
PARALLEL_PREP = SUBJECT TO CURRENT MERGED AUTHORITY
CANONICAL_P2_MUTATION = NO
MONITORING = CROSS-CUTTING
CONTROL_ROOM_AUTHORITY = NO
REAL_MONEY_AUTHORIZED = NO
SCOPE_DRIFT_POLICY = FAIL CLOSED
```
