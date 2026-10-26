# Trading Lab OS — Claude New Session Pack
## Direct Current Authority Reconciliation + Mobile Monitoring + Final Product Shape Lock v1.2
### FINAL OWNER HANDOFF — READ-ONLY RECONCILIATION

**Date:** 2026-09-25

This file is self-contained. It includes:
1. Owner startup steps for a NEW Claude Code local session.
2. Mobile monitoring instructions for the SAME local session.
3. The complete read-only Direct Current Authority Reconciliation directive.
4. The complete Final Master Product Shape Lock v1.2 as Appendix A.

The only other file required is:

```text
Trading_Lab_OS_Prototype_v0.2.4_FINAL.html
```

---

# PART 1 — OWNER STARTUP ON UBUNTU

## A. Put these TWO files in one Owner-input folder

Recommended:

```bash
mkdir -p ~/Documents/TLOS-Owner-Input
```

Place exactly:

```text
Trading_Lab_OS_CLAUDE_NEW_SESSION_PACK_v1.0.md
Trading_Lab_OS_Prototype_v0.2.4_FINAL.html
```

Keep them outside the trading repository unless current repository authority explicitly requires otherwise.

---

## B. Open a NEW terminal

Do NOT stop P2 runtime, monitors, evidence processes, or another useful Claude session merely to start this review.

Go to the existing Trading Lab OS repository:

```bash
cd ~/projects/trading
```

If the actual repository root differs, use the real existing root. Do not move or clone the repo just to match this example.

---

## C. Check Claude Code

```bash
claude --version
```

If Remote Control is available in this installation/account, use it. If it is not available, do not change Trading Lab OS to solve that; continue locally and report the product/tool limitation separately.

---

## D. Start a NEW Claude Code session with read access to the two Owner files

From the repository root:

```bash
claude --add-dir ~/Documents/TLOS-Owner-Input
```

Do not grant broader filesystem access than needed.

---

## E. Monitor this SAME local session from mobile

Inside Claude Code:

```text
/remote-control
```

Then open the Claude mobile app → Code and select this local session.

If available, `/config` may expose:

```text
Enable Remote Control for all sessions
```

Session rule:

```text
LOCAL SESSION = THE SESSION BEING REVIEWED
MOBILE = VIEW / STEER THE SAME SESSION
DO NOT TELEPORT INTO A DIFFERENT CLOUD WORKSPACE
DO NOT START A PARALLEL WRITER SESSION
```

---

## F. Send Claude ONE starter instruction only

```text
Read ~/Documents/TLOS-Owner-Input/Trading_Lab_OS_CLAUDE_NEW_SESSION_PACK_v1.0.md completely.
Also read ~/Documents/TLOS-Owner-Input/Trading_Lab_OS_Prototype_v0.2.4_FINAL.html.
Execute the SESSION DIRECTIVE exactly.
Do not implement or modify anything.
```

Then let Claude complete the five mobile checkpoints unless a real authority gate blocks it.

---

# PART 2 — SESSION DIRECTIVE FOR CLAUDE CODE

You are starting a NEW Claude Code session for **Trading Lab OS**.

This is a controlled direct-authority reconciliation session.

The Owner may monitor and steer this same local session remotely from mobile.

Your purpose is to establish the current authoritative project truth before the Owner performs the final Product/UX walkthrough and Level-A freeze.

You are NOT authorized to build the product in this session.

---

# 0. ABSOLUTE SESSION MODE

Preserve:

```text
SESSION_MODE                    = READ_ONLY_RECONCILIATION

P2_MUTATION                     = FORBIDDEN
P2_RUNTIME_CHANGE               = FORBIDDEN
P2_STRATEGY_CHANGE              = FORBIDDEN
P2_RISK_CHANGE                  = FORBIDDEN
P2_DATASET_CHANGE               = FORBIDDEN
P2_T0_CHANGE                    = FORBIDDEN
P2_COHORT_CHANGE                = FORBIDDEN

P3_IMPLEMENTATION               = FORBIDDEN
P3_RUNTIME_CHANGE               = FORBIDDEN
P3_EXECUTION_PR                 = FORBIDDEN

GIT_MUTATION                    = FORBIDDEN
FILE_MUTATION                   = FORBIDDEN
RUNTIME_MUTATION                = FORBIDDEN

REAL_MONEY                      = FORBIDDEN
```

You MAY:

```text
read repository files
read git status/history
read branch/worktree metadata without switching them
read current contracts
read registries
read governance records
read documentation
read configuration
run non-mutating inspection commands
compare sources
produce an in-session reconciliation report
```

You MUST NOT:

```text
edit files
create files
delete files
format files
commit
push
merge
checkout
switch branch
rebase
reset
stash
cherry-pick
open a PR
alter worktree state
restart services
stop services
start services
change Docker state
change systemd state
modify evidence
modify registry
modify strategy
modify risk
modify dataset
modify T0
modify cohort
start P3 implementation
enable live/real money
```

If a command may mutate state, do not run it.

---

# 1. MOBILE PROGRESS CONTRACT

Emit exactly five milestone updates:

```text
[MOBILE CHECKPOINT 1/5] — REPOSITORY GROUNDING
[MOBILE CHECKPOINT 2/5] — OWNER INPUTS READ
[MOBILE CHECKPOINT 3/5] — DIRECT AUTHORITY SOURCES READ
[MOBILE CHECKPOINT 4/5] — CONFLICT RECONCILIATION
[MOBILE CHECKPOINT 5/5] — FINAL VERDICT
```

Each checkpoint must contain only:

```text
WHAT WAS READ =
WHAT WAS VERIFIED =
REAL CONFLICTS =
MISSING AUTHORITY =
CURRENT VERDICT =
NEXT READ-ONLY STEP =
```

Do not flood the mobile view with routine command output.

Do not ask the Owner routine questions.

Interrupt the Owner only if:
- a required authority source cannot be located;
- a real authority contradiction exists;
- a next step would require mutation;
- a true Owner authority gate is reached.

---

# 2. PHASE 1 — REPOSITORY GROUNDING

Run only non-mutating inspection.

At minimum:

```bash
pwd
git rev-parse --show-toplevel
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline
git worktree list
git remote -v
```

Determine without changing anything:

```text
REPOSITORY_ROOT
CURRENT_WORKTREE
CURRENT_BRANCH_OR_DETACHED_STATE
CURRENT_HEAD
CURRENT_MAIN_HEAD
WORKTREE_CLEAN_OR_DIRTY
CURRENT_STAGE
CURRENT_P2_STATUS
CURRENT_RUNTIME_SOURCE_IDENTITY if recorded
CURRENT_GOVERNANCE_MAIN_IDENTITY if recorded
```

If the worktree is dirty:

```text
REPORT IT
DO NOT CLEAN IT
DO NOT STASH IT
DO NOT RESET IT
```

If runtime is intentionally pinned behind governance main:

```text
REPORT THE DECLARED RELATIONSHIP
DO NOT CALL IT A CONFLICT UNLESS DIRECT AUTHORITY SAYS IT IS
```

Then emit:

```text
[MOBILE CHECKPOINT 1/5]
```

---

# 3. PHASE 2 — OWNER INPUTS

Read completely:

```text
~/Documents/TLOS-Owner-Input/Trading_Lab_OS_CLAUDE_NEW_SESSION_PACK_v1.0.md
~/Documents/TLOS-Owner-Input/Trading_Lab_OS_Prototype_v0.2.4_FINAL.html
```

Treat the embedded:

```text
FINAL MASTER PRODUCT SHAPE LOCK v1.2
```

as:

```text
FINAL OWNER PRODUCT-SHAPE INTENT
PRE-CANONICAL UNTIL DIRECT CURRENT AUTHORITY RECONCILIATION PASSES
```

Treat the prototype as:

```text
FINAL REVIEW PROTOTYPE
NON-PRODUCTION
NON-AUTHORITATIVE
UI REFERENCE
```

Verify the prototype remains:

```text
STATIC MOCK DATA
OFFLINE
NO LIVE TRADING CONNECTION
NO RUNTIME AUTHORITY
NO GOVERNANCE AUTHORITY
```

Do not edit either file.

Then emit:

```text
[MOBILE CHECKPOINT 2/5]
```

---

# 4. PHASE 3 — LOCATE AND READ DIRECT CURRENT AUTHORITY

Locate and READ DIRECTLY the best current source for each domain:

```text
A. CURRENT MERGED REPOSITORY STATE
B. CURRENT P2 CONTRACT
C. CURRENT REGISTRY
D. P2 FINAL EXECUTION AND COMPLETE CLOSURE
E. P3 MASTER PLANNING BLUEPRINT
F. APPROVED CONTROL ROOM VISUAL DIRECTION
```

Use direct current repository evidence wherever it exists.

Do not substitute:
- chat recollection;
- old handoff text;
- stale copies;
- inferred state;
- prototype DEMO values.

For each source return:

```text
SOURCE =
PATH =
COMMIT / VERSION / DATE =
READ_DIRECTLY = YES / NO
AUTHORITY_DOMAIN =
CURRENT / HISTORICAL / SUPERSEDED =
```

If multiple candidates exist, determine precedence from current governance instead of guessing by filename.

If a required source cannot be found:

```text
SOURCE_NOT_FOUND
```

Do not infer its contents.

Also identify direct current records for:

```text
P2_RUNNING
P2_CLOSED
P2_TERMINAL_OUTCOME
P3_STARTED
P3_CODE_IMPLEMENTATION_AUTHORIZED
REAL_MONEY_AUTHORIZED
```

Then emit:

```text
[MOBILE CHECKPOINT 3/5]
```

---

# 5. PHASE 4 — ROADMAP AND P3 RECONCILIATION

Target roadmap:

```text
P1 → P2 → P3 → POST-BETA
```

Expected meanings:

```text
P1 = Host Reconstitution
P2 = Prospective Paper Proof
P3 = Paper Beta Release
POST-BETA = Controlled-Live Readiness
```

Verify:

```text
NEW_STAGES = NONE
```

Forbidden stage proliferation:

```text
NO P3A
NO P3B
NO P3.5
NO P4
NO Recovery Stage
NO Control Room Stage
NO Monitoring Stage
NO Backup Stage
NO AI Stage
```

A capability/workstream is not a roadmap stage.

Verify exact P3 workstream count:

```text
P3_WORKSTREAM_COUNT = 12
```

Expected:

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
```

If direct authority differs, report the exact source and exact difference.

Do not repair anything in this session.

---

# 6. CURRENT EXECUTION BOUNDARY

Determine current truth from direct authority.

Return:

```text
P2_RUNNING =
P2_CLOSED =
P2_TERMINAL_OUTCOME =

P3_PLANNING_ALLOWED =
P3_STARTED =
P3_IMPLEMENTATION_AUTHORIZED =

REAL_MONEY_AUTHORIZED =
```

Preserve truthful P2 closure outcomes:

```text
PASS
FAIL
INCONCLUSIVE / INSUFFICIENT
```

Do not force PASS.

Do not classify absence of a natural lifecycle as automatic technical failure unless current direct authority explicitly requires that classification.

---

# 7. P3 ENTRY / EXECUTION SEMANTICS

Reconcile direct authority for:

```text
P3 planning during P2
P3-PLN-00 preparation
P3-PLN-00 final binding
P3-PLN-01 contract review/freeze
Owner authorization
P3_STARTED
P3 production implementation
```

Owner Shape Lock interpretation:

```text
P3 PLANNING / DESIGN
= may be allowed during P2

P3-PLN-00 DRAFT / PREPARATION
= planning, not production implementation

FINAL P2→P3 BINDING
= after truthful P2 closure

FINAL PLN-01 CONTRACT REVIEW / FREEZE
= before execution authorization

OWNER_AUTHORIZES_P3_EXECUTION
↓
P3_STARTED = YES
↓
P3 PRODUCTION IMPLEMENTATION / RUNTIME EXECUTION
```

Current direct authority wins.

If terminology differs:
- explain the difference;
- classify it;
- do not invent a bridge stage.

---

# 8. PRODUCT-SHAPE RECONCILIATION

Test whether direct authority requires reopening any of:

```text
Product identity
Application shell
Truth Strip
Sidebar / navigation
Inspector
Attention model

Command Center
Project & Continuity
Incidents

Market Workspace
Decisions
Trades & Positions

Risk & Authority
Evidence & Reconciliation
History

Operations
System
Settings

Desktop IA
Mobile IA
Arabic RTL
English LTR
Capability-driven reveal
State / trust vocabulary
Continuity model
```

Permanent navigation intent:

```text
NOW
  Command Center
  Project & Continuity
  Incidents

TRADING
  Market Workspace
  Decisions
  Trades & Positions

GOVERNANCE
  Risk & Authority
  Evidence & Reconciliation
  History

PLATFORM
  Operations
  System

Settings
```

Normal Level-B / Level-C implementation choices are NOT Product Architecture conflicts.

Examples that do NOT reopen architecture by themselves:

```text
new provider
new pair
new timeframe
backup implementation
notification method
off-host monitor
new evidence check
new operator action
new model/LLM
different storage adapter
```

These fit existing slots/workstreams unless direct authority proves otherwise.

---

# 9. VISUAL DIRECTION RECONCILIATION

Verify compatibility with:

```text
Trading Lab OS — Governed Control Room

dark-mode first
calm
premium
technical
trustworthy
precise
operations-control-room hierarchy before performance
not crypto-exchange clone
not retail buy/sell
not casino/cyberpunk

Arabic + English
RTL / LTR

PAPER prominent
REAL MONEY blocked explicit
Kill Switch isolated
UI = operator surface, not trading authority
```

Owner's final style interpretation:

```text
IMAGE 3 = BASE VISUAL IDENTITY
IMAGE 1 = COMMAND-CENTER / OPERATIONS FEEL
IMAGE 2 = CLARITY / BREATHING SPACE
```

Do not invent a fourth style.

This reconciliation does not authorize redesign.

---

# 10. PROTOTYPE TRUTH-MODEL CHECK

Verify final Prototype v0.2.4 remains semantically compatible.

Operational states:

```text
HEALTHY
DEGRADED
ACTION_REQUIRED where applicable
INCIDENT
RECOVERING
FAIL_CLOSED
STOPPED
```

Trust/freshness:

```text
FRESH
STALE
UNKNOWN
UNVERIFIED
CONFLICT
```

P2 outcomes:

```text
PASS
FAIL
INCONCLUSIVE / INSUFFICIENT
```

Verify specifically:

```text
Risk state propagation
Trades / PnL trust propagation
Closure event-time vs current-observation freshness
Market STALE / UNKNOWN overlay
No standalone Beta roadmap stage
P3 = Paper Beta Release
POST-BETA = Controlled-Live Readiness
```

Prototype DEMO values are not current runtime facts.

---

# 11. FIELD-SPECIFIC AUTHORITY

Do not invent one global truth hierarchy.

Use field-specific authorities:

```text
Governance / stage / contract
→ current merged governance authority

Runtime
→ actual runtime observation/stamp + declared relationship

Host
→ OS / host observations

Evidence
→ ledgers / archives / digests

Reconciliation
→ reconciliation record

Git / PR / merge
→ repository / GitHub records

UI summary
→ deterministic derived view only
```

UI snapshot, Resume Brief, browser state, cache or last-view marker must NOT become SSOT.

---

# 12. CONFLICT CLASSIFICATION

Every difference must be exactly one of:

```text
REAL_CONFLICT
EXPECTED_DIFFERENCE
HISTORICAL
SUPERSEDED
HANDOFF_ONLY
DEMO_ONLY
SOURCE_NOT_FOUND
```

For each REAL_CONFLICT:

```text
FIELD =
DIRECT SOURCE A =
DIRECT SOURCE B =
WHY IT CONFLICTS =
WINNING AUTHORITY =
MINIMUM CORRECTION REQUIRED =
TOUCHES P2 = YES / NO
REOPENS PRODUCT ARCHITECTURE = YES / NO
P0 = YES / NO
```

No implementation.
No edits.
No repair.

Then emit:

```text
[MOBILE CHECKPOINT 4/5]
```

---

# 13. NO-REOPEN TEST

Answer exactly:

```text
DOES DIRECT CURRENT AUTHORITY REQUIRE
THE FINAL PRODUCT ARCHITECTURE TO REOPEN?
```

Allowed answers:

```text
NO — PRODUCT SHAPE CAN REMAIN LOCKED
```

or:

```text
YES — P0 GOVERNING CONTRADICTION
```

If YES:
- identify the exact direct authority;
- identify the exact conflicting frozen product decision;
- do not broaden the reopening.

Preference ≠ P0.
Implementation detail ≠ P0.
Unresolved Level-C mechanism ≠ P0.
Future capability ≠ P0.

---

# 14. OWNER WALKTHROUGH GATE

Owner Walkthrough is allowed only if:

```text
DIRECT_CURRENT_AUTHORITY_RECONCILIATION = PASS
AND
P0_PRODUCT_SHAPE_CONFLICTS = 0
AND
FINAL_PROTOTYPE_COMPATIBILITY = PASS
```

Do NOT declare:

```text
LEVEL_A = FROZEN
```

Only the Owner performs Level-A Product/UX freeze after the walkthrough.

---

# 15. REQUIRED FINAL REPORT

Return:

## A. Direct sources table

Columns:

```text
SOURCE
PATH
VERSION / COMMIT
READ DIRECTLY?
AUTHORITY DOMAIN
CURRENT / HISTORICAL / SUPERSEDED
```

## B. Real conflicts table

Only REAL_CONFLICT rows.

## C. Product-shape verdict

Exactly:

```text
KEEP
```

or:

```text
P0_CONFLICT
```

## D. Exact final status block

```text
SESSION_MODE =
READ_ONLY_RECONCILIATION

REPOSITORY_ROOT =
CURRENT_HEAD =
CURRENT_MAIN_HEAD =
CURRENT_WORKTREE_STATE =

CURRENT_STAGE =

P2_RUNNING =
P2_CLOSED =
P2_TERMINAL_OUTCOME =

P3_PLANNING_ALLOWED =
P3_STARTED =
P3_IMPLEMENTATION_AUTHORIZED =

REAL_MONEY_AUTHORIZED =

DIRECT_SOURCES_REQUIRED = 6
DIRECT_SOURCES_READ =
DIRECT_SOURCES_MISSING =

ROADMAP =
P1 → P2 → P3 → POST-BETA

NEW_STAGES =
NONE / VIOLATION

P3_WORKSTREAM_COUNT =
12 / CONFLICT

PRODUCT_ARCHITECTURE =
KEEP / P0_CONFLICT

FINAL_PROTOTYPE =
COMPATIBLE / CONFLICT

DIRECT_CURRENT_AUTHORITY_RECONCILIATION =
PASS / CONFLICT / INCOMPLETE

OWNER_WALKTHROUGH_READY =
YES / NO

LEVEL_A =
NOT FROZEN

P2_TOUCHED =
NO

P3_IMPLEMENTATION_STARTED =
NO

GIT_MUTATED =
NO

RUNTIME_TOUCHED =
NO

FILES_MODIFIED =
NO

REAL_MONEY_AUTHORIZED =
NO / OTHER_DIRECT_AUTHORITY_VALUE

NEXT_OWNER_ACTION =
```

If PASS:

```text
NEXT_OWNER_ACTION =
OWNER WALKTHROUGH OF FINAL PRODUCT SHAPE
```

If INCOMPLETE:

```text
NEXT_OWNER_ACTION =
PROVIDE / LOCATE THE SPECIFIC MISSING DIRECT AUTHORITY SOURCE
```

If CONFLICT:

```text
NEXT_OWNER_ACTION =
REVIEW ONLY THE SPECIFIC P0 / AUTHORITY CONFLICTS LISTED ABOVE
```

Then emit:

```text
[MOBILE CHECKPOINT 5/5]
```

and STOP.

Do not implement anything after the report.

---

# APPENDIX A — FINAL MASTER PRODUCT SHAPE LOCK v1.2
## Embedded Owner Product-Shape Intent


# Trading Lab OS — FINAL MASTER PRODUCT SHAPE LOCK
## الخطة النهائية الشاملة لشكل المشروع والمنتج والصفحة الرئيسية — Owner Pre-Freeze Master

**التاريخ:** 2026-09-25  
**الحالة:** FINAL MASTER PRODUCT-SHAPE PLAN / PRE-CANONICAL / PLANNING ONLY  
**نطاق الوثيقة:** Project + Product + UX + Continuity + Recovery + P3 Planning Alignment  
**التنفيذ:** غير مصرح به داخل P3 حتى تحقق بوابات P2→P3 الحاكمة  
**P2:** مستمرة بدون أي تعديل من هذه الوثيقة  
**P3_STARTED:** NO  
**REAL_MONEY_AUTHORIZED:** NO  

---

# 0. الهدف النهائي من هذه الوثيقة

هذه الوثيقة هي **المرجع الشامل لإقفال شكل Trading Lab OS كمنتج** حتى لا نعيد فتح Product Architecture كلما أصبحت ميزة أو capability أو مصدر بيانات جديد جاهزًا.

الهدف منها أن يستطيع Claude Chat، إذا استلم هذا الملف وحده في نفس المحادثة، أن يعرف:

1. ما هو Trading Lab OS فعلًا.
2. ما هي المراحل الحاكمة بدون اختراع مراحل جديدة.
3. أين المشروع الآن، وما الذي هو Current/Historical/Handoff-only.
4. ما الذي يحكم P2 وكيف تغلق قانونيًا.
5. ما الذي يدخل داخل P3 بالضبط.
6. ما هو الشكل النهائي الثابت للبرنامج.
7. ما هي القوائم النهائية.
8. ما هي الصفحة الرئيسية النهائية.
9. ما الذي يظهر دائمًا، وما الذي يظهر فقط عندما يصبح حقيقيًا/مصرحًا به.
10. كيف يُعرض UNKNOWN / STALE / UNVERIFIED / RECOVERING بدون اختلاق حقيقة.
11. كيف نحل الاستمرارية بعد انقطاع الكهرباء/النت/الجهاز/Claude.
12. كيف نمنع UI أو Snapshot أو Chat من التحول إلى SSOT منافس.
13. ما الذي يُجمّد الآن وما الذي يظل Provisional وما الذي ينتظر P3.
14. ما الذي يجب على Claude فعله الآن، وما الذي لا يجوز له فعله.

القاعدة الحاكمة للمنتج:

> **القالب ثابت، والحقيقة هي التي تملأه.**

والقاعدة الحاكمة للتطوير:

> **إذا اشتغل شيء جديد، يظهر داخل مكانه الموجود أصلًا. لا نعيد فتح شكل المشروع.**

---

# 1. Authority / Evidence Labels — كيف نقرأ أي معلومة

أي معلومة تشغيلية أو حكومية في هذه الوثيقة يجب أن تُفهم بأحد التصنيفات التالية:

```text
VERIFIED
= قُرئت/أُثبتت مباشرة من مصدر حاكم أو مصدر تشغيل موثوق داخل نفس المراجعة.

HANDOFF_ONLY
= آخر حالة نقلها Owner/جلسة سابقة، لكن لم تُتحقق مباشرة من الـhost/repo في هذه المراجعة.

DERIVED
= مشتقة حتميًا من حقائق أخرى معروفة.

HISTORICAL
= صحيحة في وقتها وتظل سجلًا، لكنها لا تصف الحالة الحالية.

PROVISIONAL
= تصميم/عقد/خطة مرشحة، وليست Runtime authority.

UNKNOWN
= لا يوجد مصدر كافٍ للحسم.

SUPERSEDED
= لا يجوز استخدامها كحقيقة حالية.
```

قانون مهم:

> لا يتم ترقية `HANDOFF_ONLY` إلى `VERIFIED` بسبب تكرارها في محادثات كثيرة.

---

# 2. Source Basis — المصادر التي تبني عليها هذه الخطة

هذه الوثيقة تُبنى على المواد الحاكمة/المرجعية التالية، مع التمييز بين Authority وReference:

## 2.1 Governing / High-value project sources

- `Trading_Lab_OS_P3_Master_Planning_Blueprint_AR_EN.md`
- `Trading Lab OS — P2 Final Execution and Complete Closure.md`
- P2 executable/merged contract and registry when directly available.
- Current merged repository authority when directly available.

## 2.2 Product / Visual references

- `Trading_Lab_OS_P3_Control_Room_Approved_Design.md`
- `Trading Lab OS — Product Design Specification` + consolidation corrections.
- `Trading Lab OS — Whole-Project Canonical Review (1).md`
- `Trading Lab OS — Mock Prototype v0.2.2 (offline, non-production).html`

## 2.3 Historical sources

- FP-CONTROL-1 historical records.
- FP-CONTROL-2 historical records.
- Earlier P2 reports that predate FP-CONTROL-3 activation.

قانون الاستخدام:

```text
Current authority/runtime/evidence
> current contract/registry
> current P3 blueprint
> current product spec
> handoff
> historical reports
```

لكن **السلطة Field-specific** وليست Hierarchy واحدة لكل شيء؛ هذا موضح لاحقًا.

---

# 3. Roadmap Lock — لا مراحل جديدة

الخريطة الوحيدة للمشروع:

```text
P1 — Host Reconstitution
↓
P2 — Prospective Paper Proof
↓
P3 — Paper Beta Release
↓
POST-BETA — Controlled-Live Readiness
```

القوانين النهائية:

```text
NEW_STAGES = NONE
P3_IS_ONE_STAGE = YES
P3_WORKSTREAM_COUNT = 12
```

ممنوع إنشاء:

```text
P3A
P3B
P3.5
P4
Recovery Stage
Monitoring Stage
Control Room Stage
Backup Stage
AI Stage
Agent Stage
Source Inventory Stage
Design Freeze Stage
```

أي Finding أو Feature جديد يجب أن يذهب إلى:

1. Workstream موجودة داخل P3، أو
2. POST-BETA، أو
3. REFERENCE / DEFERRED.

**صعوبة التصنيف ليست مبررًا لفتح Stage.**

---

# 4. P3 — Workstream Lock: العدد = 12 فقط

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
```

لا Workstream رقم 13.

## 4.1 Placement law

### PLN-00
- final P2 truth
- P2 outcome
- registry reconciliation
- final runtime identity
- evidence archives/digests
- A15 final result
- shutdown proof
- incident history
- lessons learned

### PLN-01
- P3 scope
- acceptance
- authority
- entry law
- stage contract
- allowed / forbidden behavior

### PLN-02
- state inventory
- source inventory
- recovery dependency graph
- which source owns which fact
- missing vs derivable truth

### PLN-03
- backup
- verified backup
- retention
- off-host copy where justified
- restore points
- restore proof

### PLN-04
- host reboot
- unexpected host restart
- Docker recovery
- runtime recovery
- network restoration
- planned shutdown record

### PLN-05
- evidence survival
- chain durability
- archives
- digests
- corruption detection
- gap preservation
- post-restore evidence integrity

### PLN-06
- monitoring
- monitor-of-monitor
- host health
- Docker health
- runtime health
- feed/network/clock/disk
- off-host observation
- Owner notification
- heartbeat
- remote operational visibility

### PLN-07
- failure injection
- restart/reboot tests
- network-loss tests
- Docker-loss tests
- disk-pressure
- clock skew
- recovery tests
- restore tests
- evidence-gap tests

### PLN-08
- permissions
- Safe Stop
- Governed Restart
- Resume Paper
- manual reconciliation
- acknowledgement semantics
- Kill Switch
- action audit / preconditions

### PLN-09
- final product shell
- Command Center
- Project & Continuity
- navigation
- Arabic/English
- desktop/mobile
- state/provenance UX

### PLN-10
- Paper Beta test matrix
- acceptance evidence
- Owner acceptance
- beta completion

### PLN-11
- final freeze
- implementation handoff
- execution order
- dependency freeze
- implementation pack

---

# 5. Current Project State — latest handoff, not live verification

**مهم:** القيم التالية `HANDOFF_ONLY` ما لم تُقرأ مباشرة من الـhost/repo في نفس الجلسة.

```text
CURRENT_STAGE = P2 RUNNING                      HANDOFF_ONLY
ACTIVE_CONTROL = FP-CONTROL-3                  HANDOFF_ONLY
P2_CLOSED = NO                                 HANDOFF_ONLY
P3_STARTED = NO                                GOVERNING / HANDOFF-CONSISTENT
REAL_MONEY_AUTHORIZED = NO                     GOVERNING
```

آخر هوية Git/Runtime المعلنة:

```text
M2 runtime source = 3191285a                   HANDOFF_ONLY
M3 merged main = 52e0d2bf                     HANDOFF_ONLY
runtime worktree = detached @ 3191285a         HANDOFF_ONLY
control worktree = main @ M3                   HANDOFF_ONLY
```

هذا الاختلاف قد يكون **Expected by design** ولا يُسمى Conflict تلقائيًا.

آخر حالة P2 تشغيلية معلنة تقريبًا:

```text
WATCH = OK                                     HANDOFF_ONLY
RECONCILIATION = PASS                          HANDOFF_ONLY
14/14 findings present                        HANDOFF_ONLY
POST_T0+LIVE credited ≈ 12                    STALE_HANDOFF
GAP_BARS = 0                                  STALE_HANDOFF
TRADES = 0                                    STALE_HANDOFF
CAPABILITY = 9/12                             STALE_HANDOFF
FULL_TRADE_LIFECYCLE = NOT_YET_OBSERVED       STALE_HANDOFF
PROSPECTIVE_PAPER_EDGE = NOT_EVALUATED        HANDOFF_ONLY / CONTRACT-CONSISTENT
```

A15 handoff:

```text
A15 restart/continuity = PASS                  HANDOFF_ONLY
A15 final closure half = NOT YET COMPLETE     HANDOFF_ONLY
```

Reported monitor:

```text
tlos-p2-window-fp-control-3.timer
systemd --user
Persistent=yes
hourly at *:10 UTC
```

Reported continuity conclusion:

```text
SESSION_CAN_SAFELY_DISCONNECT = YES            HANDOFF_ONLY
```

Reported Owner-notification gap:

```text
DURABLE OWNER OUTBOUND NOTIFICATION = NONE     HANDOFF_ONLY
```

Reported exact hard cap:

```text
2026-10-24T12:01:14Z                           HANDOFF_ONLY
≈ 2026-10-24 15:01:14 Africa/Cairo
```

القاعدة الحاكمة نفسها:

```text
HARD CAP = ACTIVATION_UTC + 30 calendar days
NO automatic extension
```

---

# 6. P1 / P2 Historical Lock

## 6.1 P1

```text
P1 = CLOSED / PASS
```

لا يُعاد فتح P1 بسبب Finding جديد داخل P3.

## 6.2 FP-CONTROL-1 / FP-CONTROL-2

تظل Historical controls.

لا يتم:

- إعادة استخدامها كـcurrent cohort.
- نقل T0 أو evidence منها إلى FP-CONTROL-3.
- إعادة credit لها.
- تفسيرها كأنها current runtime.

FP-CONTROL-2 تاريخيًا سجّل عددًا كبيرًا من decisions بدون trades؛ هذا **Historical context** فقط، وليس prediction للحالة الحالية.

---

# 7. P2 Laws — لا تُعاد مناقشتها كتصميم

## 7.1 Evidence credit law

يُحتسب فقط evidence الذي يطابق CURRENT cohort law، بما في ذلك:

- correct role
- correct cohort_id
- correct source identity
- correct lane
- POST_T0
- LIVE
- valid chain
- lawful provenance

لا inherited evidence credit.

## 7.2 Performance law

```text
Positive P&L ≠ P2 PASS
Negative P&L ≠ P2 FAIL
Zero trades ≠ technical defect automatically
```

ممنوع:

- force a trade
- lower thresholds
- change strategy semantics
- alter exits
- widen markets just to obtain activity
- cherry-pick favorable conditions
- performance-shop

## 7.3 Normal terminal law

```text
NORMAL_TERMINAL_CONDITION =
  naturally completed full paper trade lifecycle
  + all 12 PAPER_TRADING_OPERATIONAL_CAPABILITY properties
    (9 pre-T0 + 3 post-T0)
  + reconciliation PASS
  + evidence PASS
  + safety PASS
```

`full_trade_lifecycle` يُعرض **بجانب** الـ12 وليس Property رقم 13.

## 7.4 Hard cap law

```text
HARD_CAP = ACTIVATION_UTC + 30 calendar days
NO automatic extension
```

بلوغ الـhard cap بدون lifecycle طبيعية ليس failure تلقائيًا.

## 7.5 Three lawful closure outcome families

```text
P2 CLOSED / PASS
P2 CLOSED / FAIL
P2 INCONCLUSIVE / INSUFFICIENT
```

### PASS
يتطلب ما يفرضه current contract، بما في ذلك capability/lifecycle/reconciliation/evidence/identity/safe-end/archives/merged closure.

### FAIL
FAIL تتعلق بـsystem/safety/integrity/authority failure، **وليس P&L**.

### INCONCLUSIVE / INSUFFICIENT
نتيجة قانونية عندما يكون evidence صالحًا لكن الطبيعي المطلوب لم يثبت ضمن النافذة.

لا يتم تغيير الاستراتيجية لصناعة PASS.

---

# 8. P2 Closure State ≠ Closure Outcome

## 8.1 Closure state ladder

```text
P2 RUNNING
↓
TERMINAL CONDITION DETECTED
↓
CLOSURE DUE
↓
CLOSURE TRANSACTION IN PROGRESS
  - Final closure evidence
  - Governed shutdown
  - Archive / seal / digest
  - Closure record / registry
  - Gates
  - Closure PR + CI
↓
OWNER_MERGE_REQUIRED
↓
OWNER NORMAL TWO-PARENT MERGE
↓
MERGED-MAIN VERIFICATION
↓
P2 CLOSED
```

لا يُفترض:

```text
terminal detected = runtime stopped
terminal detected = Owner action required immediately
terminal detected = P2 closed
```

## 8.2 Responsibility split

كل حالة حرجة يجب أن تعرض أربعة حقول مستقلة:

```text
SYSTEM_STATE
OWNER_ACTION
CLAUDE_ACTION
NEXT_GOVERNED_STEP
```

مثال terminal detected:

```text
SYSTEM: terminal trigger recorded
OWNER: none yet
CLAUDE: execute governed closure transaction when contract requires
NEXT OWNER GATE: OWNER_MERGE_REQUIRED
```

---

# 9. P3 Entry Law

P3 لا تبدأ تلقائيًا بعد إغلاق P2.

```text
P2 CLOSED
↓
P2 outcome review
↓
P3-PLN-00 Final P2 → P3 Reconciliation
↓
P3_ENTRY_TRUTH = RECONCILED
↓
P3-PLN-01 Contract & Acceptance
↓
Owner authorization as required
↓
P3-PLN-02 … P3-PLN-11
```

Outcome-dependent:

- PASS: لا تزال تحتاج reconciliation + contract + authorization.
- INCONCLUSIVE: لا auto-start؛ Owner يقرر المسار المحكوم.
- FAIL: تُحل failure authority أولًا.

---

# 10. Product Identity Lock

الهوية النهائية:

# Trading Lab OS — Governed Trading Operating System

والعائلة البصرية:

# Trading Lab OS — Governed Trading Control Room

ليس:

- trading bot بسيط
- crypto exchange clone
- retail Buy/Sell app
- performance dashboard
- Grafana clone
- agent framework
- monitoring-only app

المبادئ التي لا تُعاد فتحها:

```text
Execution ≠ Verified Outcome
Capability ≠ Authority
Observed ≠ Verified
Recovered ≠ Correct
UI ≠ Trading Authority
Chat ≠ Source of Truth
```

الواجهة = **Operator Surface** فقط.

---

# 11. Core Trading Architecture Lock

```text
Market / Data Truth
↓
Spotter
↓
Verifier
↓
Prior / Regime
↓
Risk Sizer
↓
Exit Contract
↓
One Core
↓
Paper Execution
↓
Reconciliation
↓
Verified Outcome
```

قواعد:

- Market/Data Truth = upstream truth/context layer.
- Spotter → Verified Outcome في UI = `Decision / Execution Trace`، وليس كامل architecture.
- One Core deterministic.
- LLM/Agents يمكن أن تساعد Research/Challenge/Explain/QA/Reporting.
- لا LLM/Agent/MCP/Skill يكتسب signal/risk/exit/execution/evidence authority تلقائيًا.

---

# 12. Final Product Shape Law — لا نعيد فتح المنتج

## 12.1 القاعدة الأساسية

> **الشاشات ثابتة؛ الحقيقة والقدرات هي التي تتغير داخلها.**

ميزة جديدة لا تنشئ صفحة جديدة تلقائيًا.

مصدر جديد لا يغير Navigation.

Capability جديدة تظهر في مكانها الموجود أصلًا.

## 12.2 Re-open criteria الوحيدة

بعد Level-A Freeze، يُسمح بإعادة فتح Product Architecture فقط إذا:

1. Governing requirement حتمي لا يمكن استيعابه داخل القالب الحالي.
2. Owner غيّر Product Scope نفسه خارج Governed Trading OS.
3. Usability acceptance أثبت أن Requirement حاكم لا يمكن تحقيقه داخل أي screen موجودة.

غير ذلك:

```text
FEATURE REQUEST ≠ ARCHITECTURE REOPEN
```

---

# 13. Permanent Application Shell — القالب النهائي

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ IDENTITY BAR                                                             │
│ Trading Lab OS · Stage/Substate · PAPER · Real Money BLOCKED             │
│ Owner Attention · View Heartbeat · AR/EN                                 │
├──────────────────────────────────────────────────────────────────────────┤
│ TRUTH STRIP                                                              │
│ Health · Authority · Evidence · Freshness · Runtime · Reconciliation     │
├──────────────────────────────────────────────────────────────────────────┤
│ CONDITIONAL ATTENTION BANNER                                             │
├───────────────┬───────────────────────────────────────────┬──────────────┤
│ SIDEBAR       │ MAIN CONTENT                              │ INSPECTOR    │
│ permanent     │ 12-column logical grid                   │ on demand     │
└───────────────┴───────────────────────────────────────────┴──────────────┘
```

مكونات ثابتة:

1. Identity Bar
2. Truth Strip
3. Sidebar
4. Main Content
5. Canonical Inspector
6. Conditional Attention Banner

لا Footer status rail مستقل.

## 13.1 Inspector behavior

- Wide desktop: dock candidate.
- Normal desktop/laptop: overlay/drawer.
- Tablet: sheet/overlay.
- Mobile: full-screen detail.

الـbreakpoint الدقيق Token/visual decision، وليس Architecture جديدة.

---

# 14. Final Navigation Lock — القوائم النهائية

```text
NOW / الآن
  Command Center / مركز التحكم
  Project & Continuity / المشروع والاستمرارية
  Incidents / الحوادث

TRADING / التداول
  Market Workspace / مساحة السوق
  Decisions / القرارات
  Trades & Positions / الصفقات والمراكز

GOVERNANCE / الحوكمة
  Risk & Authority / المخاطر والصلاحيات
  Evidence & Reconciliation / الأدلة والمطابقة
  History / السجل التاريخي

PLATFORM / المنصة
  Operations / العمليات
  System / النظام

Settings / الإعدادات
```

لا Top-level pages مستقلة لـ:

- Backup
- Restore
- Recovery
- Notifications
- Remote Monitoring
- AI
- Agents
- Security

تدخل داخل الشاشات الحالية.

---

# 15. Capability-Driven Reveal — «اللي يشتغل يظهر»

هذا هو القانون الذي يمنع إعادة فتح التصميم مستقبلًا.

## 15.1 Module states

### Source + capability + authority + freshness صحيحة

```text
ACTIVE / LIVE
```

اعرض المحتوى الكامل.

### Source موجود لكن authority تمنع

```text
NOT AUTHORIZED
```

اعرض الحقيقة والسبب والـauthority source، بدون زر نشط.

### Capability مخطط لها لكن لم تُنفذ

```text
NOT IMPLEMENTED
```

اعرض Placeholder مختصر وصادق، وليس widget وهمي.

### لا نعرف هل المصدر/التنفيذ موجود

```text
UNKNOWN
```

لا تفترض missing ولا healthy.

### آخر قيمة قديمة

```text
STALE + age
```

### Recovery بدأ ولم يتم verify

```text
RECOVERING / UNVERIFIED
```

### لا توجد بيانات بعد

```text
NO DATA
```

### النظام متوقف قانونيًا

```text
STOPPED
```

### Fail-closed presentation

```text
FAIL-CLOSED
```

دلالته التشغيلية الفعلية تُحدد في PLN-01/08، وليست من اختراع UI.

## 15.2 Reveal classes

### A. Always visible — دائمًا مرئي

- Stage/Substate
- PAPER / Real Money authority
- Truth Strip
- Owner/Claude/System/Next
- Risk & Authority destination
- Operations categories
- Project & Continuity

### B. Compact until meaningful — مختصر حتى توجد حقيقة مفيدة

- Backup
- Restore
- Off-host monitoring
- Notifications
- advanced decision trace
- advanced market context
- future capability rows
- future authorized actions

### C. Expand when active / actionable

عندما يصبح source موثوقًا + capability مطبقة + authority تسمح:

- يظهر summary على Command Center إذا كان مهمًا.
- يتوسع داخل Screen المخصصة.
- لا يتم إنشاء Screen جديدة.

### D. Never hide when unhealthy

ممنوع إخفاء:

- incident
- stale
- unknown
- conflict
- failed reconciliation
- backup unavailable
- authority block
- recovery pending verification

## 15.3 مثال

```text
Backup BEFORE:
UNKNOWN — source not inventoried

Backup AFTER:
HEALTHY — last verified backup 02:00
```

نفس الصفحة، نفس الـslot، لا redesign.

---

# 16. FINAL COMMAND CENTER — الصفحة الرئيسية النهائية

هذه أهم شاشة في Trading Lab OS.

هدفها خلال 10 ثوانٍ:

```text
هل النظام سليم؟
أين نحن في المشروع؟
هل عليّ أن أفعل شيئًا؟
ماذا يفعل Claude؟
ما الخطوة المحكومة التالية؟
ما آخر قرار؟
ما المخاطر/التعرض؟
هل توجد مراكز مفتوحة؟
هل توجد حادثة؟
هل evidence/reconciliation موثوقان؟
ما capability شغالة وما المحظور؟
```

## 16.1 Truth Strip vs body law

```text
TRUTH STRIP
= WHAT IS TRUE NOW

COMMAND CENTER BODY
= WHAT IT MEANS
  WHAT NEEDS ATTENTION
  WHAT IS NEXT
```

لا نكرر Truth Strip كـdashboard wall.

## 16.2 Desktop final layout

```text
┌ IDENTITY BAR ─────────────────────────────────────────────────────────────┐
│ Trading Lab OS │ Stage/Substate │ PAPER │ 🔒 Real Money BLOCKED         │
│ Owner: none/action │ View: live/stale │ AR | EN                         │
├ TRUTH STRIP ──────────────────────────────────────────────────────────────┤
│ Health │ Authority │ Evidence │ Freshness │ Runtime │ Reconciliation     │
├ ATTENTION BANNER — conditional ──────────────────────────────────────────┤
│ What happened · what remains safe · what is unknown · View detail         │
├ SITUATION ────────────────────────────────────────────────────────────────┤
│ Plain-language verdict                                                    │
│                                                                           │
│ OWNER              CLAUDE              SYSTEM              NEXT           │
│ exact action       exact delegated     observed state      governed step  │
├ PROJECT NOW ──────────────────────────────────────────────────────────────┤
│ P1 ✓ │ P2 current/closed │ P3 not authorized/running │ next gate          │
│ last governed checkpoint │ closure substep/outcome if applicable          │
├ TRADING NOW ──────────────────────────────────────────────────────────────┤
│ Latest Decision     │ Risk / Exposure        │ Open Positions             │
│ Market/Data context → Decision / Execution Trace                          │
├ ACTIVE CAPABILITIES ──────────────────────────────────────────────────────┤
│ Paper ✓ │ Long ✓ │ Shorts blocked │ Leverage blocked │ Real $ blocked    │
│ only critical summary — full matrix lives in Risk & Authority             │
├ ATTENTION / EXCEPTIONS ──────────────────────────────────────────────────┤
│ Open incidents            │ only non-healthy truth dimensions             │
├ SINCE LAST GOVERNED CHECKPOINT ──────────────────────────────────────────┤
│ governed events · gaps · restart · reconciliation · merge                 │
├ BELOW FOLD ───────────────────────────────────────────────────────────────┤
│ Performance — secondary, muted, never a health/proof verdict              │
└───────────────────────────────────────────────────────────────────────────┘
```

## 16.3 Why PROJECT NOW is permanent

لأن Trading Lab OS ليس Trading terminal فقط؛ هو Operating System للمشروع والتشغيل.

`PROJECT NOW` يمنع ضياع:

- stage truth
- closure state
- next gate
- last governed checkpoint

## 16.4 Why ACTIVE CAPABILITIES is permanent

حتى عندما تعمل capability جديدة، تظهر بدون redesign.

لا يعرض إلا أهم 4–6 facts المرتبطة بـexecution/authority.

التفاصيل الكاملة في `Risk & Authority`.

## 16.5 Command Center display rules

- Healthy = هادئ، لا panels خضراء ضخمة.
- Incident = banner واحد واضح + affected fields.
- Owner action = بارز فقط عند authority gate حقيقية.
- Claude action = منفصل عن Owner.
- Unknown = واضح وليس grey-good.
- Performance = أسفل fold.
- Technical detail = Inspector/System/Evidence drill-down.

---

# 17. FINAL MOBILE HOME

الموبايل = Monitoring / Continuity / Attention، وليس Desktop مصغرًا.

Navigation:

```text
Status
Resume
Incidents
More
```

أول viewport بدون scroll:

```text
TLOS · Stage · PAPER · Real-money lock · View heartbeat
Truth glyph row
Attention banner if any
Verdict
Owner action
Claude action
Next governed step
Project stage / next gate
Open positions / exposure
Open incident count
```

لا full chart.

لا consequential runtime controls افتراضيًا.

Kill Switch على mobile = غير موجود إلا بقرار authority مستقل مستقبلًا.

---

# 18. Screen Contracts — الشكل النهائي لكل شاشة

| Screen | السؤال الرئيسي | المحتوى النهائي | الذي يتغير بدون redesign |
|---|---|---|---|
| Command Center | ما الوضع الآن؟ | Situation, Project Now, Trading Now, capabilities, exceptions | values/states |
| Project & Continuity | أين نحن وكيف نستأنف؟ | Resume, checkpoints, closure ladder, uncertainty, timeline | derived truth |
| Incidents | ماذا حدث وما بقي آمنًا؟ | Known/Unknown/Affected/Unverified/Evidence | incident records |
| Market Workspace | ماذا رأى النظام في السوق؟ | OHLCV/context/data capabilities/decision markers | pairs/timeframes/capabilities |
| Decisions | لماذا اتخذ القرار؟ | Decision/Execution Trace + evidence refs | stage outputs where sourced |
| Trades & Positions | ماذا نملك وهل Verified؟ | open/closed, verification, risk, exit contract | execution capabilities |
| Risk & Authority | ما المسموح والمحظور؟ | dynamic Capability & Authority Matrix | rows from authority truth |
| Evidence & Reconciliation | هل يمكن الوثوق بالسجل؟ | checks/chains/archive/dataset/recon | contract-defined checks |
| History | ماذا حدث تاريخيًا؟ | governed timeline | event classes/sources |
| Operations | ماذا يمكن فعله وكيف نتعافى؟ | runtime/backup/restore/recovery/actions/emergency | capability + authority |
| System | هل الجهاز/runtime قادران على التشغيل؟ | host/runtime/feed/API/clock/containers/build identity | observed components |
| Settings | كيف أرى البرنامج؟ | language/time/density/return detection | UI-only preferences |

---

# 19. Project & Continuity — القفل النهائي

هذه الشاشة هي الضمان ضد ضياع المشروع بعد:

- الكهرباء
- الانترنت
- reboot
- Docker restart
- runtime restart
- فقد Claude session
- الغياب أيام/أسابيع

ترتيبها النهائي:

1. Stage Ribbon
2. Closure Ladder عندما تكون closure relevant
3. Closure Outcome
4. Resume From Here
5. Last Governed Checkpoint
6. Last Healthy Operational Observation
7. Current Observed State
8. Known
9. Unknown
10. Affected
11. Unverified
12. Owner
13. Claude
14. System
15. Next Governed Step
16. Forbidden Now
17. Since-Checkpoint Timeline
18. Uncertainty Register
19. Stage & Gate Map
20. Copy Resume Brief

`Resume Brief` = Derived artifact، وليس SSOT.

## 19.1 Project truth vs viewer convenience

Project truth:

```text
Since last governed checkpoint
Since last healthy operational observation
```

Viewer convenience:

```text
Since this user/device last viewed
```

الـviewer-last-visit لا يغير:

- authority
- stage
- evidence
- Owner gates
- health
- Resume truth

---

# 20. Incidents — final contract

كل Incident يجب أن يجيب:

```text
WHAT HAPPENED
WHEN
HOW DETECTED
KNOWN
UNKNOWN
AFFECTED
WHAT REMAINED SAFE
RECOVERY
CURRENT STATE
RECONCILIATION REQUIRED?
OWNER ACTION
CLAUDE ACTION
EVIDENCE
```

قانون اللغة:

- `Unexpected host restart` بدل `power failure` إذا السبب غير مثبت.
- لا نقول “positions unchanged” أو “no decisions happened” بدون evidence.
- Recovered لا تساوي Verified.

`Acknowledge Incident` = Proposed operator action، authority/audit semantics في PLN-08.

---

# 21. Market Workspace — final contract

الغرض:

> عرض السوق كما رآه النظام، وليس تقليد TradingView.

يحتوي:

- OHLCV
- volume
- regime
- volatility
- liquidity
- HTF context
- data freshness
- decision markers
- position entry/exit markers
- upstream Market/Data Truth context

لا:

- Buy/Sell buttons
- order book by default
- ticker tape
- retail-exchange clutter

Pairs/timeframes تأتي من capability truth، ليست hardcoded product law.

---

# 22. Decisions — final contract

لكل Decision:

```text
timestamp
pair/market
Market/Data Truth context
Spotter
Verifier
Prior/Regime
Risk Sizer
Exit Contract
One Core
Final decision
veto/reason
evidence refs
runtime/source identity
```

هذا يسمى:

```text
Decision / Execution Trace
```

وليس كامل Architecture.

---

# 23. Trades & Positions — final contract

- Open / Closed
- side generic
- size
- entry
- exit
- risk at entry
- exit contract
- execution trace
- reconciliation
- verified outcome
- PnL secondary

`long-only` ليست Product Architecture؛ current authority قد تعرض `SHORTS = BLOCKED`.

---

# 24. Risk & Authority — dynamic Capability Matrix

لا hardcoded boundary board أبدية.

استخدم:

# Capability & Authority Matrix

Rows تأتي من truth.

أمثلة حالية:

```text
Paper Trading
Long Entries
Shorts
Leverage
Margin
Futures
Real Money
Withdrawals
```

لكل row:

```text
CAPABILITY
STATE
AUTHORITY SOURCE
SINCE
EXPECTED RELATIONSHIP / PRECONDITIONS where relevant
```

Unknown capability:

```text
UNKNOWN — TREAT AS BLOCKED
```

Real Money wording النهائي:

```text
POST-BETA controlled-live authority
+ explicit Owner authorization
```

Withdrawals:

```text
separate post-beta authority
+ explicit Owner authorization
```

لا عبارة `new stage contract`.

---

# 25. Evidence & Reconciliation — final contract

يعرض Operator-readable truth:

- reconciliation result
- chain verification
- input/decision/trade/incident chain state
- source identity checks
- dataset lock
- archive integrity
- digest verification
- duplicate detection
- evidence freshness
- failed/unverified checks first

كل result expandable إلى:

```text
source
observed_at
verification time
provenance
hash/reference
raw excerpt / advanced details
```

---

# 26. Operations — final recovery surface

Operations ليست Button catalogue فقط.

```text
OPERATIONS OVERVIEW

RUNTIME
  Operational state
  Safe-state status
  Recovery state

BACKUP
  Backup health
  Last backup
  Last verified backup
  Retention / readiness

RESTORE
  Restore readiness
  Recovery points
  Last successful restore proof

RECOVERY
  Host recovery
  Runtime recovery
  Evidence recovery
  Post-recovery reconciliation
  Unresolved conditions
  Recovery history

AUTHORIZED ACTIONS
  Safe Stop
  Resume Paper
  Governed Restart
  Run Reconciliation
  Verify Backup
  Restore
  Acknowledge Incident
  ...only if authority exists

EMERGENCY
  Kill Switch — isolated
```

لا Backup/Recovery pages منفصلة.

## 26.1 Actions authority law

وجود Action في UI لا يعني authorization.

كل action مستقبلًا يحتاج:

- authority
- permission
- preconditions
- exact effect
- audit
- failure behavior
- recovery behavior

## 26.2 Kill Switch

يُجمّد الآن فقط:

- منفصل عن Safe Stop
- visually isolated
- high-friction
- consequence-aware
- authority-bound
- لا accidental activation

لا يُجمّد الآن:

- typed phrase
- hold duration
- number of confirmations
- exact mechanics

هذه PLN-08.

---

# 27. System — final contract

يعرض فقط ما يفيد تشغيل النظام:

- host
- boot/boot_id
- CPU/RAM/disk
- GPU where relevant
- network
- Docker/containers
- services
- timers
- runtime
- market feed
- API
- clock/NTP
- build/version
- governance source
- runtime source
- expected relationship

لا يتحول إلى Grafana clone.

Deep metrics يمكن ربطها بـGrafana لاحقًا دون إعادة تصميم System.

---

# 28. History — final contract

Timeline محكوم، وليس Chat history.

Event classes تشمل:

- stages
- runs/cohorts
- T0/activation
- Git/merge
- restart/reboot
- incidents
- backup/restore
- operator actions
- authority changes
- versions
- closure

Continuity وIncidents وHistory تستخدم **نفس event entities** لكن scoped views مختلفة.

---

# 29. Settings — final contract

UI preferences فقط:

- Arabic/English
- theme
- time display
- density
- viewer return-detection preference

P3 future:

- notification preferences
- remote access preferences

ممنوع أن تصبح Settings مكانًا لتغيير:

- risk authority
- trading mode authority
- evidence authority
- live authority

---

# 30. Truth / Trust / Freshness Model

كل displayed value يجب أن يحمل مفهومين مستقلين:

## 30.1 How obtained

```text
DIRECT OBSERVATION
DERIVED
CACHED
```

## 30.2 Can we trust it now?

```text
FRESH
STALE
UNKNOWN
UNVERIFIED
CONFLICT
```

Operational states أمثلة:

```text
HEALTHY
DEGRADED
ACTION_REQUIRED
INCIDENT
RECOVERING
FAIL-CLOSED
STOPPED
```

قوانين:

```text
UNKNOWN ≠ HEALTHY
RECOVERED ≠ VERIFIED
DIFFERENT ≠ CONFLICT automatically
```

`CONFLICT` فقط إذا خالفت علاقة معلنة.

---

# 31. Freshness Law

لا exact budgets من UI imagination.

```text
FRESHNESS_BUDGET =
  CONTRACT_DEFINED
  or SOURCE_CADENCE_DERIVED
```

يجب فصل:

- market feed cadence
- runtime observation
- P2 monitor cadence
- Prometheus scrape
- evidence write cadence
- reconciliation cadence
- GitHub refresh
- Control Room heartbeat

Browser/client ageing يجب أن يمنع stale green screen إذا backend مات.

---

# 32. Field-Specific Authority — لا global hierarchy واحدة

| Field | Authority concept |
|---|---|
| Stage / Contract | merged governance records / contracts |
| Runtime identity | runtime stamp + declared pin relation |
| Host | live OS/monitor observations |
| Evidence | evidence ledgers / archives |
| Reconciliation | reconciliation record |
| Git/PR/CI | repository / GitHub |
| Project summary | deterministic derived view |
| Viewer-last-visit | UI-only |

مثال:

```text
Governance main SHA != Runtime SHA
```

قد يكون صحيحًا by design.

الـUI يعرض:

```text
GOVERNANCE SOURCE
RUNTIME SOURCE
EXPECTED RELATIONSHIP
RELATIONSHIP STATUS
```

---

# 33. State Resolution / Data Architecture

```text
Authoritative Sources
↓
State Resolution Layer
↓
Materialized Operator View
↓
Control Room
```

`State Resolution Layer` = architectural responsibility، وليس قرار implementation.

لا نثبت الآن:

- daemon
- service
- CLI
- container
- systemd timer
- database

أي UI snapshot/history cache افتراضيًا:

```text
MATERIALIZED VIEW
NON-AUTHORITATIVE
REBUILDABLE
```

ممنوع أن يصبح SSOT ثانيًا.

---

# 34. Four Continuity Problems — يجب ألا تختلط

```text
A. RUNTIME SURVIVAL
B. EVIDENCE SURVIVAL
C. PROJECT CONTINUITY / RECONSTRUCTION
D. OWNER AWARENESS / NOTIFICATION
```

قد ينجو runtime بدون notification.

قد يعود runtime بدون verification.

قد تبقى logs بدون Resume UX.

---

# 35. Off-host Monitoring / Electricity / Internet Requirement

متطلب Owner النهائي:

> إذا الجهاز الرئيسي فقد الكهرباء أو الانترنت، أريد أن أعرف أن شيئًا حدث بدل أن تعتمد الحقيقة على نفس الجهاز الميت.

قانون معماري:

> **A dead host cannot report its own death.**

إذن P3 يجب أن تقيّم Off-host observation.

مكانه:

```text
P3-PLN-06 Monitoring & Operational Hardening
```

مع dependencies على PLN-02/03/04/05.

Planning questions:

- outbound heartbeat
- off-host observer
- mobile delivery
- loss-of-heartbeat
- host-down vs internet-down
- UPS/router telemetry if available
- secondary connectivity only if justified

لا implementation choice الآن.

---

# 36. Visual System Lock

المعتمد Semantic family:

- Dark-first
- Calm
- Premium
- Technical
- Trustworthy
- Operations-first
- no neon/casino/cyberpunk
- no retail exchange look
- performance secondary
- semantic colors only
- no color-only meaning
- Arabic RTL full
- English LTR full
- technical IDs isolated LTR

Exact font/hex/spacing/radii تبقى token candidates حتى Owner visual approval.

بعد Level-A visual freeze لا تُعاد فتحها إلا بسبب:

- accessibility failure
- rendering failure
- governing usability requirement

---

# 37. Arabic Terminology Lock Candidate

يجب أن يكون Concept واحد = مصطلح عربي واحد.

```text
System              = النظام
Runtime             = التشغيل
Regime              = نظام السوق
Recovery            = التعافي
Reconciliation      = المطابقة
Evidence            = الأدلة
Authority           = الصلاحية / المرجعية حسب نوع الحقل
Incident            = الحادثة
Resume              = الاستئناف
Verifier            = المُتحقق
Prior               = الاحتمال المسبق
Risk Sizer          = مُحدِّد المخاطر
Exit Contract       = عقد الخروج
One Core            = النواة الموحدة
Verified Outcome    = النتيجة المتحقق منها
```

يُراجع Owner مرة واحدة ثم يُجمّد.

IDs / SHA / pair / timestamps = LTR isolated.

Trading numbers = Western digits by default for clarity.

Financial chart time axis = LTR حتى في Arabic UI.

---

# 38. Responsive / Device Model Lock

## Desktop
Full operating surface.

## Tablet
Two-column monitoring/operations surface، Inspector overlay.

## Mobile
Monitoring/continuity first:

```text
Status
Resume
Incidents
More
```

لا full chart افتراضيًا.

لا Kill Switch افتراضيًا.

أي consequential mobile action يحتاج authority مستقلة مستقبلًا.

---

# 39. Prototype v0.2.2 — Pre-Freeze Corrections Required

قبل Level-A Freeze:

## P0 — Generic FAIL scenario

لا يرث optimistic PASS values إذا failure cause غير محدد.

يعرض:

```text
P2 CLOSED
OUTCOME = FAIL
RUNTIME = STOPPED / observed according to DEMO
EVIDENCE PACKAGE = PRESERVED
FAILURE CAUSE = READ CLOSURE RECORD / NOT INFERRED
P3 = NOT AUTHORIZED
```

dependent fields:

```text
AS CLOSURE RECORD STATES
```

أو:

```text
UNKNOWN IN THIS GENERIC DEMO
```

## P0 — Capability wording

احذف:

```text
Owner + new stage contract
```

واستخدم post-beta authority language.

## P1 — Resume copy truthfulness

Clipboard failure ≠ “copied”.

## P1 — Render evidence claim

لا تدّع browser matrix PASS بدون Browser-level evidence.

## P1 — Offline self-contained

Prototype review artifact:

```text
EXTERNAL_REQUESTS = 0
NETWORK_DEPENDENCIES = 0
LIVE_SYSTEM_CONNECTIONS = 0
```

No external fonts/scripts/styles/fetch/websocket/telemetry.

---

# 40. Required Prototype Scenario Catalogue

الـPrototype النهائي يجب أن يمثل على الأقل:

```text
1. Normal / Healthy
2. Control Room Stale
3. Network / Data Degraded
4. Unexpected Host Restart
5. Recovering
6. Reconciliation Failed
7. Unknown Current State
8. Terminal Condition Detected
9. Closure Due
10. Closure Transaction In Progress
11. OWNER_MERGE_REQUIRED
12. Merged-Main Verification
13. P2 CLOSED / PASS
14. P2 CLOSED / FAIL
15. P2 INCONCLUSIVE / INSUFFICIENT
```

كلها DEMO.

لا live connection.

---

# 41. Final Command Center Acceptance

لا Freeze للصفحة الرئيسية إلا إذا الإجابات كلها PASS:

1. خلال 10 ثوانٍ أعرف الحالة الحالية؟
2. أعرف Stage/Substate؟
3. أعرف PAPER / Real Money authority؟
4. أعرف Owner action؟
5. أعرف Claude action؟
6. أعرف System state؟
7. أعرف Next governed step؟
8. أعرف Latest Decision؟
9. أعرف Risk/Exposure؟
10. أعرف Open Positions؟
11. أعرف critical active/blocked capabilities؟
12. أعرف Open incidents؟
13. أعرف Evidence/Recon trust؟
14. أعرف Last Governed Checkpoint؟
15. capability جديدة تظهر بدون redesign؟
16. source غير موجود يظهر UNKNOWN وليس fake data؟
17. Performance ثانوية؟
18. الصفحة هادئة Healthy؟
19. Project state واضح وليس Trading-only؟
20. لا duplicate Truth Strip؟

إذا PASS كلها:

```text
COMMAND_CENTER_SHAPE = FROZEN
```

---

# 42. Final Product Acceptance / No-Reopen Freeze

Level-A لا يعتبر Frozen إلا بعد Owner walkthrough يوافق على:

- Navigation
- Application shell
- Command Center
- Project & Continuity
- Incidents
- Operations
- Risk & Authority
- Evidence & Reconciliation
- System
- Arabic desktop
- Arabic mobile
- Inspector behavior
- PASS / FAIL / INCONCLUSIVE scenarios
- Unknown vs Stale vs Recovering
- capability-driven reveal law

ثم:

```text
PRODUCT_ARCHITECTURE = FROZEN
NAVIGATION = FROZEN
SCREEN_PURPOSES = FROZEN
RESPONSIVE_IA = FROZEN
STATE_UX = FROZEN
CAPABILITY_REVEAL_MODEL = FROZEN
ARABIC_GLOSSARY = FROZEN
```

---

# 43. Three Freeze Levels — لا مستوى رابع

## LEVEL A — PRODUCT / UX

Freeze after Owner walkthrough:

- product identity
- shell
- navigation
- screen purposes
- information hierarchy
- Project & Continuity placement
- Command Center
- Inspector pattern
- mobile IA
- Arabic/English behavior
- state vocabulary/presentation
- visual family
- capability-driven reveal

## LEVEL B — DATA CONTRACT

Provisional until PLN-02:

- ProjectState schema
- entity relationships
- exact field authority mapping
- provenance schema
- freshness mapping
- event schema
- incident schema
- Resume Brief schema
- screen data requirements

## LEVEL C — OPERATIONAL

Wait for P3 authority:

- live adapters
- State Resolution implementation form
- systemd units
- polling/scheduling
- storage/persistence
- notifications
- remote access
- backup implementation
- restore implementation
- recovery implementation
- operator permissions
- Safe Stop mechanics
- Kill Switch mechanics

```text
NO LEVEL D
```

---

# 44. Required P3 Planning Artifact Set — لا document proliferation

الـP3 Blueprint يتوقع مجموعة مخرجات أساسية؛ لا ننشئ عشرات SSOTs جديدة فوقها.

Canonical/expected set includes:

```text
P3_ENTRY_STATE.md
P3_CONTRACT.md
P3_ACCEPTANCE_MATRIX.md
P3_AUTHORITY_MATRIX.md
P3_STATE_INVENTORY.md
P3_RECOVERY_DEPENDENCY_GRAPH.md
P3_BACKUP_RESTORE_SPEC.md
P3_FAILURE_RECOVERY_MATRIX.md
P3_EVIDENCE_DURABILITY_SPEC.md
P3_MONITORING_SPEC.md
P3_OPERATOR_CONTROL_SPEC.md
P3_DESIGN_SYSTEM.md
P3_CONTROL_ROOM_SPEC.md
P3_PAPER_BETA_TEST_PLAN.md
P3_EXECUTION_PLAN.md
```

يُعمل `P3 ARTIFACT CROSSWALK` بدل إنشاء وثائق متوازية بلا ضرورة.

لكل Artifact:

```text
PURPOSE
WORKSTREAM
CURRENT SOURCE MATERIAL
STATUS
WHAT REMAINS
FINAL OWNER/AUTHORITY GATE
```

---

# 45. P3 Workstream → Product Surface Mapping

| Workstream | Product surfaces most affected |
|---|---|
| PLN-00 Reconciliation | Project & Continuity, History, Evidence |
| PLN-01 Contract & Acceptance | Risk & Authority, all action states |
| PLN-02 State & Recovery Inventory | State Resolution, all screens |
| PLN-03 Backup & Restore | Operations, History, Incidents |
| PLN-04 Host/Runtime Recovery | Operations, System, Incidents, Continuity |
| PLN-05 Evidence Durability | Evidence, Continuity, History |
| PLN-06 Monitoring | System, Incidents, mobile awareness, off-host |
| PLN-07 Failure/Recovery Verification | Incidents, History, acceptance fixtures |
| PLN-08 Operator Controls | Operations, Risk & Authority |
| PLN-09 Control Room UX/UI | entire product shell |
| PLN-10 Paper Beta Acceptance | acceptance/status surfaces |
| PLN-11 Final Freeze/Execution | implementation handoff, version identity |

لا Workstream جديدة بسبب UI requirement.

---

# 46. Work We Finish While P2 Runs

## FINISH NOW — source-safe planning/design

- direct authority-document reconciliation
- Product Design v0.2 canonical preparation
- Prototype correction + Owner walkthrough
- Arabic terminology review
- mobile review
- P3 artifact crosswalk
- P3 contract draft
- acceptance matrix draft
- authority matrix draft
- failure/recovery catalogue
- backup/restore architecture draft
- monitoring/off-host alternatives
- Operator Control Contract draft
- P2→P3 reconciliation checklist
- Level-C decision register
- implementation handoff structure

## DRAFT NOW / BIND AFTER P2

- authoritative source mappings
- final state inventory
- exact field relationships
- final freshness budgets
- final recovery rules
- final backup scope
- final notification method
- final operator permissions

## WAIT FOR AUTHORIZATION

- production code
- live source wiring
- new systemd units
- new monitors
- host fault injection
- backup drills
- restore drills
- reboot tests
- network-loss tests
- operator control execution
- Kill Switch execution
- P3 execution PRs

---

# 47. Forbidden During P2

ممنوع بسبب هذه الخطة:

```text
P2 runtime mutation
Strategy mutation
Risk mutation
Dataset mutation
T0 mutation
Cohort mutation
pair-set manipulation to get activity
threshold lowering
forced trade
forced entry
forced exit
evidence rewriting
gap backfill
silent window extension
P3 production code
P3 live integration
P3 execution PR
live trading
real money
```

Planning/design/mock only.

---

# 48. Security / Failure Review — لا Stage جديدة

يجب أن تستوعب P3 الحالية كل هذه المخاطر:

- stale-data deception
- UI cache becoming authority
- manual status drift
- false runtime/main conflict
- partial source outage
- clock skew
- host loss
- internet loss
- Docker loss
- monitor loss
- monitor-of-monitor loss
- evidence tail corruption
- backup regression
- stale restore point
- duplicate execution after recovery
- recovered-but-unverified shown healthy
- Owner action executed by Claude
- UI bypassing authority
- public dashboard exposure
- secrets leaking into UI
- mobile controls gaining authority

كل Finding يُسكن داخل PLN-00…11، وليس Stage جديدة.

---

# 49. Infrastructure Discipline

Prefer existing/simple stack.

لا introduce by default:

- Kubernetes
- Kafka
- Ray
- distributed event bus
- second tracing system
- new authority database
- agent swarm
- cloud control plane

أي dependency جديدة تحتاج:

```text
missing capability
why existing stack cannot provide it
operational cost
security impact
recovery impact
acceptance test
```

---

# 50. Owner Walkthrough — آخر مراجعة للشكل قبل Freeze

الترتيب المقترح:

1. Command Center — Normal
2. Project & Continuity — Normal
3. Unexpected Restart → Recovering
4. Unknown State vs Control Room Stale
5. Closure Due
6. OWNER_MERGE_REQUIRED
7. P2 CLOSED / PASS
8. P2 CLOSED / FAIL
9. P2 INCONCLUSIVE / INSUFFICIENT
10. Operations / Recovery
11. Risk & Authority capability matrix
12. Arabic Desktop
13. Arabic Mobile Status
14. Arabic Mobile Resume
15. Inspector dock/drawer

لكل محطة Owner يقرر فقط:

```text
APPROVE
or
REVISE THIS SPECIFIC UX POINT
```

لا إعادة فتح Architecture عامة.

---

# 51. Direct Authority Reconciliation — gate before CANONICAL label

قبل تسمية Product Design v0.2 بأنها `CANONICAL` يجب reconcile مباشرة:

- current merged repo authority
- current P2 contract
- current registry
- P2 Final Execution and Complete Closure
- P3 Master Planning Blueprint
- Approved Control Room Visual Direction
- latest Product Design / prototype

لكل Source:

```text
SOURCE
VERSION / DATE
READ DIRECTLY? YES/NO
WHAT IT GOVERNS
CONFLICT FOUND?
WINNING AUTHORITY
REQUIRED CORRECTION
```

إذا المصدر غير مقروء:

```text
SOURCE_NOT_READ
```

ولا نختلق Canonical certainty.

---

# 52. Final No-Reopen Law

بعد Level-A Freeze، الأشياء التالية لا تعيد فتح Product Architecture:

- pair جديدة
- timeframe جديد
- strategy جديدة
- data provider جديد
- monitoring source
- backup implementation
- notification method
- off-host observer
- remote mobile delivery
- capability row جديدة
- operator action جديدة
- evidence check جديد
- incident class جديدة
- research reference جديدة
- model/LLM/tool change

تدخل كلها داخل:

```text
existing screens
existing workstreams
existing state/capability model
```

---

# 53. FINAL DIRECTIVE TO CLAUDE CHAT

استخدم هذه الوثيقة كـ **Final Master Product Shape Lock Plan**.

المطلوب منك الآن ليس اقتراح Architecture جديدة.

المطلوب:

1. Reconcile هذه الوثيقة مباشرة مع المصادر الحاكمة المتاحة.
2. لا تفتح Stage أو Workstream أو Top-level page جديدة.
3. صحح Prototype v0.2.2 في Pre-Freeze corrections فقط.
4. طبّق `PROJECT NOW` و`ACTIVE CAPABILITIES` في Command Center كـcompact summaries بدون تكرار Truth Strip.
5. تأكد أن كل Screen النهائية لها contract ثابت.
6. طبّق Capability-Driven Reveal: ما يشتغل ويُصرح له يظهر داخل slot الموجود؛ غير الجاهز يظهر بحالته الصادقة.
7. لا تخفي unhealthy/unknown/blocked truth.
8. لا تنشئ SSOT جديد للـUI.
9. لا تثبت State Resolution implementation قبل PLN-02/Level C.
10. اكتب `Trading Lab OS — Product Design Specification v0.2 CANONICAL` فقط بعد Direct Authority Reconciliation = PASS.
11. لا تبدأ P3 implementation.
12. لا تلمس P2.

## Required Claude output

```text
A. DIRECT AUTHORITY RECONCILIATION
B. CONFLICT / EXPECTED-DIFFERENCE TABLE
C. PRE-FREEZE PROTOTYPE CORRECTIONS
D. FINAL COMMAND CENTER WIREFRAME
E. FINAL NAVIGATION CONFIRMATION
F. CAPABILITY-DRIVEN REVEAL MATRIX
G. FINAL SCREEN CONTRACT CONFIRMATION
H. P3 ARTIFACT CROSSWALK
I. ARABIC GLOSSARY
J. OWNER WALKTHROUGH CHECKLIST
K. LEVEL-A FREEZE DECISION
L. REMAINING LEVEL-B / LEVEL-C ITEMS ONLY
```

نهاية رد Claude يجب أن تكون:

```text
ROADMAP = P1 → P2 → P3 → POST-BETA
NEW_STAGES = NONE
P3_IS_ONE_STAGE = YES
P3_WORKSTREAM_COUNT = 12

CURRENT_STAGE =
P2_CLOSED =
P3_STARTED = NO
REAL_MONEY_AUTHORIZED = NO

DIRECT_AUTHORITY_RECONCILIATION =
PRODUCT_ARCHITECTURE = FROZEN / NOT YET FROZEN
NAVIGATION = FROZEN / NOT YET FROZEN
COMMAND_CENTER = FROZEN / REVISE
PROJECT_CONTINUITY = FROZEN / REVISE
CAPABILITY_REVEAL_MODEL = FROZEN / REVISE
ARABIC_GLOSSARY = FROZEN / REVISE

LEVEL_A =
LEVEL_B = PROVISIONAL
LEVEL_C = WAIT FOR P3 AUTHORITY

P2_TOUCHED = NO
P3_IMPLEMENTATION_STARTED = NO
REAL_MONEY_AUTHORIZED = NO
```

ثم خطوة واحدة فقط:

```text
RECOMMENDED_NEXT_ACTION =
```

لا Roadmap جديدة.

---

# 54. Final Owner Summary

الشكل النهائي المطلوب:

```text
ONE PRODUCT
ONE SHELL
ONE NAVIGATION
ONE TRUTH MODEL
ONE CONTINUITY MODEL
ONE OPERATIONS SURFACE
ONE CAPABILITY/STATUS MODEL
DYNAMIC CAPABILITIES
NO MANUAL STATUS TRUTH
NO SECOND SSOT
NO NEW STAGES
NO ARCHITECTURE REOPEN FOR ORDINARY FEATURES
```

أهم قانونين:

> **إذا اشتغل شيء جديد، يظهر داخل مكانه الموجود أصلًا. لا نعيد فتح شكل المشروع.**

> **إذا الحقيقة غير معروفة، نعرض UNKNOWN. لا نخترع نجاحًا ولا بيانات.**

---

# 55. Final Pre-Freeze Decision Target

بعد أن يراجع Owner الـPrototype المصحح ويوافق على Level A:

```text
PRODUCT_SHAPE = APPROVED / FROZEN
PRODUCT_ARCHITECTURE = FROZEN
NAVIGATION = FROZEN
COMMAND_CENTER_SHAPE = FROZEN
PROJECT_CONTINUITY_SHAPE = FROZEN
CAPABILITY_REVEAL_MODEL = FROZEN
RESPONSIVE_IA = FROZEN
ARABIC_GLOSSARY = FROZEN

LEVEL_B = PROVISIONAL UNTIL PLN-02
LEVEL_C = BIND INSIDE P3 UNDER AUTHORITY
```

بعد هذا القرار، لا تُفتح Product Architecture مرة أخرى بسبب Feature عادية.
---

# 54. FINAL INDEPENDENT PRE-FREEZE REVIEW — 2026-09-25
## المراجعة المستقلة الأخيرة قبل Owner Walkthrough

هذه الإضافة هي آخر مراجعة تصحيحية على:
- `Trading Lab OS — Whole-Project Canonical Review (2).md`
- `Trading Lab OS — Mock Prototype v0.2.3 (offline, non-production).html`

ولا تعيد فتح Product Architecture.

القانون من هذه النقطة:

```text
NO NEW STAGE
NO NEW WORKSTREAM
NO NEW TOP-LEVEL PAGE
NO ARCHITECTURE REDESIGN
```

أي تصحيح متبقٍ هو **Truth-State Consistency Patch** داخل الـslots الحالية فقط.

---

## 54.1 Independent validation result

تم فحص Prototype v0.2.3 بصورة مستقلة باستخدام Headless Chromium.

النتيجة:

```text
SCENARIO_COUNT                 = 15
LANGUAGES                      = 2
DEVICE_MODES                   = 2
PRIMARY_SCENARIO_COMBINATIONS  = 60
FAILED_COMBINATIONS            = 0
UNCAUGHT_PAGE_ERRORS           = 0
UNDEFINED_TEXT                 = 0
EXTERNAL_REQUESTS              = 0
NETWORK_DEPENDENCIES           = 0
LIVE_SYSTEM_CONNECTIONS        = 0

DESKTOP_NAVIGATION:
  Command Center               = PASS
  Project & Continuity         = PASS
  Incidents                    = PASS
  Market Workspace             = PASS
  Decisions                    = PASS
  Trades & Positions           = PASS
  Risk & Authority             = PASS
  Evidence & Reconciliation    = PASS
  History                      = PASS
  Operations                   = PASS
  System                       = PASS
  Settings                     = PASS

INSPECTOR                      = PASS
RETURN_DETECTION               = PASS
```

هذا يثبت أن v0.2.3 مستقرة كـreview prototype.

لا يثبت:
- Safari
- Firefox
- physical mobile browsers
- screen readers
- production connectivity
- runtime adapters

ولا يجوز توسيع claim خارج ما تم اختباره.

---

# 55. DIRECT AUTHORITY RECONCILIATION — UPDATED UNDER THIS REVIEW

تمت مراجعة مباشرة للمصادر التالية في بيئة هذه المراجعة:

```text
P3 Master Planning Blueprint               = DIRECTLY REVIEWED
P3 Control Room Approved Visual Direction = DIRECTLY REVIEWED
P2 Final Execution and Complete Closure    = DIRECTLY RETRIEVED / REVIEWED
```

ما زال يلزم قبل `CANONICAL`:

```text
CURRENT MERGED REPOSITORY = SOURCE_NOT_READ
CURRENT P2 CONTRACT       = SOURCE_NOT_READ
CURRENT REGISTRY          = SOURCE_NOT_READ
```

إذًا:

```text
DIRECT_AUTHORITY_RECONCILIATION = PARTIAL
CANONICAL_LABEL                 = BLOCKED
LEVEL_A_PRODUCT_FREEZE          = BLOCKED UNTIL DIRECT CURRENT AUTHORITY CHECK COMPLETES

القانون النهائي:

```text
قبل Owner Walkthrough وقبل Level A Freeze:
يجب قراءة ومطابقة:
- CURRENT MERGED REPOSITORY
- CURRENT P2 CONTRACT
- CURRENT REGISTRY
- P2 Final Execution and Complete Closure
- P3 Master Planning Blueprint
- Approved Control Room Visual Direction

أي تعارض حقيقي:
يُصحح داخل الـslots الحالية فقط.

لا redesign.
لا Stage جديدة.
لا Workstream جديدة.
لا Top-level page جديدة.
```
```

الـCanonical label يظل gated حتى current merged authority / contract / registry تُقرأ مباشرة.

---

# 56. P3 ENTRY TERMINOLOGY — FINAL RECONCILIATION

يوجد فرق لغوي يجب تثبيته مرة واحدة حتى لا يعاد فتحه:

الـP3 Blueprint يقول إن:

```text
P2_CLOSED
→ P2 outcome reviewed
→ OWNER_AUTHORIZES_P3
→ P3 START
```

وفي نفس الـBlueprint، التخطيط بعد P2 يمر عبر:

```text
P2 → P3 reconciliation
→ Final P3 review
→ Freeze P3 contract
→ Owner authorization
→ P3 execution
```

الحل النهائي المتسق:

```text
P2_CLOSED
↓
P2 OUTCOME REVIEW
↓
P3-PLN-00 FINAL P2→P3 RECONCILIATION
    (entry-preparation / planning; NOT production implementation)
↓
FINAL P3 CONTRACT REVIEW / PLN-01 FREEZE
    (planning / contract preparation)
↓
OWNER_AUTHORIZES_P3_EXECUTION
↓
P3_STARTED = YES
↓
P3 EXECUTION / AUTHORIZED WORK
```

وبالتالي:

```text
P3-PLN-00 / final PLN-01 preparation
≠ P3 production implementation

OWNER authorization
= gate before P3 execution / runtime implementation
```

هذا يحسم التعارض اللفظي بدون Stage جديدة.

---

# 57. FINAL PROTOTYPE PATCH — REQUIRED BEFORE OWNER WALKTHROUGH

Architecture v0.2.3 تُحفظ كما هي.

المطلوب فقط تصحيح State Propagation في الصفحات التفصيلية.

## 57.1 P0 — Risk & Authority must be state-aware

المشكلة الحالية:

Full `Risk & Authority` screen تعرض DEMO current metrics ثابتة مثل:

```text
Exposure     18% / 40%
Daily loss   0.4% / 2.0%
Vetoes       3
Risk/trade   0.5%
```

حتى في حالات:

```text
CONTROL ROOM STALE
UNKNOWN CURRENT STATE
P2 CLOSED / PASS
P2 CLOSED / FAIL
P2 INCONCLUSIVE / INSUFFICIENT
```

بينما Command Center نفسها تتعامل مع بعض هذه الحالات بصورة أصح.

هذا ممنوع لأن:

```text
DETAIL SCREEN TRUTH
MUST NOT BE MORE OPTIMISTIC
THAN COMMAND CENTER TRUTH
```

### Required behavior

#### NORMAL
```text
Exposure = DEMO 18% / 40%
Daily loss = DEMO 0.4% / 2.0%
Vetoes = DEMO 3
```

#### CONTROL ROOM STALE
اعرض:

```text
Exposure = last known 18% / 40% · STALE
Daily loss = last known · STALE
Vetoes = last known · STALE
```

أو equivalent truthful stale presentation.

لا تعرض رقمًا current-looking بلا stale label.

#### UNKNOWN CURRENT STATE
اعرض:

```text
Exposure = UNKNOWN
Current daily loss = UNKNOWN
Current veto count = UNKNOWN
```

مع last-known value اختياري وموسوم بوضوح بأنه last-known.

#### NETWORK / DATA DEGRADED
إذا valuation تعتمد على market data القديمة:

```text
Exposure valuation = UNVERIFIED / STALE
```

ولا تدّع current mark-to-market certainty.

#### RESTART / RECOVERING
إذا position state بعد restart غير متحقق:

```text
Exposure = UNVERIFIED
```

حتى reconciliation تثبت الحالة.

#### CLOSURE TRANSACTION / OWNER MERGE / VERIFY / P2 CLOSED
إذا runtime تم إيقافه محكومًا ولا توجد open positions:

```text
CURRENT EXPOSURE = 0%
OPEN POSITIONS   = 0
```

limits/config يمكن أن تظل معروضة كـgoverned configuration.

#### P2 CLOSED / FAIL
لأن Generic FAIL لا يحدد failure cause:

```text
CURRENT EXPOSURE = AS CLOSURE RECORD STATES
or UNKNOWN IN THIS GENERIC DEMO
```

ما لم يوجد current observation مستقل يثبت 0.

### Important separation

لا تخلط:

```text
CURRENT EXPOSURE
```

مع:

```text
RISK LIMIT CONFIGURATION
```

يمكن أن يكون current exposure = 0 أو UNKNOWN بينما risk cap = 40% ما زال contract/config fact.

---

## 57.2 P0 — Trades & Positions PnL must honor trust state

المشكلة الحالية:

Open position PnL ما زالت تظهر كرقم:

```text
+0.6%
```

في:

```text
CONTROL ROOM STALE
NETWORK / DATA DEGRADED
UNKNOWN STATE
RESTART / RECOVERING
```

حتى عندما position أو price truth ليست verified.

### Required behavior

#### FRESH + VERIFIED
```text
PnL = numeric DEMO value
```

#### PRICE / MARKET STALE
```text
PnL = PRICE STALE
```

أو:

```text
LAST KNOWN PnL · STALE
```

#### POSITION / POST-RESTART UNVERIFIED
```text
PnL = UNVERIFIED
```

#### CURRENT STATE UNKNOWN
```text
PnL = UNKNOWN
```

لا تعرض numeric current PnL إذا source truth غير current/verified.

Verification column يجب أن يسبق PnL كما هو الآن.

---

## 57.3 P1 — Closure freshness wording must be internally consistent

في closed scenarios، إذا Truth Strip تقول:

```text
Freshness = FRESH
Runtime = STOPPED
```

فإن runtime stopped يجب أن يكون **current observation**.

لا تقل:

```text
Runtime stopped · observed at DEMO 12:30
```

ثم تعرض في 14:00:

```text
Freshness = FRESH
```

إلا إذا 12:30 هو shutdown-event timestamp وليس current-observation timestamp.

التصحيح الأفضل:

```text
Governed shutdown occurred: 12:30
Current runtime observation: STOPPED · observed 4s ago
```

أو إذا لا يوجد current observation:

```text
Runtime last observed stopped at 12:30 · STALE
Current runtime state = UNKNOWN
```

لا يوجد خيار ثالث.

---

## 57.4 P1 — Market Workspace stale / unknown presentation

لا redesign.

أضف فقط state overlay داخل chart slot الحالي.

### STALE
- chart ينتهي عند آخر known bar.
- stale band / `data ends ... ago`.
- context = STALE.
- لا markers جديدة بعد data end.

### UNKNOWN
- last-known chart يمكن عرضه.
- لكن overlay واضح:

```text
CURRENT MARKET STATE UNKNOWN
LAST OBSERVATION = ...
```

لا يبدو chart كأنه live/current.

---

# 58. REVIEW DOCUMENT CORRECTION

`Whole-Project Canonical Review (2)` قوية وصحيحة في معظمها.

لكن قبل اعتمادها كآخر review:

## 58.1 Update direct-source table

إذا أُرسلت المصادر إلى Claude في نفس المحادثة، يجب تحديث:

```text
P3 Master Planning Blueprint
P3 Control Room Approved Visual Direction
P2 Final Execution and Complete Closure
```

من:

```text
SOURCE_NOT_READ
```

إلى:

```text
DIRECTLY_READ
```

ثم reconcile actual conflicts.

لا تعتمد هذه الوثيقة على restatement إذا الملفات الأصلية متاحة.

## 58.2 Add P3 execution-start clarification

أضف النص الحاكم:

```text
PLN-00 reconciliation and final PLN-01 contract freeze are
post-P2 entry-preparation/planning activities.

P3_STARTED = YES
only after explicit Owner authorization for P3 execution.
```

حتى لا نفهم `PLN-00` كتنفيذ P3 مبكر.

## 58.3 Add state-propagation defect

أضف للـconflict table:

```text
Risk full screen current metrics did not inherit scenario trust state.
Trades PnL did not inherit price/position trust state.
Closure freshness wording mixed shutdown-event time with current observation.
Market chart lacked explicit stale/unknown overlay.
```

وكلها:

```text
PATCH EXISTING SLOTS
NO NEW PAGE
NO NEW STAGE
NO NEW WORKSTREAM
```

---

# 59. FINAL FREEZE GATE — AUTHORITATIVE ORDER

لا يبدأ Owner Walkthrough، ولا يتم Level A Freeze، قبل إكمال **Direct Current Authority Reconciliation**.

الترتيب النهائي الإلزامي هو:

```text
CURRENT AUTHORITY DIRECT CHECK
  merged repository
  current P2 contract
  current registry
  P2 closure law
  P3 Master Blueprint
  approved visual direction
↓
RESOLVE ONLY REAL CONFLICTS
  داخل الـslots الحالية فقط
  NO redesign
  NO new stage
  NO new workstream
  NO new top-level page
↓
LAST TRUTH-STATE PATCH
  Risk & Authority propagation
  Trades / PnL trust propagation
  Closure freshness/current-observation truth
  Market stale/unknown overlay
↓
Prototype v0.2.4
↓
MECHANICAL / HEADLESS REGRESSION
  15 scenarios
  AR / EN
  Desktop / Mobile
  all 12 screens
  Inspector
  Return Detection
  clipboard success/failure
  zero external network
↓
OWNER WALKTHROUGH — 15 STOPS
↓
APPROVE / ONE SPECIFIC REVISE POINT
↓
LEVEL A PRODUCT / UX FREEZE
↓
PRODUCT SHAPE CLOSED
```

القانون:

```text
DIRECT AUTHORITY CHECK
BEFORE
OWNER WALKTHROUGH
BEFORE
LEVEL A FREEZE
```

السبب:
أي تعارض حاكم يُكتشف بعد الـFreeze سيجبرنا على إعادة فتح ما سبق تجميده، وهذا ممنوع ما لم يكن P0 حقيقيًا.

ولا توجد مراجعة Architecture عامة بعد ذلك.

إذا كل الـ15 stops APPROVE:

```text
PRODUCT_ARCHITECTURE       = FROZEN
NAVIGATION                 = FROZEN
SCREEN_PURPOSES            = FROZEN
COMMAND_CENTER_SHAPE       = FROZEN
PROJECT_CONTINUITY_SHAPE   = FROZEN
RESPONSIVE_IA              = FROZEN
STATE_UX                   = FROZEN
CAPABILITY_REVEAL_MODEL    = FROZEN
ARABIC_GLOSSARY            = FROZEN
VISUAL_FAMILY              = FROZEN
```

Exact production tokens/implementation details remain Level B/C where already defined.

---

# 60. NO-REOPEN LAW — RECONFIRMED

بعد Level A Freeze:

```text
FEATURE REQUEST ≠ ARCHITECTURE REOPEN
NEW CAPABILITY ≠ NEW PAGE
NEW SOURCE ≠ NEW PAGE
NEW FAILURE CLASS ≠ NEW STAGE
NEW MONITOR ≠ NEW STAGE
NEW BACKUP METHOD ≠ NEW STAGE
NEW NOTIFICATION METHOD ≠ NEW STAGE
NEW MODEL / LLM ≠ NEW STAGE
```

كل شيء يظهر داخل slots الحالية.

القانون:

```text
SOURCE EXISTS?
CAPABILITY IMPLEMENTED?
AUTHORITY ALLOWS?
DATA CURRENT?
VERIFICATION PASSED?
```

ثم UI تعرض الحالة المناسبة.

---

# 61. FINAL CLAUDE CHAT DIRECTIVE — LAST PATCH ONLY

ارسل هذا الملف إلى Claude Chat في نفس المحادثة التي تحتوي على v0.2.3 والمراجعة الحالية.

المطلوب منه:

```text
DO NOT REDESIGN.
DO NOT OPEN A STAGE.
DO NOT OPEN A WORKSTREAM.
DO NOT ADD A TOP-LEVEL PAGE.
DO NOT START P3 IMPLEMENTATION.
DO NOT TOUCH P2.
```

نفّذ فقط:

1. اقرأ هذا الملف كاملًا، خصوصًا §54–§64.
2. نفّذ **Direct Current Authority Reconciliation أولًا**:
   - current merged repository
   - current P2 contract
   - current registry
   - P2 Final Execution and Complete Closure
   - P3 Master Planning Blueprint
   - Approved Control Room Visual Direction
3. صنّف كل تعارض:
   - REAL CONFLICT
   - EXPECTED DIFFERENCE
   - HISTORICAL
   - SUPERSEDED
   - HANDOFF_ONLY
4. صحح فقط التعارضات الحقيقية داخل Architecture الحالية.
5. لا تفتح Stage أو Workstream أو Top-level Page جديدة.
6. بعد نجاح Direct Authority Reconciliation فقط:
   - صحح Full Risk & Authority state propagation.
   - صحح Trades & Positions PnL trust propagation.
   - صحح closure freshness/current-observation wording.
   - أضف stale/unknown overlay إلى Market Workspace داخل نفس chart slot.
7. ثبّت تعريف:
   `P3_STARTED = YES only after explicit Owner authorization for P3 execution`.
8. أخرج `Prototype v0.2.4` في نفس artifact lineage.
9. أعد Headless Chromium regression:
   - 15 scenarios
   - Arabic / English
   - Desktop / Mobile
   - all 12 screens
   - Inspector
   - Return Detection
   - clipboard success/failure
   - zero external network
10. لا تعلن Level A Frozen.
11. إذا Direct Authority Reconciliation أو أي P0 patch فشل:
    `OWNER_WALKTHROUGH_READY = NO`.
12. إذا كل شيء PASS:
    أعد فقط readiness for Owner Walkthrough.

Required final block:

```text
ROADMAP                       = P1 → P2 → P3 → POST-BETA
NEW_STAGES                    = NONE
NEW_WORKSTREAMS               = NONE
NEW_TOP_LEVEL_PAGES           = NONE

PROTOTYPE                     = v0.2.4
RISK_STATE_PROPAGATION        = PASS / FAIL
TRADES_PNL_TRUST_PROPAGATION  = PASS / FAIL
CLOSURE_FRESHNESS             = PASS / FAIL
MARKET_STALE_UNKNOWN_UX       = PASS / FAIL

HEADLESS_RENDER_MATRIX        =
EXTERNAL_REQUESTS             =
NETWORK_DEPENDENCIES          =
LIVE_SYSTEM_CONNECTIONS       =

DIRECT_AUTHORITY_RECONCILIATION =
  PASS / INCOMPLETE / CONFLICT

CANONICAL_LABEL =
  BLOCKED UNTIL DIRECT_CURRENT_AUTHORITY_RECONCILIATION = PASS

LEVEL_A =
  READY FOR OWNER WALKTHROUGH
  only if:
  DIRECT_AUTHORITY_RECONCILIATION = PASS
  AND all final truth-state patches = PASS
  AND regression = PASS

P2_TOUCHED                    = NO
P3_IMPLEMENTATION_STARTED     = NO
REAL_MONEY_AUTHORIZED         = NO

RECOMMENDED_NEXT_ACTION =
```

`RECOMMENDED_NEXT_ACTION`:

إذا Direct Authority Reconciliation لم يكتمل:

```text
COMPLETE DIRECT CURRENT AUTHORITY RECONCILIATION
```

إذا Direct Authority Reconciliation = PASS
وكل Patch + Regression = PASS:

```text
OWNER WALKTHROUGH — 15 STOPS
```

STOP.

---

# 62. FINAL REVIEW VERDICT

بعد المراجعة المستقلة:

```text
PRODUCT ARCHITECTURE             = KEEP
NAVIGATION                       = KEEP
COMMAND CENTER                   = KEEP
PROJECT & CONTINUITY             = KEEP
OPERATIONS / RECOVERY            = KEEP
MOBILE IA                        = KEEP
ARABIC / ENGLISH MODEL           = KEEP
CAPABILITY-DRIVEN REVEAL         = KEEP
12-WORKSTREAM P3 MODEL           = KEEP
NO-NEW-STAGES LAW                = KEEP

PROTOTYPE v0.2.3 STRUCTURE       = PASS
PROTOTYPE v0.2.3 TECHNICAL SMOKE = PASS
TRUTH-STATE PROPAGATION          = LAST PATCH REQUIRED

OWNER_WALKTHROUGH_READY          = AFTER DIRECT AUTHORITY PASS + §57 PATCH + REGRESSION
LEVEL_A                          = NOT YET FROZEN

DIRECT_AUTHORITY_RECONCILIATION  = PARTIAL / MUST COMPLETE FIRST
CANONICAL SPEC LABEL             = BLOCKED UNTIL CURRENT REPO / CONTRACT / REGISTRY DIRECT CHECK

P2_TOUCHED                       = NO
P3_IMPLEMENTATION_STARTED        = NO
REAL_MONEY_AUTHORIZED            = NO
```

هذه هي آخر مراجعة Architecture-level.

بعد اكتمال Direct Current Authority Reconciliation ثم تطبيق §57:
- لا نعيد فتح Product Shape.
- نعيد Regression كامل.
- نعمل Owner Walkthrough.
- ثم Level A Freeze.
- أي تفاصيل لاحقة تذهب Level B / Level C داخل P3-PLN-00…11 فقط.
---

# 63. v1.2 FINAL FREEZE GATE — SUPERSEDING ORDER

هذه الفقرة تحكم ترتيب الإغلاق النهائي لأي نص أقدم داخل الملف إذا بدا أن هناك تعارضًا في ترتيب الـgates.

## 63.1 Final immutable order

```text
1. DIRECT CURRENT AUTHORITY RECONCILIATION
2. RESOLVE REAL CONFLICTS ONLY
3. LAST TRUTH-STATE PATCH
4. PROTOTYPE v0.2.4
5. FULL REGRESSION
6. OWNER WALKTHROUGH
7. LEVEL A FREEZE
8. PRODUCT SHAPE CLOSED
```

## 63.2 What Direct Authority Reconciliation must read

```text
CURRENT MERGED REPOSITORY
CURRENT P2 CONTRACT
CURRENT REGISTRY
P2 FINAL EXECUTION AND COMPLETE CLOSURE
P3 MASTER PLANNING BLUEPRINT
APPROVED CONTROL ROOM VISUAL DIRECTION
```

Anything not read directly remains:

```text
SOURCE_NOT_READ
```

ولا يمكن استخدامه لحسم تعارض canonical/frozen.

## 63.3 Final P3 execution-start law

```text
P3 PLANNING / DESIGN
= ALLOWED DURING P2

P3-PLN-00 DRAFT / PREPARATION
= ALLOWED DURING P2

P3-PLN-00 FINAL BINDING
= AFTER TRUTHFUL P2 CLOSURE

FINAL PLN-01 CONTRACT REVIEW / FREEZE
= BEFORE EXECUTION AUTHORIZATION

OWNER_AUTHORIZES_P3_EXECUTION
↓
P3_STARTED = YES
↓
P3 PRODUCTION IMPLEMENTATION / RUNTIME EXECUTION
```

لا تعتبر أي preparation أو reconciliation draft:

```text
P3_STARTED = YES
```

## 63.4 Final no-reopen condition

بعد:

```text
LEVEL_A = FROZEN
```

لا يتم فتح Product Architecture مرة أخرى بسبب:
- capability جديدة;
- provider جديد;
- monitor جديد;
- backup method جديد;
- notification transport جديد;
- model/LLM جديد;
- pair/timeframe جديد;
- evidence check جديد;
- operator action جديد.

كل ذلك يدخل داخل الـslots الموجودة.

إعادة الفتح مسموحة فقط إذا ظهر:

```text
P0 GOVERNING CONTRADICTION
```

يثبت أن الشكل المجمد نفسه يخالف authority أعلى.

---

# 64. v1.2 STATUS

```text
DOCUMENT =
Trading Lab OS — FINAL MASTER PRODUCT SHAPE LOCK v1.2

ROADMAP =
P1 → P2 → P3 → POST-BETA

NEW_STAGES =
NONE

P3_WORKSTREAM_COUNT =
12

DIRECT_AUTHORITY_RECONCILIATION =
REQUIRED BEFORE OWNER WALKTHROUGH

LAST_TRUTH_STATE_PATCH =
AFTER AUTHORITY RECONCILIATION

OWNER_WALKTHROUGH =
AFTER AUTHORITY + PATCH + REGRESSION

LEVEL_A_FREEZE =
AFTER OWNER APPROVAL

PRODUCT_SHAPE_REOPEN =
NO, EXCEPT P0 GOVERNING CONTRADICTION

P2_TOUCHED =
NO

P3_IMPLEMENTATION_STARTED =
NO

REAL_MONEY_AUTHORIZED =
NO
```
