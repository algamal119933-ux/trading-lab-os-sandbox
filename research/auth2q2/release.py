#!/usr/bin/env python3
"""The snapshot's immutable release (Owner decisions OD-S2 and OD-S3; readiness tests RT-1, RT-3, RT-4).

    python -m auth2q2.release publish   --repo-slug O/R --dir OUT --commit SHA --out FILE
    python -m auth2q2.release verify    --repo-slug O/R --commit SHA [--address sha256:HEX] --out FILE
    python -m auth2q2.release download  --repo-slug O/R --commit SHA --dest DIR [--address sha256:HEX] --out FILE
    python -m auth2q2.release probe-immutable --repo-slug O/R --commit SHA --dir DIR --out FILE   (contents: write)
    python -m auth2q2.release probe-read-only --repo-slug O/R --commit SHA --out FILE             (contents: read)

Two identities. The snapshot's identity is its address, the sha256 of its manifest: content, never a commit. The
readiness execution's identity is the commit every readiness run of one qualification is dispatched at (OD-S8).
A snapshot release binds both: one release per (address, readiness commit), tagged
``auth2q2-snapshot-sha256-<hex>-at-<commit>`` on that commit, holding exactly three assets: manifest.json (its
sha256 is the address), snapshot.tar and prepare-record.json (the cold preparation of the RT-1 run that published
it, at that commit). A readiness commit has at most one snapshot release; releases of other commits are history,
never read and never changed.

It is published the way GitHub's immutable releases are meant to be: a draft first, every asset attached and
checked against the digest GitHub computed for it, and only then published. After publishing, the release must
report ``immutable: true``. GitHub's API shows whether the repository has immutable releases enabled only to a
token with admin access, which no workflow token has, so it is checked on the release itself: a release this job
just published that reports ``immutable: false`` means the setting is off, and that release and its tag are
deleted (they were never immutable, so nothing is burned) before the job fails, saying exactly what, if anything,
could not be removed. A release whose immutability GitHub does not state is never deleted; the job fails. A draft is deleted if anything fails before it
is published, and a draft of this commit's tag that an earlier run left behind is deleted before publishing (a
draft is never immutable and has no tag yet). Nothing here ever deletes, changes or moves an immutable release or
its tag.

RT-1 dispatched again at the same commit, after a publication that succeeded or one that was published and then
failed, is idempotent: the release's three assets are downloaded and hashed, its manifest and tar must be this
run's own cold preparation byte for byte, its record must be an earlier RT-1 run's at this commit (that run's
first attempt), and the release is verified and left exactly as it is (VERIFIED_EXISTING). At a new commit RT-1 prepares cold and publishes that commit's own
release; an earlier commit's release never stands in for it.

Readers (``verify``, ``download``) accept the snapshot only from the one published, immutable release of the
readiness commit, its tag on that commit, with the three assets whose digests GitHub reports, and they check every
downloaded byte against those digests; the restore then checks every file against the manifest (snapshot.py).

``probe-immutable`` (RT-3, the publish job's write token) tries to change the published release in ways that
can be undone if GitHub wrongly allowed them: attach a new asset, rename an asset, delete the small
prepare-record.json asset (re-uploaded from the verified local copy if the delete went through), and move the
tag to another commit (moved back). Every attempt must be refused; anything that got through is reverted and
fails the test. It never tries to delete the release, the tag or the snapshot itself: GitHub allows deleting an
immutable release, and that could not be undone. ``probe-read-only`` (RT-3, a read-only job) tries to write with
a contents: read token and must be refused every time.

The workflow token reaches GitHub through ``gh``; the billing token is removed from every call's environment.
PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from auth2q2 import plan as PL  # noqa: E402
from auth2q2 import snapshot as SN  # noqa: E402

TAG_PREFIX = "auth2q2-snapshot-sha256-"
TAG = re.compile(re.escape(TAG_PREFIX) + r"([0-9a-f]{64})-at-([0-9a-f]{40})")
COMMIT = re.compile(r"[0-9a-f]{40}")
MANIFEST, TAR, RECORD = "manifest.json", "snapshot.tar", "prepare-record.json"
ASSETS = (MANIFEST, TAR, RECORD)
BOT = "github-actions[bot]"
DIGEST = re.compile(r"sha256:([0-9a-f]{64})")
NO_TOKEN_ENV = ("AUTH2_BILLING_TOKEN",)
PUBLISHED, VERIFIED_EXISTING = "PUBLISHED", "VERIFIED_EXISTING"


class ReleaseError(Exception):
    """The release is not the snapshot it claims to be, or GitHub did not do what it must. Fail closed."""


def tag_for(address: str, commit: str) -> str:
    """The tag of the snapshot release binding ``address`` to the readiness commit ``commit``."""
    m = SN.DIGEST.fullmatch(address or "")
    if not m:
        raise ReleaseError(f"{str(address)[:80]!r} is not a snapshot address")
    if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
        raise ReleaseError(f"{str(commit)[:80]!r} is not a full commit sha")
    return f"{TAG_PREFIX}{m[1]}-at-{commit}"


def address_of(tag: str) -> str | None:
    m = TAG.fullmatch(tag or "")
    return f"sha256:{m[1]}" if m else None


def commit_of(tag: str) -> str | None:
    """The readiness commit a snapshot tag names (the tag must also point at it: ``tag_commit``)."""
    m = TAG.fullmatch(tag or "")
    return m[2] if m else None


def is_commit(commit) -> bool:
    return isinstance(commit, str) and COMMIT.fullmatch(commit) is not None


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(SN.CHUNK):
            h.update(chunk)
    return h.hexdigest()


# -- GitHub, through gh -----------------------------------------------------------------------------

class GH:
    """``gh`` with the workflow token only. ``api`` returns (HTTP status, parsed body or text)."""

    def __init__(self, slug: str) -> None:
        self.slug = slug

    def _env(self) -> dict:
        return {k: v for k, v in os.environ.items() if k not in NO_TOKEN_ENV}

    def run(self, args: list[str]) -> tuple[int, str, str]:
        p = subprocess.run(["gh", *args], capture_output=True, text=True, env=self._env())
        return p.returncode, p.stdout, p.stderr

    def api(self, method: str, path: str, body: dict | None = None) -> tuple[int | None, object]:
        args = ["api", "-X", method, "-H", "Accept: application/vnd.github+json",
                "-H", "X-GitHub-Api-Version: 2022-11-28", path]
        tmp = None
        if body is not None:
            tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
            json.dump(body, tmp)
            tmp.close()
            args += ["--input", tmp.name]
        try:
            rc, out, err = self.run(args)
        finally:
            if tmp:
                os.unlink(tmp.name)
        if rc != 0:
            m = re.search(r"\(HTTP (\d{3})\)", err or out or "")
            return (int(m[1]) if m else None), (err or out or "").strip()[:400]
        try:
            return 200, json.loads(out) if out.strip() else None
        except ValueError:
            return 200, out[:400]

    def create_draft(self, tag: str, commit: str, title: str, notes: str, files: list[Path]) -> tuple[int, str]:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as nf:
            nf.write(notes)
        try:
            rc, out, err = self.run(["release", "create", tag, *map(str, files), "--repo", self.slug, "--draft",
                                     "--target", commit, "--title", title, "--notes-file", nf.name,
                                     "--latest=false"])
        finally:
            os.unlink(nf.name)
        return rc, (err or out).strip()[:400]

    def upload(self, tag: str, path: Path) -> tuple[int, str]:
        rc, out, err = self.run(["release", "upload", tag, str(path), "--repo", self.slug])
        return rc, (err or out).strip()[:400]

    def api_bytes(self, path: str) -> tuple[int | None, bytes]:
        """GET ``path`` as raw bytes (an artifact's zip)."""
        p = subprocess.run(["gh", "api", "-H", "X-GitHub-Api-Version: 2022-11-28", path], capture_output=True,
                           env=self._env())
        if p.returncode != 0:
            m = re.search(rb"\(HTTP (\d{3})\)", p.stderr or b"")
            return (int(m[1]) if m else None), (p.stderr or b"")[:400]
        return 200, p.stdout

    def download(self, tag: str, names: list[str], dest: Path) -> tuple[int, str]:
        args = ["release", "download", tag, "--repo", self.slug, "--dir", str(dest)]
        for n in names:
            args += ["--pattern", n]
        rc, out, err = self.run(args)
        return rc, (err or out).strip()[:400]


# -- what a snapshot release must be ----------------------------------------------------------------

def asset_map(rel: dict) -> dict:
    return {a.get("name"): a for a in rel.get("assets") or [] if isinstance(a, dict)}


def release_problems(rel, *, address: str | None = None, commit: str | None = None, tar_sha256: str | None = None,
                     draft_ok: bool = False) -> list[str]:
    """Why ``rel`` is not a published, immutable snapshot release ([] when it is). With ``address`` / ``commit``
    / ``tar_sha256``, its tag and digests must be those. Its target is always the commit its tag names."""
    if not isinstance(rel, dict):
        return ["the release is unreadable"]
    p = []
    tag = rel.get("tag_name")
    got, at = address_of(tag), commit_of(tag)
    if got is None:
        p.append(f"tag {str(tag)[:140]!r} is not a snapshot tag")
    else:
        if address is not None and got != address:
            p.append(f"tag {tag} is not the snapshot {address}")
        if commit is not None and at != commit:
            p.append(f"STALE_RELEASE: tag {tag} binds commit {at}, not the readiness commit {commit}")
        if rel.get("target_commitish") != at:
            p.append(f"the release targets {str(rel.get('target_commitish'))[:60]!r}, not the commit {at} its tag "
                     "names")
    if not draft_ok:
        if rel.get("draft") is not False:
            p.append("the release is a draft")
        if rel.get("immutable") is not True:
            p.append("the release is not immutable (enable release immutability in the repository settings)")
    if rel.get("prerelease") is not False:
        p.append("the release is a prerelease")
    assets = asset_map(rel)
    if sorted(assets) != sorted(ASSETS) or len(rel.get("assets") or []) != len(ASSETS):
        p.append(f"assets are {sorted(str(n) for n in assets)}, not {sorted(ASSETS)}")
        return p
    for name, a in assets.items():
        if a.get("state") != "uploaded":
            p.append(f"{name}: state {a.get('state')!r}, not 'uploaded'")
        if not isinstance(a.get("digest"), str) or not DIGEST.fullmatch(a["digest"]):
            p.append(f"{name}: GitHub reports no sha256 digest ({str(a.get('digest'))[:80]!r})")
        if not isinstance(a.get("size"), int) or a["size"] <= 0:
            p.append(f"{name}: size {a.get('size')!r}")
    if got is not None and assets[MANIFEST].get("digest") != got:
        p.append(f"{MANIFEST}: digest {assets[MANIFEST].get('digest')} is not the tag's address {got}")
    if tar_sha256 is not None and assets[TAR].get("digest") != f"sha256:{tar_sha256}":
        p.append(f"{TAR}: digest {assets[TAR].get('digest')} is not sha256:{tar_sha256}")
    return p


def snapshot_releases(gh: GH) -> list[dict]:
    """Every release whose tag is a snapshot tag (drafts too, where the token can see them)."""
    out, page = [], 1
    while True:
        status, body = gh.api("GET", f"/repos/{gh.slug}/releases?per_page=100&page={page}")
        if status != 200 or not isinstance(body, list):
            raise ReleaseError(f"cannot list releases (HTTP {status}): {str(body)[:200]}")
        out += [r for r in body if isinstance(r, dict) and address_of(r.get("tag_name")) is not None]
        if len(body) < 100:
            return out
        page += 1


def tag_commit(gh: GH, tag: str) -> str | None:
    """The commit ``tag`` points at (a lightweight tag on a commit), or None."""
    status, ref = gh.api("GET", f"/repos/{gh.slug}/git/ref/tags/{tag}")
    obj = (ref.get("object") or {}) if status == 200 and isinstance(ref, dict) else {}
    return obj.get("sha") if obj.get("type") == "commit" and is_commit(obj.get("sha")) else None


def at_commit(rels: list[dict], commit: str) -> list[dict]:
    """The published snapshot releases bound to the readiness commit ``commit``."""
    return [r for r in rels if r.get("draft") is False and commit_of(r.get("tag_name")) == commit]


def the_snapshot(gh: GH, commit: str, address: str | None = None) -> dict:
    """The readiness commit's one published snapshot release (``address``'s, if given): refused unless exactly one
    release is bound to ``commit``, it is published, immutable, complete and the bot's, and its tag points at
    ``commit``. Releases of other commits are history and are never read."""
    if not is_commit(commit):
        raise ReleaseError(f"{str(commit)[:60]!r} is not a full commit sha; the readiness commit is required")
    rels = at_commit(snapshot_releases(gh), commit)
    if len(rels) != 1:
        raise ReleaseError(f"{len(rels)} published snapshot release(s) for the readiness commit {commit}; exactly "
                           "one is required")
    p = release_problems(rels[0], address=address, commit=commit)
    if (rels[0].get("author") or {}).get("login") != BOT:
        p.append(f"the release's author is {(rels[0].get('author') or {}).get('login')!r}, not {BOT}")
    if not p and tag_commit(gh, rels[0]["tag_name"]) != commit:
        p.append(f"the tag {rels[0]['tag_name']} does not point at the readiness commit {commit}")
    if p:
        raise ReleaseError("; ".join(p))
    return rels[0]


def summary(rel: dict) -> dict:
    return {"tag": rel.get("tag_name"), "address": address_of(rel.get("tag_name")),
            "commit": commit_of(rel.get("tag_name")), "release_id": rel.get("id"),
            "immutable": rel.get("immutable"), "draft": rel.get("draft"), "published_at": rel.get("published_at"),
            "target_commitish": rel.get("target_commitish"),
            "author": (rel.get("author") or {}).get("login"),
            "assets": {n: {"id": a.get("id"), "size": a.get("size"), "digest": a.get("digest"),
                           "state": a.get("state")} for n, a in sorted(asset_map(rel).items())}}


# -- publish (RT-1: the preparation workflow's publish job, the only job with contents: write) ------

def local_files(directory: Path, commit: str | None = None, run_id: str | None = None) -> tuple[dict, dict]:
    """The three snapshot files in ``directory``, checked: the manifest at its own address, the tar against it
    and the record naming both, made at ``commit`` by run ``run_id`` when they are given. Returns (paths, facts)."""
    paths = {n: directory / n for n in ASSETS}
    for n, p in paths.items():
        if not p.is_file() or p.is_symlink():
            raise ReleaseError(f"{p} is missing")
    try:
        record = json.loads(paths[RECORD].read_text())
    except (UnicodeDecodeError, ValueError) as exc:
        raise ReleaseError(f"{RECORD} is not JSON ({str(exc)[:120]})") from exc
    if not isinstance(record, dict):
        raise ReleaseError(f"{RECORD} is not a JSON object")
    address = record.get("address")
    raw = paths[MANIFEST].read_bytes()
    man = SN.load_manifest(raw, address)
    with open(paths[TAR], "rb") as f:
        tar_sha = SN.scan_tar(f, man["files"])
    if tar_sha != record.get("tar_sha256"):
        raise ReleaseError(f"the tar hashes to {tar_sha}, the record says {record.get('tar_sha256')}")
    if record.get("program") != SN.PROGRAM_ID:
        raise ReleaseError(f"the record's program is {record.get('program')!r}")
    if commit is not None and record.get("commit") != commit:
        raise ReleaseError(f"the preparation record was made at {str(record.get('commit'))[:40]}, not {commit}")
    if run_id is not None and str(record.get("run_id")) != str(run_id):
        raise ReleaseError(f"the preparation record is run {str(record.get('run_id'))[:24]}'s, not run {run_id}'s")
    facts = {"address": address, "tar_sha256": tar_sha, "files": man["counts"]["files"],
             "digests": {n: "sha256:" + sha256_file(p) for n, p in paths.items()},
             "sizes": {n: p.stat().st_size for n, p in paths.items()}}
    return paths, facts


def notes(facts: dict, commit: str) -> str:
    return (f"Dataset V3 archive snapshot of {SN.PROGRAM_ID} (readiness, Owner decisions OD-S2/OD-S3).\n\n"
            f"Address (sha256 of {MANIFEST}): `{facts['address']}`\n\n"
            f"{TAR}: sha256 `{facts['tar_sha256']}`, {facts['files']} files\n\n"
            f"Readiness commit: `{commit}`. Prepared cold and published at that commit by the preparation "
            "workflow's RT-1 run; it is the snapshot of that commit's readiness execution only. Restore and verify "
            "with `python -m auth2q2.snapshot restore` from that commit. PAPER / RESEARCH ONLY.\n")


def publishing_run_problems(gh: GH, run_id, commit: str) -> list[str]:
    """Why run ``run_id`` is not an RT-1 run of the preparation workflow, dispatched on main at ``commit``, at its
    first attempt ([] when it is). Its first attempt is read as such: a later "Re-run" click (refused by the gate,
    its jobs skipped) moves the run's latest attempt but not what attempt 1 published. The readiness record checks
    its actor as well."""
    if not str(run_id).isdigit():
        return [f"the publishing run id {str(run_id)[:30]!r} is not a run id"]
    status, run = gh.api("GET", f"/repos/{gh.slug}/actions/runs/{int(run_id)}/attempts/1")
    if status != 200 or not isinstance(run, dict):
        return [f"the publishing run {run_id} is unreadable (HTTP {status})"]
    want = {"id": int(run_id), "path": f".github/workflows/{PL.PREPARE_WORKFLOW}", "event": "workflow_dispatch",
            "head_branch": "main", "head_sha": commit, "display_title": PL.TITLE.format(test="RT-1"),
            "run_attempt": 1}
    return [f"the publishing run {run_id}'s {k} is {str(run.get(k))[:80]!r}, not {v!r}" for k, v in want.items()
            if run.get(k) != v]


def verify_existing(gh: GH, rel: dict, facts: dict, commit: str, run_id: str) -> dict:
    """RT-1 again at ``commit``, whose snapshot release an earlier RT-1 run published: this run's own cold
    preparation (``facts``) must be that release byte for byte, and its record an earlier RT-1 run's at this
    commit. Nothing is written: the release, its assets and its tag stay exactly as they are."""
    tag = rel.get("tag_name")
    p = release_problems(rel, address=facts["address"], commit=commit, tar_sha256=facts["tar_sha256"])
    if (rel.get("author") or {}).get("login") != BOT:
        p.append(f"the release's author is {(rel.get('author') or {}).get('login')!r}, not {BOT}")
    if p:
        raise ReleaseError(f"the published release {tag} of this commit is not a usable snapshot release: "
                           + "; ".join(p)[:600])
    assets = asset_map(rel)
    p = [f"{n}: the release holds {assets[n].get('digest')} ({assets[n].get('size')} bytes), this run's cold "
         f"preparation {facts['digests'][n]} ({facts['sizes'][n]} bytes)" for n in (MANIFEST, TAR)
         if assets[n].get("digest") != facts["digests"][n] or assets[n].get("size") != facts["sizes"][n]]
    if p:
        raise ReleaseError("SNAPSHOT_MISMATCH: this run's cold preparation is not the published snapshot: "
                           + "; ".join(p))
    tagged = tag_commit(gh, tag)
    if tagged != commit:
        raise ReleaseError(f"the tag {tag} points at {tagged}, not the readiness commit {commit}")
    with tempfile.TemporaryDirectory() as td:  # every asset's bytes, not only the digests GitHub reports
        rc, msg = gh.download(tag, list(ASSETS), Path(td))
        if rc != 0:
            raise ReleaseError(f"downloading the release's assets failed: {msg}")
        got = {n: "sha256:" + sha256_file(Path(td) / n) if (Path(td) / n).is_file() else None for n in ASSETS}
        raw = (Path(td) / RECORD).read_bytes() if got[RECORD] else b""
    p = [f"{n}: the downloaded bytes hash to {got[n]}, not the release's digest {assets[n]['digest']}"
         for n in ASSETS if got[n] != assets[n]["digest"]]
    p += [f"{n}: the downloaded bytes are not this run's cold preparation {facts['digests'][n]}"
          for n in (MANIFEST, TAR) if got[n] != facts["digests"][n]]
    if p:
        raise ReleaseError("SNAPSHOT_MISMATCH: " + "; ".join(p))
    try:
        prior = json.loads(raw)
    except ValueError as exc:
        raise ReleaseError(f"the release's {RECORD} is not JSON ({str(exc)[:120]})") from exc
    prior = prior if isinstance(prior, dict) else {}
    want = {"program": SN.PROGRAM_ID, "address": facts["address"], "tar_sha256": facts["tar_sha256"],
            "commit": commit}
    p = [f"its {k} is {str(prior.get(k))[:80]!r}, not {v!r}" for k, v in want.items() if prior.get(k) != v]
    if str(prior.get("run_id")) == str(run_id):
        p.append(f"it names this run {run_id}, which did not publish it")
    if str(prior.get("run_attempt")) != "1":
        p.append(f"it was prepared at attempt {str(prior.get('run_attempt'))[:10]}, not 1")
    p += publishing_run_problems(gh, prior.get("run_id"), commit)
    if p:
        raise ReleaseError(f"PROVENANCE: the release's {RECORD} is not an earlier RT-1 run's at this commit: "
                           + "; ".join(p)[:600])
    return {"result": VERIFIED_EXISTING, **summary(rel), "tag_commit": tagged, "facts": facts,
            "published_by_run": int(prior["run_id"]), "published_record_digest": assets[RECORD]["digest"]}


def publish(gh: GH, directory: Path, commit: str, run_id: str | None) -> dict:
    """RT-1 at ``commit`` (run ``run_id``): publish this run's cold preparation as the commit's immutable snapshot
    release, or, if an earlier RT-1 run at this commit already published it, verify it (``verify_existing``).
    A release of another commit is never read, reused or changed."""
    if not is_commit(commit):
        raise ReleaseError(f"{str(commit)[:50]!r} is not a full commit sha")
    if not str(run_id or "").isdigit():
        raise ReleaseError(f"the publishing run's id is required (GITHUB_RUN_ID is {str(run_id)[:30]!r})")
    paths, facts = local_files(directory, commit, run_id)
    tag = tag_for(facts["address"], commit)
    mine = [r for r in snapshot_releases(gh) if commit_of(r.get("tag_name")) == commit]
    published = [r for r in mine if r.get("draft") is not True]  # anything not plainly a draft is never removed
    other = sorted(str(r.get("tag_name")) for r in published if r.get("tag_name") != tag)
    if other:
        raise ReleaseError(f"SNAPSHOT_CONFLICT: the readiness commit {commit} already has the snapshot release(s) "
                           f"{other}, of another address; this run's cold preparation is {facts['address']}. A "
                           "readiness commit has one snapshot; nothing is published")
    if len(published) > 1:
        raise ReleaseError(f"{len(published)} releases are tagged {tag}; exactly one may be")
    if published:
        return verify_existing(gh, published[0], facts, commit, run_id)
    for d in mine:  # drafts only: an earlier run's draft of this tag, never published, never immutable
        if d.get("tag_name") != tag or (d.get("author") or {}).get("login") != BOT:
            raise ReleaseError(f"a draft {str(d.get('tag_name'))[:140]} of this commit by "
                               f"{(d.get('author') or {}).get('login')!r} exists that is not this snapshot's or "
                               "not the bot's; nothing is published")
        status, body = gh.api("DELETE", f"/repos/{gh.slug}/releases/{d['id']}")
        if status != 200:
            raise ReleaseError(f"an earlier run's draft {d.get('id')} of {tag} cannot be removed (HTTP {status})")
    status, ref = gh.api("GET", f"/repos/{gh.slug}/git/ref/tags/{tag}")
    if status != 404:
        raise ReleaseError(f"the tag {tag} already exists or is unreadable (HTTP {status}); a snapshot release "
                           "creates its own tag at the publishing commit")
    rc, msg = gh.create_draft(tag, commit, f"AUTH-2-Q2 snapshot {facts['address'][:19]} at {commit[:12]}",
                              notes(facts, commit), [paths[n] for n in ASSETS])
    drafts = [r for r in snapshot_releases(gh) if r.get("tag_name") == tag and r.get("draft") is True]
    if rc != 0 or len(drafts) != 1:
        for d in drafts:
            gh.api("DELETE", f"/repos/{gh.slug}/releases/{d['id']}")
        raise ReleaseError(f"creating the draft failed (gh exit {rc}, {len(drafts)} draft(s)): {msg}")
    draft = drafts[0]
    try:
        p = release_problems(draft, address=facts["address"], commit=commit, tar_sha256=facts["tar_sha256"],
                             draft_ok=True)
        assets = asset_map(draft)
        p += [f"{n}: GitHub's digest {assets[n].get('digest')} is not the local {d}"
              for n, d in facts["digests"].items() if n in assets and assets[n].get("digest") != d]
        p += [f"{n}: {assets[n].get('size')} bytes uploaded, {s} local" for n, s in facts["sizes"].items()
              if n in assets and assets[n].get("size") != s]
        if (draft.get("author") or {}).get("login") != BOT:
            p.append(f"the draft's author is {(draft.get('author') or {}).get('login')!r}, not {BOT}")
        if p:
            raise ReleaseError("the draft is not the snapshot: " + "; ".join(p))
        status, body = gh.api("PATCH", f"/repos/{gh.slug}/releases/{draft['id']}",
                              {"draft": False, "make_latest": "false"})
        if status != 200:
            raise ReleaseError(f"publishing failed (HTTP {status}): {str(body)[:200]}")
    except ReleaseError:
        # Delete only what is still a draft (a draft was never immutable). A PATCH that GitHub carried out but
        # reported as failed has published the release: that is never deleted here; the checks below judge it.
        status, now = gh.api("GET", f"/repos/{gh.slug}/releases/{draft['id']}")
        if status == 200 and isinstance(now, dict) and now.get("draft") is True:
            gh.api("DELETE", f"/repos/{gh.slug}/releases/{draft['id']}")
            raise
        if not (status == 200 and isinstance(now, dict) and now.get("draft") is False):
            raise
    status, rel = gh.api("GET", f"/repos/{gh.slug}/releases/tags/{tag}")
    p = release_problems(rel, address=facts["address"], commit=commit, tar_sha256=facts["tar_sha256"]) \
        if status == 200 else [f"the published release is unreadable (HTTP {status})"]
    if status == 200 and isinstance(rel, dict) and rel.get("id") == draft["id"] and rel.get("immutable") is False:
        # Published but explicitly mutable: the repository setting is off. This job's own release, never
        # immutable, so it and its tag are removed and the tag stays usable; then fail, saying what is left. A
        # release whose immutability GitHub does not state is never deleted (it may be immutable): it fails below.
        gone_rel = gh.api("DELETE", f"/repos/{gh.slug}/releases/{rel['id']}")[0] == 200
        gone_tag = gh.api("DELETE", f"/repos/{gh.slug}/git/refs/tags/{tag}")[0] == 200
        left = [x for x, gone in ((f"the mutable release {rel['id']}", gone_rel), (f"the tag {tag}", gone_tag))
                if not gone]
        raise ReleaseError("IMMUTABLE_RELEASES_NOT_ENABLED: the published release reported immutable false. "
                           + ("It and its tag were removed. " if not left else
                              f"Removing it failed; still there: {', '.join(left)}. Every later RT-1 at this commit "
                              "is refused until the Owner removes them, or readiness moves to a new commit. ")
                           + "Enable release immutability (Settings > General > Releases), then dispatch RT-1 "
                           "again")
    if p:
        raise ReleaseError("the published release is not the snapshot: " + "; ".join(p))
    tagged = tag_commit(gh, tag)
    if tagged != commit:
        raise ReleaseError(f"the tag points at {tagged}, not the publishing commit {commit}")
    return {"result": PUBLISHED, **summary(rel), "tag_commit": tagged, "facts": facts,
            "published_by_run": int(run_id), "published_record_digest": facts["digests"][RECORD]}


# -- read -----------------------------------------------------------------------------------------

def download(gh: GH, dest: Path, commit: str, address: str | None = None) -> dict:
    """The readiness commit's snapshot release's three assets into ``dest`` (new or empty), each checked against
    GitHub's digest, and the manifest against the tag's address."""
    rel = the_snapshot(gh, commit, address)
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.iterdir()):
        raise ReleaseError(f"{dest} is not empty")
    rc, msg = gh.download(rel["tag_name"], list(ASSETS), dest)
    if rc != 0:
        raise ReleaseError(f"downloading {rel['tag_name']} failed: {msg}")
    assets = asset_map(rel)
    for n in ASSETS:
        got = "sha256:" + sha256_file(dest / n)
        if got != assets[n]["digest"]:
            raise ReleaseError(f"{n}: downloaded bytes hash to {got}, the release says {assets[n]['digest']}")
    SN.load_manifest((dest / MANIFEST).read_bytes(), address_of(rel["tag_name"]))
    return summary(rel)


# -- RT-3 probes ------------------------------------------------------------------------------------

def _refused(status) -> bool:
    return isinstance(status, int) and 400 <= status < 500


def probe_immutable(gh: GH, directory: Path, commit: str) -> dict:
    """With the publish job's write token: every change to the readiness commit's snapshot release must be
    refused."""
    rel = the_snapshot(gh, commit)
    tag, assets = rel["tag_name"], asset_map(rel)
    record_path = directory / RECORD
    if "sha256:" + sha256_file(record_path) != assets[RECORD]["digest"]:
        raise ReleaseError(f"the local {RECORD} is not the release's; download the release first")
    status, ref = gh.api("GET", f"/repos/{gh.slug}/git/ref/tags/{tag}")
    tagged = (ref.get("object") or {}).get("sha") if status == 200 and isinstance(ref, dict) else None
    if not tagged:
        raise ReleaseError(f"the tag {tag} is unreadable (HTTP {status})")
    status, commit = gh.api("GET", f"/repos/{gh.slug}/git/commits/{tagged}")
    parents = [p.get("sha") for p in (commit.get("parents") or [])] if isinstance(commit, dict) else []
    if not parents:
        raise ReleaseError("the tagged commit has no parent to move the tag to")
    probes: dict[str, dict] = {}

    with tempfile.TemporaryDirectory() as td:
        probe = Path(td) / "rt3-probe.txt"
        probe.write_text("RT-3 immutability probe: this upload must be refused\n")
        rc, msg = gh.upload(tag, probe)
        m = re.search(r"\bHTTP (\d{3})\b", msg or "")
        probes["attach_new_asset"] = {"refused": rc != 0 and _refused(int(m[1]) if m else None),
                                      "status": int(m[1]) if m else None, "detail": msg[:200]}
        if rc == 0:
            again = asset_map(gh.api("GET", f"/repos/{gh.slug}/releases/{rel['id']}")[1] or {})
            if "rt3-probe.txt" in again:
                gh.api("DELETE", f"/repos/{gh.slug}/releases/assets/{again['rt3-probe.txt']['id']}")

    status, body = gh.api("PATCH", f"/repos/{gh.slug}/releases/assets/{assets[RECORD]['id']}",
                          {"name": RECORD + ".probe"})
    probes["rename_asset"] = {"refused": _refused(status), "status": status}
    if status == 200:
        gh.api("PATCH", f"/repos/{gh.slug}/releases/assets/{assets[RECORD]['id']}", {"name": RECORD})

    status, body = gh.api("DELETE", f"/repos/{gh.slug}/releases/assets/{assets[RECORD]['id']}")
    probes["delete_record_asset"] = {"refused": _refused(status), "status": status}
    if status in (200, 204):
        rc, msg = gh.upload(tag, record_path)
        probes["delete_record_asset"]["restored"] = rc == 0

    status, body = gh.api("PATCH", f"/repos/{gh.slug}/git/refs/tags/{tag}", {"sha": parents[0], "force": True})
    probes["move_tag"] = {"refused": _refused(status), "status": status, "to": parents[0]}
    if status == 200:
        gh.api("PATCH", f"/repos/{gh.slug}/git/refs/tags/{tag}", {"sha": tagged, "force": True})

    after = the_snapshot_or_none(gh, tag)
    status, ref = gh.api("GET", f"/repos/{gh.slug}/git/ref/tags/{tag}")
    now_tagged = (ref.get("object") or {}).get("sha") if status == 200 and isinstance(ref, dict) else None
    unchanged = after is not None and summary(after)["assets"] == summary(rel)["assets"] and now_tagged == tagged
    ok = all(v["refused"] for v in probes.values()) and unchanged
    return {"test": "RT-3", "part": "immutability", "probes": probes, "release_unchanged": unchanged,
            "tag_commit": tagged, "result": "PASS" if ok else "FAIL", **{"release": summary(rel)}}


def the_snapshot_or_none(gh: GH, tag: str) -> dict | None:
    status, rel = gh.api("GET", f"/repos/{gh.slug}/releases/tags/{tag}")
    return rel if status == 200 and isinstance(rel, dict) else None


def probe_read_only(gh: GH, run_id: str, commit: str) -> dict:
    """With a contents: read token: every write must be refused (HTTP 4xx). Each probe is harmless or undone if
    GitHub wrongly allowed it: an unreferenced blob, a probe tag and a probe draft (both deleted again with the
    token that created them) and a release-notes edit that writes the notes back unchanged."""
    rel = the_snapshot(gh, commit)
    tag = rel["tag_name"]
    status, ref = gh.api("GET", f"/repos/{gh.slug}/git/ref/tags/{tag}")
    sha = (ref.get("object") or {}).get("sha") if status == 200 and isinstance(ref, dict) else None
    if not sha:
        raise ReleaseError(f"the tag {tag} is unreadable (HTTP {status})")
    probe = f"auth2q2-rt3-read-only-probe-{run_id}"
    probes = {}
    status, _ = gh.api("POST", f"/repos/{gh.slug}/git/blobs", {"content": "RT-3 read-only probe\n",
                                                                "encoding": "utf-8"})
    probes["create_blob"] = {"refused": _refused(status), "status": status}
    status, _ = gh.api("POST", f"/repos/{gh.slug}/git/refs", {"ref": f"refs/tags/{probe}", "sha": sha})
    probes["create_tag"] = {"refused": _refused(status), "status": status}
    if status == 200:
        probes["create_tag"]["reverted"] = gh.api("DELETE", f"/repos/{gh.slug}/git/refs/tags/{probe}")[0] == 200
    status, body = gh.api("POST", f"/repos/{gh.slug}/releases", {"tag_name": probe, "target_commitish": sha,
                                                                 "name": probe, "draft": True})
    probes["create_draft_release"] = {"refused": _refused(status), "status": status}
    if status == 200 and isinstance(body, dict) and body.get("id"):
        probes["create_draft_release"]["reverted"] = \
            gh.api("DELETE", f"/repos/{gh.slug}/releases/{body['id']}")[0] == 200
    status, _ = gh.api("PATCH", f"/repos/{gh.slug}/releases/{rel['id']}", {"body": rel.get("body") or ""})
    probes["edit_release_notes"] = {"refused": _refused(status), "status": status}
    ok = all(v["refused"] for v in probes.values())
    return {"test": "RT-3", "part": "read-only", "probes": probes, "result": "PASS" if ok else "FAIL",
            "release": summary(rel)}


# -- CLI --------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("publish", "verify", "download", "probe-immutable", "probe-read-only"):
        p = sub.add_parser(name)
        p.add_argument("--repo-slug", required=True)
        p.add_argument("--out", required=True)
        p.add_argument("--commit", required=True, help="the readiness commit (the run's GITHUB_SHA)")
        if name in ("publish", "probe-immutable"):
            p.add_argument("--dir", required=True)
        if name in ("verify", "download"):
            p.add_argument("--address")
        if name == "download":
            p.add_argument("--dest", required=True)
    a = ap.parse_args(argv)
    gh = GH(a.repo_slug)
    try:
        if not is_commit(a.commit):
            raise ReleaseError(f"{a.commit[:50]!r} is not a full commit sha")
        if a.cmd == "publish":
            rec = publish(gh, Path(a.dir), a.commit, os.environ.get("GITHUB_RUN_ID"))
        elif a.cmd == "verify":
            rec = summary(the_snapshot(gh, a.commit, a.address))
        elif a.cmd == "download":
            rec = download(gh, Path(a.dest), a.commit, a.address)
        elif a.cmd == "probe-immutable":
            rec = probe_immutable(gh, Path(a.dir), a.commit)
        else:
            rec = probe_read_only(gh, os.environ.get("GITHUB_RUN_ID") or "local", a.commit)
    except (ReleaseError, SN.SnapshotError, OSError, ValueError) as exc:
        rec = {"result": "FAIL", "error": str(exc)[:1500]}
        print(f"::error::RELEASE_REFUSED: {str(exc)[:1500]}")
    rec["checked_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = json.dumps(rec, indent=1, sort_keys=True) + "\n"
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(body)
    print(body, end="")
    ok = rec.get("result") in (PUBLISHED, VERIFIED_EXISTING, "PASS") or (
        a.cmd in ("verify", "download") and "error" not in rec)
    print(f"RELEASE_{a.cmd.upper().replace('-', '_')} = {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
