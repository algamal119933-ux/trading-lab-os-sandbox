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

## 1a. How each step is executed and recorded
Every step below is one row: **Open** (where), **PASS when** (what you must see), **FAIL when** (what makes it fail),
and an **evidence id** `PLN09-W-<item>`. Write PASS or FAIL against each evidence id in the §6 block, with a short note
for every FAIL. Nothing is left blank: a step that cannot be checked is FAIL with the note "not checkable". No step needs
a runtime, a launch or any trading authority; the view is a static page and every button in it is navigation.

Before the steps, record the page identity once (evidence id `PLN09-W-ID`): the banner's observation time and host, and
`sha256sum ~/tlos-paper/p3-evidence/control_room/index.html`.

## 2. Global checks (every screen) · فحوص عامة

| # | Open | PASS when | FAIL when | Evidence id | ✓ |
|---|---|---|---|---|---|
| G1 | any screen, top line | it reads "LIVE PROJECTION · READ-ONLY · NOT EVIDENCE AUTHORITY", with the observation time and host · شريط "عرض مباشر للقراءة فقط" ظاهر | the line is missing, or shows no time or host | `PLN09-W-G1` | ☐ |
| G2 | every screen | no "DEMO", "DEMO-PAIR" or "DEMO-PRICE" text anywhere · لا قيم تجريبية | any DEMO value appears on a bound screen | `PLN09-W-G2` | ☐ |
| G3 | identity bar; Risk & Authority | PAPER and "Real money blocked" in the bar; Real money = Blocked (or Unknown — treated as blocked) in the matrix · المال الحقيقي محظور | Real money reads allowed, ok or green anywhere | `PLN09-W-G3` | ☐ |
| G4 | Truth Strip | order Health · Authority · Evidence · Freshness · Runtime · Reconciliation · الترتيب مطابق | another order, or a dimension missing | `PLN09-W-G4` | ☐ |
| G5 | every screen | anything not observed reads Unknown; Paper trading / Long entries never read "Allowed" while Runtime is not Running · غير المرصود يظهر "غير معروف" | an unobserved value is green, or a capability reads "Allowed · paper" with no running runtime | `PLN09-W-G5` | ☐ |
| G6 | the page, more than 2 h after its observation time (or compare banner time with the clock) | the stale banner appears and the dimensions turn stale; Authority stays as recorded unless the authorization has expired · العرض القديم يُعلَن | an old page still reads Fresh | `PLN09-W-G6` | ☐ |
| G7 | AR toggle | the layout mirrors, the frozen Arabic terms are used, nothing is left in English · العربية من اليمين لليسار | layout not mirrored or untranslated text | `PLN09-W-G7` | ☐ |
| G8 | the page with the network off; page source | it loads and works; the source keeps `connect-src 'none'` · يعمل دون شبكة | a network error, a blank page, or the CSP line missing | `PLN09-W-G8` | ☐ |
| G9 | every button | nothing starts, stops, acknowledges or changes anything; the Kill Switch appears only as a CLI reference · لا يوجد أي تحكم | any control has an effect | `PLN09-W-G9` | ☐ |

## 3. Desktop screens (12) · شاشات سطح المكتب

| # | Open | PASS when (traced to its source) | FAIL when | Evidence id | ✓ |
|---|---|---|---|---|---|
| S1 | Command Center · مركز القيادة | verdict; Owner / Claude / System / Next; Project now and PLN-00..11 chips match `research/p3/records/p3_workstreams.json` at the built SHA; Runtime = Stopped (no cohort) | a text or chip differs from the record, or Runtime is not what `docker ps` shows | `PLN09-W-S1` | ☐ |
| S2 | Project & Continuity · المشروع والاستمرارية | resume brief, P2 terminal law, checkpoints and stage map trace to `docs/p2/P2_CLOSURE.md`, the workstream record and git; the ladder is the P2 closure ladder (7/7) | a value has no source, or the brief says DEMO | `PLN09-W-S2` | ☐ |
| S3 | Incidents · الحوادث | one open incident per non-INFO health finding (§19 checks included); "None open" only when health is INFO; **Unknown** when the health run gave no findings | "None open" while a finding is WARNING/CRITICAL or while there are no findings | `PLN09-W-S3` | ☐ |
| S4 | Market Workspace · مساحة السوق | sealed bars and fill markers from the sealed P2 input ledger via the newest PLN-07 audit; current market state = Unknown (no feed) | a live price, or a marker that is not a recorded fill | `PLN09-W-S4` | ☐ |
| S5 | Decisions · القرارات | the list (≤ 40) and the 9-stage trace from the sealed decision ledger; Exit Contract / Verified Outcome = "not logged" | an inferred stage value, or DEMO rows | `PLN09-W-S5` | ☐ |
| S6 | Trades & Positions · الصفقات والمراكز | open = none (runtime stopped); closed: BTC #1 Backed, ETH #2 Contextual · unbacked (F-2) | an unbacked leg shown as backed, or open positions while stopped | `PLN09-W-S6` | ☐ |
| S7 | Risk & Authority · المخاطر والصلاحيات | capability matrix from the registry, contract §23 and the authorization at 7b1b1fa1; exposure 0 % **only** while Runtime = Stopped; otherwise Unknown | exposure 0 % with Runtime Unknown or Running; a blocked capability shown allowed | `PLN09-W-S7` | ☐ |
| S8 | Evidence & Reconciliation · الأدلة والمطابقة | P2 reconcile 14/14, backup verify, drill record, ledger chain, PLN-07 audit, each with its source; the 2 unbacked executions shown as a finding | a check without a source, or the finding hidden | `PLN09-W-S8` | ☐ |
| S9 | History · السجل | git merges, backup sets, operator ledger, drills and audits in time order | an event without a source, or out of order | `PLN09-W-S9` | ☐ |
| S10 | Operations · العمليات | backup, restore and recovery from the newest set, `p3-evidence/drills/*.json` and the operator ledger. Host reboot recovery: with the F-CR-1 fix (PR #97) merged, it reads "Reboot correctness PASS · … accepted by PR #94" and the Resume "unverified" list shows the open PLN-04 decisions from the workstream record; without it, it reads "not yet exercised" — record that as finding F-CR-1 (§5) | a reboot PASS shown with no record behind it, or "not yet exercised" after PR #97 is merged | `PLN09-W-S10` | ☐ |
| S11 | System · النظام | host, disks, timers, runtime pin vs main match the host (`uptime`, `systemctl --user list-timers`, `git rev-parse`) | a value that the host contradicts | `PLN09-W-S11` | ☐ |
| S12 | Settings · الإعدادات | viewer preferences only; Return detection = not active (static view); notifications cite `scripts/p3/scheduled_health.sh` | any setting that changes risk, mode or authority | `PLN09-W-S12` | ☐ |

## 4. Mobile tabs · تبويبات الجوال
Open with a window narrower than 720 px, or `#mobile` at the end of the address.

| # | Open | PASS when | FAIL when | Evidence id | ✓ |
|---|---|---|---|---|---|
| M1 | Status · الحالة | stage = "P3 · Paper Beta executing" (or "authorization not valid" if it expired); Owner / Claude / System / Next; project chips; next Owner gate; exposure; open incidents — same scenario as desktop | the stage reads "P2 Closed", or a value differs from desktop | `PLN09-W-M1` | ☐ |
| M2 | Resume · استئناف | step 7/7 (P2 closure ladder); verdict; closure outcome PASS; lifecycle; checkpoint; healthy-at; known / unknown / unverified; Forbidden now = Real money · H1 launch · Restarting FP-CONTROL-3 · Strategy, risk or dataset change · Reopening the product shape | a field without its source, or another forbidden list | `PLN09-W-M2` | ☐ |
| M3 | Incidents · الحوادث | rows open a read-only detail; "None open" when INFO; **Unknown** when no findings | "None open" without findings | `PLN09-W-M3` | ☐ |
| M4 | More → Decisions | last **sealed** decision with the 9-stage trace, marked "Sealed record"; Unknown if the record is missing | a decision not marked sealed | `PLN09-W-M4` | ☐ |
| M5 | More → Trades | open = none (runtime stopped); sealed closed trades with backing; Unknown if missing | as S6 | `PLN09-W-M5` | ☐ |
| M6 | More → Operations | runtime, safe state, recovery, backup, restore, host-reboot recovery as S10; "The Kill Switch is never in this view and never on mobile" | as S10, or any action offered | `PLN09-W-M6` | ☐ |
| M7 | More → Market | no chart (by design); data age shown | a chart, or a live price | `PLN09-W-M7` | ☐ |
| M8 | More → Risk / Evidence / History / System / Settings | as on desktop, compact | a value that differs from desktop | `PLN09-W-M8` | ☐ |
| M9 | every mobile button | only navigation (tabs, list rows, Back) · لا إجراءات على الجوال | an acknowledge, stop or Kill Switch control | `PLN09-W-M9` | ☐ |

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
- **F-CR-1 (integration finding; fixed by PR #97, open until that PR is merged):** the host-reboot recovery state is a fixed text in `research/p3/control_room.py` (`LIVE.ops.reboot` and the Resume "unverified" list), not read from the PLN-04 record. Since PR #94 it understates the evidence. It is conservative (never shows green without evidence), but it is not accurate, and it is fixed only by a Control Room PR.

## 6. Owner sign-off (filled by the Owner in the Owner's own PR)
```text
PLN09_OWNER_ACCEPTANCE   = PENDING
RUN_ID                   = <STANDALONE for the PLN-09 acceptance; the PLN-10 run_id when re-walked inside that run>
VIEW_BUILT_AT_MAIN       = <sha>
VIEW_OBSERVED_UTC        = <time shown in the banner>
PAGE_IDENTITY (PLN09-W-ID) = <banner time · host · sha256 of index.html>
DESKTOP_CHECKS (PLN09-W-G1..G9, PLN09-W-S1..S12) = <PASS / FAIL per evidence id>
MOBILE_CHECKS (PLN09-W-M1..M9)                    = <PASS / FAIL per evidence id>
FINDINGS                 = <list, or NONE>
SIGNED                   = <Owner, date>
```
A FAIL is recorded and fixed under the contract. It is never waived. Accepting PLN-09 does not accept PLN-10 or authorize anything else.

**Use in PLN-10.** The Paper Beta acceptance run reuses this checklist unchanged as its S-UI procedure (evidence id `PLN-09.projection`, [`PLN_10_PAPER_BETA_ACCEPTANCE_PROGRAM.md`](PLN_10_PAPER_BETA_ACCEPTANCE_PROGRAM.md) §2). The standalone sign-off above (`RUN_ID = STANDALONE`) is the PLN-09 prerequisite. Inside the run, the Owner walks §2–§4 again and fills a second §6 block with that run's `run_id`.
