# H1-PAPER-COHORT-1 — launch binder

**Status: prepared and held until P2 reaches its terminal state. It is not authorized.**
This binder gathers every non-result-bearing launch artifact in one place. It sets no
T0, starts nothing, and creates no live-money configuration. The cohort starts only
under the Owner's `H1_LAUNCH_AUTHORIZATION`, which names the package digest below. The
authorization is valid only when `h1_launch_card.py` reads `READY_FOR_OWNER_AUTHORIZATION`.
Under any other reading, the default is **DENY**.

```text
AUTHORITY            Owner directive "PREPARE NEXT H1 PHASE NOW", 2026-10-17T18:09:02Z (preparation only)
PAPER / DRY-RUN ONLY REAL_MONEY_AUTHORIZED = NO · no exchange key · no live order route · no P3 path
```

## 1. Identities (frozen; any change voids an authorization)

| Item | Value |
|---|---|
| Package | `H1-PAPER-COHORT-PACKAGE-1` v1.0.0 · `PACKAGE_MANIFEST.sha256` = `ef9a3d0c5b5b9abe122faaa1bd4ef67feb0c3ec4437bed56cd6ef33d910bc43c` |
| Cohort | `H1-PAPER-COHORT-1` · candidate `H1_EMACROSS` · family `BTSL_EMA_REGIME` |
| Strategy | `wiktorj137/btc-strategy-lab@b68a5518`. Files: `EmaCross.py` `387cf39f…a95f24` (2,183 B) · `EmaCross.json` `9209a90e…27e3ee` (168 B; `ema_period 600`, `exit_threshold 2.0`) · `LICENSE` GPL-3.0 `3972dc97…dfb36986` (35,149 B) |
| Config | `research/paper/h1/package/config.h1-paper.json` `8c780507…be1db`: `dry_run true`, wallet 100, stake 10, fee 0.1%/side, empty key and secret, `force_entry_enable false` |
| Engine | `freqtradeorg/freqtrade@sha256:da3428fde0f7f9f976eaafba8abc7eba42bf978f23e4808347e15d476ad9a643` (2026.7) |
| Market | Binance spot · BTC/USDT · 1h · long-only |
| Runtime | compose project `tlos-h1-paper-cohort-1` · container `tlos-h1-paper-cohort-1-freqtrade` · network `tlos-h1-paper-cohort-1-net` · API `127.0.0.1:8181` |

## 2. Source verification and authority records

| Record | Where | sha256 |
|---|---|---|
| G5 host check (RECOVERED) | `research/paper/h1/amendments/G5_HOST_CHECK.md` (G11 PR) | `2870d7dc6ca812342b040e3864dfdf0b5151c9cf876483eeaa7f79ed909159f9` |
| G6 amendments (G.2-a and G.2-b) | `research/paper/h1/amendments/H1_AMENDMENTS_G6.md` (G11 PR) | `0575c3a2d780892ceaee28f703d7d73caa675a8a53d8409c0f084feb669252fd` |
| Recovered source | `hamza-workstation:/home/hamza/projects/trading/tlos-control/.upstream-cache/btc_strategy_lab/` | all three pins match (G5) |

## 3. Tools (this directory; none starts anything)

| Tool | Does | Verdicts |
|---|---|---|
| `h1_materialise.py` | G.2-b: credential-free, hash-verified copy of exactly three files into a fresh workspace; writes `MATERIALISATION_RECORD.json` | `H1_MATERIALISATION = PASS / FAIL` |
| `h1_p2_entry_gate.py` | G.2-a: reads the P2 closure, registry, digests, package and amendment from the git ref | `H1_ENTRY_ELIGIBLE / WAITING / BLOCKED` |
| `h1_host_placement.py` | §8: no running P2 container, unless an Owner exception is merged; H1's name, network and port are free | `PASS / PASS_ISOLATED_SAME_HOST / BLOCKED / UNPROVEN` |
| `h1_launch_card.py` | assembles every row of `H1_LAUNCH_AUTHORIZATION` | `READY_FOR_OWNER_AUTHORIZATION`, otherwise `DENY` |
| `../package/h1_paper.py` | `verify`, `preflight`, `incident` (unchanged; frozen package) | `PASS / FAIL` |

**The P2 closure record's machine block.** `h1_p2_entry_gate.py` reads `docs/p2/P2_CLOSURE.md`. That record must
carry, inside a fenced block, one `KEY = VALUE` line per field:

```text
P2_TERMINAL_STATUS = CLOSED / PASS | INCONCLUSIVE / INSUFFICIENT | CLOSED / FAIL
COHORT_ID = FP-CONTROL-3-20260924T120000Z
EVIDENCE_VALID = YES
EVIDENCE_CHAINS = INTACT
RECONCILIATION = PASS
UNRESOLVED_INTEGRITY_DEFECTS = NONE
UNRESOLVED_TECHNICAL_DEFECTS = NONE
SAFETY_FAILURES = NONE
REAL_MONEY_AUTHORIZED = NO
```

If a field is missing, unknown or conflicting, the gate returns BLOCKED. The block reports the P2 outcome; it does not
decide it. The P2 contract (§12) still decides, and this binder changes nothing in P2.

## 4. Host bindings (launch-time; recorded in COHORT_START)

```text
H1_PAPER_STRATEGY_DIR   <workspace>/btc_strategy_lab/user_data/strategies   (output of h1_materialise.py; read-only mount)
H1_PAPER_LANE_DIR       /home/hamza/tlos-paper/h1-paper-cohort-1             (recommended in cohort.json; empty, new,
                                                                              outside every git worktree and P2 path)
  db                    <lane>/tradesv3.sqlite            (container /freqtrade/lane/tradesv3.sqlite)
  log                   <lane>/logs/freqtrade.log
  evidence              <lane>/evidence/
  incident ledger       <lane>/evidence/paper_incident_ledger.jsonl   (CANONICAL_LEDGER_V1, hash-chained)
SECOND_EVIDENCE_STORE   an Owner-named directory on a different device from the lane (a launch precondition, §9.2)
API login               an operator-local env file outside git: H1_PAPER_API_USER, H1_PAPER_API_PASSWORD,
                        H1_PAPER_JWT_SECRET, H1_PAPER_WS_TOKEN. This is the local API-server login, never an exchange key
```

## 5. Launch sequence (TEMPLATE. Run only after an Owner `H1_LAUNCH_AUTHORIZATION`)

```bash
# 0. a clean checkout of the merged main that the card names, NOT the P2 runtime checkout
git -C <h1-checkout> rev-parse HEAD                         # must equal the card's ref_commit
# 1. P2 entry gate                       → H1_ENTRY_ELIGIBLE
python3 research/paper/h1/launch/h1_p2_entry_gate.py --ref origin/main
# 2. host placement                      → HOST_PLACEMENT = PASS
python3 research/paper/h1/launch/h1_host_placement.py --ref origin/main
# 3. package verify                      → H1_PAPER_PACKAGE_VERIFY = PASS
python3 research/paper/h1/package/h1_paper.py verify
# 4. materialise (G.2-b)                 → H1_MATERIALISATION = PASS
env -i PATH=/usr/bin:/bin python3 -I research/paper/h1/launch/h1_materialise.py \
    --source /home/hamza/projects/trading/tlos-control/.upstream-cache/btc_strategy_lab \
    --workspace-root /home/hamza/tlos-paper/materialise
# 5. preflight                           → H1_PAPER_PREFLIGHT = PASS
python3 research/paper/h1/package/h1_paper.py preflight --lane-dir <LANE> --strategy-dir <STRATEGY_DIR>
# 6. the card                            → READY_FOR_OWNER_AUTHORIZATION (anything else: DENY, stop)
python3 research/paper/h1/launch/h1_launch_card.py --materialisation-record <WS>/MATERIALISATION_RECORD.json \
    --lane-dir <LANE> --second-store <STORE> --json <LANE>/../h1_launch_card.json
# 7. start (the Owner's authorization names the package digest)
env -i PATH=/usr/bin:/bin HOME=/nonexistent H1_PAPER_STRATEGY_DIR=<STRATEGY_DIR> H1_PAPER_LANE_DIR=<LANE> \
    docker compose --env-file <operator-local env file> -f research/paper/h1/package/docker-compose.h1-paper.yml up -d
# 8. COHORT_START: its recorded_utc is PAPER_T0
python3 research/paper/h1/package/h1_paper.py incident --lane-dir <LANE> --type COHORT_START \
    --detail '<MATERIALISATION_RECORD.json, package digest, card sha256, host bindings>'
```

If any step does not print its expected verdict, stop. Do not retry with changed inputs, and record what happened.

## 6. Monitoring (from T0; read-only)

- **Each hour.** `docker inspect` state, `/api/v1/ping` on 127.0.0.1:8181, and the age of the last processed candle.
  A missed candle is recorded as `ACTIVATION_GAP`. Missed signals are never executed afterwards.
- **Each day.** Lane disk use (budget 2 GB), host free space (≥ 20 GB), and the incident ledger's `verify()` result,
  which must be `[]`. Also confirm that FP-CONTROL-3's health has not degraded. P2 wins every contention (§8).
- **Each week.** A `RECONCILIATION` incident compares the DB's open trades with `/api/v1/status` and the log.
- **Never.** `/forceenter` or `/forceexit`, a config edit, a parameter change, or any benchmark change after T0 (§6).

## 7. Incident ledger

Every incident is written with `h1_paper.py incident --type <T>`, using the types in `incident.schema.json`. The
first record is `COHORT_START` and nothing may follow `COHORT_TERMINAL`. `restart_counter` is derived by the tool
and never reset. A container recreated for recovery comes from the identical package: re-run preflight, and its
digest must equal the one in COHORT_START.

## 8. Shutdown and kill (any of: SAFETY_BREACH, an Owner stop, P2 protection, END_UTC)

```bash
docker compose -f research/paper/h1/package/docker-compose.h1-paper.yml stop       # never 'down -v'; the lane is kept
python3 research/paper/h1/package/h1_paper.py incident --lane-dir <LANE> --type COHORT_TERMINAL --detail '<reason>'
sha256sum <LANE>/tradesv3.sqlite <LANE>/logs/* <LANE>/evidence/*                   # digests go into COHORT_TERMINAL
cp -a <LANE> <primary evidence store>/ && cp -a <LANE> <SECOND_EVIDENCE_STORE>/   # then verify both copies' sha256
```

- **SAFETY_BREACH.** This covers `dry_run ≠ true`, a credential found, or a P2 path written. Stop immediately and
  record the breach. No restart under this cohort.
- **Open positions.** No position is force-closed (§5.1). An open position is valued at the last close for reporting
  only.

## 9. Closure and review schedule

| When | What |
|---|---|
| T0 | `COHORT_START` (PAPER_T0). The freeze law binds |
| T0 + 1 h, + 24 h | first-candle check and first-day check (coverage, ledger `verify()`, isolation from P2) |
| weekly | `RECONCILIATION` incident; a status line to the Owner, with no performance claim |
| ACTIVATION_UTC + 30 d = END_UTC (H1-WINDOW-AMENDMENT-1) | stop the worker, write `COHORT_TERMINAL`, copy and verify both evidence copies |
| after END_UTC | fetch the window's public candles, run the B1 replay and the §4 benchmarks, and classify PROSPECTIVE_BEHAVIOR (B1, B3, B4, B5; B2 reported only) and OPERATIONAL_CAPABILITY (§5). EDGE_EVIDENCE = NOT_EVALUATED |

There is no early stop for performance, no extension and no automatic transition (§5.1, §10).
