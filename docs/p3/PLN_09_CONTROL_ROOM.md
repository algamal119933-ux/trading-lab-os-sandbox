# P3-PLN-09 — Control Room (execution record)

**Authority:** [`PLN_09_PRODUCT_SHAPE_AUTHORITY.md`](PLN_09_PRODUCT_SHAPE_AUTHORITY.md) (PR #80, Owner-merged at `d21bebe5`; PLN-09 is unblocked) and [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-09.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCH_AUTHORIZED = NO

## Approach: realise the frozen shape, without redesigning it
| Item | Path | Reuse (§10) |
|---|---|---|
| Frozen prototype, used **verbatim** (digest-checked; any other digest is refused) | `docs/p3/product_shape/Trading_Lab_OS_Prototype_v0.2.5_FINAL.html` | REUSE_EXISTING |
| Evidence adapter: `collect` (observe), `project` (map to the prototype's scenario schema), `build` | `research/p3/control_room.py` | WRAP_EXISTING: health, backup verify, operator ledger, restart guard, docker, git, registry |
| Live script, appended once; it re-declares only data-bearing components, with the same markup and classes | `research/p3/control_room_live.js` | — |
| Governed workstream status (changes only by merged PR; the view never writes it) | `research/p3/records/p3_workstreams.json` | record |
| CLI `build` | `scripts/p3/control_room.py` | — |
| Hourly regeneration inside the existing health run (a failed build never changes the health verdict) | `scripts/p3/scheduled_health.sh` | REUSE (the existing timer) |
| Tests: 28, synthetic only | `tests/test_p3_control_room.py` | — |

Properties:
- **NEW_CONTROL_PLANE = NO.** The page is a static file with the prototype's CSP (`connect-src 'none'`). There is no server, no network and no write, and it has no control.
- **Truthful states.** Anything not observed is *unknown*, never healthy. An unreadable docker shows runtime unknown. A broken ledger or an unverified backup fails Evidence. An expired authorization fails Authority.
- **Freshness.** The view carries its observation time. Past 2 h (the hourly regeneration plus margin) it switches to the frozen stale-view state: banner, stale Truth Strip, "status unknown since".
- **Provenance.** The Inspector shows the real source for each Truth Strip dimension (the health check, the authorization record at 7b1b1fa1, the backup set and ledger, docker, P2_CLOSURE).
- The output (`~/tlos-paper/p3-evidence/control_room/`) is regenerable, so the inventory classifies it as derived.

## Slice 1 delivered: shell, Command Center and System (verified 2026-10-25T21:5xZ, EN + AR/RTL)
- **Shell:** identity bar (P3 · Paper Beta executing · 7b1b1fa1 · PAPER · real money blocked · Owner: action required), the Truth Strip in the frozen order (Health ok · Authority ok · Evidence ok · Freshness ok · Runtime stopped/observed · Reconciliation 14/14 P2 final), and the 12-item navigation unchanged.
- **Command Center:**
  - verdict;
  - the four slots (Owner / Claude / System / next governed step);
  - Project now: P1 and P2 closed PASS, P3 executing, and the PLN-00..11 status chips from the governed record;
  - Trading now: no cohort, so no decisions, exposure 0 %, real money blocked;
  - active capabilities;
  - Attention: no incidents; the one exception is Runtime stopped, with its reason;
  - the timeline since the last governed checkpoint (the PR #78 merge, the backup set, the health check);
  - Performance: edge not evaluated.

  **0 DEMO values** on the screen.
- **System:** runtime, feed, API and clock; host uptime and boot ID; disk and mounts; timers; runtime pin 3191285a (clean) against main; Owner awareness (local notification implemented, off-host not).
- **The other 10 screens** keep their frozen bodies under the prototype's own info banner: "not yet bound to live evidence; values tagged DEMO are the prototype reference". Nothing is passed off as live.

## Slice 2 delivered: six more screens (verified 2026-10-25T22:1xZ, EN + AR/RTL, 0 DEMO values, no console errors)
- **Project & Continuity:**
  - resume block and resume brief (the live brief, copyable);
  - P2 terminal law, with its source cited;
  - checkpoints;
  - stage map: P1/P2 closed with their closure records, P3 executing under 7b1b1fa1, POST-BETA not authorized.
- **Incidents:** each non-INFO health finding opens an incident; nothing else does. Today there are none. The incident page keeps the frozen field set.
- **Operations:**
  - backup health and newest set from the health check;
  - restore readiness from the **persisted** drill record `p3-evidence/drills/<set>.json`. A fresh drill of `20261025T211956Z` passed, with 8 archives ARCHIVE_VERIFIED;
  - host-reboot recovery shown as "not yet exercised";
  - the actions are listed as operator CLIs ("not in this view"). The Kill Switch button is never live in the view.
- **Risk & Authority:** no cohort, so exposure is 0 % and the other metrics are not applicable. Shown with the governed limits of the last cohort and the capability matrix with preconditions.
- **Evidence & Reconciliation:** real checks with their sources:
  - the P2 final reconciliation, 14/14;
  - sealed archives re-verified on restore, 8;
  - backup verify;
  - restore drill;
  - ledger chain;
  - the PLN-07 execution audit of the sealed P2 archive: **2 unbacked, contextual (F-2)**, shown as a finding, not hidden. Record: `p3-evidence/audits/l2-cohort-20260924T120000Z.json`.
- **History:** governance merges, backup sets, operator ledger records, drills and audits on one filtered timeline.

## Slice 3 delivered: Decisions, Trades & Positions, Market Workspace, Settings (all 12 screens bound)
Source: the sealed cohort that the newest PLN-07 execution-audit record names (`p3-evidence/audits/*.json` → `evidence_dir`). Its decision, trade and input ledgers are read **read-only** by `control_room.sealed_cohort`. No paper cohort runs now, so every slice-3 screen says that this is a sealed record and that there is no current state.

- **Decisions:**
  - The listed decisions are every enter/exit intent and every admission, plus the last decision per pair. They are capped at the newest 40, out of 3,194 in the P2 cohort.
  - The 9-stage trace shows only what the runtime logged:
    - Spotter: the signal state
    - Verifier: the bar class
    - Prior / Regime: the EMA values
    - Risk Sizer: the admission result and its reasons
    - One Core: the intended action
    - Paper Execution and Reconciliation: the fill and its backing, from the PLN-07 audit
  - The Exit Contract and Verified Outcome stages are **not logged per decision**, so they read "not logged" and are never inferred.
  - The evidence reference (ledger path and market_event_id) and the strategy and config digests are shown for each decision.
- **Trades & Positions:**
  - Open: none, because no cohort is running.
  - Closed: from the sealed trade ledger, showing entry, exit, exit reason and realised PnL as recorded.
  - Reconciliation and outcome are shown **per leg** from the audit: both legs backed gives "Backed · entry + exit"; an unbacked leg gives "Contextual · unbacked (F-2)"; a missing leg gives unknown.
- **Market Workspace:**
  - The current market state is **unknown** (no runtime, no feed). The prototype's own unknown overlay is shown.
  - The chart shows the last 56 bars of the sealed input ledger only, with markers at the recorded fills.
  - Pairs and timeframe come from the record.
  - Capabilities: candles "No live feed · sealed record only"; order book not provided; regime unknown.
- **Settings:** viewer preferences only.
  - Return detection reads "not active", because a static view keeps no viewer state.
  - The notification row cites `scripts/p3/scheduled_health.sh`.
  - Settings never change risk, mode or authority.
- **Missing or unreadable evidence:** when no audit record exists or the ledgers cannot be read, each slice-3 screen shows **unknown** with the reason. Nothing is rendered as healthy. This is covered by a negative test.
- **Verification (synthetic):** headless Chromium, EN and AR/RTL, bound and missing-evidence cases. No console errors, and no DEMO text on any slice-3 screen.

## Mobile slice delivered: Status, Resume, Incidents, More (the same scenario; monitoring and continuity only)
The frozen mobile components are re-declared only where they carry data. Same markup and classes, prototype bytes verbatim, digest check intact, offline CSP.

| Mobile element | Bound from | Note |
|---|---|---|
| Stage label (mobile bar) | `LIVE.ident.stage` ("P3 · Paper Beta executing") | The prototype's `STAGELBL[step]` would read "P2 Closed" |
| Status · project line | the governed project chips and next Owner gate (the workstream record) | Replaces the prototype's hard-coded "P2 · ladder" line |
| Status · decision / exposure / incidents | the scenario (no cohort: no decisions; exposure 0 %; incidents from non-INFO health) | — |
| Resume | the prototype's own body over the live scenario | The ladder is the frozen P2-closure ladder (7/7), as on desktop |
| Incidents | the prototype's own body (non-INFO health findings) | Acknowledge stays "not in this view" |
| More → Operations | backup / restore / host-reboot recovery from the newest set and the persisted drill record | The prototype hard-coded backup and restore as unknown |
| More → Decisions | the last **sealed** decision, with its 9-stage trace, marked "Sealed record" | Unknown, with the reason, when the sealed record is missing |
| More → Trades | open: none; the sealed closed trades with per-leg backing | Unknown when missing |
| More → Market | the prototype's body: no chart on mobile, by design | — |
| More → Risk / Evidence / History / System | the prototype's bodies over the live scenario | — |
| More → Settings | viewer preferences only | The prototype's "desktop-first in this prototype" copy is replaced by a factual line |

- **Device selection:** the prototype's device toggle lives in the hidden prototype panel. A viewport ≤ 720 px opens the mobile view, and `#mobile` / `#desktop` in the address override it. This is view state only; nothing is stored.
- **No consequential control on mobile:** every mobile button is navigation (`data-mtab` / `data-mdet`). There is no acknowledge, no stop and no Kill Switch, and a test asserts this.
- **Governed forbidden list:** the prototype's FORBID list describes P2 ("P3 code or runtime action"). The live view now uses the governed list (`control_room.FORBIDDEN_NOW`): real money, H1 launch, restarting FP-CONTROL-3, strategy/risk/dataset change, reopening the product shape. It is the same as the resume brief's FORBIDDEN line, and it applies on desktop and mobile.
- **Verification (synthetic, headless Chromium, 390×844, EN and AR/RTL, sealed-bound and evidence-missing cases):**
  - every tab and every More detail rendered;
  - 0 console errors and no DEMO text;
  - the stage label is never "P2 Closed";
  - no Kill Switch element;
  - unknown shown when the sealed record is missing;
  - a 1400 px viewport opens the desktop layout, and `#mobile` forces the mobile one.
- **Owner acceptance preparation:** [`PLN_09_OWNER_ACCEPTANCE_CHECKLIST.md`](PLN_09_OWNER_ACCEPTANCE_CHECKLIST.md). `PLN09_OWNER_ACCEPTANCE = PENDING`. The Owner records the sign-off in the Owner's own PR.

**Status: 12 of 12 screens and the 4 mobile tabs are bound.** What remains for PLN-09 is the Owner review and acceptance round (the checklist). It runs on the host after the planned reboot and after `tlos-p3` is updated.

Earlier status line (slice 3): **Status: 12 of 12 screens are bound.** What remains for PLN-09:
- the mobile tabs (same scenario, prototype mobile components, about 0.5 d);
- the Owner review round.

## Remaining screens: binding plan and estimate (historical estimate; see slice 3)
| Screen | Live source (existing) | Effort |
|---|---|---|
| Project & Continuity (resume brief, checkpoints, ladder) | git merges, the workstream record, P2_CLOSURE, the pre-reboot snapshot | 0.5 d |
| Incidents | the operator ledger plus health findings (WARNING/CRITICAL become incident rows). An incident ledger is needed, as a PLN-06 record | 0.5–1 d |
| Operations / Recovery | kill_switch, recovery (may-restart, verify-boot), the backup/drill records | 0.5 d |
| Risk & Authority (capability matrix) | registry, paper_guard, the contract | 0.5 d |
| Evidence & Reconciliation | reconcile/verify_archive on sealed archives, the PLN-07 execution audit, backup verify | 0.5–1 d |
| History | git, the ledger and backup records, on one timeline | 0.5 d |
| Decisions / Trades & Positions | the decision and trade ledgers of a running cohort; read from sealed P2 until a P3 cohort runs | 1 d |
| Market Workspace | the dataset lock and OHLCV cache (read-only); the frozen shape shows no chart on mobile | 1 d |
| Settings | per-viewer settings only (return threshold, language), held in the browser | 0.25 d |
| Mobile (4 tabs + details) | the same scenario; the prototype's mobile components | 0.5 d |

**Total about 6–7 working days** for all 12 screens bound, plus Owner review rounds. After slice 2, **8 of 12 screens are bound**. The remainder is Decisions, Trades & Positions, Market Workspace, Settings and Mobile, **about 3 working days**.
