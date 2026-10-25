# P3-PLN-09 — Control Room (execution record)

**Authority:** [`PLN_09_PRODUCT_SHAPE_AUTHORITY.md`](PLN_09_PRODUCT_SHAPE_AUTHORITY.md) (PR #80; it unblocks PLN-09 on Owner merge) and [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-09.
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
| Tests: 17, synthetic only | `tests/test_p3_control_room.py` | — |

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

## Remaining screens: binding plan and estimate
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

**Total about 6–7 working days** for all 12 screens bound, plus Owner review rounds. Each PR binds one or two screens, and the `LIVE_BOUND` list grows.
