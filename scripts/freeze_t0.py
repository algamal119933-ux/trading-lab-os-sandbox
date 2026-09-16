#!/usr/bin/env python3
"""Freeze T0: the one act that turns a registered instance into a cohort.

    scripts/freeze_t0.py FP-CONTROL-2 --t0 2026-09-20T14:00:00Z

This tool is BUILT in S2 and RUN in S5b, and nothing about that ordering is
enforced by a flag. It is enforced by the thing it reads:

    docs/p2/OWNER_T0_AUTHORIZATION.md

which does not exist, is created only by an Owner-merged PR at the moment the
Owner grants T0 authority, and is read FROM GIT AT HEAD — not from the working
tree, which anyone at this keyboard can write. Its absence is the default, and
the default is refusal.

There is no authorization token, and adding one would be a downgrade. A secret
can be guessed, leaked, copied out of a transcript, or supplied by whoever is
sitting here. A merge cannot: only the Owner can perform one, and the record of
it is public, dated and reviewable.

WHAT IT MAY CHANGE — contract section 6, and nothing else:

    research/fp/records/forward_paper_cohort_registry.json
    MANIFEST.txt

    t0_utc                          null -> <T0>
    cohort_id                       null -> <role>-<T0 with : and - removed>
    status                          NOT_STARTED -> RUNNING
    runtime_identity.source_commit  null -> M1 (this HEAD)
    change_log                      [] -> [ one class-O entry ]
    fp_run_active                   false -> true
    registry_updated_utc            bumped

Two files is not a stylistic preference: it makes the equivalence proof total
and reviewable in one line, because ``git diff --name-only M1 M2`` must equal
exactly that pair.

Exit codes: 0 frozen; 2 refused. Every refusal leaves the registry, MANIFEST and
the working tree byte-identical — a gate that half-applies its transaction is
worse than no gate.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from fp import archive as fp_archive  # noqa: E402
from fp import registry_law as fp_law  # noqa: E402
from fp import semantic_identity as fp_semantic  # noqa: E402

AUTHORIZATION_PATH = "docs/p2/OWNER_T0_AUTHORIZATION.md"
BINDING_PATH = "research/fp/records/p2_qualification_binding.json"
REGISTRY_PATH = "research/fp/records/forward_paper_cohort_registry.json"
MANIFEST_PATH = "MANIFEST.txt"

T0_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

# A T0 frozen far ahead is a cohort whose identity is frozen against a system
# that has time to move underneath it before anything runs. Seven days is
# generous for a merge the Owner has already decided to perform.
MAX_FREEZE_TO_T0 = timedelta(days=7)

# The keys an authorization must carry, each exactly once. A file that says two
# things about the same key is not an authorization, it is an ambiguity, and
# resolving it here would mean choosing on the Owner's behalf.
AUTHORIZATION_KEYS = (
    "ROLE",
    "QUALIFICATION_COMMIT",
    "QUALIFICATION_CERTIFICATE_SHA256",
    "REAL_MONEY_AUTHORIZED",
    "EXPIRES_UTC",
)
AUTHORIZATION_LINE = re.compile(r"^\s*([A-Z0-9_]+)\s*=\s*(\S.*?)\s*$")


class FreezeRefused(Exception):
    """T0 was not frozen. Nothing was written."""


def _git(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, timeout=300
    )
    if check and result.returncode != 0:
        raise FreezeRefused(f"git {' '.join(args)} failed: {result.stderr.strip()[:300]}")
    return result


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc(value: str, field: str) -> datetime:
    if not T0_RE.match(value or ""):
        raise FreezeRefused(f"{field} is {value!r}, which is not YYYY-MM-DDTHH:MM:SSZ")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def read_authorization(head: str) -> dict:
    """The Owner's authorization as it exists in git at HEAD, or a refusal.

    Read with ``git show``, never from the working tree. A working-tree read
    would make "the Owner authorized this" a claim anyone with write access to
    this directory could manufacture, which is the entire distinction between a
    merge and a file.
    """
    result = _git(["show", f"{head}:{AUTHORIZATION_PATH}"], check=False)
    if result.returncode != 0:
        raise FreezeRefused(
            f"{AUTHORIZATION_PATH} does not exist at {head[:8]}. T0 authority is a merged record: "
            "it is created by an Owner-merged PR at the moment authority is granted, and never "
            "before. Its absence is the default, and the default is refusal"
        )
    text = result.stdout

    found: dict[str, list[str]] = {}
    for line in text.splitlines():
        match = AUTHORIZATION_LINE.match(line)
        if match and match.group(1) in AUTHORIZATION_KEYS:
            found.setdefault(match.group(1), []).append(match.group(2))

    missing = [key for key in AUTHORIZATION_KEYS if key not in found]
    if missing:
        raise FreezeRefused(
            f"{AUTHORIZATION_PATH} at {head[:8]} does not declare {missing}. Every field is "
            "required: an authorization that omits what it authorizes authorizes nothing"
        )
    ambiguous = sorted(key for key, values in found.items() if len(values) > 1)
    if ambiguous:
        raise FreezeRefused(
            f"{AUTHORIZATION_PATH} declares {ambiguous} more than once. A file that says two "
            "things about one field is an ambiguity, and resolving it here would mean choosing "
            "on the Owner's behalf"
        )
    return {key: values[0] for key, values in found.items()}


def read_binding(head: str) -> dict:
    """The S3b qualification binding at HEAD, or a refusal."""
    result = _git(["show", f"{head}:{BINDING_PATH}"], check=False)
    if result.returncode != 0:
        raise FreezeRefused(
            f"{BINDING_PATH} does not exist at {head[:8]}. The authorization names a qualification "
            "certificate, and without the merged S3b binding there is nothing to check that name "
            "against — a hash compared to nothing is not a check"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FreezeRefused(f"{BINDING_PATH} at {head[:8]} is not valid JSON: {exc}") from exc


def check_preconditions(role: str, t0: str, *, head: str | None = None) -> dict:
    """Every condition that must hold before a T0 may be written.

    Returns the facts the freeze will use. Raises :class:`FreezeRefused` on the
    first condition that does not hold, and writes nothing under any outcome.
    """
    # -- the source must describe what will run ---------------------------
    state = _git(["status", "--porcelain", "--untracked-files=no"]).stdout.strip()
    if state:
        raise FreezeRefused(
            f"tracked files differ from HEAD; the frozen source commit would not describe what "
            f"runs:\n{state}"
        )
    head = head or _git(["rev-parse", "HEAD"]).stdout.strip()

    parents = _git(["rev-list", "--parents", "-n", "1", head]).stdout.split()
    if len(parents) != 3:
        raise FreezeRefused(
            f"HEAD {head[:8]} has {len(parents) - 1} parent(s); M1 is a merged main, which is a "
            "two-parent merge the Owner performed. Freezing from a commit that was never merged "
            "would declare a source commit no review ever saw"
        )
    # Ancestry is proved, not asserted — contract section 1.
    _git(["fetch", "--quiet", "origin", "main"], check=False)
    for ref in ("refs/remotes/origin/main", "FETCH_HEAD"):
        probe = _git(["merge-base", "--is-ancestor", head, ref], check=False)
        if probe.returncode == 0:
            break
    else:
        raise FreezeRefused(
            f"HEAD {head[:8]} is not an ancestor of origin/main. M1 is merged main; a commit that "
            "is not on main is not the authoritative pre-freeze source"
        )

    # -- the Owner's authorization ----------------------------------------
    authorization = read_authorization(head)
    if authorization["ROLE"] != role:
        raise FreezeRefused(
            f"the authorization names role {authorization['ROLE']!r}, not {role!r}"
        )
    if authorization["REAL_MONEY_AUTHORIZED"].strip().upper() != "NO":
        raise FreezeRefused(
            f"the authorization declares REAL_MONEY_AUTHORIZED = "
            f"{authorization['REAL_MONEY_AUTHORIZED']!r}. This project is PAPER / RESEARCH ONLY "
            "and the only admissible value is NO"
        )
    expires = _parse_utc(authorization["EXPIRES_UTC"], "EXPIRES_UTC")
    now = _utc_now()
    if expires <= now:
        raise FreezeRefused(
            f"the authorization expired at {authorization['EXPIRES_UTC']}; it is now "
            f"{now.strftime('%Y-%m-%dT%H:%M:%SZ')}. An authorization that never expires is one "
            "that outlives the state it was granted against"
        )
    mq = authorization["QUALIFICATION_COMMIT"].strip()
    if not COMMIT_RE.match(mq):
        raise FreezeRefused(f"QUALIFICATION_COMMIT {mq!r} is not a 40-hex commit id")
    certificate_sha = authorization["QUALIFICATION_CERTIFICATE_SHA256"].strip().lower()
    if not SHA256_RE.match(certificate_sha):
        raise FreezeRefused(
            f"QUALIFICATION_CERTIFICATE_SHA256 {certificate_sha!r} is not a sha256 digest"
        )

    # -- the S3b binding must agree with it -------------------------------
    binding = read_binding(head)
    if binding.get("role") != role:
        raise FreezeRefused(f"the S3b binding is for {binding.get('role')!r}, not {role!r}")
    if binding.get("certificate_sha256") != certificate_sha:
        raise FreezeRefused(
            f"the authorization names certificate {certificate_sha[:12]}… but the merged S3b "
            f"binding pins {str(binding.get('certificate_sha256'))[:12]}…. The Owner authorized a "
            "different qualification run than the one on main"
        )
    if binding.get("qualification_commit") != mq:
        raise FreezeRefused(
            f"the authorization names Mq {mq[:8]} but the binding records "
            f"{str(binding.get('qualification_commit'))[:8]}"
        )
    if binding.get("real_money_authorized") is not False:
        raise FreezeRefused("the S3b binding does not declare real_money_authorized = false")

    if _git(["merge-base", "--is-ancestor", mq, head], check=False).returncode != 0:
        raise FreezeRefused(
            f"the qualification commit {mq[:8]} is not an ancestor of {head[:8]}; the run that "
            "qualified this host is not in the history being frozen"
        )

    # -- the two commits must run the same system -------------------------
    equivalence = fp_semantic.compare(mq, head, role)
    if equivalence["result"] != fp_semantic.EQUIVALENT:
        raise FreezeRefused(
            f"SEMANTIC_IDENTITY({mq[:8]}) is not SEMANTIC_IDENTITY({head[:8]}): "
            f"{equivalence['result']} — {equivalence['detail']}"
        )
    declared_digest = binding.get("semantic_identity_digest")
    if declared_digest and declared_digest != equivalence["left"]["digest"]:
        raise FreezeRefused(
            f"the S3b binding records semantic identity {declared_digest[:12]}… for {mq[:8]}, but "
            f"it computes to {equivalence['left']['digest'][:12]}… now"
        )

    # -- the registry must be in the pre-freeze state ---------------------
    registry = fp_law.load_registry()
    violations = fp_law.check_registry(registry)
    if violations:
        raise FreezeRefused("the cohort registry is not lawful: " + "; ".join(violations[:3]))
    rows = [item for item in registry["instances"] if item.get("role") == role]
    if len(rows) != 1:
        raise FreezeRefused(f"the registry declares {len(rows)} rows for {role}")
    row = rows[0]
    if row.get("status") != "NOT_STARTED":
        raise FreezeRefused(
            f"{role} is {row.get('status')}, not NOT_STARTED. A T0 is frozen once, onto a row that "
            "has started nothing; re-freezing a started row would replace a cohort's identity "
            "while its evidence still claims the old one"
        )
    for field in ("t0_utc", "cohort_id", "closed_utc", "closure_reason"):
        if row.get(field) is not None:
            raise FreezeRefused(f"{role} already carries {field}={row[field]!r}")
    if (row.get("runtime_identity") or {}).get("source_commit") is not None:
        raise FreezeRefused(f"{role} already declares a source_commit")
    if row.get("change_log"):
        raise FreezeRefused(
            f"{role}'s change_log is not empty; the freeze appends the first entry and would "
            "otherwise be writing into a history it did not create"
        )
    if registry.get("fp_run_active") is not False:
        raise FreezeRefused("fp_run_active is already true; a run is recorded as live")
    if registry.get("real_money_authorized") is not False:
        raise FreezeRefused("the registry does not declare real_money_authorized = false")

    # -- the lane must be fresh and empty ---------------------------------
    empty, detail = fp_archive.lane_is_empty(role, registry)
    if not empty:
        raise FreezeRefused(
            f"{role}'s lane is not empty: {detail}. A cohort frozen over an existing lane would "
            "carry pre-T0 wallet, position and ledger state into prospective evidence. Archive "
            "the whole lane first: scripts/archive_fp_lane.py"
        )

    # -- T0 itself --------------------------------------------------------
    t0_dt = _parse_utc(t0, "--t0")
    if t0_dt <= now:
        raise FreezeRefused(
            f"--t0 {t0} is not in the future (now {now.strftime('%Y-%m-%dT%H:%M:%SZ')}). A "
            "back-dated T0 would convert warm-up already on disk into prospective evidence"
        )
    if t0_dt - now > MAX_FREEZE_TO_T0:
        raise FreezeRefused(
            f"--t0 {t0} is more than {MAX_FREEZE_TO_T0.days} days ahead; a cohort's identity would "
            "be frozen against a system with time to move underneath it before anything runs"
        )

    return {
        "role": role,
        "head": head,
        "m1": head,
        "mq": mq,
        "t0_utc": t0,
        "cohort_id": fp_law.cohort_id_for(role, t0),
        "certificate_sha256": certificate_sha,
        "semantic_identity_digest": equivalence["left"]["digest"],
        "expires_utc": authorization["EXPIRES_UTC"],
        "registry": registry,
    }


def apply_freeze(facts: dict) -> dict:
    """Write the seven values, regenerate MANIFEST, and verify what was written.

    ORDER MATTERS, and it is not obvious. ``scripts/verify_repo.py --fix`` hashes
    each tracked file **as it stands in the git index**, not as it sits in the
    working tree — deliberately, so an unstaged edit cannot slip a hash into the
    manifest for content that is never committed. That means the registry has to
    be STAGED before the manifest is regenerated. Regenerating first produces a
    manifest built from the pre-freeze registry, which is byte-identical to the
    one already committed, and the transaction then fails its own two-file check
    every time. A freeze tool that can never succeed is a worse failure than one
    that fails loudly, because it only reveals itself the one time it is run.

    The verification afterwards is not decoration either: it re-reads the file
    from disk, re-runs the registry law over it, and requires the staged diff
    against HEAD to name exactly the two permitted files — so a freeze that
    touched anything else is caught by the same rule CI applies, before a commit
    exists rather than after.
    """
    role = facts["role"]
    registry_path = REPO_ROOT / REGISTRY_PATH
    manifest_path = REPO_ROOT / MANIFEST_PATH
    before = registry_path.read_text(encoding="utf-8")
    before_manifest = manifest_path.read_text(encoding="utf-8")
    registry = json.loads(before)
    row = next(item for item in registry["instances"] if item["role"] == role)

    row["t0_utc"] = facts["t0_utc"]
    row["cohort_id"] = facts["cohort_id"]
    row["status"] = "RUNNING"
    row["runtime_identity"]["source_commit"] = facts["m1"]
    row["change_log"] = [
        {
            "utc": facts["t0_utc"],
            "class": "O",
            "description": (
                f"T0 frozen for {role} under the P2 contract. Authority is the Owner-merged "
                f"{AUTHORIZATION_PATH} read from git at {facts['head'][:12]}, naming qualification "
                f"commit {facts['mq'][:12]} and certificate sha256 "
                f"{facts['certificate_sha256'][:12]}, which matches the merged S3b binding. "
                f"SEMANTIC_IDENTITY({facts['mq'][:8]}) == SEMANTIC_IDENTITY({facts['m1'][:8]}) == "
                f"{facts['semantic_identity_digest'][:12]}, so the declared source commit and the "
                "commit the runtime will stamp run the same system. The lane was verified empty "
                "before this entry was written. This entry records the freeze; it changes no "
                "trading semantics."
            ),
            "replay_parity_before_after": None,
        }
    ]
    registry["fp_run_active"] = True
    registry["registry_updated_utc"] = _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")

    text = json.dumps(registry, indent=2) + "\n"
    registry_path.write_text(text, encoding="utf-8")

    try:
        violations = fp_law.check_registry(json.loads(registry_path.read_text(encoding="utf-8")))
        if violations:
            raise FreezeRefused(
                "the registry this freeze produced is not lawful: " + "; ".join(violations[:3])
            )
        _git(["add", "--", REGISTRY_PATH])
        fix = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "verify_repo.py"), "--fix"],
            capture_output=True, text=True, timeout=300, cwd=str(REPO_ROOT),
        )
        if fix.returncode != 0:
            raise FreezeRefused(f"MANIFEST regeneration failed: {fix.stderr.strip()[:300]}")
        _git(["add", "--", MANIFEST_PATH])

        expected = sorted([MANIFEST_PATH, REGISTRY_PATH])
        staged = sorted(
            line for line in _git(["diff", "--cached", "--name-only"]).stdout.splitlines()
            if line.strip()
        )
        if staged != expected:
            raise FreezeRefused(f"the freeze staged {staged}, not exactly {expected}")
        unstaged = sorted(
            line for line in _git(["diff", "--name-only"]).stdout.splitlines() if line.strip()
        )
        if unstaged:
            raise FreezeRefused(
                f"the freeze left {unstaged} unstaged; what is committed would not be what was "
                "verified"
            )
        verify = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "verify_repo.py")],
            capture_output=True, text=True, timeout=300, cwd=str(REPO_ROOT),
        )
        if verify.returncode != 0:
            raise FreezeRefused(
                f"the repository does not verify after the freeze: {verify.stdout.strip()[:300]}"
            )
    except Exception:
        # All-or-nothing, index included. A half-applied freeze is a registry
        # claiming a cohort whose MANIFEST, lane or commit disagree, and that is
        # harder to unpick than never having started.
        registry_path.write_text(before, encoding="utf-8")
        manifest_path.write_text(before_manifest, encoding="utf-8")
        _git(["restore", "--staged", "--", REGISTRY_PATH, MANIFEST_PATH], check=False)
        registry_path.write_text(before, encoding="utf-8")
        manifest_path.write_text(before_manifest, encoding="utf-8")
        raise

    return registry


def _commit_and_push(facts: dict, *, push: bool) -> str:
    message = (
        f"Freeze T0 for {facts['role']} at {facts['t0_utc']}\n"
        f"\n"
        f"Cohort {facts['cohort_id']}. The declared source commit is {facts['m1']}, the merged "
        f"main this freeze is cut from; every record the runtime writes will be stamped with the "
        f"commit this change is merged as, and the two are proved to carry identical semantic "
        f"identity {facts['semantic_identity_digest'][:12]}.\n"
        f"\n"
        f"Authority: the Owner-merged {AUTHORIZATION_PATH}, read from git at "
        f"{facts['head'][:12]}, naming qualification commit {facts['mq']} and certificate "
        f"{facts['certificate_sha256']}. No authorization token exists and none was supplied.\n"
        f"\n"
        f"Exactly two files change and exactly seven registry values move. The FP-CONTROL-1 row "
        f"is byte-identical. The lane was verified empty before the freeze.\n"
        f"\n"
        f"PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.\n"
    )
    _git(["add", REGISTRY_PATH, MANIFEST_PATH])
    _git(["commit", "-m", message])
    freeze_commit = _git(["rev-parse", "HEAD"]).stdout.strip()
    if push:
        branch = _git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        if branch == "main":
            raise FreezeRefused(
                "refusing to push to main. The freeze is a candidate the Owner merges, never a "
                "direct write"
            )
        _git(["push", "--set-upstream", "origin", branch])
    return freeze_commit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("role")
    parser.add_argument(
        "--t0",
        required=True,
        help=(
            "the prospective boundary, YYYY-MM-DDTHH:MM:SSZ. Required and never defaulted: only "
            "the Owner knows when the freeze will be merged, and a guessed T0 buys an activation "
            "gap nobody chose"
        ),
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="report whether every precondition holds and write nothing",
    )
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        facts = check_preconditions(args.role, args.t0)
    except (FreezeRefused, fp_semantic.SemanticIdentityError) as exc:
        print(f"T0_FREEZE_REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.check_only:
        print("T0_PRECONDITIONS = PASS")
        print(f"  role            {facts['role']}")
        print(f"  M1 (declared)   {facts['m1']}")
        print(f"  Mq              {facts['mq']}")
        print(f"  T0              {facts['t0_utc']}")
        print(f"  cohort_id       {facts['cohort_id']}")
        print(f"  semantic id     {facts['semantic_identity_digest']}")
        print()
        print("Nothing was written. Freezing is a separate act and requires a separate Owner")
        print("confirmation: OWNER_T0_EXECUTION_CONFIRMATION_REQUIRED.")
        return 0

    try:
        apply_freeze(facts)
        commit = _commit_and_push(facts, push=not args.no_push)
    except FreezeRefused as exc:
        print(f"T0_FREEZE_REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.json:
        sys.stdout.write(json.dumps({**{k: v for k, v in facts.items() if k != "registry"},
                                     "freeze_commit": commit}, indent=2) + "\n")
    else:
        print(f"T0_FROZEN {facts['role']} cohort {facts['cohort_id']} at {facts['t0_utc']}")
        print(f"  freeze candidate commit {commit}")
        print()
        print("This is a CANDIDATE. It becomes M2 only when the Owner merges it, and the cohort")
        print("does not exist until a fresh runtime process starts after that merge: the capture")
        print("loop reads T0 once, at construction, so a loop already running will never see it.")
        print()
        print("OWNER_MERGE_REQUIRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
