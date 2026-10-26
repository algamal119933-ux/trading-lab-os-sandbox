"""P3-PLN-10 Paper Beta Acceptance Program: the acceptance matrix, the evidence schema and its validators.

P3_CONTRACT.md §3 PLN-10. The acceptance requires every PLN-02..PLN-09 acceptance to hold in ONE continuous
Paper Beta run, and the P&L measurement to reconcile to fills and fees. This module does not run anything: it
validates evidence records that the run produces. It is developed and tested against synthetic evidence only.

Fail-closed: a criterion without PASS evidence from the same run is NOT met. UNPROVEN is not PASS. A missing,
malformed or contradictory record never counts. Nothing here can mark PLN-10 accepted on its own; the verdict
it computes is an input to the Owner's acceptance record.

The P&L reconciliation is MEASUREMENT ONLY (Priority 1 in the contract): it checks that reported net results
equal fills minus fees. It says nothing about profitability.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

RECORD_TYPE = "P3_PLN10_EVIDENCE_V1"
PASS, FAIL, UNPROVEN = "PASS", "FAIL", "UNPROVEN"
STATUSES = (PASS, FAIL, UNPROVEN)

# --- the acceptance matrix: every PLN-02..PLN-09 criterion → scenario, evidence, validator ------------------
# Criterion texts follow P3_CONTRACT.md §3 (frozen at fcd06b21). One contract cell may hold several criteria.
ACCEPTANCE_MATRIX: dict[str, dict[str, str]] = {
    "PLN-02.inventory_complete": {
        "ws": "PLN-02", "criterion": "the inventory lists 100% of tracked and untracked TLOS state",
        "scenario": "S-INV: state inventory at run start and run end",
        "evidence": "scripts/p3/state_inventory.py JSON: COVERAGE PASS, 0 unclassified, 0 unreadable",
        "validator": "status_pass"},
    "PLN-02.recovery_sources": {
        "ws": "PLN-02", "criterion": "each item has a verified recovery source",
        "scenario": "S-INV: recheck against the newest scheduled backup set",
        "evidence": "state inventory RECOVERY PASS on every declared root", "validator": "status_pass"},
    "PLN-03.restore_drill": {
        "ws": "PLN-03", "criterion": "restore drill passes: manifest sha256 equal, git fsck clean, ARCHIVE_VERIFIED, "
                                     "restored runtime starts in dry-run",
        "scenario": "S-RESTORE: drill from a set taken during the run, into an empty scratch",
        "evidence": "scripts/p3/backup.py drill --json: every check PASS", "validator": "status_pass"},
    "PLN-03.repeated_after_change": {
        "ws": "PLN-03", "criterion": "the drill is repeated after a change",
        "scenario": "S-RESTORE-2: second drill after any code/config change merged during the run",
        "evidence": "second drill JSON, newer set than the first", "validator": "status_pass"},
    "PLN-04.reboot_correct": {
        "ws": "PLN-04", "criterion": "after a reboot, the stack's state is correct",
        "scenario": "S-REBOOT: planned clean reboot during the run (runbook PLN_04_REBOOT_ACCEPTANCE_RUNBOOK.md)",
        "evidence": "verify-boot JSON PASS + clean-shutdown journal lines + health exit 0",
        "validator": "status_pass"},
    "PLN-04.terminal_never_restarted": {
        "ws": "PLN-04", "criterion": "a terminal or Owner-stopped cohort is never auto-restarted (negative test)",
        "scenario": "S-RESTART: kill-switch stop, then reboot; the stopped runtime must stay stopped",
        "evidence": "restart_continuity record: stopped runtime stayed stopped; may-restart = NO",
        "validator": "restart_continuity"},
    "PLN-04.host_recovery_drill": {
        "ws": "PLN-04", "criterion": "a host-recovery drill from backup passes",
        "scenario": "S-RESTORE (shared with PLN-03)", "evidence": "drill JSON PASS", "validator": "status_pass"},
    "PLN-05.host_loss_redundancy": {
        "ws": "PLN-05", "criterion": "HOST_LOSS_REDUNDANCY = PROVEN by restoring from the independent host",
        "scenario": "S-TIER3: push + restore drill from the independent host (PLN_05_TIER3_PROCEDURE.md)",
        "evidence": "offsite push JSON destination_verify PASS + remote-restore drill JSON PASS",
        "validator": "status_pass"},
    "PLN-05.attributable_stop_start": {
        "ws": "PLN-05", "criterion": "every governed stop/start has an attributable record",
        "scenario": "S-KILL and every start during the run",
        "evidence": "operator ledger: chain verifies; one record per stop/start with operator and reason",
        "validator": "status_pass"},
    "PLN-06.s19_alerts": {
        "ws": "PLN-06", "criterion": "each §19 CRITICAL condition raises an alert in a test",
        "scenario": "S-ALERT: promtool rule tests + one delivered test alert on the chosen channel",
        "evidence": "promtool test rules SUCCESS + delivered-alert record (time, channel, alert name)",
        "validator": "status_pass"},
    "PLN-06.capacity_enforced": {
        "ws": "PLN-06", "criterion": "capacity thresholds are enforced",
        "scenario": "S-ALERT: health findings free_space:root / free_space:h1_lane at run start and end",
        "evidence": "health JSON with the thresholds applied", "validator": "status_pass"},
    "PLN-06.normal_end_detected": {
        "ws": "PLN-06", "criterion": "normal end is detected on lifecycle completion",
        "scenario": "S-END: the run's cohort completes its lifecycle",
        "evidence": "health finding normal_end WARNING 'governed stop due' raised at completion",
        "validator": "status_pass"},
    "PLN-07.matrix_rows": {
        "ws": "PLN-07", "criterion": "every failure/recovery matrix row has a passing test",
        "scenario": "S-CI: full suite at the run's frozen commit", "evidence": "CI run id + pytest exit 0",
        "validator": "status_pass"},
    "PLN-07.f2_finding": {
        "ws": "PLN-07", "criterion": "F-2 has a reconcile finding with negative controls",
        "scenario": "S-AUDIT: execution audit over the run's fills", "evidence": "execution_audit JSON",
        "validator": "status_pass"},
    "PLN-07.data_truth": {
        "ws": "PLN-07", "criterion": "the data-truth checks pass",
        "scenario": "S-AUDIT: missing/duplicate candles recorded, never filled (§13)",
        "evidence": "data-truth report over the run's input ledger", "validator": "status_pass"},
    "PLN-08.kill_bounded": {
        "ws": "PLN-08", "criterion": "the kill switch stops everything within a bounded time and leaves an "
                                     "attributable record",
        "scenario": "S-KILL: engage the kill switch on the run's paper runtime",
        "evidence": "P3_KILL_SWITCH_V1 ledger record", "validator": "kill_switch_bounded"},
    "PLN-08.no_live_route": {
        "ws": "PLN-08", "criterion": "no control can set dry_run=false or reach a live route (guard test)",
        "scenario": "S-CI + S-ALERT: paper guard and real_money health findings throughout the run",
        "evidence": "paper_guard PASS + real_money INFO in every health run", "validator": "status_pass"},
    "PLN-09.projection": {
        "ws": "PLN-09", "criterion": "a Control Room projection over canonical evidence, Arabic/English, realising "
                                     "the frozen shape; the UI is never evidence authority",
        "scenario": "S-UI: Owner acceptance checklist on the host",
        "evidence": "signed Owner acceptance checklist (PLN-09)", "validator": "status_pass"},
    "PLN-10.pnl_reconciles": {
        "ws": "PLN-10", "criterion": "P&L measurement reconciles to fills and fees (measurement only)",
        "scenario": "S-PNL: every closed trade of the run", "evidence": "fills + fees + reported P&L records",
        "validator": "reconcile_pnl"},
}
REQUIRED_WORKSTREAMS = ("PLN-02", "PLN-03", "PLN-04", "PLN-05", "PLN-06", "PLN-07", "PLN-08", "PLN-09")
VALIDATORS = ("status_pass", "restart_continuity", "kill_switch_bounded", "reconcile_pnl")

# --- the evidence schema ------------------------------------------------------------------------------------
EVIDENCE_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": RECORD_TYPE,
    "type": "object",
    "additionalProperties": False,
    "required": ["record_type", "run_id", "criterion_id", "scenario", "utc", "status", "artifacts",
                 "real_money_authorized"],
    "properties": {
        "record_type": {"const": RECORD_TYPE},
        "run_id": {"type": "string", "minLength": 1},
        "criterion_id": {"type": "string", "enum": sorted(ACCEPTANCE_MATRIX)},
        "scenario": {"type": "string", "minLength": 1},
        "utc": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"},
        "status": {"enum": list(STATUSES)},
        "artifacts": {"type": "array", "minItems": 1, "items": {
            "type": "object", "additionalProperties": False, "required": ["path", "sha256"],
            "properties": {"path": {"type": "string", "minLength": 1},
                           "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}}},
        "detail": {"type": "string"},
        "real_money_authorized": {"const": False},
    },
}


def validate_evidence(record: dict) -> list[str]:
    """Schema errors for one evidence record ([] when valid)."""
    import jsonschema  # noqa: PLC0415 - pinned in requirements-dev.txt

    validator = jsonschema.Draft202012Validator(EVIDENCE_SCHEMA)
    return sorted(f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
                  for e in validator.iter_errors(record))


def matrix_completeness(matrix: dict[str, dict[str, str]] = ACCEPTANCE_MATRIX) -> list[str]:
    """Problems with the matrix itself: a workstream without criteria, or an entry without scenario/evidence/
    a known validator. [] means complete."""
    problems = []
    covered = {row.get("ws") for row in matrix.values()}
    problems += [f"{ws}: no acceptance criterion mapped" for ws in REQUIRED_WORKSTREAMS if ws not in covered]
    for cid, row in sorted(matrix.items()):
        for key in ("ws", "criterion", "scenario", "evidence", "validator"):
            if not str(row.get(key, "")).strip():
                problems.append(f"{cid}: missing {key}")
        if row.get("validator") and row["validator"] not in VALIDATORS:
            problems.append(f"{cid}: unknown validator {row['validator']!r}")
    return problems


# --- P&L reconciliation (measurement only) ------------------------------------------------------------------
def _d(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"not a number: {value!r}") from exc


@dataclass(frozen=True)
class PnlCheck:
    trade_id: str
    status: str
    computed_net_quote: Decimal | None
    reported_net_quote: Decimal | None
    fees_quote: Decimal | None
    dust_base: Decimal | None
    detail: str


def reconcile_pnl(fills: list[dict], fees: list[dict], reported: list[dict], *, base_asset: str,
                  quote_asset: str = "USDT", fee_prices: dict[str, dict] | None = None,
                  tolerance_quote: str = "0.00000001") -> list[PnlCheck]:
    """Recompute each closed trade's realised net P&L from fills minus fees, and compare with what was reported.

    fills:    [{trade_id, fill_id, side: buy|sell, qty (base), price (quote)}]
    fees:     [{trade_id, fill_id, asset, amount}] — the asset may be the quote, the base, or another (e.g. BNB).
              A quote fee is deducted. A third-asset fee (BNB) is converted with fee_prices[fill_id][asset]
              (quote per unit), which must be given, and deducted. A base-asset fee is not deducted again: it
              reduces the base held (its cost is already in the gross) and is measured as dust and fee value.
    reported: [{trade_id, net_quote}]
    Fail-closed: a trade with an unconvertible fee, a duplicate fill id, a missing report, a report without
    fills, or an unclosed position (sold more than bought) is FAIL. The base-asset residue (dust) left by
    fees taken in the base asset is measured and reported, not hidden.
    """
    tol = _d(tolerance_quote)
    fee_prices = fee_prices or {}
    by_trade: dict[str, list[dict]] = defaultdict(list)
    seen_fills: set[str] = set()
    duplicates: set[str] = set()
    for f in fills:
        fid = str(f["fill_id"])
        if fid in seen_fills:
            duplicates.add(str(f["trade_id"]))
        seen_fills.add(fid)
        by_trade[str(f["trade_id"])].append(f)
    fees_by_trade: dict[str, list[dict]] = defaultdict(list)
    for fee in fees:
        fees_by_trade[str(fee["trade_id"])].append(fee)
    reported_by_trade = {str(r["trade_id"]): r for r in reported}
    results = []
    for tid in sorted(set(by_trade) | set(reported_by_trade)):
        rep = reported_by_trade.get(tid)
        legs = by_trade.get(tid, [])
        if tid in duplicates:
            results.append(PnlCheck(tid, FAIL, None, None, None, None, "duplicate fill id (double execution)"))
            continue
        if not legs:
            results.append(PnlCheck(tid, FAIL, None, _d(rep["net_quote"]), None, None, "reported trade has no fills"))
            continue
        if rep is None:
            results.append(PnlCheck(tid, FAIL, None, None, None, None, "fills without a reported P&L"))
            continue
        try:
            bought = sum((_d(f["qty"]) for f in legs if f["side"] == "buy"), Decimal(0))
            sold = sum((_d(f["qty"]) for f in legs if f["side"] == "sell"), Decimal(0))
            gross = sum((_d(f["qty"]) * _d(f["price"]) * (1 if f["side"] == "sell" else -1) for f in legs), Decimal(0))
            fee_quote, base_fee, base_fee_value = Decimal(0), Decimal(0), Decimal(0)
            fill_price = {str(f["fill_id"]): _d(f["price"]) for f in legs}
            for fee in fees_by_trade.get(tid, []):
                amount, asset, fid = _d(fee["amount"]), fee["asset"], str(fee["fill_id"])
                if asset == quote_asset:
                    fee_quote += amount
                elif asset == base_asset:
                    # A base-asset fee shrinks the base actually held. Its cost is already inside the gross
                    # (the fee base cannot be sold), so it is NOT deducted again; it is measured as dust/fee value.
                    base_fee += amount
                    base_fee_value += amount * fill_price.get(fid, Decimal(0))
                else:
                    price = (fee_prices.get(fid) or {}).get(asset)
                    if price is None:
                        raise ValueError(f"fee in {asset} on fill {fid} has no conversion price")
                    fee_quote += amount * _d(price)
        except (KeyError, ValueError) as exc:
            results.append(PnlCheck(tid, FAIL, None, _d(rep["net_quote"]), None, None, f"cannot compute: {exc}"))
            continue
        dust = bought - sold - base_fee
        if dust < 0:
            results.append(PnlCheck(tid, FAIL, None, _d(rep["net_quote"]), fee_quote + base_fee_value, dust,
                                    "sold more than bought net of base fees (position not closed consistently)"))
            continue
        net = gross - fee_quote
        reported_net = _d(rep["net_quote"])
        ok = abs(net - reported_net) <= tol
        results.append(PnlCheck(tid, PASS if ok else FAIL, net, reported_net, fee_quote + base_fee_value, dust,
                                "reconciles" if ok else f"differs by {net - reported_net}"))
    return results


# --- kill switch: bounded time + attributable record --------------------------------------------------------
def kill_switch_bounded(record: dict, *, bound_s: float) -> tuple[str, str]:
    """PLN-08 acceptance on one P3_KILL_SWITCH_V1 ledger record from the run."""
    if record.get("record_type") != "P3_KILL_SWITCH_V1":
        return FAIL, "not a kill-switch record"
    if record.get("dry_run") is not False:
        return FAIL, "a dry-run engagement does not prove a stop"
    if not str(record.get("reason", "")).strip() or not str(record.get("operator", "")).strip():
        return FAIL, "not attributable (reason and operator required)"
    if not record.get("digest") or "prev_digest" not in record:
        return FAIL, "record is not hash-chained"
    if not record.get("targets"):
        return UNPROVEN, "nothing was running; a stop of a running runtime was not exercised"
    if record.get("outcome") != "STOPPED" or record.get("still_running"):
        return FAIL, f"outcome {record.get('outcome')}, still running {record.get('still_running')}"
    try:
        elapsed = float(record["elapsed_s"])
    except (KeyError, TypeError, ValueError):
        return FAIL, "elapsed time missing"
    if elapsed > bound_s:
        return FAIL, f"stop took {elapsed} s > bound {bound_s} s"
    return PASS, f"{len(record['targets'])} target(s) stopped in {elapsed} s (bound {bound_s} s)"


# --- restart continuity ---------------------------------------------------------------------------------------
def restart_continuity(before: dict, after: dict) -> tuple[str, str]:
    """A restart/reboot inside the run kept identity and evidence continuous, and never revived a stopped runtime.

    before/after: {cohort_id, t0_utc, source_commit, ledger_last_digest | ledger_first_prev_digest,
                   fill_ids: [...], stopped_runtimes: [...], running_runtimes: [...]}
    `after["ledger_first_prev_digest"]` must equal `before["ledger_last_digest"]` (the chain continues).
    """
    problems = []
    for key in ("cohort_id", "t0_utc", "source_commit"):
        if before.get(key) is None or before.get(key) != after.get(key):
            problems.append(f"{key} changed or unknown ({before.get(key)!r} -> {after.get(key)!r})")
    if not before.get("ledger_last_digest") or after.get("ledger_first_prev_digest") != before.get("ledger_last_digest"):
        problems.append("evidence chain does not continue across the restart")
    dup = set(map(str, before.get("fill_ids", []))) & set(map(str, after.get("fill_ids", [])))
    if dup:
        problems.append(f"duplicate execution across the restart: {sorted(dup)[:3]}")
    revived = set(before.get("stopped_runtimes", [])) & set(after.get("running_runtimes", []))
    if revived:
        problems.append(f"a stopped runtime came back: {sorted(revived)}")
    return (FAIL, "; ".join(problems)) if problems else (PASS, "identity, chain and stop state continuous")


# --- the run verdict ------------------------------------------------------------------------------------------
def run_verdict(records: list[dict], *, run_id: str, matrix: dict[str, dict[str, str]] = ACCEPTANCE_MATRIX) -> dict:
    """PLN-10 acceptance input: every criterion needs a valid PASS record from THIS run. Never ACCEPTED by default.

    The returned verdict is CANDIDATE_FOR_OWNER_ACCEPTANCE at best: the Owner's merged acceptance record decides.
    """
    problems = list(matrix_completeness(matrix))
    best: dict[str, str] = {}
    for rec in records:
        errs = validate_evidence(rec)
        if errs:
            problems.append(f"invalid record {rec.get('criterion_id', '?')}: {errs[0]}")
            continue
        if rec["run_id"] != run_id:
            continue  # evidence from another run never counts toward this one
        cid = rec["criterion_id"]
        # Precedence within one run: FAIL > PASS > UNPROVEN. A failure is never overwritten by a later pass;
        # a failed acceptance needs a fix and a new continuous run (contract §8: never waived).
        rank = {UNPROVEN: 0, PASS: 1, FAIL: 2}
        if cid not in best or rank[rec["status"]] > rank[best[cid]]:
            best[cid] = rec["status"]
    unmet = {cid: best.get(cid, "MISSING") for cid in sorted(matrix) if best.get(cid) != PASS}
    verdict = "CANDIDATE_FOR_OWNER_ACCEPTANCE" if not unmet and not problems else "NOT_ACCEPTED"
    return {"run_id": run_id, "verdict": verdict, "unmet": unmet, "problems": problems,
            "criteria": len(matrix), "met": len(matrix) - len(unmet), "real_money_authorized": False}
