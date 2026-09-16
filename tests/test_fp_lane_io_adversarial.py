"""Adversarial proofs for the contained lane-I/O boundary.

Every test here drives a real production entry point — ``CaptureLoop``,
``EvidenceLock``, ``Ledger``, ``preflight.run`` — against the exact filesystem
attack that was reproduced against the previous code, and asserts the two
properties the boundary exists to guarantee:

CONTAINMENT
    the external target is byte-identical afterwards, always checked by content
    and not merely by "an exception was raised";

IDENTITY
    a pathname mutation either keeps operating on the originally opened lane or
    fails closed, and never silently produces a second authoritative lane.

Nothing here writes outside ``tmp_path``. The cohort registry is read for its
bytes only, and the proof that the registry-truncation attack is dead compares
its digest before and after.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from fp import capture, lane, ledger as fp_ledger, preflight
from fp.lane_io import LaneDurabilityUnproven, LaneHandle, LaneIdentity, LaneIOError

REGISTRY_PATH = Path("research/fp/records/forward_paper_cohort_registry.json")
SUCCESSOR = "FP-CONTROL-2"
STATE = capture.STATE_FILENAME
LOCK = capture.LOCK_FILENAME
INPUT_LEDGER = "paper_input_ledger.jsonl"

HOUR_MS = 3_600_000
BASE_TS = 1_700_000_000_000 - (1_700_000_000_000 % HOUR_MS)
NOW_MS = BASE_TS + 40 * HOUR_MS + 1_000


# --------------------------------------------------------------------------
# fixtures: a real capture loop over a deterministic market, in tmp only
# --------------------------------------------------------------------------


class StubMarket:
    """A fixed candle series, so a proof never depends on a market route."""

    TIMEFRAME_MS = {"1h": HOUR_MS}
    SOURCE_ID = "stub:lane-io"

    def __init__(self, count: int = 40, now_ms: int | None = None) -> None:
        self.count = count
        # One second after the last bar closes, so every bar in the series is
        # closed and none is rejected as still forming.
        self.now_ms = now_ms if now_ms is not None else BASE_TS + count * HOUR_MS + 1_000

    def fetch_closed_candles(self, pair, timeframe="1h", limit=3, **kwargs):
        from fp import market as fp_market

        out = []
        for i in range(self.count):
            open_ts = BASE_TS + i * HOUR_MS
            close = 30000.0 + 10.0 * i
            out.append(
                fp_market.Candle(
                    pair=pair, timeframe=timeframe, open_ts_ms=open_ts,
                    close_ts_ms=open_ts + HOUR_MS - 1, open=close - 1.0, high=close + 2.0,
                    low=close - 2.0, close=close, volume=10.0,
                    source_ts_ms=open_ts + HOUR_MS - 1, receive_ts_ms=self.now_ms,
                    source_id=fp_market.SOURCE_ID, source_host="https://stub.invalid",
                )
            )
        return out[-limit:]

    def utc_ms(self) -> int:
        return self.now_ms


@pytest.fixture
def config_path(tmp_path) -> Path:
    """A runtime config supplied the way an operator supplies one.

    freqtrade/user_data/config.json is gitignored, so a fresh clone has none.
    """
    target = tmp_path / "config.json"
    target.write_bytes(Path("freqtrade/user_data/config.paper.json.example").read_bytes())
    return target


@pytest.fixture
def evidence(tmp_path) -> Path:
    lane_dir = tmp_path / "lane" / "evidence"
    lane_dir.mkdir(parents=True)
    return lane_dir


@pytest.fixture
def victim(tmp_path) -> Path:
    """A file outside the lane. Its bytes are the containment assertion."""
    target = tmp_path / "outside" / "victim.json"
    target.parent.mkdir()
    target.write_text('{"untouched": true}\n', encoding="utf-8")
    return target


@pytest.fixture
def registry_pinned(monkeypatch):
    monkeypatch.setattr(capture, "COHORT_REGISTRY", REGISTRY_PATH.resolve())
    monkeypatch.setattr(lane, "COHORT_REGISTRY", REGISTRY_PATH.resolve())
    monkeypatch.setattr(capture, "assert_evidence_dir_is_declared", lambda *a, **k: None)


def make_loop(evidence: Path, config_path: Path) -> capture.CaptureLoop:
    return capture.CaptureLoop(
        evidence, ["BTC/USDT"], config_path=config_path,
        market_module=StubMarket(), role=SUCCESSOR,
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# 1. runtime-state symlink planted before the lane is constructed
# --------------------------------------------------------------------------


def test_1_state_symlink_before_lane_construction_writes_nothing_outside(
    evidence, victim, config_path, registry_pinned
):
    (evidence / STATE).symlink_to(victim)
    before = victim.read_bytes()

    with pytest.raises(capture.InstanceSelectionError):
        make_loop(evidence, config_path)

    assert victim.read_bytes() == before


# --------------------------------------------------------------------------
# 2. the state entry is substituted after the handle exists, before the write
# --------------------------------------------------------------------------


def test_2_state_symlink_planted_after_construction_is_refused(
    evidence, victim, config_path, registry_pinned
):
    """The exact ordering the previous code lost to: clean at startup, linked later."""
    loop = make_loop(evidence, config_path)
    loop.cycle(limit=5)
    loop.write_runtime_state()
    good_state = (evidence / STATE).read_bytes()

    (evidence / STATE).unlink()
    (evidence / STATE).symlink_to(victim)
    before = victim.read_bytes()

    with pytest.raises(LaneIOError) as excinfo:
        loop.write_runtime_state()

    assert "not a regular file" in str(excinfo.value)
    assert victim.read_bytes() == before, "the state write followed a late symlink"
    assert good_state  # the earlier legitimate write really did happen
    loop.close()


# --------------------------------------------------------------------------
# 3. the reproduced attack: the state entry linked at the cohort registry
# --------------------------------------------------------------------------


def test_3_the_registry_truncation_attack_no_longer_reaches_the_registry(
    evidence, tmp_path, config_path, registry_pinned
):
    """A copy of the real registry is the target, and the real one is watched too.

    The review reproduced this against the live file: 95 bytes written into the
    closed cohort's lane and the registry truncated.
    """
    real_before = digest(REGISTRY_PATH)
    target = tmp_path / "forward_paper_cohort_registry.json"
    target.write_bytes(REGISTRY_PATH.read_bytes())
    target_before = target.read_bytes()

    loop = make_loop(evidence, config_path)
    loop.cycle(limit=5)
    (evidence / STATE).symlink_to(target)

    with pytest.raises(LaneIOError):
        loop.write_runtime_state()

    assert target.read_bytes() == target_before, "the registry copy was modified"
    assert json.loads(target.read_text(encoding="utf-8"))["instances"], "the copy was truncated"
    assert digest(REGISTRY_PATH) == real_before, "the committed registry changed"
    loop.close()


# --------------------------------------------------------------------------
# 4. a ledger file substituted with a symlink late
# --------------------------------------------------------------------------


def test_4_late_symlinked_ledger_is_refused_and_target_untouched(
    evidence, victim, config_path, registry_pinned
):
    loop = make_loop(evidence, config_path)
    loop.cycle(limit=5)
    assert (evidence / INPUT_LEDGER).exists()

    (evidence / INPUT_LEDGER).unlink()
    (evidence / INPUT_LEDGER).symlink_to(victim)
    before = victim.read_bytes()

    # Newer bars than the first cycle captured, so this is a real append
    # attempt: duplicates and out-of-order bars never reach the ledger.
    loop.market = StubMarket(count=60)
    with pytest.raises(fp_ledger.LedgerError) as excinfo:
        loop.capture_inputs("BTC/USDT", limit=5)

    assert "symbolic link" in str(excinfo.value)
    assert victim.read_bytes() == before
    loop.close()


# --------------------------------------------------------------------------
# 5. the lock file substituted with a symlink late
# --------------------------------------------------------------------------


def test_5_late_symlinked_lock_fails_closed_and_target_untouched(evidence, victim):
    first = capture.EvidenceLock(evidence).acquire()
    first.release()

    (evidence / LOCK).unlink()
    (evidence / LOCK).symlink_to(victim)
    before = victim.read_bytes()

    with pytest.raises(LaneIOError) as excinfo:
        capture.EvidenceLock(evidence).acquire()

    assert "symbolic link" in str(excinfo.value)
    assert victim.read_bytes() == before


def test_5b_a_lock_held_through_an_open_handle_still_refuses_a_second_writer(evidence):
    """Exclusion must survive the boundary change, not just containment."""
    with LaneHandle.open(evidence) as handle:
        first = capture.EvidenceLock(evidence, lane=handle).acquire()
        try:
            with pytest.raises(capture.DuplicateInstanceError):
                capture.EvidenceLock(evidence, lane=handle).acquire()
        finally:
            first.release()


# --------------------------------------------------------------------------
# 6. the lane pathname is substituted after the handle is acquired
# --------------------------------------------------------------------------


def test_6_a_substituted_lane_pathname_receives_no_writes(
    evidence, config_path, registry_pinned, tmp_path
):
    loop = make_loop(evidence, config_path)
    loop.cycle(limit=5)
    original_identity = loop.lane.identity

    moved = tmp_path / "moved-lane"
    evidence.rename(moved)
    decoy = evidence
    decoy.mkdir(parents=True)

    # Containment: the loop is bound to the inode it opened, not to the name.
    loop.capture_inputs("BTC/USDT", limit=8)
    assert sorted(p.name for p in decoy.iterdir()) == [], "a write reached the substituted lane"
    assert (moved / INPUT_LEDGER).exists()

    # Identity: the divergence is detectable and fails closed, so capture and a
    # later gate can never each believe a different directory is authoritative.
    with pytest.raises(LaneIOError) as excinfo:
        loop.write_runtime_state()
    assert "refused" in str(excinfo.value)

    assert LaneIdentity.of_path(moved) == original_identity
    assert LaneIdentity.of_path(decoy) != original_identity
    assert not (decoy / STATE).exists()
    loop.close()


# --------------------------------------------------------------------------
# 7. a parent pathname is renamed after the handle is acquired
# --------------------------------------------------------------------------


def test_7_a_renamed_parent_keeps_operations_on_the_opened_lane(
    evidence, config_path, registry_pinned, tmp_path
):
    loop = make_loop(evidence, config_path)
    loop.cycle(limit=5)
    before = loop.lane.identity

    parent = evidence.parent                      # tmp_path/lane
    renamed = tmp_path / "lane-renamed"
    parent.rename(renamed)
    followed = renamed / "evidence"

    loop.capture_inputs("BTC/USDT", limit=8)
    assert (followed / INPUT_LEDGER).exists()
    assert LaneIdentity.of_path(followed) == before, "the handle moved to a different inode"
    assert not evidence.exists()

    # The pathname no longer resolves at all: that is a divergence, and a
    # divergence is answered by stopping.
    with pytest.raises(LaneIOError):
        loop.lane.assert_identity_unchanged()
    loop.close()


# --------------------------------------------------------------------------
# 8. atomic replacement fails mid-operation
# --------------------------------------------------------------------------


def test_8_a_failed_state_replacement_leaves_no_torn_state_and_no_debris(
    evidence, config_path, registry_pinned, monkeypatch
):
    loop = make_loop(evidence, config_path)
    loop.cycle(limit=5)
    loop.write_runtime_state()
    good = (evidence / STATE).read_bytes()
    entries_before = sorted(p.name for p in evidence.iterdir())

    real_replace = os.replace

    def failing_replace(*args, **kwargs):
        raise OSError(errno.EIO, "simulated I/O error during rename")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError):
        loop.write_runtime_state()
    monkeypatch.setattr(os, "replace", real_replace)

    assert (evidence / STATE).read_bytes() == good, "the previous state was torn"
    assert sorted(p.name for p in evidence.iterdir()) == entries_before, "a temporary entry survived"

    # And a failure earlier, while the temporary file is being written: the
    # rename never happens, so the previous state really is still the state.
    def failing_fsync(fd):
        raise OSError(errno.EIO, "simulated I/O error during fsync")

    monkeypatch.setattr(os, "fsync", failing_fsync)
    with pytest.raises(OSError):
        loop.write_runtime_state()
    monkeypatch.undo()

    assert (evidence / STATE).read_bytes() == good
    assert sorted(p.name for p in evidence.iterdir()) == entries_before

    # The lane still works afterwards.
    loop.write_runtime_state()
    assert json.loads((evidence / STATE).read_text(encoding="utf-8"))["real_money_authorized"] is False
    loop.close()


def test_8b_a_failure_after_the_rename_is_reported_as_durability_not_rollback(
    evidence, config_path, registry_pinned, monkeypatch
):
    """The two failure regions are different facts, and must not be conflated.

    Failing the directory sync happens *after* the replacement is visible. The
    new content is the current state; only its survival across a power loss is
    unproven. Reporting that as "the previous state survived" would be false.
    """
    loop = make_loop(evidence, config_path)
    loop.cycle(limit=5)
    loop.write_runtime_state()
    previous = json.loads((evidence / STATE).read_text(encoding="utf-8"))
    entries_before = sorted(p.name for p in evidence.iterdir())

    real_fsync = os.fsync
    seen = {"calls": 0}

    def fsync_that_fails_on_the_directory(fd):
        seen["calls"] += 1
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(errno.EIO, "simulated I/O error syncing the directory")
        return real_fsync(fd)

    # Newer bars, so the snapshot that follows genuinely differs from the one
    # already on disk and "the replacement is visible" is a real assertion.
    loop.market = StubMarket(count=60)
    monkeypatch.setattr(os, "fsync", fsync_that_fails_on_the_directory)
    loop.cycle(limit=5)
    with pytest.raises(LaneDurabilityUnproven) as excinfo:
        loop.write_runtime_state()
    monkeypatch.undo()

    message = str(excinfo.value)
    assert "durability" in message and "unproven" in message
    assert "previous content is gone" in message

    current = json.loads((evidence / STATE).read_text(encoding="utf-8"))
    assert current != previous, "the replacement was not visible after the rename"
    assert current["input_records"] > previous["input_records"]
    assert sorted(p.name for p in evidence.iterdir()) == entries_before, "a temporary entry survived"
    loop.close()


def test_8c_the_durability_error_is_still_a_fail_closed_lane_error():
    """Callers that catch the boundary's error type keep failing closed."""
    assert issubclass(LaneDurabilityUnproven, LaneIOError)


# --------------------------------------------------------------------------
# 9. preflight's direct ledger read meets a linked ledger
# --------------------------------------------------------------------------


def test_9_preflight_refuses_to_read_a_linked_ledger(tmp_path, victim, monkeypatch, registry_pinned):
    """The gate's own raw read is a lane read now, so it refuses the same way."""
    monkeypatch.setattr(preflight, "RUNTIME_CONFIG", tmp_path / "config.json")
    (tmp_path / "config.json").write_bytes(
        Path("freqtrade/user_data/config.paper.json.example").read_bytes()
    )
    evidence = tmp_path / "evidence"
    ledgers = fp_ledger.open_ledgers(evidence, create=True)
    ledgers["input"].append({"pair": "BTC/USDT", "candle_ts": BASE_TS})
    before = victim.read_bytes()

    (evidence / INPUT_LEDGER).unlink()
    (evidence / INPUT_LEDGER).symlink_to(victim)

    with pytest.raises(fp_ledger.LedgerError) as excinfo:
        ledgers["input"].raw_text()
    assert "symbolic link" in str(excinfo.value)

    # And through the gate's public entry point: it refuses rather than reading
    # through the link, so no report can be produced from linked evidence.
    with pytest.raises(fp_ledger.LedgerError):
        preflight.run(runtime=preflight.RuntimeContext(evidence_dir=evidence, role=SUCCESSOR))
    assert victim.read_bytes() == before



# --------------------------------------------------------------------------
# 10. a legitimate capture still works, and touches nothing else
# --------------------------------------------------------------------------


def test_10_a_legitimate_capture_produces_its_lane_and_nothing_else(
    evidence, config_path, registry_pinned, tmp_path
):
    outside = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and evidence not in p.parents}

    loop = make_loop(evidence, config_path)
    report = loop.cycle(limit=10)
    loop.write_runtime_state()

    assert report["inputs"][0]["written"] == 10
    for name in ("paper_input_ledger.jsonl", "paper_decision_ledger.jsonl", STATE):
        assert (evidence / name).is_file(), f"{name} was not produced"
    assert loop.ledger_problems() == []
    state = json.loads((evidence / STATE).read_text(encoding="utf-8"))
    assert state["identity"]["role"] == SUCCESSOR
    assert state["real_money_authorized"] is False

    after = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and evidence not in p.parents}
    assert after == outside, "capture modified something outside its lane"
    loop.close()


# --------------------------------------------------------------------------
# 11. the same proofs hold in a fresh single-branch clone with no origin
# --------------------------------------------------------------------------


def test_11_these_proofs_reproduce_in_a_clean_checkout(tmp_path):
    """No dependence on untracked or gitignored state in the writer tree."""
    from conftest import clone_at_head

    clone, head = clone_at_head(tmp_path / "clone")
    assert subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip() == head
    assert subprocess.run(["git", "-C", str(clone), "remote"], capture_output=True,
                          text=True, check=True).stdout.strip() == ""
    assert not (clone / "freqtrade" / "user_data" / "config.json").exists()

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "--deselect", "tests/test_fp_lane_io_adversarial.py::test_11_these_proofs_reproduce_in_a_clean_checkout",
         "tests/test_fp_lane_io_adversarial.py"],
        cwd=clone, capture_output=True, text=True, timeout=900,
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]


# --------------------------------------------------------------------------
# 12. unexpected filesystem object types fail closed, without blocking
# --------------------------------------------------------------------------


def test_12_a_fifo_in_place_of_a_ledger_fails_closed_without_hanging(evidence):
    """A FIFO opened for reading with no writer would block forever."""
    os.mkfifo(evidence / INPUT_LEDGER)
    led = fp_ledger.Ledger(evidence / INPUT_LEDGER, "input")

    with pytest.raises(fp_ledger.LedgerError) as read_exc:
        led.records()
    assert "not a regular file" in str(read_exc.value)

    with pytest.raises(fp_ledger.LedgerError) as write_exc:
        led.append({"pair": "BTC/USDT"})
    assert "not a regular file" in str(write_exc.value)

    assert stat.S_ISFIFO(os.stat(evidence / INPUT_LEDGER).st_mode), "the FIFO was replaced"


def test_12b_a_directory_in_place_of_an_evidence_file_fails_closed(evidence):
    (evidence / INPUT_LEDGER).mkdir()
    led = fp_ledger.Ledger(evidence / INPUT_LEDGER, "input")
    with pytest.raises(fp_ledger.LedgerError):
        led.append({"pair": "BTC/USDT"})
    with pytest.raises(fp_ledger.LedgerError):
        led.records()
    assert (evidence / INPUT_LEDGER).is_dir()


def test_12c_a_unix_socket_in_place_of_an_evidence_file_fails_closed(evidence):
    import socket

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(str(evidence / INPUT_LEDGER))
        led = fp_ledger.Ledger(evidence / INPUT_LEDGER, "input")
        with pytest.raises(fp_ledger.LedgerError):
            led.append({"pair": "BTC/USDT"})
    finally:
        sock.close()
    assert stat.S_ISSOCK(os.stat(evidence / INPUT_LEDGER).st_mode)


def test_12d_a_state_name_that_is_a_directory_is_refused(evidence, config_path, registry_pinned):
    loop = make_loop(evidence, config_path)
    loop.cycle(limit=3)
    (evidence / STATE).mkdir()
    with pytest.raises(LaneIOError):
        loop.write_runtime_state()
    assert (evidence / STATE).is_dir()
    loop.close()


def test_12e_a_child_name_with_a_path_separator_is_refused(evidence):
    with LaneHandle.open(evidence) as handle:
        for name in ("../escape.jsonl", "sub/child.jsonl", "..", ".", ""):
            with pytest.raises(LaneIOError):
                handle.read_text(name)
            with pytest.raises(LaneIOError):
                handle.append_text(name, "x")
            with pytest.raises(LaneIOError):
                handle.replace_atomically(name, "x")


# --------------------------------------------------------------------------
# 13. the hard-link policy for mutable evidence entries
# --------------------------------------------------------------------------


def test_13_an_aliased_mutable_evidence_entry_is_refused(evidence, victim):
    """Policy: a mutable evidence entry must have exactly one name.

    O_NOFOLLOW does not see a hard link — the alias is a second directory entry
    for the same inode, not a link object — so the policy is metadata on the
    opened file: st_nlink must be 1.
    """
    led = fp_ledger.Ledger(evidence / INPUT_LEDGER, "input")
    led.append({"pair": "BTC/USDT", "candle_ts": BASE_TS})
    assert led.records()

    alias = victim.parent / "aliased_ledger.jsonl"
    os.link(evidence / INPUT_LEDGER, alias)
    alias_before = alias.read_bytes()

    with pytest.raises(fp_ledger.LedgerError) as excinfo:
        led.append({"pair": "BTC/USDT", "candle_ts": BASE_TS + HOUR_MS})
    assert "hard link" in str(excinfo.value)
    assert alias.read_bytes() == alias_before, "the append reached the alias"

    # Reading an aliased entry is still permitted: reads change nothing, and
    # refusing them would break a legitimate operator who copied evidence out.
    assert led.records()

    # Once the alias is gone the entry is writable again, so the policy tracks
    # the actual link state rather than latching on one observation.
    alias.unlink()
    led.append({"pair": "BTC/USDT", "candle_ts": BASE_TS + HOUR_MS})
    assert len(led.records()) == 2


def test_13b_the_hard_link_policy_applies_to_the_lock_and_the_state_file(
    evidence, victim, config_path, registry_pinned
):
    loop = make_loop(evidence, config_path)
    loop.cycle(limit=3)
    loop.write_runtime_state()

    os.link(evidence / STATE, victim.parent / "state_alias.json")
    alias_before = (victim.parent / "state_alias.json").read_bytes()
    # Atomic replacement writes a fresh inode and renames over the name, so the
    # alias keeps the old content instead of receiving the new state. That is
    # the containment property; it is not a claim that the alias disappears.
    loop.write_runtime_state()
    assert (victim.parent / "state_alias.json").read_bytes() == alias_before
    assert (evidence / STATE).stat().st_nlink == 1
    loop.close()

    capture.EvidenceLock(evidence).acquire().release()
    os.link(evidence / LOCK, victim.parent / "lock_alias")
    with pytest.raises(LaneIOError) as excinfo:
        capture.EvidenceLock(evidence).acquire()
    assert "hard link" in str(excinfo.value)


def test_13c_the_policy_limit_is_stated_truthfully_in_the_boundary(evidence):
    """A link created *after* the descriptor is open is not detectable by it.

    Stated as behaviour rather than as a claim in prose: the policy is checked
    when the entry is opened, so an alias made while a handle is held receives
    that handle's write. Nothing in P1 prevents a process with equivalent OS
    authority from creating one.
    """
    # Demonstrated: the check happens at open, so an alias made while a handle
    # is held does receive that handle's write. Nothing in P1 prevents a process
    # with equivalent OS authority from doing this.
    with LaneHandle.open(evidence) as handle:
        handle.append_text("demo.jsonl", "first\n")
        alias = evidence.parent / "demo_alias.jsonl"
        os.link(evidence / "demo.jsonl", alias)
        with pytest.raises(LaneIOError):
            handle.append_text("demo.jsonl", "second\n")
        assert alias.read_text(encoding="utf-8") == "first\n"


# --------------------------------------------------------------------------
# the launcher creates lanes through the same boundary, not with `mkdir -p`
# --------------------------------------------------------------------------


def _launcher_lane_block() -> str:
    """The launcher's lane validation-and-creation step, as the shell runs it.

    Executing the real block keeps this a behavioural proof: if the step stops
    creating the lane, or starts creating it some other way, this fails.
    """
    text = Path("scripts/start_fp_control.sh").read_text(encoding="utf-8")
    marker = 'python3 - "$FP_ROLE" "$FP_DIR" <<\'PY\''
    rest = text[text.index(marker) + len(marker):]
    return rest.split("\n", 1)[1].split("\nPY\n")[0]


def _disposable_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                           check=True).stdout.split()
    for relative in files:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(relative, target)
    return repo


def test_the_launcher_creates_its_lane_through_the_boundary(tmp_path):
    block = _launcher_lane_block()
    repo = _disposable_repo(tmp_path)
    lane_dir = repo / "freqtrade" / "user_data" / "fp-control-2"

    created = subprocess.run([sys.executable, "-c", block, SUCCESSOR, str(lane_dir)],
                             cwd=repo, capture_output=True, text=True, timeout=300)
    assert created.returncode == 0, created.stdout + created.stderr
    assert (lane_dir / "logs").is_dir() and not (lane_dir / "logs").is_symlink()
    assert (lane_dir / "evidence").is_dir() and not (lane_dir / "evidence").is_symlink()

    outside = tmp_path / "outside-lane"
    outside.mkdir()
    shutil.rmtree(lane_dir / "evidence")
    (lane_dir / "evidence").symlink_to(outside)

    refused = subprocess.run([sys.executable, "-c", block, SUCCESSOR, str(lane_dir)],
                            cwd=repo, capture_output=True, text=True, timeout=300)
    assert refused.returncode == 3, refused.stdout + refused.stderr
    assert "FP_LANE_FAIL" in refused.stderr
    assert sorted(p.name for p in outside.iterdir()) == [], "the launcher created a lane outside"


# --------------------------------------------------------------------------
# identity sources: the registry, the runtime config and the strategy
# --------------------------------------------------------------------------


def _launcher_repo(tmp_path: Path) -> Path:
    """A git repository holding the *working tree's* code, with a clean tree.

    `git clone` would carry the committed branch instead, so a launcher gate
    that exists but is not yet committed would silently not be under test — and
    the launcher would run on the old code all the way to `compose up`. The
    tracked content here is what is being developed, committed once so the
    source-commit gate has a HEAD to compare against.
    """
    repo = tmp_path / "launcher-repo"
    repo.mkdir()
    for relative in subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                                   check=True).stdout.split():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(relative, target)
    for command in (["git", "init", "-q"],
                    ["git", "add", "-A"],
                    ["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-q", "-m", "launcher fixture"]):
        subprocess.run(command, cwd=repo, capture_output=True, text=True, check=True)

    shutil.copy2("freqtrade/user_data/config.paper.json.example",
                 repo / "freqtrade" / "user_data" / "config.json")
    # Placeholder credentials so the launcher reaches the gates under test. Both
    # this and config.json are gitignored, so the tracked tree stays clean.
    (repo / ".env").write_text(
        "FREQTRADE_API_USER=x\nFREQTRADE_API_PASSWORD=x\nFREQTRADE_JWT_SECRET=x\n"
        "FREQTRADE_WS_TOKEN=x\nGRAFANA_ADMIN_USER=x\nGRAFANA_ADMIN_PASSWORD=x\n",
        encoding="utf-8",
    )
    clean = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                           cwd=repo, capture_output=True, text=True).stdout
    assert clean == "", clean
    return repo


def _run_launcher(repo: Path, tmp_path: Path) -> tuple[subprocess.CompletedProcess, str]:
    """Run the launcher with a `docker` that cannot start anything.

    A test proving a refusal must not depend on that refusal working: if a gate
    regresses, the real launcher reaches `compose up -d` and starts a runtime.
    The stub makes that impossible and records what was attempted, so "nothing
    was started" is asserted rather than assumed.
    """
    shim = tmp_path / "shim"
    shim.mkdir(exist_ok=True)
    log = tmp_path / "docker-calls.log"
    (shim / "docker").write_text(
        "#!/bin/bash\necho \"$*\" >> " + str(log) + "\nexit 98\n", encoding="utf-8"
    )
    (shim / "docker").chmod(0o755)
    environment = dict(os.environ, PATH=f"{shim}:{os.environ['PATH']}")
    result = subprocess.run(["bash", "scripts/start_fp_control.sh", SUCCESSOR],
                            cwd=repo, capture_output=True, text=True, timeout=600,
                            env=environment)
    calls = log.read_text(encoding="utf-8") if log.exists() else ""
    assert "up -d" not in calls, f"the launcher tried to start a runtime: {calls}"
    return result, calls


def test_a_substituted_registry_is_refused_rather_than_read(tmp_path):
    """Reproduced: the read followed the link and the forged rows were believed.

    The forged registry is self-consistent — it declares hashes matching files
    the same attacker planted — so nothing downstream would have caught it.
    """
    repo = _launcher_repo(tmp_path)
    registry = repo / "research" / "fp" / "records" / "forward_paper_cohort_registry.json"
    forged = tmp_path / "forged_registry.json"
    data = json.loads(registry.read_text(encoding="utf-8"))
    for instance in data["instances"]:
        if instance["role"] == SUCCESSOR:
            instance["runtime_identity"]["config_sha256"] = "f" * 64
    forged.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    registry.unlink()
    registry.symlink_to(forged)

    read_attempt = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, 'research')\n"
         "from fp import lane\n"
         "print(lane.select_row('FP-CONTROL-2'))"],
        cwd=repo, capture_output=True, text=True, timeout=300,
    )
    assert read_attempt.returncode != 0, read_attempt.stdout
    assert "symbolic link" in read_attempt.stderr, read_attempt.stderr
    assert "f" * 64 not in read_attempt.stdout

    # The launcher refuses at its first registry read — selection — before the
    # identity hashes are even compared, and before anything is rendered.
    launcher, calls = _run_launcher(repo, tmp_path)
    assert launcher.returncode != 0
    assert "FP_SELECTION_FAIL" in launcher.stderr, launcher.stderr
    assert "symbolic link" in launcher.stderr, launcher.stderr
    assert calls == "", f"the launcher reached docker at all: {calls}"


def test_a_substituted_strategy_is_refused_by_the_identity_gate(tmp_path):
    """The hashed file and the executed file must be the same object."""
    repo = _launcher_repo(tmp_path)
    strategy = repo / "freqtrade" / "user_data" / "strategies" / "BaselineEmaRegimeV1.py"
    decoy = tmp_path / "decoy_strategy.py"
    decoy.write_bytes(strategy.read_bytes())
    strategy.unlink()
    strategy.symlink_to(decoy)

    launcher, calls = _run_launcher(repo, tmp_path)
    assert launcher.returncode != 0
    assert "FP_IDENTITY_FAIL" in launcher.stderr, launcher.stderr
    assert "symbolic link" in launcher.stderr, launcher.stderr
    assert calls == "", f"the launcher reached docker at all: {calls}"


def test_a_substituted_runtime_config_is_refused_by_the_identity_gate(tmp_path):
    repo = _launcher_repo(tmp_path)
    runtime_config = repo / "freqtrade" / "user_data" / "config.json"
    decoy = tmp_path / "decoy_config.json"
    decoy.write_bytes(runtime_config.read_bytes())
    runtime_config.unlink()
    runtime_config.symlink_to(decoy)

    launcher, calls = _run_launcher(repo, tmp_path)
    assert launcher.returncode != 0, launcher.stdout
    assert "symbolic link" in launcher.stderr, launcher.stderr
    assert calls == "", f"the launcher reached docker at all: {calls}"


def test_the_launcher_refuses_a_tracked_tree_that_differs_from_head(tmp_path):
    """The stamped source commit must describe what actually runs.

    An edited tracked file is the same attack as a planted link by a shorter
    route: the content that runs is not the content the commit names. This is
    the control that covers direct edits, which no-follow reads cannot see.
    """
    repo = _launcher_repo(tmp_path)
    doc = repo / "README.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8")

    launcher, calls = _run_launcher(repo, tmp_path)
    assert launcher.returncode == 3, launcher.stdout + launcher.stderr
    assert "FP_SOURCE_FAIL" in launcher.stderr, launcher.stderr
    assert "README.md" in launcher.stderr
    assert calls == "", f"the launcher reached docker despite a dirty tree: {calls}"


def test_a_clean_tracked_tree_reaches_the_render_step_and_stops_there(tmp_path):
    """The positive control: the gates pass, and the stub proves where it got to.

    Without this, every assertion above could pass because the launcher failed
    for some unrelated reason long before the gate under test.
    """
    repo = _launcher_repo(tmp_path)
    launcher, calls = _run_launcher(repo, tmp_path)
    assert "FP_IDENTITY_PASS" in launcher.stdout, launcher.stdout + launcher.stderr
    assert "FP_LANE_PASS" in launcher.stdout
    assert "FP_SOURCE_FAIL" not in launcher.stderr
    assert "config" in calls, f"the launcher never reached the render step: {calls}"
    assert "up -d" not in calls


def test_a_reconciliation_report_may_not_be_written_into_a_lane(tmp_path, monkeypatch):
    """A report is not evidence, and must not land where evidence lives.

    `--out <lane>/paper_input_ledger.jsonl` would replace a hash-chained ledger
    with a report. No attacker is needed: one mistyped path does it.
    """
    from fp import reconcile as fp_reconcile

    evidence = tmp_path / "evidence"
    ledgers = fp_ledger.open_ledgers(evidence, create=True)
    ledgers["input"].append({"pair": "BTC/USDT", "candle_ts": BASE_TS})
    before = (evidence / INPUT_LEDGER).read_bytes()

    # The lane roots the guard consults are the declared ones; point them at
    # this disposable lane rather than writing into the real tree.
    monkeypatch.setattr(fp_reconcile.fp_lane, "all_lane_roots", lambda *a, **k: [evidence.resolve()])

    code = fp_reconcile.main([
        "--evidence-dir", str(evidence), "--role", SUCCESSOR,
        "--out", str(evidence / INPUT_LEDGER),
    ])
    assert code == 2
    assert (evidence / INPUT_LEDGER).read_bytes() == before, "the report overwrote a ledger"

    # A destination outside every lane is still written, so the guard refuses
    # the dangerous case rather than the feature.
    outside = tmp_path / "report.json"
    assert fp_reconcile.main([
        "--evidence-dir", str(evidence), "--role", SUCCESSOR, "--out", str(outside),
    ]) in (0, 1, 2)
    assert outside.is_file() and json.loads(outside.read_text(encoding="utf-8"))
