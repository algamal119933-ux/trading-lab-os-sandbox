# P3-PLN-06 — §19 alert evaluation and delivery (prepared; Owner actions pending)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-06 (frozen at fcd06b21), executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1). Master plan §19 severities.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCH_AUTHORIZED = NO

This closes the repository side of the one remaining PLN-06 condition recorded in
[`PLN_06_07_08_OPERATIONS.md`](PLN_06_07_08_OPERATIONS.md): "the §19 Prometheus/Grafana leg … a scrape target and an
alert rule". Nothing here was installed or started. **PLN-06 stays PARTIAL** until the Owner actions in §3 are done
and the acceptance in §4 is evidenced.

## 1. Design (reuse only, P3_CONTRACT §4)
```text
tlos-p3-health.timer (hourly, exists) → scheduled_health.sh → ~/tlos-paper/p3-evidence/tlos_p3_health.prom
  → prometheus-node-exporter textfile collector (Ubuntu package, 127.0.0.1:9100)       [OWNER: install]
  → tlos-p3-prometheus (prom/prometheus:v3.14.0, the FP stack's image, 127.0.0.1:9091) rules: scripts/p3/ops/rules/
  → tlos-p3-alertmanager (prom/alertmanager:v0.28.1, 127.0.0.1:9093)                 [OWNER: channel + secrets]
  → Telegram or ntfy (critical: now, repeat 1 h · warning: grouped, repeat 12 h)
  → TLOSWatchdog (always firing) → healthchecks.io / remote Uptime Kuma push URL       [OWNER: optional account]
```
- `scripts/p3/ops/docker-compose.p3-ops.yml` is a **separate compose project** (`tlos-p3-ops`). It is not the FP runtime, has no
  trading component, no exchange credential and no published port: host networking with every listener on 127.0.0.1.
- The rules read only what `research/p3/health.py` emits (`tlos_p3_health_check{check}` 0/1/2 and
  `tlos_p3_health_overall`) and node-exporter's own textfile metrics. The health job now also emits the §19
  CRITICAL conditions a read-only host check can observe (`s19_findings`, §1.1); one generic rule pages each.
- Reuse classification: Prometheus = REUSE_EXISTING; node-exporter and Alertmanager = REUSE (upstream Prometheus
  ecosystem); rules/config = BUILD_SMALL_MISSING_LAYER. NEW_MONITORING_PLATFORM = NO.

| Alert | Condition | §19 severity |
|---|---|---|
| `TLOSHealthCritical` | any `tlos_p3_health_check == 2` (one alert per check label: free space, WDC mount, backup verify/absence, P2 timer re-enabled, the health timer itself not scheduled, §19 checks …) | CRITICAL |
| `TLOSHealthWarning` | any `tlos_p3_health_check == 1` (backup older than RPO, backup timer not active, normal end due, clock not NTP-synchronised, any UNPROVEN state) | WARNING |
| `TLOSHealthTextfileStale` | the health textfile is more than ~2 h old (the hourly job died) | CRITICAL |
| `TLOSHealthTextfileMissing` | node-exporter cannot see the textfile for 10 min | CRITICAL |
| `TLOSTextfileScrapeError` | node-exporter cannot parse a textfile for 5 min | WARNING |
| `TLOSNodeExporterDown` | the exporter is unreachable for 5 min | CRITICAL |
| `TLOSWatchdog` | always firing; delivered only to the off-host dead-man | — |

### 1.1 Master plan §19 coverage matrix (reconciled 2026-10-27 at main `bf208ba6`)
Every row is a read-only check in `research/p3/health.py` (`s19_findings`, run hourly by `scripts/p3/health_check.py`
and by the Control Room build), emitted as `tlos_p3_health_check{check="…"}` and paged by `TLOSHealthCritical` /
`TLOSHealthWarning`. Tests: `tests/test_p3_health_s19.py` (positive + negative per row) and the promtool rule
tests (each label raises its alert). A check that cannot run reports WARNING/CRITICAL, never INFO.

| §19 condition | Check label → severity | Source (reused) | Status |
|---|---|---|---|
| **paper guard failure** | `paper_guard` → CRITICAL on any violation or a guard that cannot run | `scripts/paper_guard.py check_config` on the runtime `config.json`, the H1 package config and any materialised H1 lane config present | **COVERED** |
| **real-money enabled** | `real_money` → CRITICAL | `dry_run` not true; exchange credential fields set in a config or `ccxt_*` block; `FREQTRADE__DRY_RUN`≠true or `FREQTRADE__EXCHANGE__{KEY,SECRET,…}` set in the runtime `.env` or in a running paper container's env (`docker inspect`). Key names only; values are never read into a finding | **COVERED** |
| **evidence chain broken** (operator ledger) | `evidence_chain:operator_ledger` → CRITICAL on a break; WARNING if the ledger is absent | `kill_switch.verify_ledger` (hash chain, O-1) | **COVERED** |
| **evidence chain broken** (sealed evidence) | `evidence_chain:sealed_archives` → CRITICAL on any archive that no longer matches its manifest; WARNING if none found | `publish_evidence_digest.verify_archive` over `~/projects/trading/*/artifacts/*/archive_manifest.json` — full rehash hourly (~170 MB, seconds) | **COVERED** |
| **DB corruption** | sealed `tradesv3.sqlite` → via `evidence_chain:sealed_archives` | as above | **PARTIAL** — sealed DBs only; no live DB exists (no cohort running). A live-DB `PRAGMA integrity_check` belongs to the runtime that owns it (PLN-10 / H1 lane) |
| **unauthorized execution** | `unauthorized_execution` → CRITICAL: a running `tradinglab-fp-control-*` / `tlos-h1-paper-cohort-*` container with no RUNNING registry cohort | `kill_switch.paper_containers` + the registry; docker unreachable → `paper_runtime` WARNING (UNPROVEN, not healthy) | **COVERED**. Note: H1 is not in the FP registry, so a running H1 container is CRITICAL — correct while `H1_LAUNCH_AUTHORIZED = NO`; the H1 grant PR must teach this check the grant |
| **FP-CONTROL stopped** | `control_running:<role>` → CRITICAL: a RUNNING cohort whose container is not running | same | **NOT_APPLICABLE_NOW** (no RUNNING cohort; P2 closed). Implemented and tested for when one runs |
| **strategy/config hash changed** | — | registry `strategy_sha256` / `config_sha256` per cohort; enforced at launch by the FP preflight/overlay checks and by CI scope audit for the repo | **NOT_APPLICABLE_NOW** at runtime (no RUNNING cohort). A runtime hash re-check for a RUNNING cohort is a follow-up when a cohort exists |
| **T0/cohort changed** | — | registry rows change only through Owner-merged PRs; the scope audit pins every merge | **COVERED by governance (CI), not by the host monitor**; no runtime emitter |
| **unexpected writer** | `unexpected_writer` (prepared, not wired) | auditd-first design and read-only classifier: `docs/p3/PLN_06_UNEXPECTED_WRITER.md`, `research/p3/writer_watch.py` (separate PR) | **NOT_COVERED on the host** until the Owner installs auditd and its acceptance tests AT-1..AT-7 pass (or the Owner explicitly accepts the gap). Sealed-evidence tampering is still caught by the archive rehash |
| WARNING examples (research disk, API/rate limit, H1 provenance, upstream change, contention) | `free_space:*`, `backup_recency`, timers | existing | **PARTIAL** — capacity/recovery covered; API/rate-limit and upstream-change belong to a running cohort's capture loop |

### 1.2 Fail-closed audit: no safety failure can be reported as healthy
Every path where a §19 check cannot establish its answer reports WARNING (UNPROVEN) or CRITICAL. None reports INFO.

| Situation | Reported as |
|---|---|
| paper guard raises, or a config is unreadable | `paper_guard` CRITICAL |
| no paper config found at the expected paths (nothing to guard) | `paper_guard` WARNING "UNPROVEN". It used to be INFO; that was changed in this update |
| a config or env file is unreadable | `real_money` CRITICAL ("cannot prove") |
| no config and no env file could be inspected | `real_money` WARNING "UNPROVEN". It used to be INFO; changed in this update |
| docker could not be queried, so container envs are unknown | `real_money` WARNING "UNPROVEN" (changed in this update); `paper_runtime` WARNING |
| a running paper container's env cannot be read (`docker inspect` fails or raises) | `real_money` CRITICAL. Previously the container was silently skipped; changed in this update |
| operator ledger absent / verifier raises | `evidence_chain:operator_ledger` WARNING / CRITICAL |
| no sealed archive found / verifier raises on one | `evidence_chain:sealed_archives` WARNING / CRITICAL |
| the §19 set raises as a whole, or its inputs cannot be prepared (e.g. an import breaks) | `s19_checks` CRITICAL (new in this update). It is never omitted |
| §19 deliberately disabled with `--no-s19` | `s19_checks` WARNING (new in this update) |
| systemd cannot be queried, or gives no state for a timer (including the P2 timer) | `timer:<unit>` WARNING "UNPROVEN". It used to be INFO for the P2 timer, which counts as "not active"; changed in the Owner-review update |
| the health run itself raises (e.g. an unreadable registry) | `health_run` CRITICAL, exit code 2, and a textfile with `tlos_p3_health_overall 2`. It used to be a Python traceback, exit 1 (read as WARNING) and a stale textfile; changed in the Owner-review update |
| the hourly job itself dies or stops writing | `TLOSHealthTextfileStale` / `TLOSHealthTextfileMissing` CRITICAL (rule leg; requires node-exporter) |
| the exporter is down | `TLOSNodeExporterDown` CRITICAL (requires node-exporter) |
| the hourly health timer itself is not enabled/active | `timer:tlos-p3-health.timer` CRITICAL (new, residual review): the monitor is blind. Seen by any manual run and by the Control Room build; while the timer is down, no hourly run happens, so this alert needs the stale-textfile rule (node-exporter) or the dead-man to fire unattended |
| systemd cannot give the health timer's state | `timer:tlos-p3-health.timer` WARNING "UNPROVEN" |
| the host clock is not NTP-synchronised, or the state cannot be read | `clock_sync` WARNING ("NOT synchronised" / "UNPROVEN"). It is never INFO unless `timedatectl` says `yes` |

Residual limit: until node-exporter and a channel are installed (§3), alerts are evaluated only in tests, and on the host
only the journal and desktop notification from `scheduled_health.sh` are live. A dead host cannot report itself without
the optional off-host dead-man (§3 step 7).

### 1.3 Residual §19 review (2026-10-27, main `19d77e90`)
Classification: COVERED · PARTIAL · NOT_COVERED · NOT_APPLICABLE · UNPROVEN. **"UNPROVEN"** means the repository side exists and is tested, but nothing on the host has proven it yet. An unknown result is never INFO.

| Condition | What covers it | Classification |
|---|---|---|
| **Database integrity** | Sealed `tradesv3.sqlite` files are covered by `evidence_chain:sealed_archives`, which rehashes them hourly. No live trading DB exists while no cohort runs. The Prometheus/Grafana/MLflow volumes are non-authoritative; they are backed up but not integrity-checked | **PARTIAL.** Sealed: COVERED. Live DB: NOT_APPLICABLE now; it belongs to the runtime that owns it (H1 lane / PLN-10). Monitoring volumes: NOT_COVERED, non-authoritative |
| **Evidence writers** (who writes protected paths) | auditd-first design and classifier, `docs/p3/PLN_06_UNEXPECTED_WRITER.md` (separate PR). Content tampering on sealed evidence is caught by the rehash; the ledger chain is checked hourly | **NOT_COVERED** on the host until auditd is installed and AT-1..AT-7 pass. The repository side is prepared |
| **Monitoring self-failure** | `health_run` CRITICAL when the run raises (exit 2 plus a CRITICAL textfile). `timer:tlos-p3-health.timer` CRITICAL when the hourly timer is not scheduled (new). `TLOSHealthTextfileStale` / `TLOSHealthTextfileMissing` when the job silently stops. `TLOSNodeExporterDown`. `TLOSWatchdog` goes to the off-host dead-man | **PARTIAL / UNPROVEN.** The in-run checks are COVERED in tests. The unattended rule leg (stale textfile, exporter down, watchdog) is UNPROVEN until node-exporter, the ops plane and a channel are installed and the §3 acceptance passes |
| **Monitoring blind spots** | Host down, power loss, network loss or a dead Alertmanager. Only an off-host dead-man (healthchecks.io / remote Uptime Kuma receiving `TLOSWatchdog`) can report these | **NOT_COVERED** until §3 step 7 (dead-man) is done; that step is mandatory for PLN-06 acceptance (see §4). The desktop notification from `scheduled_health.sh` reaches the Owner only while logged in at the host |
| **Startup after reboot** | Hourly `mount:/mnt/tlos-wdc` (CRITICAL), the timer checks, `clock_sync` (new), and `TLOSHealthTextfileStale` if the first post-boot run does not happen. Formal correctness comes from PLN-04 `verify-boot` (reboot runbook) | **PARTIAL / UNPROVEN.** The hourly checks are COVERED in tests. Post-boot correctness waits on the planned reboot acceptance (PLN-04/07, Owner) |
| **Unauthorized paper runtimes** | `unauthorized_execution` CRITICAL for a running `tradinglab-fp-control-*` / `tlos-h1-paper-cohort-*` container with no RUNNING cohort. If docker is unreachable, `paper_runtime` reports WARNING UNPROVEN. The kill switch stops them (PLN-08) | **COVERED** in tests; UNPROVEN on the host until the first hourly run after `tlos-p3` is updated. A paper runtime under another container name is outside the pattern, and there is no lawful way to start one |

## 2. Verification done in this change (cloud, no host)
- `promtool check rules` and `promtool check config` (Prometheus 3.14.0): SUCCESS, 7 rules.
- `promtool test rules scripts/p3/ops/rules/tlos_p3_alerts.test.yml`: SUCCESS. Every CRITICAL and WARNING the
  health job emits raises its alert in a test, plus staleness, absence, scrape error and exporter-down.
- `amtool check-config` (Alertmanager 0.28.1) on the template with a dummy chat id: SUCCESS, 4 receivers.
- `docker compose -f scripts/p3/ops/docker-compose.p3-ops.yml config`: renders two services; the base `docker compose config` is unchanged.
- `tests/test_p3_alerting.py`: structure, safety and consistency checks; it runs promtool/amtool when present.
- `tests/test_p3_health_s19.py`: the §19 checks (§1.1), positive and negative per condition, no secret value in any finding,
  the real paper guard and the real archive verifier on synthetic fixtures (a changed sealed sqlite is CRITICAL).

- Residual review update (2026-10-27): `timer:tlos-p3-health.timer` (`health.monitor_timer`) and `clock_sync` are added
  to the standard set, with positive, negative and UNPROVEN tests in `tests/test_p3_health_s19.py` and a promtool group
  in `tlos_p3_alerts.test.yml`. `promtool test rules`: SUCCESS.

## 3. Owner runbook: installation and delivery acceptance (exact steps)
**Preconditions (all of them, in order):**
1. The planned reboot acceptance (PLN-04/07, `claude/REBOOT_RUNBOOK_2026-10-26.md`) has PASSED. The host freeze is lifted by the Owner.
2. `~/projects/trading/tlos-p3` is updated to a main that contains this document, by an Owner action.
3. The first hourly health run after that update was read and triaged. A CRITICAL there is a real finding and is handled before going on.

Every step writes its output to one new evidence directory. That directory is not a watched evidence path, and nothing in it is ever overwritten:
```bash
EV=~/tlos-paper/pln06-acceptance/$(date -u +%Y%m%dT%H%M%SZ); [ -e "$EV" ] && echo STOP || mkdir -p "$EV"
```

| Step | OWNER command (sudo where shown) | Expected output | Evidence to capture | Rollback |
|---|---|---|---|---|
| 0. Baseline | `{ date -Is; systemctl --user list-timers 'tlos-*' --no-pager; docker ps -a --format '{{.Names}} {{.Status}}'; ss -ltnp \| grep -E ':(9091\|9093\|9100)\b' \|\| echo 'ports free'; } > $EV/00_baseline.txt` | both tlos timers active; `ports free` | `00_baseline.txt` | — |
| 1. Install node-exporter | `sudo apt install prometheus-node-exporter 2>&1 \| tee $EV/01_install.txt` | package installed; service active | `01_install.txt`, `apt-cache policy prometheus-node-exporter >> $EV/01_install.txt` | `sudo apt remove prometheus-node-exporter` |
| 2. Loopback + textfile only | edit `/etc/default/prometheus-node-exporter`: `ARGS="--web.listen-address=127.0.0.1:9100 --collector.textfile.directory=/home/hamza/tlos-paper/p3-evidence"`; `sudo systemctl restart prometheus-node-exporter`; `ss -ltn \| grep 9100 > $EV/02_listen.txt` | listens on `127.0.0.1:9100` **only** (never `0.0.0.0` / `*`) | `02_listen.txt`, a copy of the defaults file | restore the defaults file; restart |
| 3. Read access, one directory only | `systemctl show prometheus-node-exporter -p ProtectHome` (if `yes`: drop-in `ProtectHome=read-only`); `sudo setfacl -m u:prometheus:--x /home/hamza /home/hamza/tlos-paper`; `sudo setfacl -m u:prometheus:r-x /home/hamza/tlos-paper/p3-evidence`; `sudo setfacl -d -m u:prometheus:r-- /home/hamza/tlos-paper/p3-evidence`; `curl -s 127.0.0.1:9100/metrics \| grep -E '^tlos_p3_health_(overall\|check)' > $EV/03_scrape.txt` | `tlos_p3_health_overall` present and equal to the last health run's verdict; every `check` label present | `03_scrape.txt`, `getfacl` output | `sudo setfacl -x u:prometheus …` on the three paths |
| 4. Channel + secrets | `mkdir -p ~/.config/tlos-p3-ops/secrets && chmod 700 ~/.config/tlos-p3-ops/secrets`. Copy the template to `~/.config/tlos-p3-ops/alertmanager.yml`. Choose **Telegram** (chat id + `secrets/telegram_bot_token`) **or ntfy** (`secrets/ntfy_url`), `chmod 600`. Route critical and warning to it (no longer `"null"`) | both files exist **before** step 5. `amtool check-config ~/.config/tlos-p3-ops/alertmanager.yml` → SUCCESS | `amtool` output (**never** the secret) in `$EV/04_amcheck.txt` | delete `~/.config/tlos-p3-ops` |
| 5. Start the ops plane | `docker compose -f scripts/p3/ops/docker-compose.p3-ops.yml up -d`; `curl -s 127.0.0.1:9091/-/ready; curl -s 127.0.0.1:9093/-/ready; curl -s 127.0.0.1:9091/api/v1/targets \| grep -o '"health":"up"'` | both report ready; the node target is `"health":"up"`; `curl -s 127.0.0.1:9091/api/v1/rules \| grep -c TLOS` ≥ 7 | outputs in `$EV/05_ops.txt` | `docker compose -f … down` (**never** `down -v`) |
| 6. Delivered test alert (**acceptance**) | `docker exec tlos-p3-alertmanager amtool --alertmanager.url=http://127.0.0.1:9093 alert add TLOSDeliveryTest severity=critical check=owner-test` | the message arrives on the Owner's phone within 2 minutes | photo/screenshot of the received message, time received, `amtool alert query` output in `$EV/06_delivery.txt` | `amtool silence add alertname=TLOSDeliveryTest` (the test alert expires by itself) |
| 7. Dead-man (**mandatory for PLN-06**, it is the only cover for host-down) | create a healthchecks.io check (period 5 min, grace 15 min) or a remote Uptime Kuma push monitor. Put the URL in `secrets/deadman_url`, route `TLOSWatchdog` to `deadman`, `docker restart tlos-p3-alertmanager` | the check turns green within 10 minutes | dashboard screenshot + time in `$EV/07_deadman.txt` | delete the check; route `TLOSWatchdog` to `"null"` |
| 8. Real alert path end-to-end | Stop the health timer for 2.5 h: `systemctl --user stop tlos-p3-health.timer`. Expect `TLOSHealthTextfileStale` on the phone. Then `systemctl --user start tlos-p3-health.timer` | the stale alert arrives; it clears after the next run | message screenshot + both times in `$EV/08_e2e.txt` | `systemctl --user start tlos-p3-health.timer` (mandatory, even on FAIL) |

**PASS/FAIL (all must be PASS; one FAIL keeps PLN-06 PARTIAL and is recorded, never waived):**
| Item | PASS when |
|---|---|
| Exporter loopback-only | step 2 shows only `127.0.0.1:9100` |
| Textfile scraped | step 3 shows `tlos_p3_health_overall` matching the last run |
| Rules loaded | step 5 shows ≥ 7 TLOS rules and the target is up |
| Delivery | step 6 message received |
| Dead-man | step 7 check green; optionally, pausing Alertmanager for one grace period makes it alert |
| End-to-end | step 8 stale alert received, then cleared |
| No secret in Git or backups | `git -C ~/projects/trading/tlos-p3 status` clean, and `~/.config/tlos-p3-ops` outside every backup root (by construction) |

The evidence directory listing and the PASS/FAIL table are recorded in this document by an Owner-merged PR. That merge, together with the unexpected-writer decision, is what moves PLN-06 out of PARTIAL.

Stopping is `docker compose -f scripts/p3/ops/docker-compose.p3-ops.yml down` (never `down -v`). The P3 kill switch's scope
(`tradinglab-fp-control-*`, `tlos-h1-paper-cohort-*`) does not include these containers, by design.

## 4. PLN-06 acceptance mapping
| Contract acceptance | Evidence after the Owner actions | Status now |
|---|---|---|
| "Each §19 CRITICAL condition raises an alert in a test" | `promtool test rules` + `tests/test_p3_health_s19.py` for every condition the health job emits (§1.1) | PASS in test for paper guard, real-money, evidence chains, unauthorized execution, stopped control; **NOT_COVERED: unexpected writer**; live-DB integrity and runtime hash drift N/A until a cohort runs |
| Capacity thresholds are enforced | `free_space:*` CRITICAL → `TLOSHealthCritical` (test) | rule leg PASS in test |
| Normal end is detected | `normal_end:*` WARNING → `TLOSHealthWarning` (test); detection itself already met | met |
| Alert reaches the Owner | §3 steps 3, 6 and 8 (scrape, delivered test alert, real stale-textfile alert end-to-end) | **PENDING — Owner** |
| Host-down awareness | §3 step 7 dead-man green | **PENDING — Owner** |

`PLN_06 = PARTIAL` until (a) the §3 PASS/FAIL table is all PASS and recorded here by an Owner-merged update, and (b) the
NOT_COVERED row (unexpected writer, `docs/p3/PLN_06_UNEXPECTED_WRITER.md`) is either covered (AT-1..AT-7 PASS) or explicitly accepted by
the Owner in a recorded decision. **Not CLOSED.**

**First host run after the update (Owner):** the new checks read real host configs and archives. If the first
hourly run reports a CRITICAL on `paper_guard`, `real_money` or `evidence_chain:*`, treat it as a real §19 finding:
stop and send the output to Claude; do not silence it.
