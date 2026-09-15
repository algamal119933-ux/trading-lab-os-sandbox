"""Append-only, hash-chained evidence ledgers (FP-BOOT-1 sections 8, 16, 19, 26).

The specification requires that paper evidence be *append-only* and that
corrections arrive as errata rather than silent rewrites. A plain JSONL file
satisfies "append" but not "append-only": anyone can edit line 40 afterwards and
nothing notices. So every record carries the digest of its predecessor, and
``verify`` recomputes the whole chain.

Record envelope::

    {"seq": 0, "kind": "input", "recorded_utc": "...",
     "prev_digest": "0"*64, "digest": "<sha256>", "payload": {...}}

The digest covers the sequence number, the kind, the recorded timestamp, the
previous digest and the canonical encoding of the payload. Editing any of those
after the fact breaks that record *and every record after it*, which is the
property that makes the ledger usable as evidence.

Canonical payload encoding is ``CANONICAL_LEDGER_V1``: ``json.dumps`` with
sorted keys, no insignificant whitespace and ``ensure_ascii=False``. It is
deliberately the same shape of contract as ``CANONICAL_CANDLE_V1`` in
``scripts/audit_data.py`` — a digest that survives a formatting change but not a
content change.

This module writes files. It never reads market data, never opens a network
connection and never touches a trading process.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

CANONICAL_VERSION = "CANONICAL_LEDGER_V1"
GENESIS_DIGEST = "0" * 64

# The ledger kinds named in section 31 of the specification. A kind outside this
# set is rejected on append: a typo'd kind would silently create a second,
# invisible ledger.
LEDGER_KINDS = ("input", "decision", "trade", "incident")

_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


# Ledger files are evidence entries, so ledger I/O is lane I/O: every read and
# every append below goes through a LaneHandle rather than through a pathname.
# The safety properties (no symlinked target, no aliased mutable entry, no
# traversal, no resolve/open race) are enforced there once, for every file in the
# lane, instead of being re-remembered at each call site here.
from .lane_io import LaneHandle, LaneIOError  # noqa: E402


class LedgerError(RuntimeError):
    """Raised when a ledger is malformed, tampered with, or misused."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def canonical_payload(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def record_digest(seq: int, kind: str, recorded_utc: str, prev_digest: str, payload: dict) -> str:
    material = "\n".join(
        (CANONICAL_VERSION, str(seq), kind, recorded_utc, prev_digest, canonical_payload(payload))
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Record:
    seq: int
    kind: str
    recorded_utc: str
    prev_digest: str
    digest: str
    payload: dict

    def as_dict(self) -> dict:
        return {
            "seq": self.seq,
            "kind": self.kind,
            "recorded_utc": self.recorded_utc,
            "prev_digest": self.prev_digest,
            "digest": self.digest,
            "payload": self.payload,
        }


class Ledger:
    """One append-only ledger file of a single kind.

    ``Ledger`` is deliberately not a context manager holding an open handle: the
    file is opened for the duration of one append and fsync'd before returning.
    A paper runtime that is killed between decision cycles must not be able to
    lose the record of the decision it just made.
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        kind: str,
        *,
        lane: LaneHandle | None = None,
    ) -> None:
        if kind not in LEDGER_KINDS:
            raise LedgerError(f"unknown ledger kind {kind!r}; expected one of {LEDGER_KINDS}")
        self.path = Path(path)
        self.kind = kind
        # A caller that already holds the lane open passes it in, and every
        # operation then uses that one descriptor. A caller that does not gets a
        # handle opened per operation from the containing directory. Either way
        # the file is reached through a directory descriptor, never by name.
        self._lane = lane
        self._name = self.path.name

    @contextmanager
    def _open_lane(self) -> Iterator[LaneHandle]:
        if self._lane is not None:
            yield self._lane
            return
        handle = LaneHandle.open(self.path.parent)
        try:
            yield handle
        finally:
            handle.close()

    # -- reading ---------------------------------------------------------

    def __iter__(self) -> Iterator[Record]:
        try:
            with self._open_lane() as lane:
                if not lane.exists(self._name):
                    return
                text = lane.read_text(self._name)
        except LaneIOError as exc:
            raise LedgerError(str(exc)) from exc
        if True:
            for line_no, line in enumerate(text.splitlines(), start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise LedgerError(f"{self.path}:{line_no}: unreadable JSON: {exc}") from exc
                missing = {"seq", "kind", "recorded_utc", "prev_digest", "digest", "payload"} - set(raw)
                if missing:
                    raise LedgerError(f"{self.path}:{line_no}: missing keys {sorted(missing)}")
                yield Record(
                    seq=raw["seq"],
                    kind=raw["kind"],
                    recorded_utc=raw["recorded_utc"],
                    prev_digest=raw["prev_digest"],
                    digest=raw["digest"],
                    payload=raw["payload"],
                )

    def records(self) -> list[Record]:
        return list(self)

    def raw_text(self) -> str:
        """The ledger file's bytes, read through the lane.

        Gates that need the literal lines (a tamper negative control rebuilds
        them) get them here rather than by opening ``ledger.path`` themselves.
        A direct ``path.read_text()`` is the same unguarded pattern that let a
        symlinked evidence entry be read from outside the lane.
        """
        try:
            with self._open_lane() as lane:
                if not lane.exists(self._name):
                    return ""
                return lane.read_text(self._name)
        except LaneIOError as exc:
            raise LedgerError(str(exc)) from exc

    def head(self) -> tuple[int, str]:
        """Return (next_seq, last_digest) without validating the whole chain."""
        last_seq = -1
        last_digest = GENESIS_DIGEST
        for record in self:
            last_seq = record.seq
            last_digest = record.digest
        return last_seq + 1, last_digest

    # -- writing ---------------------------------------------------------

    def append(self, payload: dict, recorded_utc: str | None = None) -> Record:
        if not isinstance(payload, dict):
            raise LedgerError("payload must be a dict")
        stamp = recorded_utc or utc_now()
        if not _TS_RE.match(stamp):
            raise LedgerError(f"recorded_utc must be UTC ISO-8601 ending in Z, got {stamp!r}")
        seq, prev = self.head()
        digest = record_digest(seq, self.kind, stamp, prev, payload)
        record = Record(seq, self.kind, stamp, prev, digest, payload)

        line = json.dumps(record.as_dict(), sort_keys=True, ensure_ascii=False) + "\n"
        try:
            with self._open_lane() as lane:
                lane.append_text(self._name, line)
        except LaneIOError as exc:
            raise LedgerError(str(exc)) from exc
        return record

    def extend(self, payloads: list[dict], recorded_utc: str | None = None) -> list[Record]:
        """Append many records under a single open and a single fsync.

        The chain is identical to calling :meth:`append` repeatedly — each
        record still carries its predecessor's digest — but the durability
        boundary moves to the end of the batch. Use this for a bulk capture
        (a startup backfill of closed candles), never for a live decision,
        where losing the tail of a batch to a crash would lose the record of a
        decision that was actually taken.
        """
        stamp = recorded_utc or utc_now()
        if not _TS_RE.match(stamp):
            raise LedgerError(f"recorded_utc must be UTC ISO-8601 ending in Z, got {stamp!r}")
        for payload in payloads:
            if not isinstance(payload, dict):
                raise LedgerError("every payload must be a dict")

        seq, prev = self.head()
        written: list[Record] = []
        lines: list[str] = []
        for payload in payloads:
            digest = record_digest(seq, self.kind, stamp, prev, payload)
            record = Record(seq, self.kind, stamp, prev, digest, payload)
            lines.append(json.dumps(record.as_dict(), sort_keys=True, ensure_ascii=False) + "\n")
            written.append(record)
            seq += 1
            prev = digest
        try:
            with self._open_lane() as lane:
                lane.append_text(self._name, "".join(lines))
        except LaneIOError as exc:
            raise LedgerError(str(exc)) from exc
        return written

    def append_erratum(self, corrects_seq: int, reason: str, correction: dict) -> Record:
        """Record a correction *without* rewriting the record being corrected.

        Section 26: "Corrections are appended as errata, not silently
        rewritten." The original stays in the chain and stays valid.
        """
        known = {record.seq for record in self}
        if corrects_seq not in known:
            raise LedgerError(f"cannot correct seq {corrects_seq}: not present in {self.path}")
        return self.append(
            {
                "erratum": True,
                "corrects_seq": corrects_seq,
                "reason": reason,
                "correction": correction,
            }
        )

    # -- integrity -------------------------------------------------------

    def verify(self) -> list[str]:
        """Return a list of integrity problems; empty means the chain is intact."""
        problems: list[str] = []
        expected_seq = 0
        prev_digest = GENESIS_DIGEST
        try:
            records = self.records()
        except LedgerError as exc:
            return [str(exc)]

        for record in records:
            where = f"{self.path}#{record.seq}"
            if record.kind != self.kind:
                problems.append(f"{where}: kind {record.kind!r} in a {self.kind!r} ledger")
            if record.seq != expected_seq:
                problems.append(f"{where}: out-of-order sequence, expected {expected_seq}")
            if record.prev_digest != prev_digest:
                problems.append(f"{where}: broken chain, prev_digest does not match the previous record")
            recomputed = record_digest(
                record.seq, record.kind, record.recorded_utc, record.prev_digest, record.payload
            )
            if recomputed != record.digest:
                problems.append(f"{where}: digest mismatch — the record was altered after it was written")
            expected_seq = record.seq + 1
            prev_digest = record.digest
        return problems

    def tip_digest(self) -> str:
        return self.head()[1]


def open_ledgers(
    directory: str | os.PathLike[str],
    *,
    lane: LaneHandle | None = None,
    create: bool = False,
) -> dict[str, Ledger]:
    """Open the four specification ledgers under one evidence directory.

    ``create`` is the only way a ledger call creates a directory. It used to
    happen implicitly on every append, which meant a mistyped evidence path
    quietly produced a second, plausible-looking lane instead of failing. Lane
    creation now has one owner, and it is whoever passes ``create=True``.
    """
    base = Path(directory)
    if lane is None and create:
        LaneHandle.open(base, create=True).close()
    return {
        kind: Ledger(base / f"paper_{kind}_ledger.jsonl", kind, lane=lane)
        for kind in LEDGER_KINDS
    }


def daily_pack_digest(ledgers: Iterable[Ledger]) -> str:
    """Digest binding a set of ledger tips together (section 26).

    The daily evidence pack "gets its own digest". Binding the tips means the
    pack cannot be reissued later over a mutated ledger without the digest
    moving.
    """
    parts = [CANONICAL_VERSION, "daily_pack"]
    for ledger in sorted(ledgers, key=lambda item: item.kind):
        parts.append(f"{ledger.kind}:{ledger.tip_digest()}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
