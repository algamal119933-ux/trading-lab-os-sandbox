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
- No health code changed. The rules read only what `research/p3/health.py` already emits
  (`tlos_p3_health_check{check}` 0/1/2 and `tlos_p3_health_overall`) and node-exporter's own textfile metrics.
- Reuse classification: Prometheus = REUSE_EXISTING; node-exporter and Alertmanager = REUSE (upstream Prometheus
  ecosystem); rules/config = BUILD_SMALL_MISSING_LAYER. NEW_MONITORING_PLATFORM = NO.

| Alert | Condition | §19 severity |
|---|---|---|
| `TLOSHealthCritical` | any `tlos_p3_health_check == 2` (one alert per check label: free space, WDC mount, backup verify/absence, P2 timer re-enabled …) | CRITICAL |
| `TLOSHealthWarning` | any `tlos_p3_health_check == 1` (backup older than RPO, backup timer not active, normal end due) | WARNING |
| `TLOSHealthTextfileStale` | the health textfile is more than ~2 h old (the hourly job died) | CRITICAL |
| `TLOSHealthTextfileMissing` | node-exporter cannot see the textfile for 10 min | CRITICAL |
| `TLOSTextfileScrapeError` | node-exporter cannot parse a textfile for 5 min | WARNING |
| `TLOSNodeExporterDown` | the exporter is unreachable for 5 min | CRITICAL |
| `TLOSWatchdog` | always firing; delivered only to the off-host dead-man | — |

Not covered, and not claimed: the §19 governance-level CRITICALs that no P3 metric emits yet (paper guard failure,
evidence chain broken, real-money enabled, unexpected writer). They need an emitter first; that is PLN-07/PLN-10 work.

## 2. Verification done in this change (cloud, no host)
- `promtool check rules` and `promtool check config` (Prometheus 3.14.0): SUCCESS, 7 rules.
- `promtool test rules scripts/p3/ops/rules/tlos_p3_alerts.test.yml`: SUCCESS. Every CRITICAL and WARNING the
  health job emits raises its alert in a test, plus staleness, absence, scrape error and exporter-down.
- `amtool check-config` (Alertmanager 0.28.1) on the template with a dummy chat id: SUCCESS, 4 receivers.
- `docker compose -f scripts/p3/ops/docker-compose.p3-ops.yml config`: renders two services; the base `docker compose config` is unchanged.
- `tests/test_p3_alerting.py`: structure, safety and consistency checks; it runs promtool/amtool when present.

## 3. Owner runbook (each step is an OWNER ACTION on hamza-workstation)
Run from the tools checkout after it is updated to a main that contains this change
(`~/projects/trading/tlos-p3`).

1. **Install node-exporter** (sudo): `sudo apt install prometheus-node-exporter`
2. **Point it at the health textfile, loopback only** (sudo): edit `/etc/default/prometheus-node-exporter` so that
   `ARGS="--web.listen-address=127.0.0.1:9100 --collector.textfile.directory=/home/hamza/tlos-paper/p3-evidence"`,
   then `sudo systemctl restart prometheus-node-exporter`.
3. **Let the `prometheus` user read only that directory** (sudo):
   `systemctl show prometheus-node-exporter -p ProtectHome` must not say `yes` (if it does, add a drop-in with
   `ProtectHome=read-only`). Then
   `sudo setfacl -m u:prometheus:--x /home/hamza /home/hamza/tlos-paper` and
   `sudo setfacl -m u:prometheus:r-x /home/hamza/tlos-paper/p3-evidence` and
   `sudo setfacl -d -m u:prometheus:r-- /home/hamza/tlos-paper/p3-evidence` (default ACL, so the hourly rewrite stays readable).
   Verify: `curl -s 127.0.0.1:9100/metrics | grep tlos_p3_health_overall` prints a value.
4. **Choose the channel** (Telegram or ntfy) and create the files outside Git and outside every backup root:
   `mkdir -p ~/.config/tlos-p3-ops/secrets && chmod 700 ~/.config/tlos-p3-ops/secrets`;
   copy `scripts/p3/ops/alertmanager.yml.template` to `~/.config/tlos-p3-ops/alertmanager.yml`, replace
   `__TELEGRAM_CHAT_ID__` (or delete the Telegram receiver), set the critical/warning routes from `"null"` to the
   chosen receiver, and write the secret to `secrets/telegram_bot_token` or `secrets/ntfy_url` with `chmod 600`.
   Both files must exist **before** step 5, or Docker creates directories in their place.
5. **Start the ops plane**: `docker compose -f scripts/p3/ops/docker-compose.p3-ops.yml up -d`.
   Verify: `curl -s 127.0.0.1:9091/-/ready`, `curl -s 127.0.0.1:9093/-/ready`, and
   `curl -s 127.0.0.1:9091/api/v1/targets | grep -o '"health":"up"'`.
6. **Prove delivery** (the acceptance evidence): send one test alert and confirm it on the phone:
   `docker exec tlos-p3-alertmanager amtool --alertmanager.url=http://127.0.0.1:9093 alert add TLOSDeliveryTest severity=critical check=owner-test`.
7. **Optional off-host dead-man**: create a healthchecks.io check (period 5 min, grace 15 min) or a remote Uptime Kuma
   push monitor, put its URL in `secrets/deadman_url`, route `TLOSWatchdog` to `deadman`, and restart Alertmanager.
   This is the only part that still reports when the host itself is dead.

Stopping is `docker compose -f scripts/p3/ops/docker-compose.p3-ops.yml down` (never `down -v`). The P3 kill switch's scope
(`tradinglab-fp-control-*`, `tlos-h1-paper-cohort-*`) does not include these containers, by design.

## 4. PLN-06 acceptance mapping
| Contract acceptance | Evidence after the Owner actions | Status now |
|---|---|---|
| "Each §19 CRITICAL condition raises an alert in a test" | `promtool test rules` (this change) for every condition the health job emits | rule leg PASS in test; governance-level CRITICALs not emitted yet (§1) |
| Capacity thresholds are enforced | `free_space:*` CRITICAL → `TLOSHealthCritical` (test) | rule leg PASS in test |
| Normal end is detected | `normal_end:*` WARNING → `TLOSHealthWarning` (test); detection itself already met | met |
| Alert reaches the Owner | step 6 test alert received + one real scrape of `tlos_p3_health_overall` | **PENDING — Owner** |

`PLN_06 = PARTIAL` until step 6 is recorded here by an Owner-merged update.
