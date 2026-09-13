"""The as-seen capture loop (FP-CONTROL-1 activation pack section 0.1).

The pack names this the one missing piece: the scaffold has ledgers, a replay
reference, an admission gate and a paper stack, but nothing binds a *running*
Freqtrade dry-run to ``paper_input_ledger`` and ``paper_decision_ledger``.
Without it, preflight checks 5, 6, 8, 10, 11, 12, 13, 14 and 16 stay UNPROVEN
and stop condition S19 holds. This module closes exactly that gap and nothing
else.

What it must not do is as important as what it does. BASELINE-1 is frozen: this
loop never imports the strategy, never sets a threshold, never places an order
and never edits a config. It observes. The decision it records is derived by
``research/fp/replay.py``, whose parameters are read out of the frozen strategy
file by AST, and the trades it records are read back from Freqtrade's read-only
API. Divergence between the two is *evidence*, so it is recorded as an incident
rather than repaired.

The evidence chain, in the order the pack requires it:

    real public candle      -> paper_input_ledger    (market.py, both timestamps)
    frozen-logic decision   -> paper_decision_ledger (replay.py, linked by market_event_id)
    risk / admission        -> carried on the decision record
    paper order / fill      -> paper_trade_ledger    (Freqtrade read-only API)
    position transition     -> paper_trade_ledger
    exit / realised PnL     -> paper_trade_ledger
    anything unexpected     -> paper_incident_ledger

Idempotence is the property that makes restart safe, and it is enforced by
reconstructing state *from the ledgers themselves* rather than from a sidecar
cursor file. A cursor can disagree with the evidence; the evidence cannot
disagree with itself. So on every start the loop replays its own ledgers, learns
which market events it already captured and which bars it already decided, and
refuses to write either again.

Public market data only. No credential is read, sent, or accepted, and no code
path here can place an order.
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from fp import ledger as fp_ledger  # noqa: E402
from fp import market as fp_market  # noqa: E402
from fp import replay as fp_replay  # noqa: E402

CAPTURE_ENGINE_VERSION = "FP_CAPTURE_LOOP_V1"

# Freqtrade's dry-run fill semantics, named so the evidence records *simulation*
# semantics rather than implying live-fill truth. The activation pack lists
# PAPER_FILL_MODEL_VERSION as genuinely unbound; this is its binding, and it is
# a description of the engine's behaviour, not a tunable.
PAPER_FILL_MODEL_VERSION = "FREQTRADE_2026.7_DRYRUN_ORDERBOOK_V1"
PAPER_FILL_MODEL_SEMANTICS = (
    "Freqtrade dry-run simulation: entry and exit prices are taken from the live order book "
    "(entry_pricing/exit_pricing price_side='other', order_book_top=1); fills are simulated "
    "immediately at that price with fee=0.001 per side and no slippage, latency or partial-fill "
    "model. These are simulation semantics and are not evidence of live fill quality."
)

STRATEGY_PATH = REPO_ROOT / "freqtrade" / "user_data" / "strategies" / "BaselineEmaRegimeV1.py"
DEFAULT_CONFIG_PATH = REPO_ROOT / "freqtrade" / "user_data" / "config.paper.json.example"
COHORT_REGISTRY = REPO_ROOT / "research" / "fp" / "records" / "forward_paper_cohort_registry.json"

LOCK_FILENAME = ".fp_capture.lock"
STATE_FILENAME = "capture_runtime.json"

ADMIT_OK = "ADMITTED"
ADMIT_BLOCKED = "BLOCKED"
ADMIT_NOT_REQUIRED = "NOT_REQUIRED"
# A bar recovered from backfill is indicator warm-up, not a decision the runtime
# could have acted on. Section A9 of the activation pack keeps that boundary
# explicit: PRE_T0 initialises state and contributes no PnL and no outcome
# claim. Recording such a bar as "BLOCKED" would misfile a bar that was never
# executable as one that risk refused.
ADMIT_WARMUP = "WARMUP_NOT_EXECUTABLE"

BAR_WARMUP = "WARMUP"
BAR_LIVE = "LIVE"


class CaptureError(RuntimeError):
    """Raised when the capture loop cannot run safely."""


class InstanceSelectionError(CaptureError):
    """The registry cannot name exactly one runnable instance for a role.

    Selection fails closed for every ambiguity. A loop that silently fell back
    to "the first row" would, the moment a cohort closed and a successor was
    registered, start stamping a closed cohort's identity onto new evidence —
    which is the one failure the closure record exists to prevent.
    """


class DuplicateInstanceError(CaptureError):
    """Raised when another capture process already holds this evidence directory."""


def utc_now() -> str:
    return fp_ledger.utc_now()


def sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def git_commit() -> str:
    """The commit this runtime was built from.

    ``FP_SOURCE_COMMIT`` takes precedence because the capture container has no
    git binary and no .git directory: the commit is stamped in by whoever
    started the runtime. Falling back to git keeps the module usable from a
    developer checkout, and the all-zero sentinel makes "unknown" visible in the
    evidence rather than plausible.
    """
    from_env = os.environ.get("FP_SOURCE_COMMIT", "").strip()
    if from_env:
        return from_env
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:  # noqa: BLE001
        return "0" * 40


# --------------------------------------------------------------------------
# Runtime identity
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RuntimeIdentity:
    """Who wrote a record, under which frozen logic, in which run.

    Three identifiers, because they answer three different questions and
    collapsing them would lose evidence:

    ``runtime_id``  the persistent instance. Stable across restarts; two of
                    these pointing at one evidence directory is the
                    duplicate-instance hazard of section 16.13.
    ``run_id``      one process lifetime. A new one on every start, which is
                    what makes a restart visible in the ledger at all.
    ``cohort_id``   the frozen forward-paper cohort. ``None`` before T0, and
                    never invented by this module - it is read from the registry
                    once the Owner-authorised freeze has written it.
    """

    runtime_id: str
    run_id: str
    cohort_id: str | None
    role: str
    source_commit: str
    strategy_name: str
    strategy_sha256: str | None
    config_sha256: str | None
    engine_version: str
    capture_engine_version: str
    paper_fill_model_version: str
    bot_name: str
    evidence_dir: str
    db_path: str | None
    log_path: str | None
    host: str
    pid: int
    restart_counter: int = 0

    def as_payload(self) -> dict:
        data = asdict(self)
        return data

    def stamp(self) -> dict:
        """The compact identity carried on every record.

        The full identity is written once per run as a ``run_started``
        incident; repeating all of it on every candle would bloat the ledger
        without adding evidence, but a record whose author cannot be
        established is not evidence either, so this subset travels everywhere.
        """
        return {
            "runtime_id": self.runtime_id,
            "run_id": self.run_id,
            "cohort_id": self.cohort_id,
            "restart_counter": self.restart_counter,
            "source_commit": self.source_commit,
            "strategy_sha256": self.strategy_sha256,
            "config_sha256": self.config_sha256,
            "capture_engine_version": self.capture_engine_version,
        }


def select_instance(role: str, registry: dict | None = None) -> dict:
    """The one registry row a runtime may run as, or a hard failure.

    There is no default row and no first-row fallback: an unknown role, a
    duplicated role, and a CLOSED row each raise. A CLOSED row is refused
    because its cohort's evidence stream ended — appending to it would splice a
    new run onto a terminated one, and no later check could unpick that.
    """
    registry = registry if registry is not None else (_load_json(COHORT_REGISTRY) or {})
    matches = [item for item in registry.get("instances", []) if item.get("role") == role]
    if not matches:
        known = sorted({item.get("role") for item in registry.get("instances", [])} - {None})
        raise InstanceSelectionError(f"unknown instance role {role!r}; the registry declares {known}")
    if len(matches) > 1:
        raise InstanceSelectionError(
            f"ambiguous selection: {len(matches)} instances declare role {role!r}"
        )
    instance = matches[0]
    status = instance.get("status")
    if status == "CLOSED":
        raise InstanceSelectionError(
            f"{role} is CLOSED (cohort {instance.get('cohort_id')}, closed {instance.get('closed_utc')}): "
            "a closed cohort accepts no further capture or evidence"
        )
    return instance


def _collides(a: Path, b: Path) -> bool:
    """True when two paths are the same, or one contains the other.

    Prefix-string comparison is not enough: ``/x/fp-control-2`` and
    ``/x/fp-control-2-evil`` share a prefix and are different lanes, while
    ``/x/lane`` and ``/x/lane/nested`` do not look equal and are the same lane.
    Comparing resolved path *components* answers both correctly.
    """
    if a == b:
        return True
    return a in b.parents or b in a.parents


def assert_paths_are_exclusive(role: str, evidence_dir: Path, registry: dict | None = None) -> None:
    """Refuse a runtime that would write anywhere another instance declares.

    Every declared path field of every other instance is compared, in both
    directions, for equality and for containment — not only the evidence
    directory, and not by string prefix. Distinct paths in the registry are a
    declaration; this is the check that the process about to write honours it.
    """
    registry = registry if registry is not None else (_load_json(COHORT_REGISTRY) or {})
    resolved = Path(evidence_dir).resolve()
    for item in registry.get("instances", []):
        if item.get("role") == role:
            continue
        identity = item.get("runtime_identity") or {}
        for field in ("evidence_dir", "db_path", "log_path"):
            other = identity.get(field)
            if not other:
                continue
            if _collides(resolved, Path(other)):
                raise InstanceSelectionError(
                    f"{role} would write to {resolved}, which collides with {item.get('role')}.{field} "
                    f"({other})"
                )


def assert_evidence_dir_is_declared(role: str, evidence_dir: Path, registry: dict | None = None) -> None:
    """The runtime's evidence directory must be the one the registry declares.

    Collision-freedom alone permits an arbitrary third lane: a run could write to
    a path no instance declares, and its evidence would then belong to no
    registered instance at all. This is asserted by the launcher and the runtime
    entry point, where the real declared path is available — unit tests build
    loops in temporary directories on purpose, and they go through
    ``assert_paths_are_exclusive`` instead.
    """
    registry = registry if registry is not None else (_load_json(COHORT_REGISTRY) or {})
    instance = select_instance(role, registry)
    declared = (instance.get("runtime_identity") or {}).get("evidence_dir")
    if not declared:
        raise InstanceSelectionError(f"{role} declares no evidence_dir")
    if Path(evidence_dir).resolve() != Path(declared):
        raise InstanceSelectionError(
            f"{role} must write its evidence to the declared {declared}, not {Path(evidence_dir).resolve()}"
        )


def build_identity(
    evidence_dir: Path,
    config_path: Path = DEFAULT_CONFIG_PATH,
    *,
    role: str,
    restart_counter: int = 0,
) -> RuntimeIdentity:
    """The runtime identity of one selected instance, taken only from the registry.

    Every field that says *which cohort this is* — cohort_id, bot_name, db_path,
    log_path — comes from the selected row and from nowhere else. They used to be
    caller-overridable, which meant a caller could stamp a cohort id the registry
    never froze, or point a run at another instance's database, without the
    selection gate ever seeing it. A forged identity is indistinguishable from a
    real one once it is in a ledger, so the parameters are gone rather than
    guarded.
    """
    registry = _load_json(COHORT_REGISTRY) or {}
    instance = select_instance(role, registry)
    assert_paths_are_exclusive(role, evidence_dir, registry)
    identity = instance.get("runtime_identity") or {}
    resolved_bot = identity.get("bot_name")
    if not resolved_bot:
        raise InstanceSelectionError(f"{role} declares no bot_name; a runtime identity must be bound before use")
    return RuntimeIdentity(
        # The instance identity is the bot name: it is what a second process
        # would collide on, and it survives restarts by construction.
        runtime_id=f"{role}:{resolved_bot}",
        run_id=uuid.uuid4().hex,
        cohort_id=instance.get("cohort_id"),
        role=role,
        source_commit=git_commit(),
        strategy_name=STRATEGY_PATH.stem,
        strategy_sha256=sha256_file(STRATEGY_PATH),
        config_sha256=sha256_file(config_path),
        engine_version=identity.get("engine_version") or "freqtradeorg/freqtrade:2026.7",
        capture_engine_version=CAPTURE_ENGINE_VERSION,
        paper_fill_model_version=PAPER_FILL_MODEL_VERSION,
        bot_name=resolved_bot,
        evidence_dir=str(evidence_dir),
        db_path=identity.get("db_path"),
        log_path=identity.get("log_path"),
        host=socket.gethostname(),
        pid=os.getpid(),
        restart_counter=restart_counter,
    )


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _registry_t0_ms(role: str) -> int | None:
    """The frozen T0 for ``role``, in epoch ms, or None while it is unfrozen.

    Read rather than cached, and never written here: freezing T0 is an
    Owner-authorised act performed once, and a capture loop that could invent
    one could manufacture prospective evidence out of warm-up.
    """
    # Selection, not a scan: an unknown role, a duplicated role or a CLOSED row
    # raises here exactly as it does everywhere else. A malformed T0 also raises
    # rather than reading as unfrozen — "the boundary is unreadable" and "there
    # is no boundary" must never collapse into the same answer, because the
    # second one silently files post-T0 bars as qualification evidence.
    instance = select_instance(role)
    raw = instance.get("t0_utc")
    if not raw:
        # A NOT_STARTED successor carries no T0, and the loop may never write
        # one: t0_relation then reads T0_NOT_FROZEN and every captured bar is
        # qualification evidence, not prospective evidence.
        return None
    try:
        return int(
            datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ")
            .replace(tzinfo=timezone.utc)
            .timestamp()
            * 1000
        )
    except ValueError as exc:
        raise InstanceSelectionError(f"{role} declares an unparseable t0_utc {raw!r}") from exc


# --------------------------------------------------------------------------
# Single-writer lock (section 16.13 — no duplicate-instance risk)
# --------------------------------------------------------------------------


class EvidenceLock:
    """An advisory exclusive lock over one evidence directory.

    ``flock`` rather than a PID file, because a PID file left behind by a killed
    process blocks every later start until someone deletes it by hand, and
    "delete the lock and retry" is a habit that eventually deletes a live one.
    The kernel drops a ``flock`` when the holding process dies, so a crash
    self-heals while a genuine second instance is still refused.
    """

    def __init__(self, evidence_dir: Path) -> None:
        self.path = Path(evidence_dir) / LOCK_FILENAME
        self._handle = None

    def acquire(self, identity: RuntimeIdentity | None = None) -> "EvidenceLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.seek(0)
            holder = handle.read().strip()
            handle.close()
            raise DuplicateInstanceError(
                f"another capture process already holds {self.path}: {holder or 'unknown holder'}"
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "run_id": identity.run_id if identity else None,
                    "runtime_id": identity.runtime_id if identity else None,
                    "acquired_utc": utc_now(),
                }
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())
        self._handle = handle
        return self

    def release(self) -> None:
        if self._handle is not None:
            try:
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            finally:
                self._handle.close()
                self._handle = None

    def __enter__(self) -> "EvidenceLock":
        return self

    def __exit__(self, *exc_info) -> None:
        self.release()


# --------------------------------------------------------------------------
# Recovered state
# --------------------------------------------------------------------------


@dataclass
class RecoveredState:
    """What the ledgers say has already happened.

    Rebuilt on every start. This is the mechanism behind restart-recovery,
    duplicate-input handling and duplicate-decision rejection all at once: a
    thing already in the evidence is never written a second time.
    """

    captured_events: set[str] = field(default_factory=set)
    decided_bars: set[tuple[str, int]] = field(default_factory=set)
    recorded_trade_events: set[str] = field(default_factory=set)
    last_candle_ts: dict[str, int] = field(default_factory=dict)
    signal_state: dict[str, str] = field(default_factory=dict)
    open_positions: dict[str, dict] = field(default_factory=dict)
    prior_runs: list[str] = field(default_factory=list)
    input_records: int = 0
    decision_records: int = 0
    trade_records: int = 0

    @property
    def restart_counter(self) -> int:
        return len(self.prior_runs)


def recover_state(evidence_dir: Path) -> RecoveredState:
    """Reconstruct capture state by reading the ledgers back from disk."""
    ledgers = fp_ledger.open_ledgers(evidence_dir)
    state = RecoveredState()

    for record in ledgers["input"]:
        payload = record.payload
        if payload.get("erratum"):
            continue
        state.input_records += 1
        event_id = payload.get("market_event_id")
        if event_id:
            state.captured_events.add(event_id)
        pair = payload.get("pair")
        candle = payload.get("candle") or {}
        if pair and "ts" in candle:
            ts = int(candle["ts"])
            if ts > state.last_candle_ts.get(pair, -1):
                state.last_candle_ts[pair] = ts

    for record in ledgers["decision"]:
        payload = record.payload
        if payload.get("erratum"):
            continue
        state.decision_records += 1
        pair = payload.get("pair")
        if pair is None or "candle_ts" not in payload:
            continue
        state.decided_bars.add((pair, int(payload["candle_ts"])))
        if payload.get("signal_state"):
            state.signal_state[pair] = payload["signal_state"]

    for record in ledgers["trade"]:
        payload = record.payload
        if payload.get("erratum"):
            continue
        state.trade_records += 1
        event_id = payload.get("trade_event_id")
        if event_id:
            state.recorded_trade_events.add(event_id)
        if payload.get("event") == "position_opened" and payload.get("pair"):
            state.open_positions[payload["pair"]] = payload
        if payload.get("event") == "position_closed" and payload.get("pair"):
            state.open_positions.pop(payload["pair"], None)

    seen: list[str] = []
    for kind in ("incident", "input", "decision", "trade"):
        for record in ledgers[kind]:
            run_id = (record.payload.get("identity") or {}).get("run_id")
            if run_id and run_id not in seen:
                seen.append(run_id)
    state.prior_runs = seen
    return state


# --------------------------------------------------------------------------
# Input validation (malformed / missing-timestamp / out-of-order)
# --------------------------------------------------------------------------

REQUIRED_CANDLE_FIELDS = ("ts", "open", "high", "low", "close", "volume")


def validate_input_payload(payload: dict, last_ts: int | None = None) -> None:
    """Reject anything that must never reach the input ledger.

    Fails closed and loudly. A malformed market event that is silently dropped
    looks identical, in the evidence, to a market event that never arrived.
    """
    if not isinstance(payload, dict):
        raise CaptureError("input payload is not an object")
    for key in ("pair", "timeframe", "candle", "market_event_id"):
        if not payload.get(key):
            raise CaptureError(f"input payload is missing required field {key!r}")

    for key in ("source_ts_ms", "receive_ts_ms"):
        value = payload.get(key)
        if value is None:
            raise CaptureError(f"input payload is missing required timestamp {key!r}")
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise CaptureError(f"input payload has a non-positive-integer {key!r}: {value!r}")

    candle = payload.get("candle")
    if not isinstance(candle, dict):
        raise CaptureError("input payload candle is not an object")
    for key in REQUIRED_CANDLE_FIELDS:
        if key not in candle:
            raise CaptureError(f"input candle is missing required field {key!r}")
    if not isinstance(candle["ts"], int) or isinstance(candle["ts"], bool):
        raise CaptureError(f"input candle ts is not an integer: {candle['ts']!r}")

    o, h, l, c = (float(candle["open"]), float(candle["high"]), float(candle["low"]), float(candle["close"]))
    if not (l <= o <= h and l <= c <= h):
        raise CaptureError(f"input candle OHLC is inconsistent: o={o} h={h} l={l} c={c}")
    if float(candle["volume"]) < 0:
        raise CaptureError(f"input candle has negative volume: {candle['volume']!r}")

    if payload.get("candle_is_closed") is not True:
        raise CaptureError("input candle is not marked closed; an unclosed candle is not evidence")
    if payload["receive_ts_ms"] < payload["source_ts_ms"]:
        raise CaptureError(
            f"receive_ts_ms {payload['receive_ts_ms']} precedes source_ts_ms {payload['source_ts_ms']}: "
            "the candle would have been received before it closed"
        )
    if last_ts is not None and int(candle["ts"]) <= last_ts:
        raise CaptureError(
            f"out-of-order candle: ts {candle['ts']} is not newer than the last captured ts {last_ts}"
        )


# --------------------------------------------------------------------------
# Risk / admission on a decision
# --------------------------------------------------------------------------


def classify_bar(staleness_ms: int, timeframe_ms: int) -> str:
    """Is this a live decision bar, or indicator warm-up?

    One candle period is the boundary the feature contract already declares as
    maximum admissible staleness, so the same number decides both questions
    rather than two thresholds drifting apart.
    """
    return BAR_LIVE if staleness_ms <= timeframe_ms else BAR_WARMUP


def evaluate_admission(
    action: str,
    pair: str,
    config: dict,
    open_positions: dict[str, dict],
    staleness_ms: int,
    timeframe_ms: int,
    bar_class: str | None = None,
) -> dict:
    """Decide whether an intended entry may be admitted to paper execution.

    This is a *record* of the risk decision, not a controller: the loop places
    no orders, so blocking here blocks nothing in Freqtrade. Its value is that a
    later reconciliation can ask whether a paper entry Freqtrade actually took
    was one this gate would have admitted, and disagreement becomes an incident
    rather than a shrug.
    """
    reasons: list[str] = []
    bar_class = bar_class or classify_bar(staleness_ms, timeframe_ms)

    if bar_class == BAR_WARMUP:
        # No risk question arises: nothing downstream may act on a warm-up bar.
        return {
            "result": ADMIT_WARMUP,
            "bar_class": bar_class,
            "reasons": [
                f"bar is indicator warm-up: {staleness_ms} ms since candle close exceeds one period "
                f"({timeframe_ms} ms), so it contributes state only and no execution claim"
            ],
            "open_position_count": len(open_positions),
            "max_open_trades": config.get("max_open_trades"),
            "stake_amount": config.get("stake_amount"),
            "dry_run_wallet": config.get("dry_run_wallet"),
            "staleness_ms": staleness_ms,
            "max_admissible_staleness_ms": timeframe_ms,
        }

    if config.get("dry_run") is not True:
        reasons.append("dry_run is not exactly true")
    if config.get("trading_mode") != "spot":
        reasons.append(f"trading_mode is {config.get('trading_mode')!r}, not spot")
    if config.get("margin_mode") not in (None, ""):
        reasons.append(f"margin_mode is {config.get('margin_mode')!r}, not empty")

    whitelist = ((config.get("exchange") or {}).get("pair_whitelist")) or []
    if whitelist and pair not in whitelist:
        reasons.append(f"{pair} is not in the configured pair whitelist")

    if action == fp_replay.ACTION_ENTER_LONG:
        max_open = config.get("max_open_trades")
        if isinstance(max_open, int) and max_open >= 0 and len(open_positions) >= max_open:
            reasons.append(f"max_open_trades {max_open} already reached ({len(open_positions)} open)")
        if pair in open_positions:
            reasons.append(f"a paper position is already open on {pair}")
        stake = config.get("stake_amount")
        wallet = config.get("dry_run_wallet")
        if isinstance(stake, (int, float)) and isinstance(wallet, (int, float)) and stake > wallet:
            reasons.append(f"stake_amount {stake} exceeds the simulated wallet {wallet}")
        result = ADMIT_BLOCKED if reasons else ADMIT_OK
    elif action == fp_replay.ACTION_EXIT_LONG:
        # An exit is never blocked by sizing or exposure limits: refusing to
        # leave a position is a risk, not a control.
        result = ADMIT_BLOCKED if any("dry_run" in r or "trading_mode" in r for r in reasons) else ADMIT_OK
    else:
        result = ADMIT_NOT_REQUIRED

    return {
        "result": result,
        "bar_class": bar_class,
        "reasons": reasons,
        "open_position_count": len(open_positions),
        "max_open_trades": config.get("max_open_trades"),
        "stake_amount": config.get("stake_amount"),
        "dry_run_wallet": config.get("dry_run_wallet"),
        "staleness_ms": staleness_ms,
        "max_admissible_staleness_ms": timeframe_ms,
    }


# --------------------------------------------------------------------------
# Freqtrade read-only API
# --------------------------------------------------------------------------


class FreqtradeClient:
    """Read-only client for the Freqtrade REST API.

    Only GET endpoints are reachable through this class. That is deliberate and
    structural: the capture loop must be incapable of causing an execution, so
    there is no method here that could place, cancel or force a trade even if
    something later called it by mistake.
    """

    def __init__(self, base_url: str, username: str | None = None, password: str | None = None, timeout: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout

    def _get(self, path: str):
        url = f"{self.base_url}/api/v1/{path.lstrip('/')}"
        request = urllib.request.Request(url, method="GET")
        if self.username and self.password:
            token = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            request.add_header("Authorization", f"Basic {token}")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
            return json.loads(response.read())

    def ping(self) -> dict:
        return self._get("ping")

    def status(self) -> list:
        result = self._get("status")
        return result if isinstance(result, list) else []

    def trades(self, limit: int = 200) -> list:
        result = self._get(f"trades?limit={int(limit)}")
        if isinstance(result, dict):
            return result.get("trades") or []
        return result if isinstance(result, list) else []

    def show_config(self) -> dict:
        result = self._get("show_config")
        return result if isinstance(result, dict) else {}


def trade_event_id(trade: dict, event: str) -> str:
    """Identity of one paper execution event.

    Keyed on the trade id and the event kind, so re-polling the same open trade
    can never append a second ``position_opened``. That is the
    no-duplicate-paper-execution property, and it is enforced by construction
    rather than by hoping the poll interval never overlaps.
    """
    return f"{trade.get('trade_id')}|{event}"


def _trade_common(trade: dict) -> dict:
    return {
        "trade_id": trade.get("trade_id"),
        "pair": trade.get("pair"),
        "is_open": trade.get("is_open"),
        "open_date_utc": trade.get("open_date"),
        "open_rate": trade.get("open_rate"),
        "amount": trade.get("amount"),
        "stake_amount": trade.get("stake_amount"),
        "enter_tag": trade.get("enter_tag"),
        "fee_open": trade.get("fee_open"),
        "fee_close": trade.get("fee_close"),
        "strategy": trade.get("strategy"),
    }


def derive_trade_events(trades: list[dict], already: set[str]) -> list[dict]:
    """Turn a Freqtrade trade listing into not-yet-recorded ledger payloads."""
    events: list[dict] = []
    for trade in trades:
        if not isinstance(trade, dict) or trade.get("trade_id") is None:
            continue
        opened_id = trade_event_id(trade, "position_opened")
        if opened_id not in already:
            payload = _trade_common(trade)
            payload.update(
                {
                    "event": "position_opened",
                    "trade_event_id": opened_id,
                    "paper_fill_model_version": PAPER_FILL_MODEL_VERSION,
                }
            )
            events.append(payload)
            already.add(opened_id)

        if not trade.get("is_open"):
            closed_id = trade_event_id(trade, "position_closed")
            if closed_id not in already:
                payload = _trade_common(trade)
                payload.update(
                    {
                        "event": "position_closed",
                        "trade_event_id": closed_id,
                        "close_date_utc": trade.get("close_date"),
                        "close_rate": trade.get("close_rate"),
                        "exit_reason": trade.get("exit_reason"),
                        "profit_abs": trade.get("profit_abs"),
                        "profit_ratio": trade.get("profit_ratio"),
                        "realised_pnl_currency": trade.get("stake_currency") or "USDT",
                        "paper_fill_model_version": PAPER_FILL_MODEL_VERSION,
                    }
                )
                events.append(payload)
                already.add(closed_id)
    return events


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------


class CaptureLoop:
    """Binds a running paper runtime to the evidence ledgers."""

    def __init__(
        self,
        evidence_dir: Path,
        pairs: list[str],
        timeframe: str = "1h",
        config_path: Path = DEFAULT_CONFIG_PATH,
        client: FreqtradeClient | None = None,
        market_module=fp_market,
        role: str | None = None,
    ) -> None:
        self.evidence_dir = Path(evidence_dir)
        self.pairs = list(pairs)
        self.timeframe = timeframe
        self.timeframe_ms = fp_market.TIMEFRAME_MS.get(timeframe, 3_600_000)
        self.config_path = Path(config_path)
        self.config = _load_json(self.config_path) or {}
        self.client = client
        self.market = market_module
        self.ledgers = fp_ledger.open_ledgers(self.evidence_dir)
        self.state = recover_state(self.evidence_dir)
        # The identity is built here or not at all. It used to be injectable,
        # and an injected one bypassed selection entirely: a forged FP-CONTROL-1
        # identity could write into the closed cohort's ledgers with no gate in
        # its way.
        if not role:
            raise InstanceSelectionError(
                "CaptureLoop requires an explicit role; there is no default, because a default "
                "would select whichever row came first, including a closed one"
            )
        self.identity = build_identity(
            self.evidence_dir, self.config_path, role=role, restart_counter=self.state.restart_counter
        )
        self.t0_ms = _registry_t0_ms(self.identity.role)

    # -- helpers ---------------------------------------------------------

    def _append(self, kind: str, payload: dict):
        enriched = dict(payload)
        enriched["identity"] = self.identity.stamp()
        return self.ledgers[kind].append(enriched)

    def record_incident(self, category: str, detail: str, **extra) -> None:
        payload = {"category": category, "detail": detail, "observed_utc": utc_now()}
        payload.update(extra)
        self._append("incident", payload)

    def record_run_started(self) -> None:
        """One full-identity record per process lifetime.

        This is what makes a restart legible: the ledger gains a new run_id with
        an incremented restart counter, so "the runtime was restarted" is a fact
        in the evidence rather than an inference from a gap in timestamps.
        """
        self._append(
            "incident",
            {
                "category": "run_started",
                "detail": f"capture loop start, restart_counter={self.identity.restart_counter}",
                "observed_utc": utc_now(),
                "full_identity": self.identity.as_payload(),
                "paper_fill_model_semantics": PAPER_FILL_MODEL_SEMANTICS,
                "recovered": {
                    "input_records": self.state.input_records,
                    "decision_records": self.state.decision_records,
                    "trade_records": self.state.trade_records,
                    "captured_events": len(self.state.captured_events),
                    "decided_bars": len(self.state.decided_bars),
                    "open_positions": sorted(self.state.open_positions),
                    "prior_runs": len(self.state.prior_runs),
                },
            },
        )

    # -- input -----------------------------------------------------------

    def capture_inputs(self, pair: str, limit: int = 3) -> dict:
        """Fetch closed candles and append the ones not already captured."""
        summary = {"pair": pair, "fetched": 0, "written": 0, "duplicates": 0, "rejected": 0}
        try:
            candles = self.market.fetch_closed_candles(pair, self.timeframe, limit=limit)
        except Exception as exc:  # noqa: BLE001
            self.record_incident("market_fetch_failed", f"{pair}: {exc}", pair=pair)
            summary["error"] = str(exc)[:300]
            return summary

        summary["fetched"] = len(candles)
        for candle in candles:
            payload = candle.as_input_payload()
            event_id = payload["market_event_id"]

            if event_id in self.state.captured_events:
                summary["duplicates"] += 1
                continue

            try:
                validate_input_payload(payload, self.state.last_candle_ts.get(pair))
            except CaptureError as exc:
                summary["rejected"] += 1
                self.record_incident(
                    "input_rejected", str(exc), pair=pair, market_event_id=event_id
                )
                continue

            self._append("input", payload)
            self.state.captured_events.add(event_id)
            self.state.last_candle_ts[pair] = int(payload["candle"]["ts"])
            self.state.input_records += 1
            summary["written"] += 1
        return summary

    # -- decision --------------------------------------------------------

    def captured_candles(self, pair: str) -> list[dict]:
        """Every candle captured for ``pair``, in event-time order."""
        return fp_replay.candles_from_input_ledger(self.ledgers["input"].records(), pair)

    def capture_decisions(self, pair: str) -> dict:
        """Derive and append decisions for captured bars not yet decided.

        The decision is derived over the whole captured history for the pair, so
        the EMA state behind it is the state the frozen logic would have had.
        Deriving from only the newest candles would give a differently-seeded
        indicator and a decision that no replay could reproduce.
        """
        summary = {"pair": pair, "written": 0, "duplicates": 0, "bars": 0}
        candles = self.captured_candles(pair)
        summary["bars"] = len(candles)
        if not candles:
            return summary

        try:
            decisions = fp_replay.derive_decisions(candles, pair)
        except fp_replay.ReplayError as exc:
            self.record_incident("decision_derivation_failed", f"{pair}: {exc}", pair=pair)
            summary["error"] = str(exc)[:300]
            return summary

        now_ms = self.market.utc_ms()
        for decision in decisions:
            key = (pair, decision.candle_ts)
            if key in self.state.decided_bars:
                summary["duplicates"] += 1
                continue

            close_ts = decision.candle_ts + self.timeframe_ms
            staleness = max(0, now_ms - close_ts)
            bar_class = classify_bar(staleness, self.timeframe_ms)
            admission = evaluate_admission(
                decision.intended_action,
                pair,
                self.config,
                self.state.open_positions,
                staleness,
                self.timeframe_ms,
                bar_class=bar_class,
            )
            payload = {
                "pair": pair,
                "timeframe": self.timeframe,
                "candle_ts": decision.candle_ts,
                "market_event_id": fp_market.market_event_id(pair, self.timeframe, decision.candle_ts),
                "decision_ts_ms": now_ms,
                "decision_utc": fp_market.iso_from_ms(now_ms),
                "signal_state": decision.signal_state,
                "intended_action": decision.intended_action,
                "bar_class": bar_class,
                "t0_relation": self.t0_relation(close_ts),
                "no_action_reason": decision.no_action_reason,
                "ema_fast": decision.ema_fast,
                "ema_slow": decision.ema_slow,
                "strategy_name": self.identity.strategy_name,
                "strategy_sha256": self.identity.strategy_sha256,
                "config_sha256": self.identity.config_sha256,
                "runtime_version": fp_replay.REPLAY_ENGINE_VERSION,
                "capture_engine_version": CAPTURE_ENGINE_VERSION,
                "admission": admission,
                "restart_counter": self.identity.restart_counter,
            }
            self._append("decision", payload)
            self.state.decided_bars.add(key)
            self.state.signal_state[pair] = decision.signal_state
            self.state.decision_records += 1
            summary["written"] += 1
        return summary

    def t0_relation(self, close_ts_ms: int) -> str:
        """Where this bar sits relative to the frozen prospective boundary.

        Before the Owner freezes T0 there is no boundary to be on either side
        of, so the honest answer is that none is frozen - not an optimistic
        "POST_T0" that would later look like prospective evidence it never was.
        """
        t0_ms = self.t0_ms
        if t0_ms is None:
            return "T0_NOT_FROZEN"
        return "POST_T0" if close_ts_ms >= t0_ms else "PRE_T0"

    # -- trades ----------------------------------------------------------

    def capture_trades(self) -> dict:
        """Read paper executions back from Freqtrade and append new events."""
        summary = {"written": 0, "open_trades": 0, "closed_trades": 0}
        if self.client is None:
            return summary
        try:
            open_trades = self.client.status()
            closed = self.client.trades()
        except Exception as exc:  # noqa: BLE001
            self.record_incident("freqtrade_api_unreachable", str(exc)[:300])
            summary["error"] = str(exc)[:300]
            return summary

        summary["open_trades"] = len(open_trades)
        summary["closed_trades"] = len(closed)

        events = derive_trade_events(list(open_trades) + list(closed), self.state.recorded_trade_events)
        for payload in events:
            self._append("trade", payload)
            self.state.trade_records += 1
            summary["written"] += 1
            pair = payload.get("pair")
            if payload["event"] == "position_opened" and pair:
                self.state.open_positions[pair] = payload
            elif payload["event"] == "position_closed" and pair:
                self.state.open_positions.pop(pair, None)
        return summary

    # -- one cycle -------------------------------------------------------

    def cycle(self, limit: int = 3) -> dict:
        report = {"cycle_utc": utc_now(), "inputs": [], "decisions": [], "trades": {}}
        for pair in self.pairs:
            report["inputs"].append(self.capture_inputs(pair, limit=limit))
            report["decisions"].append(self.capture_decisions(pair))
        report["trades"] = self.capture_trades()
        return report

    def ledger_problems(self) -> list[str]:
        problems: list[str] = []
        for kind, led in sorted(self.ledgers.items()):
            problems.extend(f"{kind}: {item}" for item in led.verify())
        return problems

    def write_runtime_state(self) -> Path:
        """A human-readable snapshot beside the ledgers.

        Explicitly *not* the source of truth — :func:`recover_state` never reads
        it. It exists so an operator can see the runtime's position without
        parsing four ledgers, and it is regenerated from the ledgers each cycle.
        """
        path = self.evidence_dir / STATE_FILENAME
        snapshot = {
            "written_utc": utc_now(),
            "identity": self.identity.as_payload(),
            "pairs": self.pairs,
            "timeframe": self.timeframe,
            "input_records": self.state.input_records,
            "decision_records": self.state.decision_records,
            "trade_records": self.state.trade_records,
            "last_candle_ts": self.state.last_candle_ts,
            "signal_state": self.state.signal_state,
            "open_positions": sorted(self.state.open_positions),
            "restart_counter": self.identity.restart_counter,
            "ledger_tips": {kind: led.tip_digest() for kind, led in sorted(self.ledgers.items())},
            "daily_pack_digest": fp_ledger.daily_pack_digest(self.ledgers.values()),
            "real_money_authorized": False,
        }
        path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        return path


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument(
        "--role",
        required=True,
        help=(
            "the registry instance this runtime is. Required and never defaulted: after a cohort "
            "closes, a default would quietly select the closed row and stamp its identity onto new evidence."
        ),
    )
    parser.add_argument("--pair", action="append", dest="pairs", default=None)
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--freqtrade-url", default=os.environ.get("FREQTRADE_URL", ""))
    parser.add_argument("--api-user", default=os.environ.get("FREQTRADE_API_USER", ""))
    parser.add_argument("--api-password", default=os.environ.get("FREQTRADE_API_PASSWORD", ""))
    parser.add_argument("--interval", type=float, default=60.0, help="seconds between cycles")
    parser.add_argument("--cycles", type=int, default=0, help="0 runs until stopped")
    parser.add_argument("--limit", type=int, default=3, help="candles requested per pair per cycle")
    parser.add_argument(
        "--backfill",
        type=int,
        default=0,
        help=(
            "candles to request on the first cycle for a pair with no prior evidence. "
            "BASELINE-1 declares startup_candle_count=600, so the EMAs need several hundred closed bars "
            "before a decision means anything; this is indicator warm-up and every bar it captures is "
            "recorded as WARMUP, contributing state and no outcome claim."
        ),
    )
    parser.add_argument(
        "--allow-undeclared-evidence-dir",
        action="store_true",
        help=(
            "run against a directory the registry does not declare. For offline drills only: "
            "the evidence it writes belongs to no registered instance and is not admissible."
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    pairs = args.pairs or ["BTC/USDT", "ETH/USDT"]
    evidence_dir = Path(args.evidence_dir)

    client = None
    if args.freqtrade_url:
        client = FreqtradeClient(args.freqtrade_url, args.api_user or None, args.api_password or None)

    try:
        select_instance(args.role)
        assert_paths_are_exclusive(args.role, evidence_dir)
        if not args.allow_undeclared_evidence_dir:
            assert_evidence_dir_is_declared(args.role, evidence_dir)
    except InstanceSelectionError as exc:
        print(f"CAPTURE_REFUSED: {exc}", file=sys.stderr)
        return 5

    try:
        lock = EvidenceLock(evidence_dir).acquire()
    except DuplicateInstanceError as exc:
        print(f"CAPTURE_REFUSED: {exc}", file=sys.stderr)
        return 3

    try:
        loop = CaptureLoop(
            evidence_dir,
            pairs,
            timeframe=args.timeframe,
            config_path=Path(args.config),
            client=client,
            role=args.role,
        )
        loop.record_run_started()
        print(
            f"FP_CAPTURE start run_id={loop.identity.run_id[:12]} "
            f"restart_counter={loop.identity.restart_counter} pairs={','.join(pairs)}",
            flush=True,
        )

        completed = 0
        while args.cycles <= 0 or completed < args.cycles:
            # Warm-up is a first-cycle concern only: once a pair has evidence the
            # loop needs just the newly closed bars, and re-requesting the whole
            # history every cycle would spend bandwidth to rediscover duplicates.
            needs_backfill = args.backfill > 0 and any(
                pair not in loop.state.last_candle_ts for pair in pairs
            )
            report = loop.cycle(limit=max(args.limit, args.backfill) if needs_backfill else args.limit)
            loop.write_runtime_state()
            problems = loop.ledger_problems()
            if problems:
                loop.record_incident("ledger_integrity", "; ".join(problems[:3]))
                print(f"LEDGER_INTEGRITY_FAIL: {problems[0]}", file=sys.stderr, flush=True)
                return 4
            if args.json:
                print(json.dumps(report), flush=True)
            else:
                written = sum(item["written"] for item in report["inputs"])
                decided = sum(item["written"] for item in report["decisions"])
                print(
                    f"{report['cycle_utc']} inputs+{written} decisions+{decided} "
                    f"trades+{report['trades'].get('written', 0)}",
                    flush=True,
                )
            completed += 1
            if args.cycles <= 0 or completed < args.cycles:
                time.sleep(max(1.0, args.interval))
        return 0
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
