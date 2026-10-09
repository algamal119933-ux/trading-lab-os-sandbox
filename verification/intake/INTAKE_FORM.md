# Intake form: Freqtrade Strategy Verification

Intake and triage are free. Fill in `intake.schema.json` (an example is in `example_intake.json`) and send it.
`triage.py` answers ACCEPT, NEEDS_INFO or OUT_OF_SCOPE, with the reason for each.

> **Never send an API key, secret, password or any exchange credential.** We never need one. Verification
> runs in dry-run only and never connects to your exchange account. A submission that contains a key is
> refused; delete and rotate that key.

## What we need

| Field | What to give |
|---|---|
| `case_id` | Leave it to us. We assign an opaque id like `C-001`. |
| `strategy.source` | A public repository URL with the full 40-character commit, or an archive with its sha256. |
| `strategy.strategy_class` | The strategy class name Freqtrade loads. |
| `strategy.strategy_sha256` | sha256 of the strategy `.py` file. |
| `strategy.params_sha256` | sha256 of the parameter JSON Freqtrade auto-loads next to it. If there is none, `null` and `params_file_absent: true`. |
| `config` | sha256 of your config **with every key and secret removed**, plus trading mode, margin mode, `can_short`, leverage and `dry_run`. |
| `engine.freqtrade_version` | The Freqtrade version you ran, e.g. `2026.7`. |
| `market` | Pairs, timeframe and the timerange the claim covers. |
| `claim` | The performance you want checked, in your words, and where it was published. Optional. |
| `rights` | The licence (SPDX id), or confirm that you hold the rights to the code. |

## What is in scope

Spot, long only, no leverage, dry-run. Futures, margin, shorts and leverage are out of scope.

## What you receive

A report like `verification/sample/SAMPLE_REPORT.md`: a verdict, the pinned identity, your claim, an independent
measurement, a fair exposure-matched comparison, validity gates and the report's own limits.

## What we keep

Your code and data are never committed to this repository and never published. The repository holds only
the form, the rubric and anonymous case ids.
