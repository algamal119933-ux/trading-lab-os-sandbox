#!/usr/bin/env python3
"""Deterministic triage of a Freqtrade Strategy Verification intake.

    python3 verification/intake/triage.py intake.json

Prints the outcome (ACCEPT · NEEDS_INFO · OUT_OF_SCOPE), every reason in a
stable order, and the customer-facing message for each. The same intake always
gets the same answer. The secret scan runs on the raw submission before
anything else, so a key is caught even in a malformed intake.

Exit codes: 0 ACCEPT · 1 NEEDS_INFO · 2 OUT_OF_SCOPE.

No database, no web service, nothing stored: the intake is read and answered.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import jsonschema

HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / "intake.schema.json").read_text(encoding="utf-8"))
RUBRIC = json.loads((HERE / "rubric.json").read_text(encoding="utf-8"))

_SECRET_NAME = re.compile(r"(?i)(api[_-]?key|secret|password|passphrase|private[_-]?key|token|^key$|^uid$)")
_SECRET_VALUE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
EXIT = {"ACCEPT": 0, "NEEDS_INFO": 1, "OUT_OF_SCOPE": 2}


def _secrets(node: object) -> bool:
    if isinstance(node, dict):
        for name, value in node.items():
            if _SECRET_NAME.search(str(name)) and value not in (None, "", False):
                return True
            if _secrets(value):
                return True
    elif isinstance(node, list):
        return any(_secrets(v) for v in node)
    elif isinstance(node, str):
        return bool(_SECRET_VALUE.search(node))
    return False


def _sha(value: object) -> bool:
    return isinstance(value, str) and bool(_HEX64.match(value))


def triage(intake: object) -> dict:
    """Pure: {outcome, reasons, messages, notes}."""
    reasons: list[str] = []
    if _secrets(intake):
        reasons.append("SECRET_IN_SUBMISSION")

    errors = sorted(jsonschema.Draft202012Validator(SCHEMA).iter_errors(intake), key=lambda e: list(e.path))
    if errors:
        reasons.append("SCHEMA_INVALID")
        return _verdict(reasons, [], detail=[e.message for e in errors])

    s, c, e, m, cl, r = (intake[k] for k in ("strategy", "config", "engine", "market", "claim", "rights"))

    if not c["dry_run"]:
        reasons.append("LIVE_TRADING_REQUESTED")
    if c["trading_mode"] != "spot" or c.get("margin_mode", ""):
        reasons.append("FUTURES_OR_MARGIN")
    if c["can_short"]:
        reasons.append("SHORTS")
    if c["leverage"] != 1:
        reasons.append("LEVERAGE")
    if not r["licence_spdx"] and not r["submitter_holds_rights"]:
        reasons.append("NO_RIGHTS")

    src = s["source"]
    if (src["kind"] == "public_repo" and not (src.get("url") and _HEX40.match(src.get("commit", "")))) or \
            (src["kind"] == "archive" and not _sha(src.get("archive_sha256"))):
        reasons.append("SOURCE_UNPINNED")

    missing = []
    if not _sha(s["strategy_sha256"]):
        missing.append("strategy")
    if not _sha(s["params_sha256"]) and not (s["params_sha256"] is None and s.get("params_file_absent") is True):
        missing.append("params")
    if not _sha(c["sha256"]):
        missing.append("config")
    if not e["freqtrade_version"]:
        missing.append("engine")
    if not m["pairs"] or not m["timeframe"] or not m["timerange"]:
        missing.append("market")
    reasons += [f"IDENTITY_INCOMPLETE:{x}" for x in missing]

    notes = []
    if cl["stated"] and not (cl.get("text") and cl.get("source")):
        reasons.append("CLAIM_WITHOUT_SOURCE")
    if not cl["stated"]:
        notes.append("NO_CLAIM")
    return _verdict(reasons, notes)


def _verdict(reasons: list[str], notes: list[str], detail: list[str] | None = None) -> dict:
    outcomes = {RUBRIC["reasons"][x.split(":", 1)[0]]["outcome"] for x in reasons}
    outcome = next((o for o in RUBRIC["precedence"] if o in outcomes), "ACCEPT")
    result = {
        "outcome": outcome,
        "reasons": reasons,
        "messages": [RUBRIC["reasons"][x.split(":", 1)[0]]["message"] for x in reasons],
        "notes": [RUBRIC["notes"][n] for n in notes],
    }
    if detail:
        result["schema_errors"] = detail
    return result


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__)
        return 1
    result = triage(json.loads(Path(args[0]).read_text(encoding="utf-8")))
    print(json.dumps(result, indent=2))
    return EXIT[result["outcome"]]


if __name__ == "__main__":
    sys.exit(main())
