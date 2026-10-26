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
    res = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
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
    res = _git(repo, "ls-tree", "-r", "--name-only", commit, "--", prefix)
    return sorted(p for p in res.stdout.splitlines() if p.endswith(".md"))


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


def evidence_index(repo: Path, commit: str) -> list[dict]:
    """The P3 workstream records (execution records) with the acceptance status lines they declare."""
    rows = []
    for path in _docs(repo, commit):
        if not re.match(r"docs/p3/PLN_\d", path):
            continue
        text = _show(repo, commit, path) or ""
        status_lines = [ln.strip() for ln in text.splitlines()
                        if re.search(r"\b(PASS|FAIL|PENDING|PARTIAL|NOT_PROVEN|BLOCKED|ACCEPTANCE)\b", ln)][:12]
        rows.append({"path": path, "title": _title(text), "declared_status_lines": status_lines})
    return rows


def acceptance_mapping(repo: Path, commit: str) -> dict:
    """The PLN-10 acceptance matrix if it exists at the commit; otherwise every criterion is PENDING."""
    text = _show(repo, commit, "research/p3/acceptance.py")
    if text is None:
        return {"source": "MISSING (research/p3/acceptance.py not at this commit)", "criteria": "PENDING"}
    ids = sorted(set(re.findall(r'^\s{4}"(PLN-\d{2}\.[a-z0-9_]+)":\s*\{', text, re.MULTILINE)))
    return {"source": "research/p3/acceptance.py", "criteria": {cid: "PENDING_EVIDENCE" for cid in ids}}


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
                "frozen": False, "p3_closed": False, "real_money_authorized": False}
    (out_dir / "PACK_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                                encoding="utf-8")
    return manifest
