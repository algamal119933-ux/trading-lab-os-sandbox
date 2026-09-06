# CLOUD-0 — closure record

**Stage:** `CLOUD-0 — REPOSITORY READINESS & REPRODUCIBLE RESEARCH HARNESS`
**Branch:** `claude/cloud-0-stage-3zbf73`
**Environment:** cloud sandbox — no access to the owner's Windows host, WSL,
Docker Desktop, `.env`, local datasets or databases.

## Gate results

| Gate | Result | Evidence |
| --- | --- | --- |
| C0.1 Repository truth | **PASS** | [`C0.1_REPOSITORY_STATE.md`](C0.1_REPOSITORY_STATE.md) — 37 files inventoried, 13 findings |
| C0.2 Secret and artifact hygiene | **PASS** | [`C0.2_ARTIFACT_CLASSIFICATION.md`](C0.2_ARTIFACT_CLASSIFICATION.md), `scripts/verify_repo.py`, `tests/test_repo_hygiene.py` |
| C0.3 Paper-safety invariant | **PASS** | `scripts/paper_guard.py`, `tests/test_paper_guard.py` (49 tests) |
| C0.4 Configuration isolation | **PASS** | [`C0.4_CONFIG_PRECEDENCE.md`](C0.4_CONFIG_PRECEDENCE.md), `scripts/effective_config.py`, `tests/test_config_isolation.py` |
| C0.5 CI | **PASS** | `.github/workflows/ci.yml` — three jobs, green (see "CI evidence") |
| C0.6 Research evidence schema | **PASS** | `research/schema/experiment_record.schema.json`, `research/record_experiment.py`, `tests/test_experiment_record.py` |
| C0.7 Data-reproduction plan | **PASS** | [`C0.7_DATA_REPRODUCTION_PLAN.md`](C0.7_DATA_REPRODUCTION_PLAN.md), `scripts/audit_data.py`, `research/datasets/dataset_v1.lock.json`, `tests/test_data_audit.py` |

## What is now enforced, not merely asserted

* **Paper safety fails closed.** `dry_run` must be exactly `true`;
  `trading_mode` must be explicitly `"spot"`; margin mode must be empty;
  leverage, shorting, forced entries, withdrawal keys, exchange and ccxt
  credentials, derivative/leveraged-token pairs and enabled telegram are all
  rejected. `max_open_trades` must be an integer in [1, 3], `dry_run_wallet` in
  (0, 1000], and `stake_amount` a positive number no larger than the wallet.
  Strategy files are scanned for `can_short`, leverage and non-spot modes.
  Every one of these has a test that mutates the shipped config and asserts
  rejection.
* **Config cannot silently override the strategy.** ROI, stoploss, timeframe and
  the trailing-stop family are rejected in the config, and `backtest.sh` no
  longer passes a timeframe.
* **The effective config is inspectable without secrets**, and its hash is
  stable across credential rotation.
* **The repository cannot drift.** Secrets, forbidden artifacts, JSON/YAML
  validity and `MANIFEST.txt` freshness are all checked on every push.
* **A result can be traced.** Any gate decision needs a record carrying the
  code commit, config hash, dataset fingerprints, strategy hash, engine version,
  window, costs and reason.
* **A dataset cannot move underneath an experiment.** `download_data.sh` refuses
  to re-download over a frozen dataset, and `audit_data.py --lock` fails on any
  fingerprint drift.
* **The locked OOS has three independent refusals**, in the benchmark script,
  the record tooling and the dataset lock.

## What is explicitly NOT proven

Stated plainly, because CLAUDE.md forbids claiming a runtime result that did not
happen in a verifiable environment.

* **No Freqtrade backtest, dry-run, lookahead or recursive analysis was executed
  in this stage.** None was authorised by CLOUD-0, and none was run.
* **No dataset was re-audited against real market data.** The fingerprints in
  `dataset_v1.lock.json` are the owner's historical local-runtime evidence,
  carried forward and labelled as such. `scripts/audit_data.py` is proven
  against synthetic data only; the first real re-audit must happen on a host
  that has the feather files.
* **The full five-service stack has never been started here.** Container image
  pulls are blocked by this sandbox's egress policy
  (`production.cloudfront.docker.com` and `pkg-containers.githubusercontent.com`
  return 403). CI does the container work instead; end-to-end health, Prometheus
  scraping, Grafana rendering and MLflow logging remain on the owner's Docker
  host, as checklist section C.
* **The `PlumbingSmokeStrategy` numbers quoted anywhere in this repository are
  historical**, and the strategy remains an infrastructure smoke test that must
  not be optimised.

## Boundaries respected

No action in this stage set `dry_run=false`, added or requested an exchange
credential, placed an order, enabled withdrawals, leverage, margin, futures or
shorts, committed a secret, weakened the paper guard, bypassed a failed gate, or
opened the locked OOS. `OWNER_AUTHORIZATION_REQUIRED` was not reached.

## Note on the branch name

`CLAUDE.md` prefers `claude/cloud-0-repo-readiness`. This session was directed
to `claude/cloud-0-stage-3zbf73`, and pushing anywhere else is not authorised, so
the session directive was followed. No other divergence from CLAUDE.md.

## Recommended next stage

`BASELINE-1 — SIMPLE DETERMINISTIC ACTIVE BENCHMARK`: 1h, spot, long-only,
EMA50/EMA200 regime logic, no hyperopt, no AI, no auxiliary filters, transparent
exits, conservative emergency stoploss only.

Two things should happen before or alongside it, and both need the owner's
Docker host:

1. Re-run `scripts/audit_data.py --lock research/datasets/dataset_v1.lock.json`
   against the real feather files, to convert the historical
   `DATA_INTEGRITY_GATE = PASS` into a current one.
2. Work through checklist section C once, recording the outcome as a schema-valid
   experiment record.

Judge BASELINE-1 against the **exposure-matched passive line (−7.83 %)**, not
buy-and-hold: the development window is strongly bearish, and reduced exposure
alone is not alpha.
