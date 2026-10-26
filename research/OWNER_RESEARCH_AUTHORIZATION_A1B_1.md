# OWNER RESEARCH AUTHORIZATION A1B-1: A1b pre-registration and historical-data preparation

**Granted by:** the Owner, and by no one else. This record grants authority **only when the Owner merges it**. Until then
it grants nothing. The PR was prepared at the Owner's directive "PARALLEL PREPARATION" (2026-10-26, priority 3); preparing
it is not the grant.

**Relation to other authority:** this is **Lane B research**, not P3.
- It is outside the scope of [`docs/p3/OWNER_P3_EXECUTION_AUTHORIZATION.md`](../docs/p3/OWNER_P3_EXECUTION_AUTHORIZATION.md).
- It amends neither the frozen P3 contract nor any P3 workstream.
- It does not touch the P3 runtime, timers, backups or evidence.

It sits beside [`OFFLINE_RESEARCH_AUTHORITY_1.md`](OFFLINE_RESEARCH_AUTHORITY_1.md) and amends none of its clauses. Under
CEA-1 §12, research **execution** runs only through an Owner-merged program charter. This record does not create one, and
it does not replace one.

PAPER / RESEARCH ONLY.

---

## The authorization

```text
AUTHORIZED_SCOPE = A1b pre-registration (research/a1b/, branch claude/research-a1b-preregistration) and historical-data preparation for its frozen plan: the Dataset V3 holdout extension lock (2026-09-01T00:00:00Z to 2027-01-01T00:00:00Z, built only after 2027-01-01T00:00:00Z) and one recorded Binance exchangeInfo snapshot for min_notional_usdt
EVALUATION_EXECUTION = NOT AUTHORIZED BY THIS RECORD; offline evaluation runs only under an Owner-merged program charter charters/programs/A1B-QUALIFICATION-1.json binding the frozen a1b_prereg.json sha256 (CEA-1 section 12)
EXECUTION_LIMITS = offline and historical only; separate runner by default (OFFLINE_RESEARCH_AUTHORITY_1 section 3); no paper worker; no live trading; no exchange trading credentials; no hyperopt or variant beyond the four declared V1-V4; no locked-holdout opening before gates E0-E10 of the frozen plan pass
TRIALS_COUNTED = YES; one scientific trial TRIAL-A1B-1 (4 configurations) appended PREREGISTERED to research/records/trial_ledger.jsonl in the charter PR, before any result; DSR N >= 39
GOVERNING_LAW = PROFITABILITY-VERIFICATION-LAW-1 (research/PROFITABILITY_VERIFICATION_LAW_1.md, PR #82, with Owner decisions OD-1..OD-3) governs every A1b gate and verdict; A1b is a new research program, so PBO <= 0.05 (CSCV, 16 blocks) is a hard gate (law section 4.1); Level A or B never grants live or scaling authority (law section 9)
DATASET = Dataset V3 (research/datasets/dataset_v3.lock.json, data.binance.vision, every zip verified against its .CHECKSUM) plus the holdout extension lock built by the same route
REAL_MONEY_AUTHORIZED = NO
H1_LAUNCH_AUTHORIZED = NO
PAPER_LAUNCH_AUTHORIZED = NO
P3_RELATION = outside P3 scope; parallel Lane B; does not read, write, start or stop any P3 runtime, timer, backup set or evidence path
EXPIRES_UTC = 2027-01-31T23:59:59Z
```

Each field appears exactly once. A file that says two things about one field is not an authorization but an ambiguity.

`EXPIRES_UTC` was proposed by the preparer to match the P3 authorization. **The value is the Owner's choice.** The Owner
edits it before merging if another date is wanted.

## What this record does not do

- It does not authorize running any backtest, replay or engine invocation for A1b. That needs the charter.
- It does not admit A1b, A1 or any candidate to paper. A `PREPAPER_CANDIDATE` outcome only makes V1 eligible to be
  **proposed** to a separate Owner paper-admission decision.
- It does not open the locked holdout early, and it does not change any frozen dataset, strategy, risk setting, threshold,
  P2 record or P3 record.
- It does not count as evidence of profitability. Historical windows are exploratory. Only prospective evidence judged
  under the verification law (`research/PROFITABILITY_VERIFICATION_LAW_1.md`, PR #82) can support such a claim, and
  even then no live or scaling authority follows automatically.

## Order of merges

1. The verification law, PR #82 (`claude/research-verification-law-1`). It fixes the PBO gate this record cites.
2. **This record, PR #83 (Owner).**
3. The A1b pre-registration, PR #84 (`claude/research-a1b-preregistration`). It binds only after this record.
4. Only then, the A1b program charter with the `TRIAL-A1B-1` ledger record (Owner).

Evaluation may not start before all three are on `main` and the charter is merged.
