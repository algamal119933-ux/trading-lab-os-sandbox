"""P3-PLN-10 Paper Beta Acceptance Program: the acceptance matrix, the evidence schema and its validators.

P3_CONTRACT.md §3 PLN-10. The acceptance requires every PLN-02..PLN-09 acceptance to hold in ONE continuous
Paper Beta run, and the P&L measurement to reconcile to fills and fees. This module does not run anything: it
validates evidence records that the run produces. It is developed and tested against synthetic evidence only.

Fail-closed: a criterion without PASS evidence from the same run is NOT met. UNPROVEN is not PASS. A missing,
malformed or contradictory record never counts. Nothing here can mark PLN-10 accepted on its own; the verdict
it computes is an input to the Owner's acceptance record.

The run configuration (P3_PLN10_RUN_CONFIG_V1) carries the five Owner decisions: approved paper runtime, trial
duration, emergency-stop bound, acceptance criteria and explicit launch authority. None has a default here. Any
unset, defaulted or placeholder decision keeps the run LAUNCH_BLOCKED and the verdict NOT_ACCEPTED, and the
validators that need a threshold (the stop bound, the P&L tolerance) take it only as an explicit argument. This
module never launches anything: PAPER_LAUNCH_AUTHORIZED = NO.

The P&L reconciliation is MEASUREMENT ONLY (Priority 1 in the contract): it checks that reported net results
equal fills minus fees. It says nothing about profitability.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from . import kill_switch  # reuse: the kill switch's own scope decides which runtimes S-KILL can cover

RECORD_TYPE = "P3_PLN10_EVIDENCE_V1"
PASS, FAIL, UNPROVEN = "PASS", "FAIL", "UNPROVEN"
STATUSES = (PASS, FAIL, UNPROVEN)

# --- the acceptance matrix: every PLN-02..PLN-09 criterion → scenario, evidence, validator ------------------
# Criterion texts follow P3_CONTRACT.md §3 (frozen at fcd06b21). One contract cell may hold several criteria.
#
# Reuse, not re-specification: each row names
#   procedure          the merged runbook / checklist / record section that already defines HOW the evidence is
#                      produced and judged. The in-run scenario re-executes exactly that procedure; this program
#                      does not restate its pass rule.
#   standalone_record  the merged record that holds the workstream's own (pre-run) acceptance, or "NONE — …".
#                      A standalone acceptance is a PREREQUISITE (program §1). It never substitutes for the in-run
#                      record: the contract requires every acceptance to hold in ONE continuous run.
#   owner              who performs the step in the window: Owner, Claude, or Owner + Claude. Claude always writes
#                      the evidence record; acceptance is always the Owner's merged record.
#   stop_condition     when this step stops the run (program §9) or records FAIL / UNPROVEN (program §10).
# The criterion id is the EVIDENCE ID. The PLN-10 evidence records (`criterion_id`) and the PLN-11 execution
# pack's evidence index are keyed by the same ids.
ACCEPTANCE_MATRIX: dict[str, dict[str, str]] = {
    "PLN-02.inventory_complete": {
        "ws": "PLN-02", "criterion": "the inventory lists 100% of tracked and untracked TLOS state",
        "scenario": "S-INV: state inventory at run start and run end",
        "procedure": "docs/p3/PLN_02_STATE_INVENTORY.md §Verdict (COVERAGE)",
        "standalone_record": "docs/p3/PLN_02_STATE_INVENTORY.md §Acceptance update (PASS, 14 roots)",
        "evidence": "the procedure's state_inventory JSON, taken inside the window", "validator": "status_pass",
        "owner": "Claude",
        "stop_condition": "the inventory cannot run, or finds an unlisted TLOS state root: FAIL for this run (§10); unattributable state stops the run (§9)"},
    "PLN-02.recovery_sources": {
        "ws": "PLN-02", "criterion": "each item has a verified recovery source",
        "scenario": "S-INV: recheck against the newest scheduled backup set",
        "procedure": "docs/p3/PLN_02_STATE_INVENTORY.md §Verdict (RECOVERY)",
        "standalone_record": "docs/p3/PLN_02_STATE_INVENTORY.md §Acceptance update (PASS, 14 roots)",
        "evidence": "the procedure's state_inventory JSON against a set written inside the window",
        "validator": "status_pass",
        "owner": "Claude",
        "stop_condition": "an item has no verified recovery source in a set written inside the window: FAIL for this run (§10)"},
    "PLN-03.restore_drill": {
        "ws": "PLN-03", "criterion": "restore drill passes: manifest sha256 equal, git fsck clean, ARCHIVE_VERIFIED, "
                                     "restored runtime starts in dry-run",
        "scenario": "S-RESTORE: drill from a set taken during the run, into an empty scratch",
        "procedure": "docs/p3/PLN_03_BACKUP_RESTORE.md §Scheduled acceptance (verify + drill)",
        "standalone_record": "docs/p3/PLN_03_BACKUP_RESTORE.md §Scheduled acceptance (PASS, set 20261025T211956Z)",
        "evidence": "the procedure's drill JSON for a set written inside the window", "validator": "status_pass",
        "owner": "Claude",
        "stop_condition": "the drill reports FAIL, or a restore would touch live state: FAIL (§10); a restore over live state is never run (§9 destructive storage operation)"},
    "PLN-03.repeated_after_change": {
        "ws": "PLN-03", "criterion": "the drill is repeated after a change",
        "scenario": "S-RESTORE-2: second drill after any code/config change merged during the run",
        "procedure": "docs/p3/PLN_03_BACKUP_RESTORE.md §Scheduled acceptance (verify + drill)",
        "standalone_record": "docs/p3/PLN_03_BACKUP_RESTORE.md §Acceptance update (second set drill PASS)",
        "evidence": "a second drill JSON, on a newer set than the first", "validator": "status_pass",
        "owner": "Claude",
        "stop_condition": "a change merged in the window without a second PASS drill on a newer set: criterion unmet (§10)"},
    "PLN-04.reboot_correct": {
        "ws": "PLN-04", "criterion": "after a reboot, the stack's state is correct",
        "scenario": "S-REBOOT: planned clean reboot during the run",
        "procedure": "docs/p3/PLN_04_REBOOT_ACCEPTANCE_RUNBOOK.md §1-§4 (record per §7)",
        "standalone_record": "docs/p3/PLN_04_RECOVERY.md §Reboot record (RUN 3 PASS 10/10, accepted by the merge "
                             "of PR #94)",
        "evidence": "the runbook §6 evidence set for a reboot inside the window", "validator": "status_pass",
        "owner": "Owner + Claude",
        "stop_condition": "verify-boot reports any FAIL or the gap attestation is not clean: FAIL (§10); a host change outside the frozen state stops the run (§9)"},
    "PLN-04.terminal_never_restarted": {
        "ws": "PLN-04", "criterion": "a terminal or Owner-stopped cohort is never auto-restarted (negative test)",
        "scenario": "S-RESTART: kill-switch stop, then reboot; the stopped runtime must stay stopped",
        "procedure": "docs/p3/PLN_04_RECOVERY.md §Acceptance status (terminal-state guard)",
        "standalone_record": "docs/p3/PLN_04_RECOVERY.md §Acceptance status (terminal-state guard PASS)",
        "evidence": "restart_continuity before/after record: the stopped runtime stayed stopped",
        "validator": "restart_continuity",
        "owner": "Owner + Claude",
        "stop_condition": "a stopped runtime comes back without an attributable resume: stop the run with the kill switch (§9) and record FAIL (§10)"},
    "PLN-04.host_recovery_drill": {
        "ws": "PLN-04", "criterion": "a host-recovery drill from backup passes",
        "scenario": "S-RESTORE (shared with PLN-03)",
        "procedure": "docs/p3/PLN_03_BACKUP_RESTORE.md §Scheduled acceptance (verify + drill)",
        "standalone_record": "docs/p3/PLN_04_RECOVERY.md §Acceptance status (host-recovery drill PASS)",
        "evidence": "the PLN-03.restore_drill artifact (one drill, cited twice)", "validator": "status_pass",
        "owner": "Claude",
        "stop_condition": "the shared S-RESTORE drill is not PASS: FAIL (§10)"},
    "PLN-05.host_loss_redundancy": {
        "ws": "PLN-05", "criterion": "HOST_LOSS_REDUNDANCY = PROVEN by restoring from the independent host",
        "scenario": "S-TIER3: push + restore drill from the independent host",
        "procedure": "docs/p3/PLN_05_TIER3_PROCEDURE.md §5-§6 (record per §8)",
        "standalone_record": "NONE — docs/p3/PLN_05_EVIDENCE_DURABILITY.md: HOST_LOSS_REDUNDANCY = NOT_PROVEN",
        "evidence": "the procedure §8 evidence for a push and remote restore inside the window",
        "validator": "status_pass",
        "owner": "Owner + Claude",
        "stop_condition": "no independent host, or the remote restore is not PASS: UNPROVEN or FAIL, never PASS (§10)"},
    "PLN-05.attributable_stop_start": {
        "ws": "PLN-05", "criterion": "every governed stop/start has an attributable record",
        "scenario": "S-KILL and every start during the run",
        "procedure": "docs/p3/PLN_06_07_08_OPERATIONS.md §PLN-08 (operator ledger, --verify-ledger)",
        "standalone_record": "docs/p3/PLN_05_EVIDENCE_DURABILITY.md §Acceptance status (ATTRIBUTABLE_STOP_START "
                             "PASS)",
        "evidence": "operator ledger over the window: chain verifies; one record per stop/start",
        "validator": "status_pass",
        "owner": "Owner + Claude",
        "stop_condition": "a stop or start without an attributable ledger record, or a broken chain: stop the run (§9 evidence unattributable)"},
    "PLN-06.s19_alerts": {
        "ws": "PLN-06", "criterion": "each §19 CRITICAL condition raises an alert in a test",
        "scenario": "S-ALERT: rule tests + a delivered test alert + the end-to-end stale alert",
        "procedure": "docs/p3/PLN_06_ALERTING.md §3 (steps 6-8, PASS/FAIL table) and §4",
        "standalone_record": "NONE — docs/p3/PLN_06_ALERTING.md §4: PLN_06 = PARTIAL (delivery PENDING — Owner)",
        "evidence": "the §3 evidence directory listing for steps 6-8 run inside the window",
        "validator": "status_pass",
        "owner": "Owner + Claude",
        "stop_condition": "a §19 condition without a delivered alert: FAIL (§10); any §19 CRITICAL raised for real stops the run (§9)"},
    "PLN-06.capacity_enforced": {
        "ws": "PLN-06", "criterion": "capacity thresholds are enforced",
        "scenario": "S-ALERT: health findings free_space:root / free_space:h1_lane at run start and end",
        "procedure": "docs/p3/PLN_06_ALERTING.md §4 (capacity row)",
        "standalone_record": "docs/p3/PLN_06_ALERTING.md §4 (rule leg PASS in test)",
        "evidence": "health JSON at run start and end", "validator": "status_pass",
        "owner": "Claude",
        "stop_condition": "a free_space finding below INFO at run start: no T0; during the window: stop the run before storage runs out (§9)"},
    "PLN-06.normal_end_detected": {
        "ws": "PLN-06", "criterion": "normal end is detected on lifecycle completion",
        "scenario": "S-END: the run's cohort completes its lifecycle",
        "procedure": "docs/p3/PLN_06_ALERTING.md §4 (normal-end row)",
        "standalone_record": "docs/p3/PLN_06_ALERTING.md §4 (detection met)",
        "evidence": "the health finding normal_end raised at the cohort's completion", "validator": "status_pass",
        "owner": "Claude",
        "stop_condition": "the lifecycle ends without a normal_end finding: FAIL (§10)"},
    "PLN-07.matrix_rows": {
        "ws": "PLN-07", "criterion": "every failure/recovery matrix row has a passing test",
        "scenario": "S-CI: full suite at the run's frozen commit",
        "procedure": "docs/p3/PLN_04_RECOVERY.md §PLN-07 failure/recovery matrix",
        "standalone_record": "docs/p3/PLN_04_RECOVERY.md §Acceptance status (PLN-07 PASS for every row, reboot row "
                             "accepted by the merge of PR #94)",
        "evidence": "CI run id + pytest exit 0 at the frozen commit", "validator": "status_pass",
        "owner": "Claude",
        "stop_condition": "any test of the failure/recovery matrix fails at frozen_commit: FAIL (§10)"},
    "PLN-07.f2_finding": {
        "ws": "PLN-07", "criterion": "F-2 has a reconcile finding with negative controls",
        "scenario": "S-AUDIT: execution audit over the run's fills",
        "procedure": "docs/p3/PLN_06_07_08_OPERATIONS.md §PLN-07 (per-execution audit)",
        "standalone_record": "docs/p3/PLN_06_07_08_OPERATIONS.md §PLN-07 (F-2 finding on the sealed P2 archive)",
        "evidence": "execution_audit JSON over the run's ledgers", "validator": "status_pass",
        "owner": "Claude",
        "stop_condition": "an execution not backed by an admitted decision is unexplained: FAIL (§10); a live route stops the run (§9)"},
    "PLN-07.data_truth": {
        "ws": "PLN-07", "criterion": "the data-truth checks pass",
        "scenario": "S-AUDIT: missing/duplicate candles recorded, never filled (§13)",
        "procedure": "docs/p3/P3_CONTRACT.md §4 (Data truth, master plan §13)",
        "standalone_record": "NONE — PLN-07 data-truth evidence is open on main",
        "evidence": "data-truth report over the run's input ledger", "validator": "status_pass",
        "owner": "Claude",
        "stop_condition": "a missing or duplicate candle is filled or hidden: FAIL (§10); a dataset authority conflict stops the run (§9)"},
    "PLN-08.kill_bounded": {
        "ws": "PLN-08", "criterion": "the kill switch stops everything within a bounded time and leaves an "
                                     "attributable record",
        "scenario": "S-KILL: engage the kill switch on the run's paper runtime",
        "procedure": "docs/p3/PLN_06_07_08_OPERATIONS.md §PLN-08 (kill switch)",
        "standalone_record": "docs/p3/PLN_06_07_08_OPERATIONS.md §Acceptance status (PLN-08 PASS, drill 0.162 s)",
        "evidence": "the P3_KILL_SWITCH_V1 ledger record of the in-window stop", "validator": "kill_switch_bounded",
        "owner": "Owner + Claude",
        "stop_condition": "the stop exceeds the D3 bound, is not attributable, or leaves a runtime running: FAIL (§10) and a §9 stop by any bounded means"},
    "PLN-08.no_live_route": {
        "ws": "PLN-08", "criterion": "no control can set dry_run=false or reach a live route (guard test)",
        "scenario": "S-CI + S-ALERT: paper guard and real_money health findings throughout the run",
        "procedure": "docs/p3/PLN_06_07_08_OPERATIONS.md §PLN-08 (guard)",
        "standalone_record": "docs/p3/PLN_06_07_08_OPERATIONS.md §Acceptance status (PLN-08 PASS)",
        "evidence": "paper_guard PASS + real_money INFO in every health run of the window",
        "validator": "status_pass",
        "owner": "Claude",
        "stop_condition": "paper_guard or real_money goes CRITICAL, or dry_run is not true: stop the run at once (§9)"},
    "PLN-09.projection": {
        "ws": "PLN-09", "criterion": "a Control Room projection over canonical evidence, Arabic/English, realising "
                                     "the frozen shape; the UI is never evidence authority",
        "scenario": "S-UI: the Owner re-walks the PLN-09 checklist inside the window",
        "procedure": "docs/p3/PLN_09_OWNER_ACCEPTANCE_CHECKLIST.md §2-§4 (sign-off block §6)",
        "standalone_record": "NONE — docs/p3/PLN_09_OWNER_ACCEPTANCE_CHECKLIST.md §6: PLN09_OWNER_ACCEPTANCE = "
                             "PENDING",
        "evidence": "the checklist §6 block filled for this run_id", "validator": "status_pass",
        "owner": "Owner",
        "stop_condition": "a walkthrough step reads FAIL: record it under FINDINGS; it is never waived (§10)"},
    "PLN-10.pnl_reconciles": {
        "ws": "PLN-10", "criterion": "P&L measurement reconciles to fills and fees (measurement only)",
        "scenario": "S-PNL: every closed trade of the run",
        "procedure": "docs/p3/PLN_10_PAPER_BETA_ACCEPTANCE_PROGRAM.md §3 S-PNL",
        "standalone_record": "NONE — measured only inside the run",
        "evidence": "fills + fees + reported P&L records of the run", "validator": "reconcile_pnl",
        "owner": "Claude",
        "stop_condition": "any closed trade does not reconcile within the D4 tolerance: FAIL (§10); never re-measured to fit"},
}
REQUIRED_WORKSTREAMS = ("PLN-02", "PLN-03", "PLN-04", "PLN-05", "PLN-06", "PLN-07", "PLN-08", "PLN-09")
VALIDATORS = ("status_pass", "restart_continuity", "kill_switch_bounded", "reconcile_pnl")
ROW_KEYS = ("ws", "criterion", "scenario", "procedure", "standalone_record", "evidence", "validator", "owner",
            "stop_condition")
ROW_OWNERS = ("Owner", "Claude", "Owner + Claude")
EVIDENCE_ID_RE = re.compile(r"^PLN-\d{2}\.[a-z0-9_]+$")
_DOC_RE = re.compile(r"(docs/p3/[A-Za-z0-9_]+\.md)")


def referenced_documents(matrix: dict[str, dict[str, str]] = ACCEPTANCE_MATRIX) -> dict[str, set[str]]:
    """{document path: {criterion ids}} for every merged document a row's procedure or standalone record cites."""
    refs: dict[str, set[str]] = defaultdict(set)
    for cid, row in matrix.items():
        for key in ("procedure", "standalone_record"):
            for path in _DOC_RE.findall(str(row.get(key, ""))):
                refs[path].add(cid)
    return dict(refs)


def matrix_digest(matrix: dict[str, dict[str, str]] = ACCEPTANCE_MATRIX) -> str:
    """sha256 of the canonical matrix. The run configuration pins it, so the criteria cannot drift silently."""
    return hashlib.sha256(json.dumps(matrix, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


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
    """Problems with the matrix itself: a workstream without criteria, or an entry without scenario, procedure,
    standalone record, evidence, a known validator, a known owner, a stop condition, or a well-formed evidence id.
    [] means complete."""
    problems = []
    covered = {row.get("ws") for row in matrix.values()}
    problems += [f"{ws}: no acceptance criterion mapped" for ws in REQUIRED_WORKSTREAMS if ws not in covered]
    for cid, row in sorted(matrix.items()):
        if not EVIDENCE_ID_RE.match(cid) or not cid.startswith(f"{row.get('ws')}."):
            problems.append(f"{cid}: evidence id must be <workstream>.<snake_case> of its own workstream")
        for key in ROW_KEYS:
            if not str(row.get(key, "")).strip():
                problems.append(f"{cid}: missing {key}")
        if row.get("procedure") and not _DOC_RE.search(row["procedure"]):
            problems.append(f"{cid}: procedure must cite a merged docs/p3 document")
        if row.get("validator") and row["validator"] not in VALIDATORS:
            problems.append(f"{cid}: unknown validator {row['validator']!r}")
        if str(row.get("owner", "")).strip() and row["owner"] not in ROW_OWNERS:
            problems.append(f"{cid}: unknown owner {row['owner']!r} (one of {ROW_OWNERS})")
        stop = str(row.get("stop_condition", ""))
        if stop.strip() and "§9" not in stop and "§10" not in stop:
            problems.append(f"{cid}: stop_condition must cite the program's §9 stop conditions or §10 failure handling")
    return problems


# --- P&L reconciliation (measurement only) ------------------------------------------------------------------
def _d(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"not a number: {value!r}") from exc


def _check_legs(legs: list[dict], fees: list[dict]) -> None:
    """Refuse fills and fees that cannot be measured: an unknown side, a non-finite or non-positive quantity or
    price, a negative or non-finite fee. Each is a FAIL of the trade, never a silently signed number."""
    for f in legs:
        if f["side"] not in ("buy", "sell"):
            raise ValueError(f"fill {f['fill_id']}: side {f['side']!r} is not buy or sell")
        for key in ("qty", "price"):
            v = _d(f[key])
            if not v.is_finite() or v <= 0:
                raise ValueError(f"fill {f['fill_id']}: {key} {f[key]!r} is not a finite positive number")
    for fee in fees:
        v = _d(fee["amount"])
        if not v.is_finite() or v < 0:
            raise ValueError(f"fee on fill {fee['fill_id']}: amount {fee['amount']!r} is not a finite number >= 0")


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
                  tolerance_quote: str, quote_asset: str = "USDT",
                  fee_prices: dict[str, dict] | None = None) -> list[PnlCheck]:
    """Recompute each closed trade's realised net P&L from fills minus fees, and compare with what was reported.

    fills:    [{trade_id, fill_id, side: buy|sell, qty (base), price (quote)}]
    fees:     [{trade_id, fill_id, asset, amount}] — the asset may be the quote, the base, or another (e.g. BNB).
              A quote fee is deducted. A third-asset fee (BNB) is converted with fee_prices[fill_id][asset]
              (quote per unit), which must be given, and deducted. A base-asset fee is not deducted again: it
              reduces the base held (its cost is already in the gross) and is measured as dust and fee value.
    reported: [{trade_id, net_quote}]
    tolerance_quote: REQUIRED, no default. It is the Owner-fixed acceptance tolerance from the run configuration
              (`acceptance_criteria.pnl_tolerance_quote`, decision D4). A missing or negative tolerance is refused.
    Fail-closed: a trade with an unconvertible fee, a duplicate fill id, a missing report, a report without
    fills, or an unclosed position (sold more than bought) is FAIL. The base-asset residue (dust) left by
    fees taken in the base asset is measured and reported, not hidden.
    """
    if tolerance_quote is None or isinstance(tolerance_quote, (bool, float)):
        raise ValueError("tolerance_quote must be given explicitly as a decimal string (run configuration D4)")
    tol = _d(tolerance_quote)
    if not tol.is_finite() or tol < 0:
        raise ValueError(f"tolerance_quote must be a finite decimal >= 0, got {tolerance_quote!r}")
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
            results.append(PnlCheck(tid, FAIL, None, None, None, None, f"reported trade has no fills (reported "
                                                                          f"{rep.get('net_quote')!r})"))
            continue
        if rep is None:
            results.append(PnlCheck(tid, FAIL, None, None, None, None, "fills without a reported P&L"))
            continue
        try:
            _check_legs(legs, fees_by_trade.get(tid, []))
            reported_net = _d(rep["net_quote"])
            if not reported_net.is_finite():
                raise ValueError(f"reported net is not finite: {rep['net_quote']!r}")
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
        except (KeyError, ValueError, ArithmeticError) as exc:
            results.append(PnlCheck(tid, FAIL, None, None, None, None, f"cannot compute: {exc}"))
            continue
        dust = bought - sold - base_fee
        if dust < 0:
            results.append(PnlCheck(tid, FAIL, None, _d(rep["net_quote"]), fee_quote + base_fee_value, dust,
                                    "sold more than bought net of base fees (position not closed consistently)"))
            continue
        net = gross - fee_quote
        ok = abs(net - reported_net) <= tol
        results.append(PnlCheck(tid, PASS if ok else FAIL, net, reported_net, fee_quote + base_fee_value, dust,
                                "reconciles" if ok else f"differs by {net - reported_net}"))
    return results


# --- kill switch: bounded time + attributable record --------------------------------------------------------
def kill_switch_bounded(record: dict, *, bound_s: float) -> tuple[str, str]:
    """PLN-08 acceptance on one P3_KILL_SWITCH_V1 ledger record from the run.

    bound_s is REQUIRED and has no default: it is the Owner's emergency-stop bound from the run configuration
    (decision D3). An unset, non-positive or non-finite bound is a FAIL, never an implied limit.
    """
    if not _positive_finite(bound_s):
        return FAIL, f"no valid emergency-stop bound (got {bound_s!r}); the Owner fixes it in the run configuration"
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
    if not math.isfinite(elapsed) or elapsed < 0:
        return FAIL, f"elapsed time {record['elapsed_s']!r} is not a finite, non-negative number of seconds"
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


# --- the run configuration: the Owner decisions that gate a launch ------------------------------------------
# PAPER_LAUNCH_AUTHORIZED = NO today. Nothing in this module launches anything. `launch_readiness` only says
# whether a configuration is COMPLETE for the Owner to act on; with any decision unset, defaulted or a
# placeholder, it is LAUNCH_BLOCKED. There is no default value for any of these fields anywhere in this module.
RUN_CONFIG_TYPE = "P3_PLN10_RUN_CONFIG_V1"
RUN_CONFIG_PATH = "docs/p3/PLN_10_RUN_CONFIG.json"  # created only by the Owner's own PR; absent today

# Each Owner decision → the configuration field that blocks until it is set. Program §8 renders this table.
OWNER_DECISIONS: dict[str, dict[str, str]] = {
    "D1": {"decision": "approved paper runtime", "field": "paper_runtime",
           "blocks_until": "runtime_id is a paper runtime inside the kill switch's scope (not FP-CONTROL-3), "
                           "dry_run is true, and its authority record is cited"},
    "D2": {"decision": "trial duration", "field": "trial_window",
           "blocks_until": "start_utc is an ISO-8601 Z time, duration_hours is a positive number, and the window ends "
                           "no later than the P3 execution authorization's EXPIRES_UTC"},
    "D3": {"decision": "emergency-stop bound", "field": "emergency_stop_bound_s",
           "blocks_until": "a positive, finite number of seconds"},
    "D4": {"decision": "acceptance criteria", "field": "acceptance_criteria",
           "blocks_until": "matrix_sha256 equals the program's matrix digest, criterion_ids lists every matrix "
                           "criterion (no subset = no waiver), and pnl_tolerance_quote is an explicit decimal string"},
    "D5": {"decision": "explicit launch authority", "field": "launch_authority",
           "blocks_until": "granted_by = Owner, paper_launch_authorized is literally true, and an Owner-merged "
                           "authority record (path + merge commit) other than the P3 execution authorization is cited"},
}

RUN_CONFIG_TEMPLATE: dict = {
    "record_type": RUN_CONFIG_TYPE,
    "run_id": None,
    "frozen_commit": None,
    "dry_run": True,
    "real_money_authorized": False,
    "paper_runtime": {"runtime_id": None, "authority_record": None, "authority_merge": None},
    "trial_window": {"start_utc": None, "duration_hours": None},
    "emergency_stop_bound_s": None,
    "acceptance_criteria": {"matrix_sha256": None, "criterion_ids": None, "pnl_tolerance_quote": None},
    "launch_authority": {"granted_by": None, "record_path": None, "merge_commit": None,
                         "paper_launch_authorized": False},
}

_PLACEHOLDERS = {"", "tbd", "todo", "unset", "default", "pending", "none", "null", "n/a", "na", "?", "x", "xxx",
                 "changeme", "owner_decision", "fill_me"}
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
P3_EXECUTION_AUTHORIZATION = "docs/p3/OWNER_P3_EXECUTION_AUTHORIZATION.md"
# EXPIRES_UTC of that record (a test pins it to the record). A trial window that outlives it is not authorized.
P3_AUTHORIZATION_EXPIRES_UTC = "2027-01-31T23:59:59Z"


def _positive_finite(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            and value > 0)


def _is_set(value) -> bool:
    """A value counts as set only when it is a real value: not None, not empty, not a placeholder like TBD or
    <runtime>, not a template marker."""
    if value is None:
        return False
    if isinstance(value, str):
        v = value.strip()
        return not (v.lower() in _PLACEHOLDERS or (v.startswith("<") and v.endswith(">")) or "TBD" in v.upper())
    return True


def validate_run_config(config: dict, *, matrix: dict[str, dict[str, str]] = ACCEPTANCE_MATRIX) -> list[str]:
    """Every reason the configuration cannot gate a launch. [] only when all five Owner decisions are set.

    Fail-closed: a missing key, a None, a placeholder, a wrong type or a template value is a blocker. Each
    blocker starts with the decision id (D1..D5) or `config` so the Owner sees which decision is open.
    """
    if not isinstance(config, dict):
        return ["config: not an object"]
    b: list[str] = []
    if config.get("record_type") != RUN_CONFIG_TYPE:
        b.append(f"config: record_type must be {RUN_CONFIG_TYPE}")
    if not _is_set(config.get("run_id")):
        b.append("config: run_id unset")
    if not (isinstance(config.get("frozen_commit"), str) and _SHA40.match(config["frozen_commit"])):
        b.append("config: frozen_commit must be the 40-hex commit the host is frozen at for the run")
    if config.get("dry_run") is not True:
        b.append("config: dry_run must be literally true")
    if config.get("real_money_authorized") is not False:
        b.append("config: real_money_authorized must be literally false")

    rt = config.get("paper_runtime") if isinstance(config.get("paper_runtime"), dict) else {}
    rid = rt.get("runtime_id")
    if not _is_set(rid) or not isinstance(rid, str):
        b.append("D1 paper_runtime.runtime_id unset")
    else:
        if not any(fnmatch.fnmatchcase(rid, pat) for pat in kill_switch.PAPER_RUNTIME_PATTERNS):
            b.append(f"D1 paper_runtime.runtime_id {rid!r} is outside the kill switch scope "
                     f"{kill_switch.PAPER_RUNTIME_PATTERNS}; S-KILL could not stop it")
        if "fp-control-3" in rid.lower():
            b.append("D1 paper_runtime: FP-CONTROL-3 must not be restarted (CLAUDE.md)")
    if not _is_set(rt.get("authority_record")):
        b.append("D1 paper_runtime.authority_record unset")
    if not (isinstance(rt.get("authority_merge"), str) and _SHA40.match(rt["authority_merge"])):
        b.append("D1 paper_runtime.authority_merge must be the 40-hex Owner merge commit")

    tw = config.get("trial_window") if isinstance(config.get("trial_window"), dict) else {}
    if not (isinstance(tw.get("start_utc"), str) and _UTC.match(tw["start_utc"])):
        b.append("D2 trial_window.start_utc unset or not ISO-8601 Z")
    if not _positive_finite(tw.get("duration_hours")):
        b.append("D2 trial_window.duration_hours unset or not a positive number")
    window = _trial_window(config)
    if window is not None and window[1] > _epoch(P3_AUTHORIZATION_EXPIRES_UTC):
        b.append(f"D2 trial_window ends after the P3 execution authorization expires ({P3_AUTHORIZATION_EXPIRES_UTC})")

    if not _positive_finite(config.get("emergency_stop_bound_s")):
        b.append("D3 emergency_stop_bound_s unset or not a positive number of seconds")

    ac = config.get("acceptance_criteria") if isinstance(config.get("acceptance_criteria"), dict) else {}
    if not (isinstance(ac.get("matrix_sha256"), str) and _SHA64.match(ac["matrix_sha256"])):
        b.append("D4 acceptance_criteria.matrix_sha256 unset")
    elif ac["matrix_sha256"] != matrix_digest(matrix):
        b.append("D4 acceptance_criteria.matrix_sha256 does not match the program's matrix (criteria drifted)")
    ids = ac.get("criterion_ids")
    if not isinstance(ids, list) or not ids:
        b.append("D4 acceptance_criteria.criterion_ids unset")
    else:
        missing, unknown = sorted(set(matrix) - set(ids)), sorted(set(ids) - set(matrix))
        if missing:
            b.append(f"D4 acceptance_criteria omits {missing}: a criterion is never waived (contract §8)")
        if unknown:
            b.append(f"D4 acceptance_criteria names unknown criteria {unknown}")
    tol = ac.get("pnl_tolerance_quote")
    if not (isinstance(tol, str) and _is_set(tol)):
        b.append("D4 acceptance_criteria.pnl_tolerance_quote unset (a decimal string, e.g. \"0.00000001\")")
    else:
        try:
            t = Decimal(tol)
            if not t.is_finite() or t < 0:
                b.append("D4 acceptance_criteria.pnl_tolerance_quote must be a finite decimal >= 0")
        except InvalidOperation:
            b.append("D4 acceptance_criteria.pnl_tolerance_quote is not a decimal")

    la = config.get("launch_authority") if isinstance(config.get("launch_authority"), dict) else {}
    if la.get("granted_by") != "Owner":
        b.append("D5 launch_authority.granted_by must be Owner")
    if la.get("paper_launch_authorized") is not True:
        b.append("D5 launch_authority.paper_launch_authorized is not literally true (PAPER_LAUNCH_AUTHORIZED = NO)")
    rec = la.get("record_path")
    if not (isinstance(rec, str) and _is_set(rec) and rec.endswith(".md")):
        b.append("D5 launch_authority.record_path unset")
    elif rec == P3_EXECUTION_AUTHORIZATION:
        b.append("D5 launch_authority: the P3 execution authorization does not itself authorize a paper launch")
    elif isinstance(rid, str) and fnmatch.fnmatchcase(rid, "tlos-h1-paper-cohort-*") \
            and "H1_LAUNCH_AUTHORIZATION" not in rec:
        b.append("D5 launch_authority: an H1 runtime needs its own H1_LAUNCH_AUTHORIZATION record")
    if not (isinstance(la.get("merge_commit"), str) and _SHA40.match(la["merge_commit"])):
        b.append("D5 launch_authority.merge_commit must be the 40-hex Owner merge commit")
    return b


def launch_readiness(config: dict, *, matrix: dict[str, dict[str, str]] = ACCEPTANCE_MATRIX) -> dict:
    """LAUNCH_BLOCKED unless every Owner decision is set. Even CONFIG_COMPLETE_FOR_OWNER_LAUNCH launches nothing:
    the launch is the Owner's act under the cited authority."""
    blockers = validate_run_config(config, matrix=matrix)
    open_decisions = sorted({x.split()[0] for x in blockers if re.match(r"^D\d ", x)})
    return {"verdict": "LAUNCH_BLOCKED" if blockers else "CONFIG_COMPLETE_FOR_OWNER_LAUNCH",
            "open_owner_decisions": open_decisions, "blockers": blockers,
            "paper_launch_performed": False, "real_money_authorized": False}


# --- the run verdict ------------------------------------------------------------------------------------------
def _epoch(utc: str) -> float:
    return datetime.strptime(utc[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp() + (
        float("0" + utc[19:-1]) if len(utc) > 20 else 0.0)


def _trial_window(config) -> tuple[float, float] | None:
    """[start, start + duration] of the configuration's trial window (D2), or None when it is not set."""
    tw = config.get("trial_window") if isinstance(config, dict) else None
    if not isinstance(tw, dict) or not (isinstance(tw.get("start_utc"), str) and _UTC.match(tw["start_utc"])) \
            or not _positive_finite(tw.get("duration_hours")):
        return None
    try:
        start = _epoch(tw["start_utc"])
    except ValueError:
        return None
    return start, start + float(tw["duration_hours"]) * 3600
def run_verdict(records: list[dict], *, config: dict, matrix: dict[str, dict[str, str]] = ACCEPTANCE_MATRIX) -> dict:
    """PLN-10 acceptance input: every criterion needs a valid PASS record from THIS run. Never ACCEPTED by default.

    `config` is REQUIRED: the run is identified by the Owner's run configuration, and an incomplete configuration
    (any Owner decision unset) blocks the verdict. The returned verdict is CANDIDATE_FOR_OWNER_ACCEPTANCE at best:
    the Owner's merged acceptance record decides.
    """
    problems = list(matrix_completeness(matrix))
    problems += [f"run config: {x}" for x in validate_run_config(config, matrix=matrix)]
    run_id = config.get("run_id") if isinstance(config, dict) else None
    window = _trial_window(config)
    best: dict[str, str] = {}
    for rec in records:
        errs = validate_evidence(rec)
        if errs:
            problems.append(f"invalid record {rec.get('criterion_id', '?')}: {errs[0]}")
            continue
        if not _is_set(run_id) or rec["run_id"] != run_id:
            continue  # evidence from another run never counts toward this one
        try:
            at = _epoch(rec["utc"])
        except ValueError:
            at = None
        if window is None or at is None or not window[0] <= at <= window[1]:
            # the contract asks for ONE continuous run: a record outside its window is not evidence of it
            problems.append(f"record {rec['criterion_id']} at {rec['utc']} is outside the trial window")
            continue
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
