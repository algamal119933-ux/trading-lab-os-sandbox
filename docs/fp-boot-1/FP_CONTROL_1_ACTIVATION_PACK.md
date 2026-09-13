# FP-CONTROL-1 — activation pack

> **SUPERSEDED — DO NOT RUN THE COMMANDS IN THIS PACK.**
> The cohort this pack activates, `FP-CONTROL-1-20260908T121513Z`, is **CLOSED**
> ([`FP_CONTROL_1_COHORT_CLOSURE.md`](FP_CONTROL_1_COHORT_CLOSURE.md)). Section
> A14 below selects the FP-CONTROL-1 row by name and writes `t0_utc`,
> `cohort_id`, `status` and `source_commit` into it — run today it would rewrite
> a closed cohort's history. A11's launcher invocation is also stale: the
> launcher now requires an explicit role and refuses a closed one.
> The pack is kept unedited as the record of how the closed cohort was
> activated. For the current host, the runnable instance and the fail-closed
> selection that guards it, see
> [`FP_PRE_T0_SUCCESSOR_CONTROL.md`](FP_PRE_T0_SUCCESSOR_CONTROL.md).
> Freezing a **new** T0 remains an Owner-only act and has no script here.

**Status:** `PROJECT_STATE = PRE_T0_READY`, `FP_RUNTIME_STATE = DEFERRED_BY_OWNER`
**Authoritative commit:** `ab39a7622bb3567aca493560afd34556d080cfc8` (`main`)
**Purpose:** the exact commands and pass evidence to activate FP-CONTROL-1 later, on an
authoritative persistent Linux/Docker host. Nothing here has been executed.

Every value below is bound by Repo Truth at the authoritative commit. Where a
value is genuinely unbound it is marked `MUST BE BOUND ONCE BEFORE T0` rather
than guessed.

---

## 0. What this activates, and what it does not

```text
FP-CONTROL-1 = BASELINE-1 as operational control, State C, control-only
NOT a candidate. NOT a survivor. NOT candidate-quality evidence.
Candidate-scoped admission conditions 1-6 must NOT be forced to PASS with it.

Proves: PAPER_TRADING_OPERATIONAL_CAPABILITY
Does not prove: PROSPECTIVE_EDGE
```

## 0.1 One known gap — read before starting

The scaffold provides the admission gate, the preflight gate, the append-only
ledgers, event-time replay and the paper Freqtrade stack. It does **not** yet
provide the process that binds a running Freqtrade dry-run to
`paper_input_ledger` and `paper_decision_ledger` — the as-seen capture loop.

`scripts/start_paper.sh` starts the paper stack; it does not write the FP
evidence lane. That capture loop is the **first build item on the host**, and it
is named here rather than glossed: without it, steps 17, 19-25 below cannot
produce their evidence, and preflight checks 8, 9, 12, 15 and 16 stay `UNPROVEN`
against a real runtime.

No work on it was performed under the park directive.

---

# A. COMMANDS TO RUN ON THE AUTHORITATIVE HOST

### A1 — runtime prerequisites

```bash
uname -a                          # expect Linux
docker --version                  # expect Docker Engine present
docker compose version            # expect Compose v2
docker info                       # expect a running daemon, no error
python3 --version                 # expect 3.12.x
df -h .                           # expect >= 20 GB free for data + images
timedatectl status                # expect NTP synchronised (clock skew is a P1 condition)
```

### A2 — clone, fetch, check out the exact authoritative commit

This pack is **not on `main`**. It lives on `claude/new-session-pvkkbj`, which
contains the authoritative commit `ab39a762…` as an ancestor. Checking out
`ab39a762…` directly would give you a tree without this file, so check out the
branch and then prove the authoritative commit is in its history.

```bash
git clone https://github.com/algamal119933-ux/trading-lab-os-sandbox.git
cd trading-lab-os-sandbox
git fetch origin main claude/new-session-pvkkbj
git checkout claude/new-session-pvkkbj
```

If the Owner merges this pack to `main` first, check out `main` at its merge
commit instead; the ancestry proof in A3 is unchanged either way.

### A3 — verify authoritative main and a clean worktree

```bash
git rev-parse HEAD                 # the branch head carrying this pack

# The authoritative commit must be an ancestor of BOTH your checkout and main.
git merge-base --is-ancestor ab39a7622bb3567aca493560afd34556d080cfc8 HEAD && echo PACK_TREE_OK
git merge-base --is-ancestor ab39a7622bb3567aca493560afd34556d080cfc8 origin/main && echo AUTHORITATIVE_OK
git merge-base --is-ancestor 1dfb69604bb87856b75c8c90957f2acc8e1fab7f origin/main && echo BASELINE_1_ANCESTOR_OK
git merge-base --is-ancestor af788f5b49b33be10c29b926b10a634a123db812 origin/main && echo AMENDMENT_ANCESTOR_OK

git status --porcelain            # expect NO output
python3 scripts/verify_repo.py    # expect REPO_CHECK_PASS
```

### A4 — dependencies and the repository's own checks

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pip install "pandas==2.2.3" "pyarrow==18.1.0"
python3 -m pytest                 # expect 443 passed, 16 skipped (0 failed)
```

### A5 — paper-only authority, before anything starts

```bash
cp freqtrade/user_data/config.paper.json.example freqtrade/user_data/config.json
python3 scripts/paper_guard.py --config freqtrade/user_data/config.json
python3 scripts/effective_config.py --hash-only
cp .env.example .env
# Replace every CHANGE_ME_* with a local password. start_paper.sh refuses to
# start while any CHANGE_ME remains. No exchange credential is set, ever.
grep -c CHANGE_ME .env            # expect 0
```

### A6 — Binance public market route probe (public data only)

```bash
curl -sS -o /dev/null -w 'api.binance.com %{http_code}\n' \
  "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=1"
curl -sS -o /dev/null -w 'data-api.binance.vision %{http_code}\n' \
  "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=1"
curl -sS -o /dev/null -w 'data.binance.vision %{http_code}\n' \
  "https://data.binance.vision/?prefix=data/spot/monthly/klines/BTCUSDT/1h/"
```

### A7 — real candle receipt, with both timestamps captured

```bash
python3 - <<'PY'
import json, time, urllib.request
url = "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=2"
received_ms = int(time.time() * 1000)
rows = json.load(urllib.request.urlopen(url, timeout=20))
closed = rows[0]                       # rows[-1] is the still-forming candle
print("pair/timeframe        BTC/USDT 1h")
print("open_time_ms         ", closed[0])
print("close_time_ms        ", closed[6])
print("source_timestamp_utc ", time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(closed[6]/1000)))
print("receive_timestamp_utc", time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(received_ms/1000)))
print("candle_is_closed     ", closed[6] < received_ms)
print("no_future_data       ", rows[-1][6] > received_ms)   # the forming candle has not closed
PY
```

### A8 — the frozen dataset, unchanged, and warm-up outside the canonical cache

```bash
mkdir -p dataset-cache/binance
python3 scripts/fetch_binance_public_data.py \
  --symbol BTCUSDT --symbol ETHUSDT --timeframe 1h --timeframe 5m \
  --start 2020-12-01 --end 2026-08-31 \
  --out-dir dataset-cache/binance --manifest artifacts/acquisition_dataset_v2.json

rm -rf freqtrade/user_data/data/binance
mkdir -p freqtrade/user_data/data/binance
cp dataset-cache/binance/*.feather freqtrade/user_data/data/binance/

python3 scripts/audit_data.py \
  --data-dir freqtrade/user_data/data/binance \
  --pair BTC/USDT --pair ETH/USDT --timeframe 1h --timeframe 5m \
  --lock research/datasets/dataset_v2.lock.json --gate lock
```

The canonical cache `dataset-cache/` is written once and never mutated
afterwards. The working copy under `freqtrade/user_data/data/` is what any
overlay join writes into. Reversing that poisons the next run, and the
canonical-identity gate will refuse it.

### A9 — pre-T0 warm-up (BASELINE-1 needs no overlay)

BASELINE-1 declares `startup_candle_count = 600` (3 x `EMA_SLOW_PERIOD` 200) and
Dataset V2's own pre-Development month supplies 744 hourly candles, so the
warm-up overlay **does not apply to FP-CONTROL-1** — `warmup_overlay.lock.json`
says so under `does_not_apply_to`. Do not join it.

```bash
python3 - <<'PY'
import json, pathlib
lock = json.loads(pathlib.Path("research/datasets/warmup_overlay.lock.json").read_text())
print("does_not_apply_to:", json.dumps(lock["does_not_apply_to"], indent=1))
PY
```

Warm-up boundary, to be enforced by the capture loop of §0.1:

```text
PRE_T0  = indicator/state initialisation only; contributes no PnL and no outcome claim
T0      = prospective evidence boundary, frozen once
POST_T0 = the only measurable forward-paper evidence
```

### A10 — control configuration freeze (all values bound by Repo Truth)

```text
authoritative_commit    ab39a7622bb3567aca493560afd34556d080cfc8
strategy                BaselineEmaRegimeV1
strategy_sha256         8c0bc6c5f705fbeabf5d6ce37e651309d8ee3fefb81fdd59490fefab22b021bc
config_example_sha256   d1d078c63adc5e4283632a1c3e65df8cd0d7c23a249575054491c6356d97a9ff
engine                  freqtradeorg/freqtrade:2026.7
pair_universe           BTC/USDT, ETH/USDT
timeframe               1h
startup_candle_count    600  (3 x EMA_SLOW_PERIOD 200)
indicators              EMA50 / EMA200 regime, long-only
stoploss                -0.25   (emergency backstop, untuned)
minimal_roi             {"0": 10.0}  (non-binding by design)
paper_wallet            100 USDT      (dry_run_wallet)
stake_amount            10 USDT fixed
max_open_trades         2
fee                     0.001 per side
slippage                none modelled
trading_mode            spot;  margin_mode empty;  can_short False
dry_run                 true
data_source             Binance spot public market data; no credential
data_contract           research/datasets/dataset_v2.lock.json (frozen, 4 canonical digests)
```

```bash
python3 - <<'PY'
import hashlib, pathlib
for p in ("freqtrade/user_data/strategies/BaselineEmaRegimeV1.py",
          "freqtrade/user_data/config.paper.json.example"):
    print(hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest(), p)
PY
```

`MUST BE BOUND ONCE BEFORE T0` — genuinely unbound in Repo Truth today:

```text
PAPER_FILL_MODEL_VERSION   unset; Freqtrade dry-run fill semantics must be
                           recorded as simulation semantics, not live-fill truth
bot_name / db_path / log_path / evidence_dir   per-instance, must be distinct
risk limits beyond stoploss and max_open_trades   none declared
```

### A11 — start the paper runtime

```bash
python3 scripts/paper_guard.py --config freqtrade/user_data/config.json
bash scripts/start_paper.sh
docker compose ps                 # expect freqtrade, exporter, prometheus, grafana up
docker compose logs -f freqtrade  # expect dry_run startup, no order route
```

### A12 — persistence, reopen, restart, duplicate-decision negative control

```bash
python3 -m pytest tests/test_fp_ledger.py tests/test_fp_replay.py -q
python3 research/fp/preflight.py --json > artifacts/fp_preflight.json
python3 research/fp/preflight.py            # human-readable

bash scripts/stop.sh
bash scripts/start_paper.sh                 # restart with persisted state
docker compose logs freqtrade | tail -40    # expect state reopened, no duplicate entry
```

### A13 — control-only admission and preflight

```bash
python3 research/fp/admission.py entry-state       # expect: C
python3 research/fp/admission.py evaluate -o artifacts/fp_admission.json
python3 research/fp/preflight.py --require-pass    # exit 0 required before T0
```

### A14 — freeze T0 and COHORT_ID, then activate

Only after A13 exits 0 and every item in section B passes.

```bash
python3 - <<'PY'
import json, pathlib, subprocess
from datetime import datetime, timezone
reg = pathlib.Path("research/fp/records/forward_paper_cohort_registry.json")
r = json.loads(reg.read_text())
t0 = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
commit = subprocess.check_output(["git","rev-parse","HEAD"], text=True).strip()
inst = next(i for i in r["instances"] if i["role"] == "FP-CONTROL-1")
inst["t0_utc"] = t0
inst["cohort_id"] = f"FP-CONTROL-1-{t0.replace(':','').replace('-','')}"
inst["status"] = "RUNNING"
inst["runtime_identity"]["source_commit"] = commit
r["fp_run_active"] = True
r["registry_updated_utc"] = t0
reg.write_text(json.dumps(r, indent=2) + "\n")
print("FP_T0 =", t0); print("COHORT_ID =", inst["cohort_id"])
PY
python3 scripts/verify_repo.py --fix && git add -A && git commit -m "FP-CONTROL-1: freeze T0 and cohort"
```

### A15 — status, logs, safe restart, closure

```bash
docker compose ps
docker compose logs --since 1h freqtrade
python3 research/fp/preflight.py --json | python3 -m json.tool | head -40

# safe restart
bash scripts/stop.sh && bash scripts/start_paper.sh
python3 -m pytest tests/test_fp_ledger.py -q     # chain must still verify

# closure evidence at the end of the ~48h window
python3 research/fp/admission.py evaluate -o artifacts/fp_control_closure_admission.json
python3 research/fp/preflight.py --json > artifacts/fp_control_closure_preflight.json
```

---

# B. EXPECTED PASS EVIDENCE

| # | Check | Expected |
| --- | --- | --- |
| 1 | authoritative commit | `PACK_TREE_OK` and `AUTHORITATIVE_OK` both printed |
| 2 | ancestry | three `_OK` lines from A3 |
| 3 | worktree | `git status --porcelain` empty; `REPO_CHECK_PASS` |
| 4 | tests | `443 passed, 16 skipped` |
| 5 | paper guard | `PAPER_GUARD_PASS` on the runtime config |
| 6 | `.env` | `grep -c CHANGE_ME` = `0` |
| 7 | market route | at least one Binance host returns `200` |
| 8 | real candle | `candle_is_closed True`, `no_future_data True` |
| 9 | timestamps | both source and receive timestamps printed, source < receive |
| 10 | pair/timeframe | `BTC/USDT 1h` |
| 11 | data integrity | `DATASET_LOCK_GATE = PASS (content matches the frozen lock)` |
| 12 | warm-up | overlay confirmed **not** applicable to BASELINE-1 |
| 13 | stack | `docker compose ps` shows the services up, `dry_run` in the logs |
| 14 | ledger + replay tests | pass |
| 15 | restart | no duplicate decision, chain still verifies |
| 16 | entry state | `C` |
| 17 | preflight | `--require-pass` exits `0` |
| 18 | paper-only | no order route, no credential, `dry_run=true` throughout |

`PAPER_TRADING_OPERATIONAL_CAPABILITY = PROVEN` requires all of:
real market input, event-time/timestamp knowability, paper-only authority,
decision logging, risk/admission, paper order/fill, position state, persistence,
restart recovery, no duplicate execution, ledger reconciliation, data integrity.

48-hour window rule: **no artificial trade may be generated to make the test
pass.** If the frozen BASELINE-1 produces no naturally-triggered closed trade,
report `FULL_TRADE_LIFECYCLE = NOT_YET_OBSERVED` and do not change the strategy,
lower a threshold, or force an entry.

---

# C. STOP CONDITIONS

Stop immediately, do not freeze T0, and report, if any of these hold:

```text
S1   ab39a7622bb3567aca493560afd34556d080cfc8 is not an ancestor of your checkout, or not an ancestor of origin/main
S2   git status --porcelain is non-empty at A3
S3   verify_repo.py does not print REPO_CHECK_PASS
S4   any test fails
S5   paper_guard.py rejects the runtime config
S6   .env still contains any CHANGE_ME
S7   any exchange key, secret, wallet or withdrawal credential is present anywhere
S8   every Binance host fails the A6 probe
S9   the A7 candle is not closed, or future data is available at decision time
S10  DATASET_LOCK_GATE != PASS, or any canonical digest moved
S11  the canonical dataset cache was written to after acquisition
S12  preflight --require-pass exits non-zero
S13  entry-state is not C
S14  admission reports ADMITTED for a candidate (there is none; State C only)
S15  a restart produces a duplicate decision, or the ledger chain fails to verify
S16  clock skew beyond one candle period (1h), or NTP not synchronised
S17  the runtime cannot remain persistent
S18  any live order route, real-money path or trading credential appears
S19  the capture loop of §0.1 does not exist, so the evidence lane cannot be written
```

`S19` is expected on a first run: build the capture loop first, then restart at A1.

---

## Security boundary — unchanged and non-negotiable

```text
NO Binance trading API key      NO private key         NO wallet
NO withdrawal credentials       NO live order route    NO real-money execution

public market data only         paper / dry-run execution only
REAL_MONEY_AUTHORIZED = NO
```

---

## Resume order

```text
AUTHORITATIVE_HOST_READY
→ REAL_MARKET_ROUTE
→ REAL_EXCHANGE_CANDLE
→ PRE-T0 ADMISSION
→ FREEZE FP_T0
→ FREEZE COHORT_ID
→ ACTIVATE FP-CONTROL-1
```

Do not reopen retrospective planning at that point.
