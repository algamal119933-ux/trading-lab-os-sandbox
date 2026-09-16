#!/usr/bin/env python3
"""Seal what the pre-T0 qualification run actually established, while it is live.

    scripts/seal_pre_t0_qualification.py FP-CONTROL-2 \
        --evidence-dir freqtrade/user_data/fp-control-2/evidence \
        --image-digest sha256:<64hex> --python-version 3.14.6 \
        -o artifacts/p2-s3-qualification/certificate.json

Contract section 6, S3: the certificate is generated WHILE L1 IS LIVE, and only
then is the lane stopped, sealed and archived. That ordering is not a
convenience. A certificate written after the lane was archived would be a
statement about a directory, not about a runtime; the observations it carries —
the engine's image digest and Python version — exist only while something is
running to observe.

What the certificate is *for*: its sha256 is the value the Owner's T0
authorization names, and the value the S3b binding record pins. That is how a
merge-gated authorization can refer to a runtime artifact that is deliberately
not in Git. A certificate whose bytes change is a different certificate, and
``freeze_t0`` will refuse it.

Every refusal below leaves the registry and the lane byte-identical. This tool
reads; the only thing it writes is the certificate, and never inside a lane.

Exit codes: 0 sealed; 2 refused.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from fp import capability as fp_capability  # noqa: E402
from fp import lane as fp_lane  # noqa: E402
from fp import ledger as fp_ledger  # noqa: E402
from fp import preflight as fp_preflight  # noqa: E402
from fp import reconcile as fp_reconcile  # noqa: E402
from fp import registry_law as fp_law  # noqa: E402
from fp import semantic_identity as fp_semantic  # noqa: E402

CERTIFICATE_VERSION = "FP_PRE_T0_QUALIFICATION_CERTIFICATE_V1"
IMAGE_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")

# Derived, never restated. research/fp/capability.py is the single source of the
# property model, and a second hand-written copy here would be a second model
# the moment one of them was edited.
NON_LIFECYCLE_PROPERTIES = fp_capability.PRE_T0_QUALIFIABLE


class SealError(Exception):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise SealError(f"git {' '.join(args)} failed: {result.stderr.strip()[:200]}")
    return result.stdout.strip()


def _require_clean_tree() -> str:
    """Mq must describe what ran. A dirty tree makes the commit a false statement.

    Same reasoning as the launcher's own source gate: a tracked file that
    differs from HEAD — an edited registry, a substituted strategy — makes the
    stamped commit untrue, and the forged content would then agree with itself
    through every later identity check.
    """
    state = _git(["status", "--porcelain", "--untracked-files=no"])
    if state:
        raise SealError(
            "tracked files differ from HEAD, so the qualification commit would not describe what "
            f"ran:\n{state}"
        )
    return _git(["rev-parse", "HEAD"])


def seal(
    role: str,
    evidence_dir: Path,
    *,
    image_digest: str,
    python_version: str,
    lane_archive_name: str | None = None,
) -> dict:
    """Build the certificate, or refuse. Never writes anything."""
    if not IMAGE_DIGEST_RE.match(image_digest or ""):
        raise SealError(
            f"--image-digest {image_digest!r} is not a sha256 digest. It is observed from the "
            "running engine, not typed from memory"
        )
    if not (python_version or "").strip():
        raise SealError("--python-version is required: it is observed from the running engine")

    mq = _require_clean_tree()

    registry = fp_law.load_registry()
    violations = fp_law.check_registry(registry)
    if violations:
        raise SealError("the cohort registry is not lawful: " + "; ".join(violations[:3]))

    try:
        row = fp_lane.select_row(role, registry)
    except fp_lane.LaneError as exc:
        raise SealError(str(exc)) from exc

    # A qualification lane is pre-T0 by definition. If the row already carries a
    # T0 or a cohort id, this is not a qualification run and sealing it as one
    # would produce a certificate that outranks its own evidence.
    if row.get("status") != "NOT_STARTED":
        raise SealError(
            f"{role} is {row.get('status')}, not NOT_STARTED. A qualification certificate "
            "describes a pre-T0 lane; a started row's evidence is prospective evidence and is "
            "never sealed as qualification"
        )
    for field in ("t0_utc", "cohort_id"):
        if row.get(field) is not None:
            raise SealError(f"{role} already carries {field}={row[field]!r}; this is not a pre-T0 lane")

    evidence_dir = Path(evidence_dir)
    lane = fp_lane.resolve_lane(role, registry)
    if not lane.matches_evidence_dir(evidence_dir):
        raise SealError(
            f"{evidence_dir} is not the evidence directory {role} declares "
            f"({lane.container_evidence_dir})"
        )
    if not evidence_dir.is_dir():
        raise SealError(f"{evidence_dir} does not exist; there is no qualification run to seal")

    # -- what the run actually established ---------------------------------
    reconciliation = fp_reconcile.reconcile(
        evidence_dir, expected_role=role, expected_source_commit=mq
    )
    if reconciliation["reconciliation"] != fp_reconcile.PASS:
        raise SealError(
            "reconciliation does not pass over the qualification lane: "
            f"{reconciliation['failing_checks']}"
        )

    runtime = fp_preflight.RuntimeContext(evidence_dir=evidence_dir, role=role)
    preflight = fp_preflight.run(runtime=runtime)
    if preflight["preflight"] != fp_preflight.PASS:
        failing = [c["check"] for c in preflight["checks"] if c["result"] != fp_preflight.PASS]
        raise SealError(f"preflight is {preflight['preflight']}; not PASS: {failing}")

    ledgers = fp_ledger.open_ledgers(evidence_dir)
    decisions = [r for r in ledgers["decision"].records() if not r.payload.get("erratum")]
    relations = {r.payload.get("t0_relation") for r in decisions if r.payload.get("t0_relation")}
    if relations - {"T0_NOT_FROZEN"}:
        raise SealError(
            f"the lane holds decisions reading {sorted(relations)}; a pre-T0 qualification lane's "
            "every record must read T0_NOT_FROZEN, or it is not a fresh lane"
        )
    cohorts = {
        (r.payload.get("identity") or {}).get("cohort_id")
        for name in ("input", "decision", "trade", "incident")
        for r in ledgers[name].records()
        if not r.payload.get("erratum")
    }
    if cohorts - {None}:
        raise SealError(
            f"the lane holds records stamped with cohort id(s) {sorted(c for c in cohorts if c)}; "
            "a qualification lane carries none"
        )

    identity = fp_semantic.semantic_identity(mq, role)

    return {
        "certificate_version": CERTIFICATE_VERSION,
        "sealed_utc": _utc(),
        "role": role,
        "qualification_commit": mq,
        "semantic_identity_digest": identity.digest,
        "runtime_tree_entries": len(identity.runtime_tree),
        "observations": {
            "image_digest": image_digest,
            "python_version": python_version,
            "engine_version": (row.get("runtime_identity") or {}).get("engine_version"),
        },
        "qualification_result": {
            "preflight": preflight["preflight"],
            "preflight_checks_passed": sum(
                1 for c in preflight["checks"] if c["result"] == fp_preflight.PASS
            ),
            "preflight_checks_total": len(preflight["checks"]),
            "reconciliation": reconciliation["reconciliation"],
            "properties_evidenced": list(NON_LIFECYCLE_PROPERTIES),
            "lane_archive_name": lane_archive_name,
        },
        "evidence": {
            "evidence_dir": str(evidence_dir),
            "counts": reconciliation["counts"],
            "ledger_tips": reconciliation["ledger_tips"],
            "daily_pack_digest": reconciliation["daily_pack_digest"],
        },
        "t0_relation_of_every_record": "T0_NOT_FROZEN",
        "prospective_evidence": "NONE",
        "prospective_lifecycle_evidence": (
            "NONE. L1 proves the machinery works at this commit. It proves nothing about a forward "
            "window, and no record sealed here may be presented as prospective lifecycle evidence."
        ),
        "real_money_authorized": False,
    }


def write_certificate(certificate: dict, out: Path) -> tuple[Path, str]:
    """Write the certificate outside every lane, and return its sha256.

    The hash is of the bytes as written, because that is what the Owner's
    authorization will name. A certificate cannot contain its own hash, so the
    file is the thing that is hashed and the value is reported here.
    """
    out = Path(out)
    destination = out.resolve()
    for declared in fp_lane.all_lane_roots():
        if destination == declared or declared in destination.parents:
            raise SealError(
                f"{out} is inside the evidence lane {declared}; a certificate about a lane is not "
                "written into it"
            )
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(certificate, indent=2, sort_keys=True) + "\n"
    out.write_text(text, encoding="utf-8")
    return out, hashlib.sha256(text.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("role")
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--image-digest", required=True, help="observed from the running engine")
    parser.add_argument("--python-version", required=True, help="observed from the running engine")
    parser.add_argument("--lane-archive-name", default=None)
    parser.add_argument("-o", "--out", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        certificate = seal(
            args.role,
            Path(args.evidence_dir),
            image_digest=args.image_digest,
            python_version=args.python_version,
            lane_archive_name=args.lane_archive_name,
        )
        path, digest = write_certificate(certificate, Path(args.out))
    except (SealError, fp_lane.LaneError, fp_semantic.SemanticIdentityError) as exc:
        print(f"QUALIFICATION_SEAL_REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.json:
        sys.stdout.write(json.dumps(certificate, indent=2) + "\n")
    else:
        print(f"QUALIFICATION_SEALED {certificate['role']} at {certificate['qualification_commit']}")
        print(f"  preflight        {certificate['qualification_result']['preflight']} "
              f"({certificate['qualification_result']['preflight_checks_passed']}/"
              f"{certificate['qualification_result']['preflight_checks_total']})")
        print(f"  reconciliation   {certificate['qualification_result']['reconciliation']}")
        print(f"  counts           {certificate['evidence']['counts']}")
        print(f"  pack digest      {certificate['evidence']['daily_pack_digest']}")
        print(f"  semantic id      {certificate['semantic_identity_digest']}")
        print()
        print(f"certificate      {path}")
        print(f"CERTIFICATE_SHA256 = {digest}")
        print()
        print("This value is what docs/p2/OWNER_T0_AUTHORIZATION.md must name, and what the S3b")
        print("binding record pins. It authorizes nothing by itself.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
