# P3-PLN-09: Owner acceptance checklist (Control Room)

**Authority:** [`PLN_09_PRODUCT_SHAPE_AUTHORITY.md`](PLN_09_PRODUCT_SHAPE_AUTHORITY.md) (PR #80, merged `d21bebe5`), [`PLN_09_CONTROL_ROOM.md`](PLN_09_CONTROL_ROOM.md) and [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-09.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCH_AUTHORIZED = NO

The Owner performs this walkthrough. It is **preparation only**. This file grants nothing and does not accept PLN-09. Acceptance is recorded only by the Owner, in the Owner's own PR, by filling in §6.

## 1. When and how to open the view (later; no host action now)

This walkthrough needs **no runtime and no trading authority**. It reads one static, offline page. It never starts, stops or changes anything, and it does not need, imply or grant any paper or live launch (`PAPER_LAUNCH_AUTHORIZED = NO`).

Preconditions, as of main `f584cd43`:

| # | Precondition | State |
|---|---|---|
| P1 | The planned reboot and its `verify-boot` check ([`PLN_04_REBOOT_ACCEPTANCE_RUNBOOK.md`](PLN_04_REBOOT_ACCEPTANCE_RUNBOOK.md), PLN-04/07) | **Done.** RUN 3 PASS 10/10, gap attestation clean, accepted by the merge of PR #94 ([`PLN_04_RECOVERY.md`](PLN_04_RECOVERY.md)) |
| P2 | The Control Room mobile slice and this checklist merged | **Done** (PR #88) |
| P3 | The Owner lifts the host freeze for the controlled `tlos-p3` update only, and updates `~/projects/trading/tlos-p3` to an Owner-chosen main SHA ([`PLN_04_RECOVERY.md`](PLN_04_RECOVERY.md), "Host-freeze lift conditions", item 3; item 2 was met by the merge of PR #94) | **Open (Owner)** |
| P4 | The first hourly health run after that update has been read; a CRITICAL there is handled first ([`PLN_06_ALERTING.md`](PLN_06_ALERTING.md) §4, last paragraph) | **Open** |

> **Not before P3 and P4.** Until then, do not update `tlos-p3`, do not restart any service, and do not start any runtime.
>
> **ليس قبل P3 وP4.** حتى ذلك الحين: لا تحدّث `tlos-p3`، ولا تُعِد تشغيل أي خدمة، ولا تبدأ أي تشغيل.

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
| S3 | Incidents · الحوادث | the list | non-INFO health findings only, §19 checks included (`paper_guard`, `real_money`, `evidence_chain:*`, `unauthorized_execution`, `health_run`) | "None open" when health is INFO. **UNKNOWN** when the health run gave no findings, and never "None open" in that case | ☐ |
| S4 | Market Workspace · مساحة السوق | sealed bars and fill markers | the sealed P2 input ledger, via the newest PLN-07 audit | Current market state = unknown (no feed). Fills older than the last 56 bars have no marker | ☐ |
| S5 | Decisions · القرارات | the list (≤ 40) and the 9-stage trace | the sealed decision ledger; PLN-07 audit | Exit Contract / Verified Outcome = "not logged" | ☐ |
| S6 | Trades & Positions · الصفقات والمراكز | open = none; the closed trades | the sealed trade ledger; PLN-07 audit | BTC #1 Backed; ETH #2 Contextual · unbacked (F-2) | ☐ |
| S7 | Risk & Authority · المخاطر والصلاحيات | capability matrix; exposure 0 % | registry; P3 contract §23; the authorization at 7b1b1fa1 | Metrics not applicable (runtime stopped) | ☐ |
| S8 | Evidence & Reconciliation · الأدلة والمطابقة | checks with their sources | P2 reconcile 14/14; backup verify; drill record; ledger chain; PLN-07 audit | The 2 unbacked executions are shown as a finding | ☐ |
| S9 | History · السجل | the timeline | git merges; backup sets; operator ledger; drills; audits | — | ☐ |
| S10 | Operations · العمليات | backup, restore, recovery; actions | newest backup set; `p3-evidence/drills/*.json`; operator ledger | **Known finding F-CR-1 (see §5):** Host reboot recovery still reads "not yet exercised", although PLN-04 reboot correctness was accepted in PR #94. Record it under FINDINGS unless a fix is merged before the walkthrough | ☐ |
| S11 | System · النظام | host, disks, timers, runtime pin vs main | host observation; systemd; git | — | ☐ |
| S12 | Settings · الإعدادات | viewer preferences only | `scripts/p3/scheduled_health.sh` (notifications) | Return detection = not active (static view) | ☐ |

## 4. Mobile tabs · تبويبات الجوال

| # | Tab | Look at | Must trace to | Expected / note | ✓ |
|---|---|---|---|---|---|
| M1 | Status · الحالة | stage = "P3 · Paper Beta executing"; Owner / Claude / System / Next; project chips; next Owner gate; exposure; open incidents | the same scenario as desktop; the workstream record | Never "P2 Closed" as the stage label | ☐ |
| M2 | Resume · استئناف | step 7/7 (P2 closure ladder); verdict; closure outcome PASS; lifecycle; checkpoint; healthy-at; known / unknown / unverified; "Forbidden now" | the scenario (P2 closure record, health check, workstream record); the governed forbidden list | Forbidden now = Real money · H1 launch · Restarting FP-CONTROL-3 · Strategy, risk or dataset change · Reopening the product shape | ☐ |
| M3 | Incidents · الحوادث | the list (rows open a read-only detail) | non-INFO health findings, §19 included | "None open" when INFO; **UNKNOWN** when no findings were produced | ☐ |
| M4 | More → Decisions | last **sealed** decision, with the 9-stage trace | the sealed decision ledger | Marked "Sealed record"; unknown if the record is missing | ☐ |
| M5 | More → Trades | open = none; the sealed closed trades with backing | the sealed trade ledger + PLN-07 audit | Unknown if missing | ☐ |
| M6 | More → Operations | runtime, safe state, recovery, backup, restore, host-reboot recovery | backup set; drill record; `LIVE.ops` | "The Kill Switch is never in this view and never on mobile". Host-reboot recovery: same finding F-CR-1 as S10 | ☐ |
| M7 | More → Market | no chart (by design); data age | — | "Charts are intentionally not shown on mobile" | ☐ |
| M8 | More → Risk / Evidence / History / System / Settings | as on desktop, compact | as on desktop | Settings: viewer preferences only | ☐ |
| M9 | No action on mobile | Only navigation buttons (tabs, list rows, Back) | — | No acknowledge, no stop, no Kill Switch · لا إجراءات على الجوال | ☐ |

## 4a. What is already verified, and what is not (three separate levels)
| Level | State | Evidence |
|---|---|---|
| Implementation | Done: 12 desktop screens + 4 mobile tabs bound | PRs #80, #81, #87, #88 merged |
| Repository verification (cloud, synthetic data) | Done | `tests/test_p3_control_room.py`. Headless Chromium EN + AR at desktop 1440 px and mobile 390 px: 0 console errors, no DEMO text, RTL in AR, navigation-only buttons on mobile, UNKNOWN on missing evidence. Frozen prototype digest `e17d50dc…` verified by the build |
| **Host acceptance (this checklist)** | **PENDING** | Owner walkthrough on the host after preconditions P3–P4 (§1); §6 sign-off |

CI green is not host acceptance. A merged PR is not operational closure.

## 5. Known limitations to accept or reject (not defects to hide)
- The view is regenerated hourly. Between runs it ages, and past 2 h it says it is stale.
- The Resume ladder is the frozen P2-closure ladder; the P3 stage shows in the stage chip and project chips (recorded delta in the authority record §2).
- Market Workspace shows the last 56 sealed bars only; earlier fills have no marker.
- The `owner` / `claude` / `next` texts come from the governed workstream record and change only by merged PR, so they can lag one merge behind.
- No off-host observation exists yet (PLN-05 Tier 3 / PLN-06).
- Until node-exporter and an alert channel are installed (PLN-06), a CRITICAL finding is visible here and in the journal/desktop notification, but is not pushed to the phone.
- Incidents have no acknowledge/close workflow in the view (operator CLI only, by design).
- **F-CR-1 (open integration finding):** the host-reboot recovery state is a fixed text in `research/p3/control_room.py` (`LIVE.ops.reboot` and the Resume "unverified" list), not read from the PLN-04 record. Since PR #94 it understates the evidence. It is conservative (never shows green without evidence), but it is not accurate, and it is fixed only by a Control Room PR.

## 6. Owner sign-off (filled by the Owner in the Owner's own PR)
```text
PLN09_OWNER_ACCEPTANCE   = PENDING
RUN_ID                   = <STANDALONE for the PLN-09 acceptance; the PLN-10 run_id when re-walked inside that run>
VIEW_BUILT_AT_MAIN       = <sha>
VIEW_OBSERVED_UTC        = <time shown in the banner>
DESKTOP_CHECKS (G1–G9, S1–S12) = <PASS / FAIL with item numbers>
MOBILE_CHECKS (M1–M9)    = <PASS / FAIL with item numbers>
FINDINGS                 = <list, or NONE>
SIGNED                   = <Owner, date>
```
A FAIL is recorded and fixed under the contract. It is never waived. Accepting PLN-09 does not accept PLN-10 or authorize anything else.

**Use in PLN-10.** The Paper Beta acceptance run reuses this checklist unchanged as its S-UI procedure (evidence id `PLN-09.projection`, [`PLN_10_PAPER_BETA_ACCEPTANCE_PROGRAM.md`](PLN_10_PAPER_BETA_ACCEPTANCE_PROGRAM.md) §2). The standalone sign-off above (`RUN_ID = STANDALONE`) is the PLN-09 prerequisite. Inside the run, the Owner walks §2–§4 again and fills a second §6 block with that run's `run_id`.
