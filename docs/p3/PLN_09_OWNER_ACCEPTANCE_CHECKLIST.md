# P3-PLN-09: Owner acceptance checklist (Control Room)

**Authority:** [`PLN_09_PRODUCT_SHAPE_AUTHORITY.md`](PLN_09_PRODUCT_SHAPE_AUTHORITY.md) (PR #80, merged `d21bebe5`), [`PLN_09_CONTROL_ROOM.md`](PLN_09_CONTROL_ROOM.md) and [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-09.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCH_AUTHORIZED = NO

The Owner performs this walkthrough. It is **preparation only**. This file grants nothing and does not accept PLN-09. Acceptance is recorded only by the Owner, in the Owner's own PR, by filling in §6.

## 1. When and how to open the view (later; no host action now)

> **Not now.** Wait until all three of these have happened:
> 1. The planned reboot and its `verify-boot` check are done (`claude/REBOOT_RUNBOOK_2026-10-26.md`, PLN-04/07).
> 2. This PR is merged.
> 3. The Owner has updated `~/projects/trading/tlos-p3` to a `main` that contains it.
>
> Before that, do not update `tlos-p3`, do not restart any service, and do not start any runtime.
>
> **ليس الآن.** انتظر حتى تتم ثلاثة أشياء: إعادة الإقلاع المخططة وفحص `verify-boot`، ودمج هذا الطلب، وتحديث `tlos-p3`.

After those steps the hourly health run regenerates the view automatically (`scripts/p3/scheduled_health.sh`). To open it:
1. Open `~/tlos-paper/p3-evidence/control_room/index.html` in a browser on the host. It works offline.
2. For the phone layout, narrow the window below 720 px or add `#mobile` to the address. Use `#desktop` to force the desktop layout.
3. To build it once by hand: `cd ~/projects/trading/tlos-p3 && ~/projects/trading/trading_lab_os_final/.venv/bin/python scripts/p3/control_room.py build`. This is read-only: it writes only the page.

## 2. Global checks (every screen) · فحوص عامة

| # | Check | Pass when | ✓ |
|---|---|---|---|
| G1 | Banner | The top line reads "LIVE PROJECTION · READ-ONLY · NOT EVIDENCE AUTHORITY", with the observation time and host · شريط "عرض مباشر للقراءة فقط" ظاهر | ☐ |
| G2 | No DEMO values | No "DEMO", "DEMO-PAIR" or "DEMO-PRICE" text anywhere · لا قيم تجريبية | ☐ |
| G3 | Real money | The identity bar shows PAPER and "Real money blocked"; Risk & Authority shows Real money = blocked · المال الحقيقي محظور | ☐ |
| G4 | Truth Strip order | Health · Authority · Evidence · Freshness · Runtime · Reconciliation · الترتيب مطابق | ☐ |
| G5 | Unknown is honest | Anything not observed reads unknown, never green · غير المرصود يظهر "غير معروف" | ☐ |
| G6 | Stale view | If the page is older than 2 h, the stale banner appears and dimensions turn stale · العرض القديم يُعلَن | ☐ |
| G7 | Arabic / RTL | Toggle AR: the layout mirrors, the frozen Arabic terms are used, and no English is left untranslated · العربية من اليمين لليسار | ☐ |
| G8 | Offline / CSP | The page loads with the network off; the page source keeps `connect-src 'none'` · يعمل دون شبكة | ☐ |
| G9 | No control | Nothing in the view starts, stops, acknowledges or changes anything. The Kill Switch appears only as a CLI reference · لا يوجد أي تحكم | ☐ |

## 3. Desktop screens (12) · شاشات سطح المكتب

| # | Screen | Look at | Must trace to | Expected unknown / note | ✓ |
|---|---|---|---|---|---|
| S1 | Command Center · مركز القيادة | verdict; Owner / Claude / System / Next; Project now; PLN-00..11 chips | health check; `research/p3/records/p3_workstreams.json`; registry; git merges | Runtime = stopped (no cohort) | ☐ |
| S2 | Project & Continuity · المشروع والاستمرارية | resume brief; P2 terminal law; checkpoints; stage map | `docs/p2/P2_CLOSURE.md`; the workstream record; git | The ladder is the P2 closure ladder (7/7 · P2 closed) | ☐ |
| S3 | Incidents · الحوادث | the list | non-INFO health findings only | Empty when health is INFO | ☐ |
| S4 | Market Workspace · مساحة السوق | sealed bars and fill markers | the sealed P2 input ledger, via the newest PLN-07 audit | Current market state = unknown (no feed). Fills older than the last 56 bars have no marker | ☐ |
| S5 | Decisions · القرارات | the list (≤ 40) and the 9-stage trace | the sealed decision ledger; PLN-07 audit | Exit Contract / Verified Outcome = "not logged" | ☐ |
| S6 | Trades & Positions · الصفقات والمراكز | open = none; the closed trades | the sealed trade ledger; PLN-07 audit | BTC #1 Backed; ETH #2 Contextual · unbacked (F-2) | ☐ |
| S7 | Risk & Authority · المخاطر والصلاحيات | capability matrix; exposure 0 % | registry; P3 contract §23; the authorization at 7b1b1fa1 | Metrics not applicable (runtime stopped) | ☐ |
| S8 | Evidence & Reconciliation · الأدلة والمطابقة | checks with their sources | P2 reconcile 14/14; backup verify; drill record; ledger chain; PLN-07 audit | The 2 unbacked executions are shown as a finding | ☐ |
| S9 | History · السجل | the timeline | git merges; backup sets; operator ledger; drills; audits | — | ☐ |
| S10 | Operations · العمليات | backup, restore, recovery; actions | newest backup set; `p3-evidence/drills/*.json`; operator ledger | Host reboot recovery = "not yet exercised" until PLN-04 closes | ☐ |
| S11 | System · النظام | host, disks, timers, runtime pin vs main | host observation; systemd; git | — | ☐ |
| S12 | Settings · الإعدادات | viewer preferences only | `scripts/p3/scheduled_health.sh` (notifications) | Return detection = not active (static view) | ☐ |

## 4. Mobile tabs · تبويبات الجوال

| # | Tab | Look at | Must trace to | Expected / note | ✓ |
|---|---|---|---|---|---|
| M1 | Status · الحالة | stage = "P3 · Paper Beta executing"; Owner / Claude / System / Next; project chips; next Owner gate; exposure; open incidents | the same scenario as desktop; the workstream record | Never "P2 Closed" as the stage label | ☐ |
| M2 | Resume · استئناف | step 7/7 (P2 closure ladder); known / unknown / unverified; "Forbidden now" | the scenario; the governed forbidden list | Forbidden now = Real money · H1 launch · Restarting FP-CONTROL-3 · Strategy, risk or dataset change · Reopening the product shape | ☐ |
| M3 | Incidents · الحوادث | the list | non-INFO health findings | Empty when health is INFO | ☐ |
| M4 | More → Decisions | last **sealed** decision, with the 9-stage trace | the sealed decision ledger | Marked "Sealed record"; unknown if the record is missing | ☐ |
| M5 | More → Trades | open = none; the sealed closed trades with backing | the sealed trade ledger + PLN-07 audit | Unknown if missing | ☐ |
| M6 | More → Operations | runtime, safe state, recovery, backup, restore, host-reboot recovery | backup set; drill record; `LIVE.ops` | "The Kill Switch is never in this view and never on mobile" | ☐ |
| M7 | More → Market | no chart (by design); data age | — | "Charts are intentionally not shown on mobile" | ☐ |
| M8 | More → Risk / Evidence / History / System / Settings | as on desktop, compact | as on desktop | Settings: viewer preferences only | ☐ |
| M9 | No action on mobile | Only navigation buttons (tabs, list rows, Back) | — | No acknowledge, no stop, no Kill Switch · لا إجراءات على الجوال | ☐ |

## 5. Known limitations to accept or reject (not defects to hide)
- The view is regenerated hourly. Between runs it ages, and past 2 h it says it is stale.
- The Resume ladder is the frozen P2-closure ladder; the P3 stage shows in the stage chip and project chips (recorded delta in the authority record §2).
- Market Workspace shows the last 56 sealed bars only; earlier fills have no marker.
- The `owner` / `claude` / `next` texts come from the governed workstream record and change only by merged PR, so they can lag one merge behind.
- No off-host observation exists yet (PLN-05 Tier 3 / PLN-06).

## 6. Owner sign-off (filled by the Owner in the Owner's own PR)
```text
PLN09_OWNER_ACCEPTANCE   = PENDING
VIEW_BUILT_AT_MAIN       = <sha>
VIEW_OBSERVED_UTC        = <time shown in the banner>
DESKTOP_CHECKS (G1–G9, S1–S12) = <PASS / FAIL with item numbers>
MOBILE_CHECKS (M1–M9)    = <PASS / FAIL with item numbers>
FINDINGS                 = <list, or NONE>
SIGNED                   = <Owner, date>
```
A FAIL is recorded and fixed under the contract. It is never waived. Accepting PLN-09 does not accept PLN-10 or authorize anything else.
