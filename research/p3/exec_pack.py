"""P3-PLN-11 execution pack: the structure generator (DRAFT / NOT FROZEN).

P3_CONTRACT.md §3 PLN-11: a frozen execution pack (versions, digests, runbooks), the P3 closure record and the
POST-BETA handoff. Acceptance: the closure record is merged by the Owner, and the pack is reproducible from Git
plus digests.

This module only builds the pack's **structure** from a repository at a given commit. It reads Git objects,
never the working tree, so the result depends only on the commit. Everything it writes is marked DRAFT /
NOT_FROZEN. It never freezes the pack, never claims PASS and never closes P3. The freeze is a later act on
actual acceptance evidence, merged by the Owner.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

PACK_VERSION = "P3_EXEC_PACK_DRAFT_V1"
STATUS = "DRAFT_NOT_FROZEN"

# Governed paths whose Git tree/blob ids pin the pack. A missing path is recorded as MISSING, never skipped.
GOVERNED_PATHS = (
    "CLAUDE.md",
    "docs/p3",
    "docs/governance/TRADING_LAB_OS_MASTER_EXECUTION_AND_MONITORING_PLAN.md",
    "research/p3",
    "scripts/p3",
    "scripts/paper_guard.py",
    "freqtrade/user_data/config.paper.json.example",
    "research/fp/records/forward_paper_cohort_registry.json",
    "docker-compose.yml",
    "docker-compose.fp.yml",
)
COMPOSE_FILES = ("docker-compose.yml", "docker-compose.fp.yml", "scripts/p3/ops/docker-compose.p3-ops.yml")
REQUIREMENT_FILES = ("requirements-dev.txt", "requirements-research.txt", "research/requirements.txt",
                     "research/requirements-cycle2.txt")
_IMAGE_RE = re.compile(r"^\s*image:\s*(\S+)\s*$", re.MULTILINE)
_DEFAULT_IN_VAR_RE = re.compile(r"^\$\{[A-Z_]+:-(.+)\}$")
_PIN_RE = re.compile(r"^\s*([A-Za-z0-9_.\-\[\]]+)\s*==\s*([^\s;#]+)", re.MULTILINE)


class ExecPackError(Exception):
    pass


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    # Git output is decoded as UTF-8 whatever the host locale is: the pack must depend on the commit only
    # (a C/ASCII locale would otherwise fail on "§" or Arabic text, or decode bytes differently).
    res = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, encoding="utf-8",
                         errors="surrogateescape")
    if check and res.returncode != 0:
        raise ExecPackError(f"git {' '.join(args)}: {res.stderr.strip()[:200]}")
    return res


def _show(repo: Path, commit: str, path: str) -> str | None:
    res = _git(repo, "show", f"{commit}:{path}", check=False)
    return res.stdout if res.returncode == 0 else None


def resolve_commit(repo: Path, ref: str) -> str:
    return _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").stdout.strip()


def version_inventory(repo: Path, commit: str) -> dict:
    """Container images and pinned Python packages, as declared in the repository at the commit."""
    images: dict[str, list[str]] = {}
    for f in COMPOSE_FILES:
        text = _show(repo, commit, f)
        if text is None:
            images[f] = ["MISSING"]
            continue
        found = []
        for raw in _IMAGE_RE.findall(text):
            m = _DEFAULT_IN_VAR_RE.match(raw)
            found.append(f"{m.group(1)} (overridable: {raw})" if m else raw)
        images[f] = found
    packages: dict[str, dict[str, str] | str] = {}
    for f in REQUIREMENT_FILES:
        text = _show(repo, commit, f)
        packages[f] = "MISSING" if text is None else dict(_PIN_RE.findall(text))
    unpinned = [f"{f}: {img}" for f, imgs in images.items() for img in imgs
                if img != "MISSING" and (":" not in img.split("/")[-1] or img.endswith(":latest"))]
    return {"images": images, "python_pins": packages, "unpinned_images": unpinned}


def source_digests(repo: Path, commit: str, paths: tuple[str, ...] = GOVERNED_PATHS) -> dict:
    """Git object ids (tree or blob) of the governed paths at the commit: reproducible from Git alone."""
    out = {}
    for path in paths:
        res = _git(repo, "rev-parse", f"{commit}:{path}", check=False)
        kind = _git(repo, "cat-file", "-t", f"{commit}:{path}", check=False)
        out[path] = ({"object": res.stdout.strip(), "type": kind.stdout.strip()} if res.returncode == 0
                     else {"object": "MISSING", "type": "MISSING"})
    return out


def _docs(repo: Path, commit: str, prefix: str = "docs/p3/") -> list[str]:
    # -z: raw path names, never C-quoted (core.quotepath would otherwise make the list depend on git config)
    res = _git(repo, "ls-tree", "-r", "-z", "--name-only", commit, "--", prefix)
    return sorted(p for p in res.stdout.split("\0") if p.endswith(".md"))


def _title(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "(untitled)"


def runbook_index(repo: Path, commit: str) -> list[dict]:
    """Every docs/p3 document whose name or title marks it as a runbook, procedure or program."""
    rows = []
    for path in _docs(repo, commit):
        text = _show(repo, commit, path) or ""
        title = _title(text)
        if re.search(r"runbook|procedure|program|checklist", path + " " + title, re.IGNORECASE):
            rows.append({"path": path, "title": title, "blob": source_digests(repo, commit, (path,))[path]["object"]})
    return rows


ACCEPTANCE_SOURCE = "research/p3/acceptance.py"
_DOC_RE = re.compile(r"(docs/p3/[A-Za-z0-9_]+\.md)")
# The PLN-10 evidence id shape: "<workstream>.<snake_case>", where the prefix is the row's own workstream.
EVIDENCE_ID_RE = re.compile(r"^PLN-\d{2}\.[a-z0-9_]+$")


def acceptance_matrix_at(repo: Path, commit: str) -> tuple[dict | None, str]:
    """The PLN-10 ACCEPTANCE_MATRIX as declared at the commit, read as a literal (never imported or executed).

    Returns (matrix, source). matrix is None when the program is absent or its matrix is not a plain literal;
    the source string then says why, and every consumer records PENDING instead of guessing.
    """
    text = _show(repo, commit, ACCEPTANCE_SOURCE)
    if text is None:
        return None, f"MISSING ({ACCEPTANCE_SOURCE} not at this commit)"
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return None, f"UNPARSEABLE ({ACCEPTANCE_SOURCE}: {exc.msg})"
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else (
            node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else None)
        if isinstance(target, ast.Name) and target.id == "ACCEPTANCE_MATRIX" and node.value is not None:
            try:
                matrix = ast.literal_eval(node.value)
            except ValueError:
                return None, f"UNPARSEABLE ({ACCEPTANCE_SOURCE}: ACCEPTANCE_MATRIX is not a literal)"
            if isinstance(matrix, dict) and all(isinstance(v, dict) for v in matrix.values()):
                return matrix, ACCEPTANCE_SOURCE
            return None, f"UNPARSEABLE ({ACCEPTANCE_SOURCE}: ACCEPTANCE_MATRIX has an unexpected shape)"
    return None, f"MISSING (no ACCEPTANCE_MATRIX in {ACCEPTANCE_SOURCE})"


def _cited(repo: Path, commit: str, text: str) -> list[dict]:
    """Each docs/p3 document a matrix field cites, with its blob id at the commit (MISSING when absent)."""
    out = []
    for path in sorted(set(_DOC_RE.findall(text or ""))):
        out.append({"path": path, "blob": source_digests(repo, commit, (path,))[path]["object"]})
    return out


def evidence_index(repo: Path, commit: str) -> dict:
    """The evidence index, keyed by the SAME evidence ids as the PLN-10 program (criterion id = evidence id).

    by_evidence_id: for each id, its workstream, the merged procedure and standalone record it cites (with blob
    ids, or MISSING), and the run evidence, which stays PENDING_EVIDENCE until the PLN-10 run's records exist.
    records: the docs/p3/PLN_* execution records with the status lines they declare.
    unresolved: every evidence id that cites a document missing at the commit (a freeze blocker).
    """
    matrix, source = acceptance_matrix_at(repo, commit)
    by_id: dict[str, dict] | str = "PENDING"
    unresolved: list[str] = []
    if matrix is not None:
        by_id = {}
        for cid in sorted(matrix):
            row = matrix[cid]
            entry = {"ws": row.get("ws", "MISSING"),
                     "procedure": row.get("procedure", "MISSING"),
                     "procedure_documents": _cited(repo, commit, row.get("procedure", "")),
                     "standalone_record": row.get("standalone_record", "MISSING"),
                     "standalone_documents": _cited(repo, commit, row.get("standalone_record", "")),
                     "run_evidence": "PENDING_EVIDENCE"}
            if not EVIDENCE_ID_RE.match(cid) or not cid.startswith(f"{entry['ws']}."):
                unresolved.append(f"{cid}: evidence id is not <workstream>.<snake_case> of its own workstream")
            if entry["procedure"] == "MISSING" or not entry["procedure_documents"]:
                unresolved.append(f"{cid}: no procedure document cited")
            unresolved += [f"{cid}: {d['path']} MISSING" for d in entry["procedure_documents"]
                           + entry["standalone_documents"] if d["blob"] == "MISSING"]
            by_id[cid] = entry
    records = []
    for path in _docs(repo, commit):
        if not re.match(r"docs/p3/PLN_\d", path):
            continue
        text = _show(repo, commit, path) or ""
        status_lines = [ln.strip() for ln in text.splitlines()
                        if re.search(r"\b(PASS|FAIL|PENDING|PARTIAL|NOT_PROVEN|BLOCKED|ACCEPTANCE)\b", ln)][:12]
        records.append({"path": path, "title": _title(text), "declared_status_lines": status_lines})
    return {"source": source, "by_evidence_id": by_id, "unresolved": sorted(unresolved), "records": records}


def acceptance_mapping(repo: Path, commit: str) -> dict:
    """Every PLN-10 evidence id → PENDING_EVIDENCE (the same ids as the evidence index). Without the program at
    the commit, the whole mapping is PENDING."""
    matrix, source = acceptance_matrix_at(repo, commit)
    if matrix is None:
        return {"source": source, "criteria": "PENDING"}
    return {"source": source, "criteria": {cid: "PENDING_EVIDENCE" for cid in sorted(matrix)}}


HANDOFF_TEMPLATE = """# POST-BETA handoff (TEMPLATE, DRAFT, NOT FROZEN)

Fill this in only after the P3 closure record is merged by the Owner. Until then every field stays TBD.

```text
P3_CLOSURE_RECORD        = TBD (merged by the Owner)
EXECUTION_PACK_COMMIT    = {commit}
EXECUTION_PACK_STATUS    = {status}
PLN-10 RUN               = TBD (run_id, window, verdict record)
OPEN FINDINGS CARRIED    = TBD
REAL_MONEY_AUTHORIZED    = NO   (POST-BETA does not grant it; a separate Owner authorization is required)
CONTROLLED_LIVE          = NOT AUTHORIZED (its contract does not exist yet)
```

## Items POST-BETA must govern (from the final product shape; none is authorized here)
- the live execution topology: one governed execution authority, with workers emitting intents
- the global risk governor: account exposure, daily loss and drawdown limits, set by the Owner
- the exchange credential model: trade-only keys, no withdrawal, an IP allowlist
- live reconciliation against exchange statements
- restart semantics with open real positions
- the jurisdiction and legal check of the Owner's residence before any live step
"""


def freeze_blockers(parts: dict) -> list[str]:
    """Why this pack cannot be frozen (the freeze rule, PLN_11_EXECUTION_PACK_STRUCTURE.md §4). Never empty for a
    generated pack: the generator only writes DRAFT_NOT_FROZEN, and freezing is a separate Owner-merged act."""
    b = [f"status is {STATUS}: the freeze is a separate Owner-merged PR after the PLN-10 acceptance"]
    ev, am = parts["evidence_index.json"], parts["acceptance_mapping.json"]
    if am["criteria"] == "PENDING":
        b.append(f"acceptance program: {am['source']}")
    else:
        pending = sorted(cid for cid, v in am["criteria"].items() if v == "PENDING_EVIDENCE")
        if pending:
            b.append(f"{len(pending)} evidence id(s) PENDING_EVIDENCE (no accepted PLN-10 run records)")
    b += [f"unresolved evidence id: {u}" for u in ev["unresolved"]]
    b += [f"unpinned image: {u}" for u in parts["version_inventory.json"]["unpinned_images"]]
    b += [f"governed path MISSING: {path}" for path, d in sorted(parts["source_digests.json"].items())
          if d["object"] == "MISSING"]
    return b


def build(repo: Path, ref: str, out_dir: Path) -> dict:
    """Write the DRAFT pack structure for `ref` into an empty or new `out_dir`. Returns the manifest."""
    repo, out_dir = Path(repo), Path(out_dir)
    commit = resolve_commit(repo, ref)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ExecPackError(f"{out_dir} is not empty; a pack is never written over another")
    out_dir.mkdir(parents=True, exist_ok=True)
    parts = {
        "version_inventory.json": version_inventory(repo, commit),
        "source_digests.json": source_digests(repo, commit),
        "runbook_index.json": runbook_index(repo, commit),
        "evidence_index.json": evidence_index(repo, commit),
        "acceptance_mapping.json": acceptance_mapping(repo, commit),
    }
    digests = {}
    for name, data in parts.items():
        body = json.dumps({"pack": PACK_VERSION, "status": STATUS, "commit": commit, "data": data},
                          indent=2, sort_keys=True) + "\n"
        (out_dir / name).write_text(body, encoding="utf-8")
        digests[name] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    handoff = HANDOFF_TEMPLATE.format(commit=commit, status=STATUS)
    (out_dir / "POST_BETA_HANDOFF_TEMPLATE.md").write_text(handoff, encoding="utf-8")
    digests["POST_BETA_HANDOFF_TEMPLATE.md"] = hashlib.sha256(handoff.encode("utf-8")).hexdigest()
    manifest = {"pack": PACK_VERSION, "status": STATUS, "commit": commit, "files": digests,
                "freeze_blockers": freeze_blockers(parts),
                "frozen": False, "p3_closed": False, "real_money_authorized": False}
    (out_dir / "PACK_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                                encoding="utf-8")
    return manifest
