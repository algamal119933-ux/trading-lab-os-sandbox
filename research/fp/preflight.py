#!/usr/bin/env python3
"""FP-BOOT-1 preflight gate (specification section 12).

"No candidate T0 before preflight PASS." This module runs the twelve preflight
checks and refuses to emit a T0 unless every one of them is ``PASS``.

Three of the checks — input ledger, decision ledger, event-time replay — are
executed here as real self-tests against a synthetic bounded sample in a
temporary directory, including a **negative control**: the replay check
deliberately corrupts one decision and requires the gate to catch it. A gate
that can only ever report PASS is not evidence of anything.

The checks that need a live paper runtime (market-data ingestion, external
feature ingestion, monitoring liveness) are reported ``UNPROVEN`` in an
environment that has no such runtime. ``UNPROVEN`` blocks T0 exactly as ``FAIL``
does.

Usage
-----
    python3 research/fp/preflight.py                # human-readable report
    python3 research/fp/preflight.py --json         # machine-readable
    python3 research/fp/preflight.py --require-pass # exit 2 unless all PASS

Exit codes: 0 report produced, 2 preflight not PASS under ``--require-pass``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if extra not in sys.path:
        sys.path.insert(0, extra)

from fp import lane_io as fp_lane_io  # noqa: E402
from fp import ledger as fp_ledger  # noqa: E402
from fp import replay as fp_replay  # noqa: E402

# Imported lazily-but-eagerly: these three are what let a check speak about a
# real runtime instead of a synthetic sample. They must not be optional, or a
# missing module would quietly downgrade a provable check back to UNPROVEN.
from fp import capture as fp_capture  # noqa: E402
from fp import market as fp_market  # noqa: E402
from fp import reconcile as fp_reconcile  # noqa: E402

EXAMPLE_CONFIG = REPO_ROOT / "freqtrade" / "user_data" / "config.paper.json.example"
RUNTIME_CONFIG = REPO_ROOT / "freqtrade" / "user_data" / "config.json"
COHORT_REGISTRY = REPO_ROOT / "research" / "fp" / "records" / "forward_paper_cohort_registry.json"

PASS, FAIL, UNPROVEN = "PASS", "FAIL", "UNPROVEN"


@dataclass
class RuntimeContext:
    """A live paper runtime that some checks may interrogate.

    The scaffold deliberately reports UNPROVEN for anything that needs a
    running candidate, and that must stay true in CI, where none exists. This
    object is how a real host says "there is one, here it is" — so the same
    check reports UNPROVEN in CI and PASS or FAIL on the authoritative host,
    without either verdict being asserted by hand.

    ``None`` everywhere is the CI case and changes nothing.
    """

    evidence_dir: Path | None = None
    # Which registry instance this runtime is. A runtime that cannot name its
    # own instance cannot be compared against a frozen identity, and comparing
    # it against "every row that has hashes" silently includes closed ones.
    role: str | None = None
    freqtrade_url: str | None = None
    api_user: str | None = None
    api_password: str | None = None
    exporter_url: str | None = None
    prometheus_url: str | None = None
    check_market_route: bool = False

    @property
    def has_evidence(self) -> bool:
        return self.evidence_dir is not None and Path(self.evidence_dir).is_dir()

    def client(self):
        if not self.freqtrade_url:
            return None
        return fp_capture.FreqtradeClient(self.freqtrade_url, self.api_user, self.api_password)


def _http_ok(url: str, timeout: int = 8) -> tuple[bool, str]:
    """Is ``url`` serving? Returns (ok, detail) and never raises."""
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            body = response.read(2048)
            return 200 <= response.status < 300, f"HTTP {response.status}, {len(body)}+ bytes"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:200]


def _real_records(evidence_dir: Path) -> dict:
    """Counts and provenance of genuinely captured (non-synthetic) evidence."""
    ledgers = fp_ledger.open_ledgers(evidence_dir)
    inputs = [r for r in ledgers["input"].records() if not r.payload.get("erratum")]
    decisions = [r for r in ledgers["decision"].records() if not r.payload.get("erratum")]
    sources = {r.payload.get("source_id") for r in inputs if r.payload.get("source_id")}
    hosts = {r.payload.get("source_host") for r in inputs if r.payload.get("source_host")}
    pairs = sorted({r.payload.get("pair") for r in inputs if r.payload.get("pair")})
    return {
        "ledgers": ledgers,
        "inputs": inputs,
        "decisions": decisions,
        "sources": sources,
        "hosts": hosts,
        "pairs": pairs,
        "exchange_sourced": bool(sources) and all(s == fp_market.SOURCE_ID for s in sources),
    }

# The mechanisms this environment can exercise, as opposed to the checks that
# need a live candidate. Section 1.3 keeps the two verdicts apart: validating
# the scaffold is not runtime readiness. Every key here must be reported by some
# check, so a mechanism that silently stops running fails the verdict rather
# than vanishing from it.
MECHANISM_KEYS = (
    "mechanism_input_ledger",
    "mechanism_decision_ledger",
    "mechanism_event_time_replay",
    "mechanism_persistence",
    "mechanism_restart",
)

# Section 16 of the v2.0 directive, verbatim and in order. Four checks are new
# relative to the superseded v1.1 section 12 (clock tolerance, evidence
# persistence, the pre-T0 restart drill, and the split of dry-run from Spot),
# and two that the scaffold previously reported PASS now say "real": a synthetic
# sample cannot satisfy them.
CHECKS = (
    "Paper Guard PASS",
    "effective config is dry_run=true",
    "effective mode is Spot",
    "no live exchange secret required",
    "runtime hashes match registry",
    "real market-data ingestion works",
    "required external-feature ingestion works if applicable",
    "input ledger works on real incoming data",
    "decision ledger works",
    "DB is isolated",
    "monitoring is alive",
    "event-time replay works on a bounded real-data sample",
    "no duplicate-instance risk",
    "clock/timestamp handling is within tolerance",
    "disk/evidence persistence works",
    "candidate can be restarted safely in a controlled pre-T0 drill",
)


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(fp_lane_io.read_identity_text(path))
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# Synthetic bounded sample
# --------------------------------------------------------------------------


def synthetic_candles(count: int = 900, start_ts: int = 1_609_459_200_000, step_ms: int = 3_600_000) -> list[dict]:
    """A deterministic 1h series containing at least one EMA50/EMA200 cross.

    Longer than the strategy's declared ``startup_candle_count`` (3 x 200), so the
    sample contains bars that would actually be scored, not only warm-up.

    Built from integer arithmetic so it is identical on every platform: a long
    decline followed by a sustained recovery, which forces the fast EMA through
    the slow one in both directions.
    """
    candles = []
    for i in range(count):
        if i < count // 2:
            close = 30000.0 - 20.0 * i
        else:
            close = 30000.0 - 20.0 * (count // 2) + 45.0 * (i - count // 2)
        close += 60.0 * (((i * 17) % 7) - 3)
        candles.append(
            {
                "ts": start_ts + i * step_ms,
                "open": round(close - 5.0, 8),
                "high": round(close + 25.0, 8),
                "low": round(close - 25.0, 8),
                "close": round(close, 8),
                "volume": round(100.0 + (i % 13), 8),
            }
        )
    return candles


def _capture_sample(evidence_dir: Path, pair: str = "BTC/USDT") -> tuple[fp_ledger.Ledger, fp_ledger.Ledger, int]:
    """Write a synthetic cycle through the real input and decision ledgers."""
    ledgers = fp_ledger.open_ledgers(evidence_dir)
    candles = synthetic_candles()

    # A bulk capture, so the batch form is the honest one to exercise here; the
    # per-append durability path is covered by the ledger tests.
    ledgers["input"].extend(
        [
            {
                "pair": pair,
                "timeframe": "1h",
                "candle": candle,
                "exchange_ts": candle["ts"] + 3_600_000,
                "received_utc": "2021-01-01T00:00:00.000Z",
                "source_id": "synthetic:preflight",
            }
            for candle in candles
        ]
    )

    ledgers["decision"].extend(
        [
            {
                "pair": pair,
                "timeframe": "1h",
                "candle_ts": decision.candle_ts,
                "signal_state": decision.signal_state,
                "intended_action": decision.intended_action,
                "no_action_reason": decision.no_action_reason,
                "runtime_version": fp_replay.REPLAY_ENGINE_VERSION,
                "restart_counter": 0,
            }
            for decision in fp_replay.derive_decisions(candles, pair)
        ]
    )

    return ledgers["input"], ledgers["decision"], len(candles)


# --------------------------------------------------------------------------
# Individual checks
# --------------------------------------------------------------------------


class MissingRuntimeConfig(Exception):
    """A runtime is attached but its configuration is not on disk."""


def _effective_config(runtime=None) -> Path:
    """The configuration a check should read.

    With a runtime attached the answer is the runtime's own config: validating
    the template while a different file executes is exactly the config-truth
    split this boundary closes. With no runtime — the CI case — the template is
    the only configuration that exists, and is used knowingly.
    """
    if runtime is not None:
        if not RUNTIME_CONFIG.is_file():
            # No silent substitution: with a runtime attached, the template is
            # not evidence about what that runtime is executing.
            raise MissingRuntimeConfig(
                f"a runtime is attached but {RUNTIME_CONFIG} does not exist; its configuration "
                "identity cannot be established"
            )
        return RUNTIME_CONFIG
    return EXAMPLE_CONFIG


def _check_guard(runtime: "RuntimeContext | None" = None) -> tuple[str, str]:
    try:
        _effective_config(runtime)
    except MissingRuntimeConfig as exc:
        return FAIL, str(exc)
    try:
        import paper_guard  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        return FAIL, f"paper_guard unavailable: {exc}"
    violations = paper_guard.Violations()
    paper_guard.check_config(_effective_config(runtime), violations)
    paper_guard.check_strategies(violations)
    if violations:
        return FAIL, "; ".join(violations[:5])
    return PASS, (
        f"scripts/paper_guard.py accepts {_effective_config(runtime).name} and every strategy file"
    )


def _check_dry_run(runtime: "RuntimeContext | None" = None) -> tuple[str, str]:
    try:
        _effective_config(runtime)
    except MissingRuntimeConfig as exc:
        return FAIL, str(exc)
    config = _load_json(_effective_config(runtime))
    if config is None:
        return FAIL, "shipped paper config is missing or unreadable"
    if config.get("dry_run") is not True:
        return FAIL, f"dry_run is {config.get('dry_run')!r}, not exactly true"
    return PASS, "dry_run is exactly true (not truthy: the guard rejects 1, 'true' and null)"


def _check_spot_mode(runtime: "RuntimeContext | None" = None) -> tuple[str, str]:
    try:
        _effective_config(runtime)
    except MissingRuntimeConfig as exc:
        return FAIL, str(exc)
    config = _load_json(_effective_config(runtime))
    if config is None:
        return FAIL, "shipped paper config is missing or unreadable"
    if config.get("trading_mode") != "spot":
        return FAIL, f"trading_mode is {config.get('trading_mode')!r}, not 'spot'"
    if config.get("margin_mode") not in (None, ""):
        return FAIL, f"margin_mode is {config.get('margin_mode')!r}, not empty"
    return PASS, "trading_mode='spot' with margin_mode empty"


def _check_clock_tolerance(runtime: RuntimeContext | None = None) -> tuple[str, str, dict]:
    """Section 16.14 — is clock and timestamp handling within tolerance?

    What the scaffold enforces structurally can be stated; the skew between this
    machine and the exchange cannot be, without asking the exchange. When a
    runtime with a market route is present the skew is *measured*, and stop
    condition S16 — skew beyond one candle period — is evaluated against the
    measurement rather than waived.
    """
    if runtime is not None and runtime.check_market_route:
        try:
            reading = fp_market.measure_clock_skew()
        except Exception as exc:  # noqa: BLE001
            return FAIL, f"clock skew could not be measured against the exchange: {exc}", {}
        payload = reading.as_payload()
        if not reading.within_tolerance:
            return (
                FAIL,
                f"S16: local-versus-exchange skew {reading.skew_ms} ms exceeds one candle period "
                f"({fp_market.CLOCK_SKEW_STOP_MS} ms)",
                {"clock": payload},
            )
        severity = "within warn threshold" if abs(reading.skew_ms) <= fp_market.CLOCK_SKEW_WARN_MS else "elevated but tolerable"
        return (
            PASS,
            f"measured against {reading.host}: skew {reading.skew_ms:+d} ms ({severity}), round trip "
            f"{reading.round_trip_ms} ms, tolerance {fp_market.CLOCK_SKEW_STOP_MS} ms. Structurally, the "
            "ledger refuses any recorded_utc that is not UTC ISO-8601 ending in Z, replay refuses "
            "out-of-order or duplicate candle timestamps, and the capture loop refuses a candle whose "
            "receipt precedes its close.",
            {"clock": payload},
        )
    return UNPROVEN, (
        "structurally enforced: the ledger refuses any recorded_utc that is not UTC ISO-8601 ending in Z, "
        "and replay refuses out-of-order or duplicate candle timestamps. Exchange-versus-local clock skew "
        "cannot be measured without a runtime that talks to the exchange, and section 21 makes serious skew "
        "an INSTANCE_PAUSE condition rather than something to tolerate silently."
    ), {}


def _check_evidence_persistence(evidence_dir: Path) -> tuple[str, str, dict]:
    """Section 16.15 — does evidence survive the process that wrote it?

    Executed, not asserted: the ledgers written earlier in this run are reopened
    from disk by fresh objects and re-verified. A ledger that only verifies
    while its writer is alive is not evidence.
    """
    reopened = fp_ledger.open_ledgers(evidence_dir)
    counts = {}
    for kind, ledger in sorted(reopened.items()):
        problems = ledger.verify()
        if problems:
            return FAIL, f"{kind} ledger did not survive reopening: {problems[0]}", {"mechanism_persistence": FAIL}
        counts[kind] = len(ledger.records())
    if not counts.get("input") or not counts.get("decision"):
        return FAIL, f"expected persisted input and decision records, found {counts}", {"mechanism_persistence": FAIL}
    digest = fp_ledger.daily_pack_digest(reopened.values())
    return (
        PASS,
        f"reopened from disk by fresh readers and re-verified: {counts}; "
        f"daily-pack digest {digest[:16]}... binds the ledger tips",
        {"mechanism_persistence": PASS},
    )


def _check_restart_drill_real(runtime: RuntimeContext) -> tuple[str, str, dict]:
    """Section 16.16 / 17 — a real restart drill against the live evidence.

    The synthetic drill below proves a fresh writer continues a chain. This asks
    the harder question of the actual runtime: did it in fact stop and start
    again, and did the restart re-decide anything it had already decided?
    """
    evidence_dir = Path(runtime.evidence_dir)
    ledgers = fp_ledger.open_ledgers(evidence_dir)
    incidents = ledgers["incident"].records()
    starts = [r for r in incidents if r.payload.get("category") == "run_started"]

    if len(starts) < 2:
        return UNPROVEN, (
            f"the runtime has recorded {len(starts)} start(s); a restart drill needs the instance stopped and "
            "started again so the second run is visible in the evidence"
        ), {}

    counters = [(r.payload.get("full_identity") or {}).get("restart_counter") for r in starts]
    if not all(isinstance(c, int) for c in counters) or any(b <= a for a, b in zip(counters, counters[1:])):
        return FAIL, f"restart counters are not strictly increasing across runs: {counters}", {}

    run_ids = [(r.payload.get("full_identity") or {}).get("run_id") for r in starts]
    if len(set(run_ids)) != len(run_ids):
        return FAIL, f"two recorded starts share a run_id: {run_ids}", {}

    for kind, led in sorted(ledgers.items()):
        problems = led.verify()
        if problems:
            return FAIL, f"the {kind} chain broke across a restart: {problems[0]}", {"mechanism_restart": FAIL}

    decisions = [r for r in ledgers["decision"].records() if not r.payload.get("erratum")]
    bars = [(r.payload.get("pair"), r.payload.get("candle_ts")) for r in decisions]
    if len(bars) != len(set(bars)):
        duplicated = [bar for bar in set(bars) if bars.count(bar) > 1]
        return FAIL, f"a restart re-decided bars it had already decided: {duplicated[:3]}", {"mechanism_restart": FAIL}

    trade_events = [
        r.payload.get("trade_event_id") for r in ledgers["trade"].records() if not r.payload.get("erratum")
    ]
    if len(trade_events) != len(set(trade_events)):
        return FAIL, "a restart re-recorded a paper execution", {"mechanism_restart": FAIL}

    recovered = fp_capture.recover_state(evidence_dir)
    return (
        PASS,
        f"the instance was stopped and restarted {len(starts) - 1} time(s) (restart counters {counters}); "
        f"every chain still verifies, {len(bars)} decisions remain unique per bar, no paper execution was "
        f"re-recorded, and {len(recovered.open_positions)} open position(s) plus "
        f"{len(recovered.captured_events)} captured market events were recovered from the ledgers",
        {
            "mechanism_restart": PASS,
            "restart_counters": counters,
            "recovered_open_positions": sorted(recovered.open_positions),
        },
    )


def _check_restart_drill(evidence_dir: Path) -> tuple[str, str, dict]:
    """Section 16.16 / 17 — can the candidate restart safely before T0?

    The ledger half of a restart is executable here and is executed: a fresh
    writer continues the existing chain rather than starting a second one or
    re-emitting a decision. The rest of the drill is not.
    """
    ledgers = fp_ledger.open_ledgers(evidence_dir)
    decision = ledgers["decision"]
    before = decision.records()
    if not before:
        return FAIL, "no decisions were recorded, so a restart cannot be exercised", {"mechanism_restart": FAIL}

    restarted = fp_ledger.Ledger(decision.path, "decision")
    resumed = restarted.append(
        {
            "pair": "BTC/USDT",
            "candle_ts": before[-1].payload.get("candle_ts", 0) + 3_600_000,
            "signal_state": before[-1].payload.get("signal_state"),
            "intended_action": "hold",
            "no_action_reason": "restart_drill",
            "restart_counter": 1,
        }
    )
    if resumed.seq != before[-1].seq + 1:
        return FAIL, f"a restarted writer resumed at seq {resumed.seq}, expected {before[-1].seq + 1}", {"mechanism_restart": FAIL}
    if resumed.prev_digest != before[-1].digest:
        return FAIL, "a restarted writer did not continue the existing chain", {"mechanism_restart": FAIL}
    if restarted.verify():
        return FAIL, "the chain broke across a restart", {"mechanism_restart": FAIL}
    timestamps = [r.payload.get("candle_ts") for r in restarted.records() if not r.payload.get("erratum")]
    if len(timestamps) != len(set(timestamps)):
        return FAIL, "a restart produced a duplicate decision for a candle already decided", {"mechanism_restart": FAIL}

    return (
        UNPROVEN,
        "the ledger half is executed and passes: a fresh writer resumed at the next sequence number, "
        "continued the hash chain, and produced no duplicate decision for an already-decided candle "
        f"(restart_counter recorded, {len(timestamps)} unique decision bars). Section 17 also requires a "
        "database reopen, a monitoring restart, a market-data interruption and state reconciliation, none "
        "of which exist without a running candidate.",
        {"mechanism_restart": PASS},
    )


def _check_no_secret(runtime: "RuntimeContext | None" = None) -> tuple[str, str]:
    try:
        _effective_config(runtime)
    except MissingRuntimeConfig as exc:
        return FAIL, str(exc)
    config = _load_json(_effective_config(runtime))
    if config is None:
        return FAIL, "shipped paper config is missing or unreadable"
    exchange = config.get("exchange") or {}
    present = [key for key in ("key", "secret", "password", "uid") if exchange.get(key)]
    if present:
        return FAIL, f"exchange credential fields are populated: {present}"
    return PASS, "exchange key and secret are empty; paper runs without any private credential"


def _check_hashes_match_registry(runtime: RuntimeContext | None = None) -> tuple[str, str, dict]:
    """Section 16.5 — do the running instance's hashes match the registry?

    The comparison is between three independent things, and agreement of only
    two would hide the interesting failure: what the registry froze, what is on
    disk now, and what the running capture loop stamped onto its own evidence.
    """
    registry = _load_json(COHORT_REGISTRY)
    if registry is None:
        return FAIL, "forward_paper_cohort_registry.json is missing or unreadable", {}
    if runtime is not None and runtime.role:
        # Bound: compare against exactly the instance this runtime declares.
        # select_instance refuses unknown, duplicated and CLOSED rows.
        try:
            frozen = [fp_capture.select_instance(runtime.role, registry)]
        except fp_capture.InstanceSelectionError as exc:
            return FAIL, f"the runtime names an unusable instance: {exc}", {}
    else:
        frozen = [
            item
            for item in registry.get("instances", [])
            if (item.get("runtime_identity") or {}).get("strategy_sha256")
            and item.get("status") != "CLOSED"
        ]
    if not frozen:
        return UNPROVEN, (
            "the registry declares no frozen runtime identity to compare against "
            f"(paper_alpha_cohort={registry.get('paper_alpha_cohort')!r})"
        ), {}

    if runtime is None or not runtime.has_evidence:
        return UNPROVEN, "hash comparison requires the running instance; not executed here", {}

    # The runtime config is what the engine reads. Hashing only the committed
    # example meant a drifted config.json could not be detected, and a record
    # stamped with any config hash at all was accepted.
    # No fallback: when a runtime is attached, its configuration must exist and
    # be the one on disk. Falling back to the example made "validated config" and
    # "executed config" two different files.
    if not RUNTIME_CONFIG.is_file():
        return FAIL, (
            f"the runtime configuration {RUNTIME_CONFIG} does not exist, so the running instance's "
            "configuration identity cannot be established"
        ), {}
    runtime_config = RUNTIME_CONFIG
    on_disk = {
        "strategy_sha256": fp_capture.sha256_file(fp_capture.STRATEGY_PATH),
        "config_sha256": fp_capture.sha256_file(runtime_config),
    }

    ledgers = fp_ledger.open_ledgers(Path(runtime.evidence_dir))
    # Every ledger, not only decisions: a foreign input or incident record is
    # just as unattributable, and checking one ledger let the others through.
    live_records = [
        record
        for name in ("input", "decision", "trade", "incident")
        for record in ledgers[name].records()
        if not record.payload.get("erratum")
    ]
    if runtime.role:
        stamped_roles = {(r.payload.get("identity") or {}).get("role") for r in live_records}
        # A record with no role is not "not contradicting" — it is unattributable,
        # and discarding it turned a missing stamp into a pass.
        if live_records and None in stamped_roles:
            missing = [r.seq for r in live_records if not (r.payload.get("identity") or {}).get("role")]
            return FAIL, (
                f"{len(missing)} record(s) in {runtime.evidence_dir} carry no role and cannot be "
                f"attributed to {runtime.role}: seq {missing[:5]}"
            ), {}
        if stamped_roles and stamped_roles != {runtime.role}:
            return FAIL, (
                f"the evidence in {runtime.evidence_dir} was written by {sorted(stamped_roles)}, "
                f"not by {runtime.role}"
            ), {}
        stamped_cohorts = {(r.payload.get("identity") or {}).get("cohort_id") for r in live_records}
        declared_cohort = frozen[0].get("cohort_id")
        if stamped_cohorts - {declared_cohort}:
            return FAIL, (
                f"the evidence carries cohort ids {sorted(c for c in stamped_cohorts if c)} that the "
                f"registry does not declare for {runtime.role} ({declared_cohort})"
            ), {}
    stamped = {
        (r.payload.get("identity") or {}).get("strategy_sha256")
        for r in live_records
    }
    stamped.discard(None)
    if not stamped:
        return UNPROVEN, "the runtime has stamped no strategy hash onto its evidence yet", {}
    if len(stamped) > 1:
        return FAIL, f"the running instance changed strategy hash mid-run: {sorted(stamped)}", {}

    stamped_configs = {(r.payload.get("identity") or {}).get("config_sha256") for r in live_records}
    stamped_configs.discard(None)
    if stamped_configs and stamped_configs != {on_disk["config_sha256"]}:
        return FAIL, (
            f"the evidence was written against config hash(es) {sorted(s[:12] for s in stamped_configs)}, "
            f"but {runtime_config.name} hashes to {on_disk['config_sha256'][:12]}"
        ), {}

    mismatches = []
    for item in frozen:
        identity = item.get("runtime_identity") or {}
        for field, actual in on_disk.items():
            declared = identity.get(field)
            if declared and actual and declared != actual:
                mismatches.append(f"{item.get('role')}.{field}: registry {declared[:12]} vs on-disk {actual[:12]}")
        declared_strategy = identity.get("strategy_sha256")
        running = next(iter(stamped))
        if declared_strategy and running != declared_strategy:
            mismatches.append(
                f"{item.get('role')}.strategy_sha256: registry {declared_strategy[:12]} vs running {running[:12]}"
            )
    if mismatches:
        return FAIL, "runtime identity does not match the frozen registry: " + "; ".join(mismatches[:3]), {}

    return (
        PASS,
        f"registry, working tree and the running instance agree: strategy {on_disk['strategy_sha256'][:12]}..., "
        f"config {on_disk['config_sha256'][:12]}... across {len(frozen)} frozen instance(s)",
        {"runtime_hashes": {"on_disk": on_disk, "running_strategy_sha256": next(iter(stamped))}},
    )


def _check_market_data_ingestion(runtime: RuntimeContext | None = None) -> tuple[str, str, dict]:
    """Section 16.6 — does real market-data ingestion work?

    Two things must both hold, and proving only one would be the easy mistake:
    the route must be reachable *now*, and candles must actually have been
    ingested through it into the evidence. A reachable host with an empty input
    ledger is not ingestion.
    """
    if runtime is None or not runtime.check_market_route:
        return UNPROVEN, (
            "no paper runtime is attached. Ingestion must be proven on a host that has the exchange route."
        ), {}

    probes = fp_market.probe_hosts()
    reachable = [item for item in probes if item.get("reachable")]
    if not reachable:
        return FAIL, f"S8: no public market host is reachable: {probes}", {"market_probe": probes}

    if not runtime.has_evidence:
        return UNPROVEN, (
            f"the market route is reachable ({', '.join(item['host'] for item in reachable)}) but no "
            "evidence directory was given, so nothing proves a candle was ingested through it"
        ), {"market_probe": probes}

    facts = _real_records(Path(runtime.evidence_dir))
    if not facts["inputs"]:
        return FAIL, "the market route is reachable but the input ledger is empty: nothing was ingested", {
            "market_probe": probes
        }
    if not facts["exchange_sourced"]:
        return FAIL, (
            f"captured inputs do not all come from the live exchange route: sources {facts['sources']}"
        ), {"market_probe": probes}

    newest = max(r.payload.get("receive_ts_ms", 0) for r in facts["inputs"])
    lags = [r.payload.get("receive_lag_ms") for r in facts["inputs"] if r.payload.get("receive_lag_ms") is not None]
    return (
        PASS,
        f"{len(reachable)} of {len(probes)} public hosts reachable; {len(facts['inputs'])} candles ingested "
        f"for {', '.join(facts['pairs'])} through {', '.join(sorted(facts['hosts']))}, newest received "
        f"{fp_market.iso_from_ms(newest)}, minimum receipt lag {min(lags) if lags else 'n/a'} ms",
        {
            "market_probe": probes,
            "ingested_candles": len(facts["inputs"]),
            "ingest_pairs": facts["pairs"],
        },
    )


def _check_external_features() -> tuple[str, str]:
    return PASS, (
        "BASELINE-1 requires no external non-market feature: its only decision-time input is the closed 1h "
        "OHLCV candle, so section 6's post-facto-archive hazard does not arise for this candidate"
    )


def _check_input_ledger_real(runtime: RuntimeContext) -> tuple[str, str, dict]:
    """Section 16.8 on real incoming data, when a runtime supplied some.

    The synthetic path below proves the mechanism. This proves the requirement:
    that the mechanism ran against candles an exchange actually sent.
    """
    facts = _real_records(Path(runtime.evidence_dir))
    inputs = facts["inputs"]
    if not inputs:
        return FAIL, "the runtime evidence directory holds no input records", {}
    if not facts["exchange_sourced"]:
        return FAIL, f"captured inputs are not all exchange-sourced: {facts['sources']}", {}

    problems = facts["ledgers"]["input"].verify()
    if problems:
        return FAIL, "; ".join(problems[:3]), {}

    # Negative control against the real ledger: altering a captured candle must
    # break the chain. Proving it on real evidence, not only on a synthetic
    # copy, is the point of this check.
    lines = facts["ledgers"]["input"].raw_text().splitlines()
    target = len(lines) // 2
    record = json.loads(lines[target])
    record["payload"]["candle"]["close"] = float(record["payload"]["candle"]["close"]) + 1.0
    lines[target] = json.dumps(record, sort_keys=True, ensure_ascii=False)
    # The negative control is written to a throwaway temporary directory, never
    # into the evidence lane it is testing. A gate that writes a file named
    # "tampered_..." into a cohort's own lane is one crash away from leaving it
    # there, and the directory it was handed might not even be the lane it
    # belongs to.
    with tempfile.TemporaryDirectory(prefix="fp-preflight-tamper-") as scratch:
        tampered_path = Path(scratch) / "tampered_real_input.jsonl"
        tampered_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        detected = bool(fp_ledger.Ledger(tampered_path, "input").verify())
    if not detected:
        return FAIL, "the input ledger did not detect an altered real candle payload", {}

    missing_ts = [
        r.seq for r in inputs
        if not isinstance(r.payload.get("source_ts_ms"), int)
        or not isinstance(r.payload.get("receive_ts_ms"), int)
    ]
    if missing_ts:
        return FAIL, f"real input records without both timestamps: {missing_ts[:5]}", {}

    return (
        PASS,
        f"{len(inputs)} candles captured from {fp_market.SOURCE_ID} for {', '.join(facts['pairs'])}; the "
        "chain verifies, every record carries both a source and a receive timestamp, and altering a real "
        "captured candle is detected",
        {
            "input_records": len(inputs),
            "input_tip": facts["ledgers"]["input"].tip_digest(),
            "input_sample": "real",
            "mechanism_input_ledger": PASS,
        },
    )


def _check_input_ledger(evidence_dir: Path) -> tuple[str, str, dict]:
    input_ledger, _, count = _capture_sample(evidence_dir)
    problems = input_ledger.verify()
    if problems:
        return FAIL, "; ".join(problems[:3]), {}

    # Negative control: an altered payload must break the chain. The lines are
    # read through the lane like any other evidence read, and the altered copy
    # is built in a throwaway directory — a gate that leaves a file named
    # "tampered_*" inside a cohort's own lane is one crash away from leaving it
    # there permanently.
    text = input_ledger.raw_text().splitlines()
    record = json.loads(text[10])
    record["payload"]["candle"]["close"] = record["payload"]["candle"]["close"] + 1
    text[10] = json.dumps(record, sort_keys=True, ensure_ascii=False)
    with tempfile.TemporaryDirectory(prefix="fp-preflight-tamper-") as scratch:
        tampered = Path(scratch) / "tampered_input.jsonl"
        tampered.write_text("\n".join(text) + "\n", encoding="utf-8")
        detected = bool(fp_ledger.Ledger(tampered, "input").verify())
    if not detected:
        return FAIL, "the input ledger did not detect an altered candle payload", {}

    return (
        UNPROVEN,
        f"the mechanism works: {count} as-seen candles captured and chain-verified, and an altered payload "
        "is detected. But section 16.8 requires the input ledger to work on *real incoming data*, and every "
        "candle in this sample is synthetic. This is FP_INFRASTRUCTURE_SCAFFOLD_VALIDATION, not "
        "FP_RUNTIME_READINESS: no candle here came from an exchange.",
        {
            "input_records": count,
            "input_tip": input_ledger.tip_digest(),
            "input_sample": "synthetic",
            "mechanism_input_ledger": PASS,
        },
    )


def _check_decision_ledger(evidence_dir: Path) -> tuple[str, str, dict]:
    ledgers = fp_ledger.open_ledgers(evidence_dir)
    decision = ledgers["decision"]
    problems = decision.verify()
    if problems:
        return FAIL, "; ".join(problems[:3]), {}
    records = decision.records()
    if not records:
        return FAIL, "no decisions were recorded", {}

    erratum = decision.append_erratum(records[0].seq, "preflight erratum self-test", {"note": "no-op"})
    if decision.verify():
        return FAIL, "appending an erratum broke the decision chain", {}
    if decision.records()[0].digest != records[0].digest:
        return FAIL, "the erratum rewrote the record it corrects", {}

    return (
        PASS,
        f"{len(records)} decisions recorded append-only; an erratum at seq {erratum.seq} corrects "
        f"seq {records[0].seq} without rewriting it",
        {
            "decision_records": len(records),
            "decision_tip": decision.tip_digest(),
            "mechanism_decision_ledger": PASS,
        },
    )


def _check_db_isolation() -> tuple[str, str]:
    registry = _load_json(COHORT_REGISTRY)
    if registry is None:
        return FAIL, "forward_paper_cohort_registry.json is missing or unreadable"
    instances = registry.get("instances", [])
    fields = ("db_path", "bot_name", "log_path", "evidence_dir")
    declared = [
        {field: (item.get("runtime_identity") or {}).get(field) for field in fields} for item in instances
    ]
    populated = [item for item in declared if any(item.values())]
    if not populated:
        return UNPROVEN, "no instance declares a db_path/bot_name/log_path/evidence_dir to check for collisions"
    for field in fields:
        values = [item[field] for item in populated if item[field]]
        if len(values) != len(set(values)):
            return FAIL, f"two instances share the same {field}; section 14 forbids shared mutable state"

    # Same-field equality is the weakest form of the question. Two lanes also
    # collide when one path contains the other, and when one instance's log path
    # sits inside another's evidence directory — so every path field is compared
    # against every other instance's path fields, in both directions.
    path_fields = ("db_path", "log_path", "evidence_dir")
    for i, first in enumerate(populated):
        for second in populated[i + 1:]:
            for field_a in path_fields:
                for field_b in path_fields:
                    a, b = first[field_a], second[field_b]
                    if not a or not b:
                        continue
                    if fp_capture._collides(Path(a), Path(b)):
                        return FAIL, (
                            f"instance paths overlap: {field_a} {a} and {field_b} {b} are the same lane; "
                            "section 14 forbids shared mutable state"
                        )
    return PASS, f"{len(populated)} instances declare distinct, non-overlapping {', '.join(fields)}"


def _check_monitoring(runtime: RuntimeContext | None = None) -> tuple[str, str, dict]:
    """Section 16.11 / 18 — is monitoring alive?

    Section 18 keeps monitoring health and candidate-runtime health apart, so
    both are probed and both are reported. A live exporter in front of a dead
    bot is not a healthy runtime, and saying so requires asking twice.
    """
    if runtime is None or not (runtime.exporter_url or runtime.freqtrade_url):
        return UNPROVEN, (
            "the exporter image builds and serves /metrics in CI, but 'monitoring is alive' is a statement "
            "about a running instance. Section 18: monitoring health and candidate-runtime health are "
            "distinct states, and neither is observable here."
        ), {}

    probes: dict = {}
    failures: list[str] = []

    if runtime.exporter_url:
        ok, detail = _http_ok(runtime.exporter_url)
        probes["exporter"] = {"url": runtime.exporter_url, "ok": ok, "detail": detail}
        if not ok:
            failures.append(f"exporter {runtime.exporter_url}: {detail}")

    if runtime.prometheus_url:
        ok, detail = _http_ok(runtime.prometheus_url)
        probes["prometheus"] = {"url": runtime.prometheus_url, "ok": ok, "detail": detail}
        if not ok:
            failures.append(f"prometheus {runtime.prometheus_url}: {detail}")

    client = runtime.client()
    if client is not None:
        try:
            probes["freqtrade_ping"] = client.ping()
        except Exception as exc:  # noqa: BLE001
            probes["freqtrade_ping"] = {"error": str(exc)[:200]}
            failures.append(f"freqtrade API: {exc}")

    if failures:
        return FAIL, "monitoring is not alive: " + "; ".join(failures[:3]), {"monitoring": probes}
    return (
        PASS,
        "monitoring and candidate runtime are separately alive: "
        + ", ".join(f"{name} ok" for name in probes),
        {"monitoring": probes},
    )


def _check_replay_real(runtime: RuntimeContext) -> tuple[str, str, dict]:
    """Section 16.12 — event-time replay on a bounded *real-data* sample."""
    # The runtime names its role; reconciliation must judge the evidence as that
    # instance's, not as anyone's.
    report = fp_reconcile.reconcile(Path(runtime.evidence_dir), expected_role=runtime.role)
    if report["reconciliation"] != PASS:
        return FAIL, f"reconciliation of the real capture failed: {report['failing_checks']}", {
            "reconciliation": report["reconciliation"],
            "failing_checks": report["failing_checks"],
        }

    replays = report["replays"]
    compared = sum(item.get("decisions_compared", 0) for item in replays.values())
    if compared == 0:
        return FAIL, "no decision was replayed against the captured inputs", {}

    # Negative control on the real sample: flip one recorded action and require
    # the replay to catch it.
    ledgers = fp_ledger.open_ledgers(Path(runtime.evidence_dir))
    inputs = [r for r in ledgers["input"].records() if not r.payload.get("erratum")]
    decisions = [r for r in ledgers["decision"].records() if not r.payload.get("erratum")]
    pair = report["pairs"][0]
    corrupted, flipped = [], False
    for record in decisions:
        payload = dict(record.payload)
        if payload.get("pair") == pair and not flipped and payload.get("intended_action") == fp_replay.ACTION_HOLD:
            payload["intended_action"] = fp_replay.ACTION_ENTER_LONG
            flipped = True
        corrupted.append(
            fp_ledger.Record(record.seq, record.kind, record.recorded_utc, record.prev_digest, record.digest, payload)
        )
    if not flipped:
        return FAIL, "the real sample contained no bar to use as a negative control", {}
    negative = fp_replay.event_time_replay(inputs, corrupted, pair)
    if negative["status"] == PASS:
        return FAIL, "event-time replay accepted a decision that contradicts the frozen logic", {}

    return (
        PASS,
        f"{compared} decisions replayed from real captured inputs across {', '.join(report['pairs'])} with "
        f"0 mismatches, and a single flipped action is detected ({negative['mismatch_count']} mismatch). "
        f"EMA parity vs TA-Lib is {fp_replay.EMA_PARITY_STATUS}, which per section 14 means "
        "EMA_IMPLEMENTATION_PARITY = PASS only: it does not prove exchange-input, strategy-level, "
        "position-state or execution parity.",
        {
            "decisions_compared": compared,
            "negative_control": "detected",
            "replay_sample": "real",
            "reconciliation": report["reconciliation"],
            "daily_pack_digest": report["daily_pack_digest"],
            "mechanism_event_time_replay": PASS,
        },
    )


def _check_replay(evidence_dir: Path) -> tuple[str, str, dict]:
    ledgers = fp_ledger.open_ledgers(evidence_dir)
    inputs = ledgers["input"].records()
    decisions = [r for r in ledgers["decision"].records() if not r.payload.get("erratum")]

    report = fp_replay.event_time_replay(inputs, decisions, "BTC/USDT")
    if report["status"] != PASS:
        return FAIL, f"event-time replay failed on its own captured sample: {report['mismatches'][:2]}", {}

    # Negative control: flip one recorded action and require the gate to fail.
    corrupted = []
    flipped = False
    for record in decisions:
        payload = dict(record.payload)
        if not flipped and payload["intended_action"] == fp_replay.ACTION_ENTER_LONG:
            payload["intended_action"] = fp_replay.ACTION_HOLD
            flipped = True
        corrupted.append(fp_ledger.Record(record.seq, record.kind, record.recorded_utc, record.prev_digest, record.digest, payload))
    if not flipped:
        return FAIL, "the synthetic sample produced no entry signal, so the negative control cannot run", {}

    negative = fp_replay.event_time_replay(inputs, corrupted, "BTC/USDT")
    if negative["status"] == PASS:
        return FAIL, "event-time replay accepted a decision that contradicts the frozen logic", {}

    return (
        UNPROVEN,
        f"the mechanism works: {report['decisions_compared']} decisions replayed from the as-seen inputs "
        f"with 0 mismatches, and a single flipped action is detected ({negative['mismatch_count']} "
        "mismatch). But section 16.12 requires a bounded *real-data* sample, and this one is synthetic. "
        f"EMA parity vs TA-Lib is {fp_replay.EMA_PARITY_STATUS}, which per section 14 means "
        "EMA_IMPLEMENTATION_PARITY = PASS only: it does not prove exchange-input, strategy-level, "
        "position-state or execution parity.",
        {
            "decisions_compared": report["decisions_compared"],
            "negative_control": "detected",
            "replay_sample": "synthetic",
            "mechanism_event_time_replay": PASS,
        },
    )


def _check_duplicate_instance(runtime: RuntimeContext | None = None) -> tuple[str, str, dict]:
    """Section 16.13 — is duplicate-instance risk excluded?

    Registry-level role uniqueness is necessary but weak: two processes can
    share a role by accident. So when a runtime is present, process-level
    exclusion is *demonstrated* — a second writer is attempted against the live
    evidence directory and must be refused.
    """
    registry = _load_json(COHORT_REGISTRY)
    if registry is None:
        return FAIL, "forward_paper_cohort_registry.json is missing or unreadable", {}
    instances = registry.get("instances", [])
    all_roles = [item.get("role") for item in instances]
    if len(all_roles) != len(set(all_roles)):
        # Checking only RUNNING rows was too narrow: a duplicated role makes
        # selection ambiguous before anything starts, and ambiguity is what lets
        # a runtime pick up the wrong identity.
        return FAIL, f"two instances share a role: {sorted(r for r in all_roles if r)}", {}
    running = [item for item in instances if item.get("status") == "RUNNING"]

    if runtime is None or not runtime.has_evidence:
        if not running:
            return UNPROVEN, (
                "no instance is running, so duplicate-instance risk cannot be observed. A single-writer lock "
                "on each db_path must be demonstrated before T0."
            ), {}
        return UNPROVEN, "role uniqueness holds in the registry, but process-level exclusion was not observed", {}

    evidence_dir = Path(runtime.evidence_dir)
    lock_path = evidence_dir / fp_capture.LOCK_FILENAME
    held_by_live_runtime = False
    try:
        probe = fp_capture.EvidenceLock(evidence_dir).acquire()
    except fp_capture.DuplicateInstanceError as exc:
        # The best possible evidence: a live capture loop already holds it and
        # this second attempt was refused.
        held_by_live_runtime = True
        detail = str(exc)
    else:
        probe.release()
        detail = "no live holder; exclusion demonstrated against a self-acquired lock"

    if not held_by_live_runtime:
        # Demonstrate it anyway rather than merely asserting the mechanism.
        first = fp_capture.EvidenceLock(evidence_dir).acquire()
        try:
            try:
                second = fp_capture.EvidenceLock(evidence_dir).acquire()
            except fp_capture.DuplicateInstanceError:
                excluded = True
            else:
                second.release()
                excluded = False
        finally:
            first.release()
        if not excluded:
            return FAIL, f"a second writer was able to open {lock_path}: single-writer exclusion is absent", {}

    return (
        PASS,
        f"role uniqueness holds in the registry ({len(running)} running) and process-level exclusion is "
        f"demonstrated on {lock_path}: {detail}",
        {"duplicate_instance": {"lock_path": str(lock_path), "held_by_live_runtime": held_by_live_runtime}},
    )


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------


def run(evidence_dir: Path | None = None, runtime: RuntimeContext | None = None) -> dict:
    """Run the sixteen preflight checks.

    ``evidence_dir`` is scratch space for the synthetic self-tests. ``runtime``
    is entirely separate: it points at a *live* paper instance, and when it is
    given, the checks that section 16 requires to be proven against a real
    runtime are answered from that runtime instead of reporting UNPROVEN. With
    no runtime — the CI case — behaviour is unchanged, which is the point: the
    gate must not become easier to pass by being run somewhere with less
    evidence available.
    """
    # A runtime that names a role must be the lane that role declares, and the
    # records in it must carry that role. Accepting an unbound or mismatched
    # runtime is how evidence from one instance ends up answering another's gate.
    if runtime is not None and runtime.has_evidence:
        if not runtime.role:
            raise ValueError("a runtime with evidence must name its role")
        fp_capture.assert_evidence_dir_is_declared(runtime.role, Path(runtime.evidence_dir))

    temp_dir = None
    if evidence_dir is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="fp-preflight-"))
        evidence_dir = temp_dir

    live = runtime if (runtime is not None and runtime.has_evidence) else None

    try:
        details: dict = {}
        # The synthetic mechanism self-tests always run: they are what
        # FP_INFRASTRUCTURE_SCAFFOLD_VALIDATION reports on, and a live runtime
        # does not excuse the scaffold from proving its own mechanisms.
        input_result, input_evidence, input_extra = _check_input_ledger(evidence_dir)
        details.update(input_extra)
        decision_result, decision_evidence, decision_extra = _check_decision_ledger(evidence_dir)
        details.update(decision_extra)
        replay_result, replay_evidence, replay_extra = _check_replay(evidence_dir)
        details.update(replay_extra)
        # Persistence and the restart drill must run last: both read back what the
        # checks above wrote, and the restart drill appends to the decision ledger.
        persistence_result, persistence_evidence, persistence_extra = _check_evidence_persistence(evidence_dir)
        details.update(persistence_extra)
        restart_result, restart_evidence, restart_extra = _check_restart_drill(evidence_dir)
        details.update(restart_extra)

        # Where a live runtime exists, its verdict replaces the synthetic one for
        # the three checks section 16 says must be about real data, and for the
        # real restart drill. The synthetic mechanism verdicts survive in
        # ``details`` regardless.
        if live is not None:
            real_input_result, real_input_evidence, real_input_extra = _check_input_ledger_real(live)
            details.update(real_input_extra)
            input_result, input_evidence = real_input_result, real_input_evidence

            real_replay_result, real_replay_evidence, real_replay_extra = _check_replay_real(live)
            details.update(real_replay_extra)
            replay_result, replay_evidence = real_replay_result, real_replay_evidence

            real_restart_result, real_restart_evidence, real_restart_extra = _check_restart_drill_real(live)
            details.update(real_restart_extra)
            restart_result, restart_evidence = real_restart_result, real_restart_evidence

        def _drop_extra(outcome):
            result, evidence, extra = outcome
            details.update(extra)
            return result, evidence

        outcomes = [
            _check_guard(runtime),
            _check_dry_run(runtime),
            _check_spot_mode(runtime),
            _check_no_secret(runtime),
            _drop_extra(_check_hashes_match_registry(runtime)),
            _drop_extra(_check_market_data_ingestion(runtime)),
            _check_external_features(),
            (input_result, input_evidence),
            (decision_result, decision_evidence),
            _check_db_isolation(),
            _drop_extra(_check_monitoring(runtime)),
            (replay_result, replay_evidence),
            _drop_extra(_check_duplicate_instance(runtime)),
            _drop_extra(_check_clock_tolerance(runtime)),
            (persistence_result, persistence_evidence),
            (restart_result, restart_evidence),
        ]
    finally:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)

    checks = [
        {"id": index + 1, "check": CHECKS[index], "result": result, "evidence": evidence}
        for index, (result, evidence) in enumerate(outcomes)
    ]
    blocking = [item["id"] for item in checks if item["result"] != PASS]
    status = PASS if not blocking else "BLOCKED"

    # Section 1.3 draws the distinction this report must not blur: the scaffold
    # mechanisms can be validated here, runtime readiness cannot. Each mechanism
    # check reports its own verdict rather than having it inferred from prose.
    mechanism_verdicts = {k: v for k, v in details.items() if k.startswith("mechanism_")}
    missing = set(MECHANISM_KEYS) - set(mechanism_verdicts)
    if missing or any(v != PASS for v in mechanism_verdicts.values()):
        scaffold_validation = FAIL
    else:
        scaffold_validation = PASS

    return {
        "spec_version": "TL-FP-BOOT-1 v2.0 FINAL 2026-09-07",
        "evaluated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checks": checks,
        "blocking_checks": blocking,
        "preflight": status,
        "t0_permitted": status == PASS,
        "fp_infrastructure_scaffold_validation": scaffold_validation,
        "mechanism_verdicts": mechanism_verdicts,
        "fp_runtime_readiness": PASS if status == PASS else "NOT_PROVEN",
        "details": details,
        "real_money_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--require-pass", action="store_true", help="exit 2 unless every check passes")
    parser.add_argument(
        "--evidence-dir",
        default=None,
        help="a live capture-loop evidence directory; enables the real-runtime checks",
    )
    parser.add_argument(
        "--role",
        default=None,
        help=(
            "the registry instance the attached runtime is. Required whenever --evidence-dir is given: "
            "an unbound runtime would be compared against every hashed row, closed ones included."
        ),
    )
    parser.add_argument("--freqtrade-url", default=os.environ.get("FREQTRADE_URL") or None)
    parser.add_argument("--api-user", default=os.environ.get("FREQTRADE_API_USER") or None)
    parser.add_argument("--api-password", default=os.environ.get("FREQTRADE_API_PASSWORD") or None)
    parser.add_argument("--exporter-url", default=os.environ.get("EXPORTER_URL") or None)
    parser.add_argument("--prometheus-url", default=os.environ.get("PROMETHEUS_URL") or None)
    parser.add_argument(
        "--check-market-route",
        action="store_true",
        help="probe the public market route and measure clock skew against the exchange",
    )
    args = parser.parse_args(argv)

    # Role validation happens before anything else and regardless of which other
    # flags were passed: a refusal that only fires when a runtime happens to be
    # attached is not a gate.
    if args.role:
        try:
            fp_capture.select_instance(args.role)
        except fp_capture.InstanceSelectionError as exc:
            print(f"PREFLIGHT_REFUSED: {exc}", file=sys.stderr)
            return 2

    runtime = None
    if any(
        (args.evidence_dir, args.role, args.freqtrade_url, args.exporter_url, args.prometheus_url,
         args.check_market_route)
    ):
        if args.evidence_dir and not args.role:
            print(
                "PREFLIGHT_REFUSED: --evidence-dir requires --role, so the runtime is compared against "
                "the instance it actually is",
                file=sys.stderr,
            )
            return 2
        runtime = RuntimeContext(
            evidence_dir=Path(args.evidence_dir) if args.evidence_dir else None,
            role=args.role,
            freqtrade_url=args.freqtrade_url,
            api_user=args.api_user,
            api_password=args.api_password,
            exporter_url=args.exporter_url,
            prometheus_url=args.prometheus_url,
            check_market_route=args.check_market_route,
        )

    report = run(runtime=runtime)

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"FP-BOOT-1 preflight — {report['evaluated_utc']}")
        for item in report["checks"]:
            print(f"  [{item['result']:>8}] {item['id']:>2}. {item['check']}")
            print(f"             {item['evidence']}")
        print()
        print(f"PREFLIGHT = {report['preflight']}")
        print(f"T0_PERMITTED = {'YES' if report['t0_permitted'] else 'NO'}")
        print(f"FP_INFRASTRUCTURE_SCAFFOLD_VALIDATION = {report['fp_infrastructure_scaffold_validation']}")
        print(f"FP_RUNTIME_READINESS = {report['fp_runtime_readiness']}")

    if args.require_pass and not report["t0_permitted"]:
        print(
            f"PREFLIGHT_BLOCKED: checks {report['blocking_checks']} are not PASS; no candidate T0 may be created.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
