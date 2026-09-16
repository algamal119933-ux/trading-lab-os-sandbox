"""SEMANTIC_IDENTITY: what it means for two commits to run the same system.

A commit cannot contain its own hash, so no model that declares *the commit the
runtime runs at* terminates. P2's source-commit model (contract section 5) gets
around that by declaring a commit that already exists — M1, the merged main
immediately before the freeze — and then proving the runtime's actual commit
equivalent to it. This module is the proof.

The predecessor model declared a source commit and compared it to nothing. That
is the same class of defect P1 closed one level down: a stamp that is required
to exist but never checked is not evidence of the source. So equivalence here is
computed, not asserted, and it is computed from git objects rather than from a
textual diff — a diff can be made to read as empty by a whitespace or
line-ending normalisation somewhere in the pipeline, and a blob id cannot.

    SEMANTIC_IDENTITY(c) = ( RUNTIME_TREE(c), REGISTRY_SEMANTICS(c) )

RUNTIME_TREE is every file that can change what the runtime does. REGISTRY
_SEMANTICS is the frozen runtime identity minus the fields that are observations
of a runtime rather than instructions to one — excluding those applies the
existing model rather than inventing a licence: FP-CONTROL-1's own first
change_log entry binds ``image_digest`` and ``python_version`` as class O,
"observability only - no trading semantics are changed."

Fail-closed throughout. A path that cannot be read at a commit, a registry that
will not parse, a git invocation that fails: each is UNPROVEN, and UNPROVEN
blocks exactly as a difference does. "I could not tell" is never "they agree".
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

EQUIVALENT = "EQUIVALENT"
DIFFERENT = "DIFFERENT"
UNPROVEN = "UNPROVEN"

SEMANTIC_IDENTITY_VERSION = "FP_SEMANTIC_IDENTITY_V1"

# Contract section 5, verbatim. Two shapes, because git addresses them
# differently and conflating them is how a subdirectory silently drops out of
# the comparison: TREE_PREFIXES are recursive, TREE_GLOBS match direct children
# only.
TREE_PREFIXES = (
    "freqtrade/user_data/strategies/",
    "monitoring/exporter/",
)
TREE_GLOBS = (
    "research/fp/*.py",
    "scripts/*.py",
    "scripts/*.sh",
)
TREE_FILES = (
    "freqtrade/user_data/config.paper.json.example",
    "docker-compose.yml",
    "docker-compose.fp.yml",
)
# research/fp/records/ is evidence and bookkeeping, not runtime behaviour. The
# glob above already excludes it — records/ holds no direct .py child — but the
# exclusion is stated rather than relied upon, because a stray module dropped in
# there later would otherwise join the comparison without anyone deciding it
# should.
TREE_EXCLUDED_PREFIXES = ("research/fp/records/",)

REGISTRY_PATH = "research/fp/records/forward_paper_cohort_registry.json"

# Fields of runtime_identity that are observations of a runtime or freeze
# bookkeeping, not instructions to one. Everything NOT listed here is included,
# so a field added to the schema later joins the comparison by default and has
# to be excluded deliberately. The opposite default — an explicit include list —
# would let a new semantic field slip in unexamined.
REGISTRY_EXCLUDED_IDENTITY_FIELDS = frozenset(
    {
        "source_commit",
        "image_digest",
        "python_version",
    }
)
# Row-level fields excluded for the same reason: they are the freeze
# transaction's own bookkeeping, and the whole point of the proof is that M1 and
# M2 differ in exactly those and nowhere else.
REGISTRY_EXCLUDED_ROW_FIELDS = frozenset(
    {
        "t0_utc",
        "cohort_id",
        "status",
        "closed_utc",
        "closure_reason",
        "outcome",
        "change_log",
    }
)


class SemanticIdentityError(Exception):
    """The identity of a commit could not be established. Never advisory."""


@dataclass
class Identity:
    """One commit's semantic identity, and the digest that stands for it."""

    commit: str
    runtime_tree: dict[str, str]
    registry_semantics: dict
    digest: str = field(default="")

    def __post_init__(self) -> None:
        if not self.digest:
            self.digest = _digest_of(self.runtime_tree, self.registry_semantics)

    def as_dict(self) -> dict:
        return {
            "commit": self.commit,
            "digest": self.digest,
            "runtime_tree_entries": len(self.runtime_tree),
            "runtime_tree": self.runtime_tree,
            "registry_semantics": self.registry_semantics,
        }


def _git(args: list[str], *, repo_root: Path | None = None) -> str:
    """Run git and return stdout, or raise. No silent empty-string fallback.

    An empty result and a failed invocation must never look alike: an empty tree
    listing would make two commits with no runtime files agree with each other,
    which is exactly the degenerate pass this module exists to refuse.
    """
    root = Path(repo_root or REPO_ROOT)
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SemanticIdentityError(f"git {' '.join(args)} could not be run: {exc}") from exc
    if result.returncode != 0:
        raise SemanticIdentityError(
            f"git {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()[:300]}"
        )
    return result.stdout


def resolve_commit(rev: str, *, repo_root: Path | None = None) -> str:
    """The full 40-hex object id a revision names, or a hard failure."""
    text = _git(["rev-parse", "--verify", f"{rev}^{{commit}}"], repo_root=repo_root).strip()
    if len(text) != 40 or not all(c in "0123456789abcdef" for c in text):
        raise SemanticIdentityError(f"{rev!r} did not resolve to a commit id (got {text!r})")
    return text


def _tree_entries(commit: str, *, repo_root: Path | None = None) -> dict[str, str]:
    """Every blob in the commit, as ``{path: "mode:oid"}``.

    The whole tree is listed and filtered here rather than handed to git as
    pathspecs. That is not a style choice: ``git ls-tree`` treats a pathspec as
    a leading-directory prefix, so ``research/fp/*.py`` and ``scripts/*.py``
    matched **nothing** while the directory prefixes beside them matched
    normally — the comparison silently dropped every Python module in the two
    directories that hold the runtime's own logic and still reported a
    populated, plausible-looking tree. Filtering in this module keeps the rule
    that decides what is compared in the same place as the rule that says what
    the comparison means.
    """
    raw = _git(["ls-tree", "-r", "-z", commit], repo_root=repo_root)
    entries: dict[str, str] = {}
    for chunk in raw.split("\0"):
        if not chunk:
            continue
        meta, _, path = chunk.partition("\t")
        parts = meta.split()
        if len(parts) != 3:
            raise SemanticIdentityError(f"unparseable ls-tree entry at {commit[:8]}: {chunk!r}")
        mode, obj_type, oid = parts
        if obj_type != "blob":
            # A submodule inside a runtime path would be a runtime input this
            # model cannot address. Checked after filtering, below, so an
            # unrelated submodule elsewhere in the repository is not this
            # module's business.
            entries[path] = f"{obj_type}:{mode}:{oid}"
            continue
        # The mode travels with the id: an executable bit is behaviour for a
        # shell script, and two blobs sharing one id can differ in it.
        entries[path] = f"{mode}:{oid}"
    return entries


def _matches_glob(path: str, pattern: str) -> bool:
    """``dir/*.py`` means a direct child of ``dir``, as a shell would read it.

    ``fnmatch`` would let ``*`` cross a directory separator, which is how
    ``research/fp/*.py`` would quietly start covering ``research/fp/records/``
    after the exclusion above was removed by someone who read the two rules as
    redundant.
    """
    prefix, _, suffix_pattern = pattern.rpartition("/")
    if not path.startswith(prefix + "/"):
        return False
    remainder = path[len(prefix) + 1 :]
    if "/" in remainder:
        return False
    return fnmatch.fnmatchcase(remainder, suffix_pattern)


def runtime_tree(commit: str, *, repo_root: Path | None = None) -> dict[str, str]:
    """``{path: "mode:blob_id"}`` for every runtime-behaviour file at ``commit``.

    Byte identity, not a textual diff: the value is git's own content address,
    so two paths agree only when their bytes agree.
    """
    everything = _tree_entries(commit, repo_root=repo_root)
    selected: dict[str, str] = {}
    # Per-rule, so a rule that stops matching anything fails loudly instead of
    # shrinking the comparison. Every rule in the contract names something that
    # exists; a rule matching nothing means either the repository moved or the
    # matching is broken, and both are refusals.
    matched_by_rule: dict[str, int] = {}

    for prefix in TREE_PREFIXES:
        hits = {p: v for p, v in everything.items() if p.startswith(prefix)}
        matched_by_rule[prefix] = len(hits)
        selected.update(hits)
    for pattern in TREE_GLOBS:
        hits = {p: v for p, v in everything.items() if _matches_glob(p, pattern)}
        matched_by_rule[pattern] = len(hits)
        selected.update(hits)
    for name in TREE_FILES:
        hits = {p: v for p, v in everything.items() if p == name}
        matched_by_rule[name] = len(hits)
        selected.update(hits)

    empty_rules = sorted(rule for rule, count in matched_by_rule.items() if count == 0)
    if empty_rules:
        raise SemanticIdentityError(
            f"at {commit[:8]} these declared runtime paths matched no file: {empty_rules}. "
            "A rule that matches nothing removes files from the comparison without anyone "
            "deciding it should, so the identity is refused rather than computed over what is left"
        )

    for path in list(selected):
        if any(path.startswith(prefix) for prefix in TREE_EXCLUDED_PREFIXES):
            del selected[path]
            continue
        if not selected[path].split(":")[0].isdigit():
            raise SemanticIdentityError(
                f"{path} at {commit[:8]} is a {selected[path].split(':')[0]}, not a file; "
                "this model cannot address it"
            )
    if not selected:
        raise SemanticIdentityError(
            f"{commit[:8]} carries none of the runtime paths; an empty runtime tree would make "
            "any two such commits agree with each other while agreeing with nothing real"
        )
    return dict(sorted(selected.items()))


def registry_semantics(commit: str, role: str, *, repo_root: Path | None = None) -> dict:
    """The role's runtime identity at ``commit``, minus observations and bookkeeping."""
    try:
        raw = _git(["show", f"{commit}:{REGISTRY_PATH}"], repo_root=repo_root)
    except SemanticIdentityError as exc:
        raise SemanticIdentityError(f"the registry is not readable at {commit[:8]}: {exc}") from exc
    try:
        registry = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SemanticIdentityError(f"the registry at {commit[:8]} is not valid JSON: {exc}") from exc

    matches = [item for item in (registry.get("instances") or []) if item.get("role") == role]
    if not matches:
        raise SemanticIdentityError(f"{commit[:8]} declares no instance with role {role!r}")
    if len(matches) > 1:
        raise SemanticIdentityError(
            f"{commit[:8]} declares {len(matches)} instances with role {role!r}; identity is ambiguous"
        )
    row = matches[0]
    identity = row.get("runtime_identity")
    if not isinstance(identity, dict):
        raise SemanticIdentityError(f"{role} at {commit[:8]} carries no runtime_identity object")

    included_identity = {
        key: value
        for key, value in identity.items()
        if key not in REGISTRY_EXCLUDED_IDENTITY_FIELDS
    }
    included_row = {
        key: value
        for key, value in row.items()
        if key not in REGISTRY_EXCLUDED_ROW_FIELDS and key != "runtime_identity"
    }
    return {
        "role": role,
        "row": dict(sorted(included_row.items())),
        "runtime_identity": dict(sorted(included_identity.items())),
    }


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest_of(tree: dict[str, str], semantics: dict) -> str:
    parts = [SEMANTIC_IDENTITY_VERSION, "runtime_tree"]
    parts.extend(f"{path}\0{oid}" for path, oid in sorted(tree.items()))
    parts.append("registry_semantics")
    parts.append(_canonical(semantics))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def semantic_identity(commit: str, role: str, *, repo_root: Path | None = None) -> Identity:
    """The full semantic identity of one commit, or a hard failure."""
    resolved = resolve_commit(commit, repo_root=repo_root)
    return Identity(
        commit=resolved,
        runtime_tree=runtime_tree(resolved, repo_root=repo_root),
        registry_semantics=registry_semantics(resolved, role, repo_root=repo_root),
    )


def compare(left: str, right: str, role: str, *, repo_root: Path | None = None) -> dict:
    """Are two commits semantically identical? Returns a report, never raises.

    A failure to establish either side is reported as UNPROVEN rather than
    propagated, because the caller is a gate: it has to record *that* the
    question could not be answered, and then refuse on that basis.
    """
    report: dict = {
        "semantic_identity_version": SEMANTIC_IDENTITY_VERSION,
        "role": role,
        "left": {"rev": left},
        "right": {"rev": right},
        "differences": [],
        "result": UNPROVEN,
        "detail": "",
    }
    try:
        left_identity = semantic_identity(left, role, repo_root=repo_root)
        right_identity = semantic_identity(right, role, repo_root=repo_root)
    except SemanticIdentityError as exc:
        report["detail"] = str(exc)
        return report

    report["left"] = left_identity.as_dict() | {"rev": left}
    report["right"] = right_identity.as_dict() | {"rev": right}

    differences: list[dict] = []
    paths = sorted(set(left_identity.runtime_tree) | set(right_identity.runtime_tree))
    for path in paths:
        a = left_identity.runtime_tree.get(path)
        b = right_identity.runtime_tree.get(path)
        if a != b:
            differences.append(
                {
                    "kind": "runtime_tree",
                    "path": path,
                    "left": a or "<absent>",
                    "right": b or "<absent>",
                }
            )
    if left_identity.registry_semantics != right_identity.registry_semantics:
        differences.extend(_semantic_differences(
            left_identity.registry_semantics, right_identity.registry_semantics
        ))

    report["differences"] = differences
    if differences:
        report["result"] = DIFFERENT
        report["detail"] = (
            f"{len(differences)} semantic difference(s) between {left_identity.commit[:8]} and "
            f"{right_identity.commit[:8]}: "
            + ", ".join(
                d.get("path") or d.get("field", "?") for d in differences[:5]
            )
        )
        return report

    # Belt and braces: the digests must agree too. If the entry-wise comparison
    # found nothing and the digests still differ, the comparison missed
    # something, and that is a refusal rather than a pass.
    if left_identity.digest != right_identity.digest:
        report["result"] = UNPROVEN
        report["detail"] = (
            "no entry-wise difference was found but the identity digests differ; the comparison "
            "does not cover everything the digest does"
        )
        return report

    report["result"] = EQUIVALENT
    report["detail"] = (
        f"{left_identity.commit[:8]} and {right_identity.commit[:8]} carry identical semantic "
        f"identity {left_identity.digest[:12]}… over {len(left_identity.runtime_tree)} runtime "
        f"file(s) and the {role} registry semantics"
    )
    return report


def _semantic_differences(left: dict, right: dict) -> list[dict]:
    """Field-level differences between two registry-semantics objects."""
    out: list[dict] = []
    for section in ("row", "runtime_identity"):
        a = left.get(section) or {}
        b = right.get(section) or {}
        for key in sorted(set(a) | set(b)):
            if a.get(key) != b.get(key):
                out.append(
                    {
                        "kind": "registry_semantics",
                        "field": f"{section}.{key}",
                        "left": _canonical(a.get(key))[:200],
                        "right": _canonical(b.get(key))[:200],
                    }
                )
    if not out and left != right:
        out.append(
            {
                "kind": "registry_semantics",
                "field": "<structure>",
                "left": _canonical(left)[:200],
                "right": _canonical(right)[:200],
            }
        )
    return out
