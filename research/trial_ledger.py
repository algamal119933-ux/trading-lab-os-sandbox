"""Append-only, hash-chained accounting for research trials.

Reuses the exact canonical digest algorithm from ``research/fp/ledger.py``
(``CANONICAL_LEDGER_V1`` payload encoding, sha256 hash chain over
seq/kind/recorded_utc/prev_digest/payload) so a research trial record and an
FP paper-runtime record are provably the same *kind* of evidence, without
merging the two domains: the FP ledger enforces paper-runtime events
(input/decision/trade/incident) for a *running* control; this one enforces
research-selection events (``trial``) for *offline* research, and refuses to
become an evidence lane for anything else. Nothing here reads market data,
opens a network connection, or touches a live trading process.

This module exists to close one specific, named gap: the project's existing
research documents (``research/schema/experiment_record.schema.json``,
``research/external/candidate_registry.json``'s own ``LOCAL_TRIAL_COUNT`` /
``upstream_selection_debt`` fields, ``qualification_gates.json``'s
``verdict_model``) already say the right things about what a trial is and how
it should be judged, but nothing technically stops a winning configuration
from being registered after the fact while its losing siblings are simply
never written down. ``TrialLedger`` is that technical stop:

* every trial must be **preregistered** — appended with ``state ==
  "PREREGISTERED"`` and no ``outcome`` — before any terminal record for the
  same ``trial_id`` may be appended;
* :meth:`TrialLedger.append` looks the preregistration up in the ledger's own
  prior records, not in a caller-supplied claim, so a terminal record cannot
  be written for a ``trial_id`` that was never preregistered, and the hash
  chain means a preregistration cannot be inserted retroactively without
  breaking every record after it;
* seven identity fields (family/lineage/candidate/config/experiment/run/
  trial) are required on every record and are never derived from one
  another, so a hundred CONFIG attempts under one LINEAGE stay a hundred rows,
  not one;
* nothing is ever rewritten. A mistaken record is corrected the same way the
  FP ledger corrects one: a new row, never an edit.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from fp.ledger import (  # noqa: E402
    CANONICAL_VERSION,
    GENESIS_DIGEST,
    canonical_payload,
    record_digest,
)

TRIAL_KIND = "trial"

PREREGISTERED = "PREREGISTERED"
TERMINAL_STATES = ("COMPLETED", "FAILED", "ABORTED", "REJECTED", "SURVIVED")
STATES = (PREREGISTERED,) + TERMINAL_STATES

IDENTITY_FIELDS = (
    "family_id", "lineage_id", "candidate_id", "config_id",
    "experiment_id", "run_id", "trial_id",
)

_SCHEMA_PATH = _RESEARCH_DIR / "schema" / "trial_record.schema.json"
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


class TrialLedgerError(RuntimeError):
    """Raised when a trial record is malformed, out of order, or unregistered."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class TrialRecord:
    seq: int
    recorded_utc: str
    prev_digest: str
    digest: str
    payload: dict

    def as_dict(self) -> dict:
        return {
            "seq": self.seq,
            "kind": TRIAL_KIND,
            "recorded_utc": self.recorded_utc,
            "prev_digest": self.prev_digest,
            "digest": self.digest,
            "payload": self.payload,
        }


class TrialLedger:
    """One append-only ledger file of research trial-accounting records."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    # -- reading -----------------------------------------------------------

    def __iter__(self) -> Iterator[TrialRecord]:
        if not self.path.exists():
            return
        text = self.path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TrialLedgerError(f"{self.path}:{line_no}: unreadable JSON: {exc}") from exc
            missing = {"seq", "kind", "recorded_utc", "prev_digest", "digest", "payload"} - set(raw)
            if missing:
                raise TrialLedgerError(f"{self.path}:{line_no}: missing keys {sorted(missing)}")
            if raw["kind"] != TRIAL_KIND:
                raise TrialLedgerError(f"{self.path}:{line_no}: kind {raw['kind']!r} in a trial ledger")
            yield TrialRecord(
                seq=raw["seq"], recorded_utc=raw["recorded_utc"],
                prev_digest=raw["prev_digest"], digest=raw["digest"], payload=raw["payload"],
            )

    def records(self) -> list[TrialRecord]:
        return list(self)

    def head(self) -> tuple[int, str]:
        last_seq, last_digest = -1, GENESIS_DIGEST
        for record in self:
            last_seq, last_digest = record.seq, record.digest
        return last_seq + 1, last_digest

    def preregistration_for(self, trial_id: str) -> TrialRecord | None:
        """The PREREGISTERED record for ``trial_id``, if one has been written."""
        for record in self:
            if record.payload.get("trial_id") == trial_id and record.payload.get("state") == PREREGISTERED:
                return record
        return None

    def records_for(self, **identity: str) -> list[TrialRecord]:
        """Records matching every named identity field (e.g. ``lineage_id=...``)."""
        return [
            r for r in self
            if all(r.payload.get(field) == value for field, value in identity.items())
        ]

    # -- writing -------------------------------------------------------------

    def append(self, payload: dict, recorded_utc: str | None = None) -> TrialRecord:
        """Validate and append one trial record.

        Refuses (raises :class:`TrialLedgerError`, writes nothing) unless:

        * ``payload`` validates against ``trial_record.schema.json``;
        * every identity field in :data:`IDENTITY_FIELDS` is present;
        * a terminal-state record (``state`` in :data:`TERMINAL_STATES`) names a
          ``trial_id`` that already has a ``PREREGISTERED`` record earlier in
          this exact ledger — never a caller-supplied claim that one exists;
        * a ``PREREGISTERED`` record for a ``trial_id`` that already has one is
          refused: a trial is preregistered exactly once.
        """
        import jsonschema

        if not isinstance(payload, dict):
            raise TrialLedgerError("payload must be a dict")
        missing_identity = [f for f in IDENTITY_FIELDS if not payload.get(f)]
        if missing_identity:
            raise TrialLedgerError(f"missing identity field(s): {missing_identity}")
        state = payload.get("state")
        if state not in STATES:
            raise TrialLedgerError(f"state must be one of {STATES}, got {state!r}")

        try:
            jsonschema.validate(payload, _load_schema())
        except jsonschema.exceptions.ValidationError as exc:
            raise TrialLedgerError(f"malformed trial record: {exc.message}") from exc

        trial_id = payload["trial_id"]
        existing_prereg = self.preregistration_for(trial_id)
        if state == PREREGISTERED:
            if existing_prereg is not None:
                raise TrialLedgerError(
                    f"trial_id {trial_id!r} is already preregistered at seq {existing_prereg.seq}; "
                    "a trial is preregistered exactly once"
                )
        else:
            if existing_prereg is None:
                raise TrialLedgerError(
                    f"cannot record a {state} outcome for trial_id {trial_id!r}: no PREREGISTERED "
                    "record for it exists in this ledger. Preregister the trial before its outcome "
                    "is known, then record the outcome as a separate, later record."
                )
            if existing_prereg.payload.get("purpose") != payload.get("purpose"):
                raise TrialLedgerError(
                    f"trial_id {trial_id!r}: purpose at outcome time does not match the "
                    "preregistered purpose — the declared reason for a trial may not change "
                    "once its outcome is known"
                )

        stamp = recorded_utc or utc_now()
        if not _TS_RE.match(stamp):
            raise TrialLedgerError(f"recorded_utc must be UTC ISO-8601 ending in Z, got {stamp!r}")
        seq, prev = self.head()
        digest = record_digest(seq, TRIAL_KIND, stamp, prev, payload)
        record = TrialRecord(seq, stamp, prev, digest, payload)

        line = json.dumps(record.as_dict(), sort_keys=True, ensure_ascii=False) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            import os

            os.fsync(fh.fileno())
        return record

    # -- integrity -----------------------------------------------------------

    def verify(self) -> list[str]:
        """Return a list of integrity problems; empty means the chain is intact."""
        problems: list[str] = []
        expected_seq = 0
        prev_digest = GENESIS_DIGEST
        preregistered_trials: set[str] = set()
        try:
            records = self.records()
        except TrialLedgerError as exc:
            return [str(exc)]

        for record in records:
            where = f"{self.path}#{record.seq}"
            if record.seq != expected_seq:
                problems.append(f"{where}: out-of-order sequence, expected {expected_seq}")
            if record.prev_digest != prev_digest:
                problems.append(f"{where}: broken chain, prev_digest does not match the previous record")
            recomputed = record_digest(record.seq, TRIAL_KIND, record.recorded_utc,
                                        record.prev_digest, record.payload)
            if recomputed != record.digest:
                problems.append(f"{where}: digest mismatch — the record was altered after it was written")

            trial_id = record.payload.get("trial_id")
            state = record.payload.get("state")
            if state == PREREGISTERED:
                if trial_id in preregistered_trials:
                    problems.append(f"{where}: trial_id {trial_id!r} preregistered more than once")
                preregistered_trials.add(trial_id)
            elif state in TERMINAL_STATES:
                if trial_id not in preregistered_trials:
                    problems.append(
                        f"{where}: terminal state {state!r} for trial_id {trial_id!r} with no "
                        "preceding PREREGISTERED record — result-only retroactive registration"
                    )

            expected_seq = record.seq + 1
            prev_digest = record.digest
        return problems

    def tip_digest(self) -> str:
        return self.head()[1]
