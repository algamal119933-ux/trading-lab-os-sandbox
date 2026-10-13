"""AUTH-2-DISCOVERY-QUALIFICATION-2 readiness (RT-1, RT-3, RT-4): the snapshot's immutable release
(research/auth2q2/release.py), against an in-memory GitHub.

The release binds the snapshot's address to the readiness commit: one release per (address, commit), tagged with
both and on that commit. It is published draft-first and checked against the digests GitHub computes; a release
that comes out mutable is the repository setting being off, and only that job's own release and tag are removed.
RT-1 dispatched again at the same commit verifies the published release byte for byte against its own cold
preparation and changes nothing; at a new commit it publishes that commit's own release, and an earlier commit's
release is never read, reused or changed. Readers take the snapshot only from the readiness commit's one
published, immutable, complete release and check every byte. The RT-3 probes must find every write refused, and
undo anything GitHub wrongly allowed.

PAPER / RESEARCH ONLY. Nothing here opens a connection.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from auth2 import archive as A
from auth2q2 import release as RL
from auth2q2 import snapshot as SN

SLUG = "owner/repo"
COMMIT = "a" * 40
PARENT = "b" * 40
NEW = "c" * 40          # a later readiness commit, after a code repair
RUN1, RUN2, RUN_NEW = "11", "12", "21"


# -- the snapshot files ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _outside_actions(monkeypatch):
    """The CLIs stamp GitHub Actions' run identity into their records; in CI those variables belong to the CI
    run, not to the fixtures, so every test here starts without them and sets what it needs."""
    for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "GITHUB_EVENT_PATH"):
        monkeypatch.delenv(k, raising=False)


def snapshot_files(tmp: Path, name: str = "out", salt: str = "", *, run_id: str = RUN1, commit: str = COMMIT,
                   attempt: str = "1") -> Path:
    """manifest.json, snapshot.tar and prepare-record.json as the preparation of run ``run_id`` at ``commit``
    writes them. The same ``salt`` gives the same manifest and tar: preparation is deterministic."""
    root = tmp / f"tree-{name}"
    keys = [f"data/spot/monthly/klines/AAAUSDT/1h/AAAUSDT-1h-2020-0{i}.zip" for i in (1, 2, 3)]
    paths = []
    for i, k in enumerate(keys):
        body = f"zip {i} {k} {salt}\n".encode() * (i + 3)
        p = root / k
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
        Path(str(p) + SN.CHECKSUM_SUFFIX).write_text(f"{hashlib.sha256(body).hexdigest()}  {Path(k).name}\n")
        paths += [k, k + SN.CHECKSUM_SUFFIX]
    (root / SN.LISTING_REL).parent.mkdir(parents=True, exist_ok=True)
    (root / SN.LISTING_REL).write_bytes(b'{"listing": "test"}\n')
    paths.append(SN.LISTING_REL)
    out = tmp / name
    out.mkdir()
    entries, tar_sha, _n = SN.write_tar(root, paths, out / RL.TAR)
    _man, raw = SN.build_manifest(entries, lock_sha256="c" * 64, last_month="2026-08", archive=A.LIST_BASE)
    (out / RL.MANIFEST).write_bytes(raw)
    (out / RL.RECORD).write_text(json.dumps({"program": SN.PROGRAM_ID, "address": SN.address(raw),
                                             "tar_sha256": tar_sha, "run_id": run_id, "run_attempt": attempt,
                                             "commit": commit}, sort_keys=True) + "\n")
    return out


# -- an in-memory GitHub ------------------------------------------------------------------------------

def _sha(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


class FakeGitHub:
    """Releases, assets and tag refs as the REST API and ``gh`` show them to one workflow token.

    immutable_setting  the repository's "Enable release immutability" setting
    enforce            whether GitHub actually refuses changes to an immutable release (RT-3's question)
    write              whether the token has contents: write
    digests            whether GitHub reports asset digests
    """

    def __init__(self, *, immutable_setting=True, enforce=True, write=True, digests=True,
                 author=RL.BOT) -> None:
        self.slug = SLUG
        self.immutable_setting, self.enforce, self.write, self.digests = immutable_setting, enforce, write, digests
        self.author = author
        self.releases: dict[int, dict] = {}
        self.refs: dict[str, str] = {}
        self.ref_types: dict[str, str] = {}   # tag -> the ref's object type ("tag": an annotated tag object)
        self.blobs = 0
        self.commits = {COMMIT: [PARENT], PARENT: [], NEW: [COMMIT]}
        self.runs: dict[int, dict] = {}
        for rid, commit in ((RUN1, COMMIT), (RUN2, COMMIT), (RUN_NEW, NEW)):
            self.add_run(rid, commit)
        self.next_id = 100
        self.calls: list[tuple] = []
        self.fail: set[str] = set()       # create_draft_rc, create_draft_partial, publish_patch, corrupt_upload,
                                          # tamper_download, download_rc
        self.publish_hook = None

    # bookkeeping
    def _id(self) -> int:
        self.next_id += 1
        return self.next_id

    def _asset(self, name: str, data: bytes) -> dict:
        return {"id": self._id(), "name": name, "size": len(data), "state": "uploaded",
                "digest": _sha(data) if self.digests else None, "_bytes": data}

    def _view(self, rel: dict) -> dict:
        out = {k: v for k, v in rel.items() if k != "assets"}
        out["assets"] = [{k: v for k, v in a.items() if k != "_bytes"} for a in rel["assets"]]
        return json.loads(json.dumps(out))

    def _by_tag(self, tag: str, published: bool | None = None) -> dict | None:
        for r in self.releases.values():
            if r["tag_name"] == tag and (published is None or r["draft"] is (not published)):
                return r
        return None

    def _locked(self, rel: dict) -> bool:
        return rel["immutable"] is True and self.enforce

    def _asset_owner(self, asset_id: int) -> tuple[dict, dict] | tuple[None, None]:
        for r in self.releases.values():
            for a in r["assets"]:
                if a["id"] == asset_id:
                    return r, a
        return None, None

    def add_run(self, run_id, commit: str, test: str = "RT-1", **kw) -> dict:
        """A readiness run as the Actions API shows it: by default an RT-1 run of the preparation workflow."""
        run = {"id": int(run_id), "path": ".github/workflows/auth2q2-prepare.yml", "event": "workflow_dispatch",
               "head_branch": "main", "head_sha": commit, "display_title": f"AUTH2Q2-READINESS {test}",
               "run_attempt": 1, **kw}
        self.runs[int(run_id)] = run
        return run

    def new_release(self, out: Path, *, draft=False, immutable=True, extra: dict | None = None) -> dict:
        """A release put there directly, as if an RT-1 run had published it earlier at its record's commit."""
        rec = json.loads((out / RL.RECORD).read_text())
        tag = RL.tag_for(rec["address"], rec["commit"])
        rel = {"id": self._id(), "tag_name": tag, "draft": draft, "prerelease": False, "immutable": immutable,
               "target_commitish": rec["commit"], "author": {"login": RL.BOT}, "body": "notes",
               "published_at": None if draft else "2026-10-13T00:00:00Z",
               "assets": [self._asset(n, (out / n).read_bytes()) for n in RL.ASSETS]}
        rel.update(extra or {})
        self.releases[rel["id"]] = rel
        if not draft:
            self.refs[rel["tag_name"]] = rel["target_commitish"]
        return rel

    def writes(self) -> list[tuple]:
        """Every call that could change GitHub."""
        return [c for c in self.calls if c[0] in ("POST", "PATCH", "PUT", "DELETE", "create_draft", "upload")]

    # gh
    def api(self, method: str, path: str, body: dict | None = None):
        self.calls.append((method, path, body))
        base = f"/repos/{SLUG}"
        assert path.startswith(base), path
        p = path[len(base):]
        writes = method in ("POST", "PATCH", "PUT", "DELETE")
        if writes and not self.write:
            return 403, "gh: Resource not accessible by integration (HTTP 403)"
        if method == "GET" and p.startswith("/releases?"):
            page = int(p.split("page=")[-1])
            rels = [self._view(r) for r in self.releases.values() if self.write or not r["draft"]]
            return 200, rels[(page - 1) * 100: page * 100]
        if method == "GET" and p.startswith("/releases/tags/"):
            r = self._by_tag(p.rsplit("/", 1)[1], published=True)
            return (200, self._view(r)) if r else (404, "gh: Not Found (HTTP 404)")
        if p.startswith("/releases/assets/"):
            r, a = self._asset_owner(int(p.rsplit("/", 1)[1]))
            if a is None:
                return 404, "gh: Not Found (HTTP 404)"
            if self._locked(r):
                return 422, "gh: Cannot modify an asset of an immutable release (HTTP 422)"
            if method == "PATCH":
                a.update({k: v for k, v in body.items() if k in ("name", "label")})
                return 200, {k: v for k, v in a.items() if k != "_bytes"}
            if method == "DELETE":
                r["assets"].remove(a)
                return 200, None
        if p.startswith("/releases/") and p.count("/") == 2:
            rid = int(p.rsplit("/", 1)[1])
            r = self.releases.get(rid)
            if r is None:
                return 404, "gh: Not Found (HTTP 404)"
            if method == "GET":
                return 200, self._view(r)
            if method == "DELETE":
                del self.releases[rid]
                return 200, None
            if method == "PATCH":
                if "publish_patch" in self.fail and body.get("draft") is False:
                    return 500, "gh: Server Error (HTTP 500)"
                if body.get("draft") is False and r["draft"]:
                    if r["tag_name"] not in self.refs:
                        self.refs[r["tag_name"]] = r["target_commitish"]
                    r.update(draft=False, immutable=self.immutable_setting, published_at="2026-10-13T01:00:00Z")
                    if self.publish_hook:
                        self.publish_hook(r)
                if "body" in body:
                    r["body"] = body["body"]
                return 200, self._view(r)
        if method == "POST" and p == "/releases":
            rel = {"id": self._id(), "tag_name": body["tag_name"], "draft": True, "prerelease": False,
                   "immutable": False, "target_commitish": body.get("target_commitish"), "body": "",
                   "author": {"login": self.author}, "published_at": None, "assets": []}
            self.releases[rel["id"]] = rel
            return 200, self._view(rel)
        if p.startswith("/git/ref/tags/") and method == "GET":
            tag = p[len("/git/ref/tags/"):]
            return (200, {"object": {"sha": self.refs[tag], "type": self.ref_types.get(tag, "commit")}}) \
                if tag in self.refs else \
                (404, "gh: Not Found (HTTP 404)")
        if method == "GET" and p.startswith("/actions/runs/"):
            parts = p.split("/")   # /actions/runs/{id} or /actions/runs/{id}/attempts/{n}
            run = self.runs.get(int(parts[3]))
            if run and len(parts) == 6:   # that attempt's view of the run
                n = int(parts[5])
                run = {**run, "run_attempt": n} if n <= run["run_attempt"] else None
            return (200, json.loads(json.dumps(run))) if run else (404, "gh: Not Found (HTTP 404)")
        if p.startswith("/git/refs/tags/"):
            tag = p[len("/git/refs/tags/"):]
            if tag not in self.refs:
                return 422, "gh: Reference does not exist (HTTP 422)"
            r = self._by_tag(tag, published=True)
            if r is not None and self._locked(r):
                return 422, "gh: Cannot update a tag of an immutable release (HTTP 422)"
            if method == "DELETE":
                del self.refs[tag]
                return 200, None
            if method == "PATCH":
                self.refs[tag] = body["sha"]
                return 200, {"object": {"sha": body["sha"]}}
        if method == "POST" and p == "/git/refs":
            tag = body["ref"].removeprefix("refs/tags/")
            if tag in self.refs:
                return 422, "gh: Reference already exists (HTTP 422)"
            self.refs[tag] = body["sha"]
            return 200, {"ref": body["ref"]}
        if method == "POST" and p == "/git/blobs":
            self.blobs += 1
            return 200, {"sha": "d" * 40}
        if method == "GET" and p.startswith("/git/commits/"):
            sha = p.rsplit("/", 1)[1]
            return (200, {"sha": sha, "parents": [{"sha": x} for x in self.commits[sha]]}) \
                if sha in self.commits else (404, "gh: Not Found (HTTP 404)")
        raise AssertionError(f"unexpected call {method} {path}")

    def create_draft(self, tag, commit, title, notes, files):
        self.calls.append(("create_draft", tag, commit))
        if not self.write:
            return 1, "HTTP 403"
        rel = {"id": self._id(), "tag_name": tag, "draft": True, "prerelease": False, "immutable": False,
               "target_commitish": commit, "author": {"login": self.author}, "body": notes, "name": title,
               "published_at": None, "assets": []}
        self.releases[rel["id"]] = rel
        for i, f in enumerate(files):
            if "create_draft_partial" in self.fail and i == 2:
                return 1, "upload failed (HTTP 502)"
            data = Path(f).read_bytes()
            a = self._asset(Path(f).name, data)
            if "corrupt_upload" in self.fail and Path(f).name == RL.TAR:
                a["digest"] = _sha(data + b"x")
            rel["assets"].append(a)
        return (1, "failed (HTTP 500)") if "create_draft_rc" in self.fail else (0, "")

    def upload(self, tag, path):
        self.calls.append(("upload", tag, str(path)))
        r = self._by_tag(tag)
        if r is None or not self.write:
            return 1, "HTTP 403"
        if self._locked(r):
            return 1, "HTTP 422: Cannot upload assets to an immutable release"
        r["assets"].append(self._asset(Path(path).name, Path(path).read_bytes()))
        return 0, ""

    def download(self, tag, names, dest):
        self.calls.append(("download", tag))
        if "download_rc" in self.fail:
            return 1, "HTTP 502"
        r = self._by_tag(tag, published=True)
        for a in r["assets"]:
            if a["name"] in names:
                data = a["_bytes"] + (b"!" if "tamper_download" in self.fail and a["name"] == RL.TAR else b"")
                (Path(dest) / a["name"]).write_bytes(data)
        return 0, ""


@pytest.fixture()
def out(tmp_path):
    return snapshot_files(tmp_path)


def address(out: Path) -> str:
    return json.loads((out / RL.RECORD).read_text())["address"]


# -- tags: the snapshot's address and the readiness commit ------------------------------------------------

def test_the_tag_binds_the_snapshot_address_and_the_readiness_commit_and_nothing_else():
    a = "sha256:" + "e" * 64
    tag = RL.tag_for(a, COMMIT)
    assert tag == "auth2q2-snapshot-sha256-" + "e" * 64 + "-at-" + COMMIT
    assert RL.address_of(tag) == a and RL.commit_of(tag) == COMMIT
    assert RL.tag_for(a, NEW) != tag and RL.address_of(RL.tag_for(a, NEW)) == a  # one address, two executions
    for bad in ("sha256:" + "E" * 64, "e" * 64, "sha256:" + "e" * 63, "", None):
        with pytest.raises(RL.ReleaseError, match="not a snapshot address"):
            RL.tag_for(bad, COMMIT)
    for bad in ("A" * 40, "a" * 39, "a" * 41, "main", "", None):
        with pytest.raises(RL.ReleaseError, match="not a full commit sha"):
            RL.tag_for(a, bad)
    for bad in ("auth2q2-snapshot-sha256-" + "e" * 64,  # the address alone names no readiness execution
                "auth2q2-snapshot-sha256-" + "e" * 63 + "-at-" + COMMIT, tag + "x", tag[:-1], "v1.0", None,
                "x" + tag, tag.replace("-at-", "-on-")):
        assert RL.address_of(bad) is None and RL.commit_of(bad) is None


# -- publish (RT-1) -----------------------------------------------------------------------------------

def test_publish_goes_draft_first_and_ends_immutable_at_the_commit(out):
    gh = FakeGitHub()
    rec = RL.publish(gh, out, COMMIT, RUN1)
    assert rec["result"] == RL.PUBLISHED and rec["immutable"] is True and rec["draft"] is False
    assert rec["tag"] == RL.tag_for(address(out), COMMIT) and rec["commit"] == rec["tag_commit"] == COMMIT
    assert rec["published_by_run"] == int(RUN1)
    assert gh.refs == {rec["tag"]: COMMIT}
    (rel,) = gh.releases.values()
    assert rel["target_commitish"] == COMMIT
    for a in rel["assets"]:
        assert a["digest"] == _sha((out / a["name"]).read_bytes())
    order = [c[0] for c in gh.calls]
    assert order.index("create_draft") < next(i for i, c in enumerate(gh.calls)
                                              if c[0] == "PATCH" and c[2] == {"draft": False, "make_latest": "false"})
    assert RL.the_snapshot(gh, COMMIT)["id"] == rel["id"]
    with pytest.raises(RL.ReleaseError, match="names this run"):  # the publishing run cannot also verify it
        RL.publish(gh, out, COMMIT, RUN1)
    assert len(gh.releases) == 1


def test_publish_needs_this_runs_id(out):
    for run_id in (None, "", "local", "1e3"):
        gh = FakeGitHub()
        with pytest.raises(RL.ReleaseError, match="run's id is required"):
            RL.publish(gh, out, COMMIT, run_id)
        assert gh.calls == []


def test_a_mutable_release_means_the_setting_is_off_and_only_this_jobs_release_and_tag_are_removed(out):
    gh = FakeGitHub(immutable_setting=False)
    other = snapshot_files(out.parent, "other", salt="other")
    keep = gh.new_release(other, immutable=False, extra={"tag_name": "v-unrelated"})
    with pytest.raises(RL.ReleaseError, match="IMMUTABLE_RELEASES_NOT_ENABLED"):
        RL.publish(gh, out, COMMIT, RUN1)
    assert list(gh.releases) == [keep["id"]] and RL.tag_for(address(out), COMMIT) not in gh.refs
    gh.immutable_setting = True
    assert RL.publish(gh, out, COMMIT, RUN1)["result"] == RL.PUBLISHED  # the tag was left usable


@pytest.mark.parametrize("fail, match", [
    ("create_draft_rc", "creating the draft failed"),
    ("create_draft_partial", "creating the draft failed"),
    ("corrupt_upload", "GitHub's digest"),
    ("publish_patch", "publishing failed"),
])
def test_a_draft_that_is_not_exactly_the_snapshot_is_deleted_and_never_published(out, fail, match):
    gh = FakeGitHub()
    gh.fail.add(fail)
    with pytest.raises(RL.ReleaseError, match=match):
        RL.publish(gh, out, COMMIT, RUN1)
    assert gh.releases == {} and gh.refs == {}


def test_without_github_digests_nothing_is_published(out):
    gh = FakeGitHub(digests=False)
    with pytest.raises(RL.ReleaseError, match="no sha256 digest"):
        RL.publish(gh, out, COMMIT, RUN1)
    assert gh.releases == {} and gh.refs == {}


def test_a_draft_written_by_anyone_but_the_workflow_bot_is_deleted(out):
    gh = FakeGitHub(author="someone")
    with pytest.raises(RL.ReleaseError, match="author"):
        RL.publish(gh, out, COMMIT, RUN1)
    assert gh.releases == {}


def test_a_tag_that_already_exists_stops_publication_before_any_draft(out):
    gh = FakeGitHub()
    gh.refs[RL.tag_for(address(out), COMMIT)] = PARENT
    with pytest.raises(RL.ReleaseError, match="already exists"):
        RL.publish(gh, out, COMMIT, RUN1)
    assert gh.releases == {} and not any(c[0] == "create_draft" for c in gh.calls)


def test_a_published_release_whose_tag_moved_is_refused(out):
    gh = FakeGitHub()
    gh.publish_hook = lambda r: gh.refs.__setitem__(r["tag_name"], PARENT)
    with pytest.raises(RL.ReleaseError, match="not the publishing commit"):
        RL.publish(gh, out, COMMIT, RUN1)


def test_an_earlier_runs_draft_of_this_tag_is_cleared_and_any_other_draft_stops_publication(out, tmp_path):
    gh = FakeGitHub()
    stale = gh.new_release(out, draft=True)  # left by an earlier run whose cleanup failed: never published
    rec = RL.publish(gh, out, COMMIT, RUN1)
    assert rec["result"] == RL.PUBLISHED and stale["id"] not in gh.releases and len(gh.releases) == 1
    for extra in ({"author": {"login": "someone"}},
                  {"tag_name": RL.tag_for(address(snapshot_files(tmp_path, "x", salt="x")), COMMIT)}):
        gh = FakeGitHub()
        d = gh.new_release(out, draft=True, extra=extra)
        with pytest.raises(RL.ReleaseError, match="nothing is published"):
            RL.publish(gh, out, COMMIT, RUN1)
        assert list(gh.releases) == [d["id"]] and gh.writes() == []


@pytest.mark.parametrize("edit, err", [
    (lambda o: (o / RL.TAR).write_bytes((o / RL.TAR).read_bytes()[:-1024] + b"\1" * 1024), SN.SnapshotError),
    (lambda o: (o / RL.MANIFEST).write_bytes((o / RL.MANIFEST).read_bytes() + b" "), SN.SnapshotError),
    (lambda o: (o / RL.RECORD).write_text("[]"), RL.ReleaseError),
    (lambda o: (o / RL.RECORD).write_text("{"), RL.ReleaseError),
    (lambda o: (o / RL.RECORD).write_text(json.dumps({**json.loads((o / RL.RECORD).read_text()),
                                                      "tar_sha256": "0" * 64})), RL.ReleaseError),
    (lambda o: (o / RL.RECORD).write_text(json.dumps({**json.loads((o / RL.RECORD).read_text()),
                                                      "program": "AUTH-2-DISCOVERY-QUALIFICATION-1"})),
     RL.ReleaseError),
    (lambda o: (o / RL.TAR).unlink(), RL.ReleaseError),
])
def test_local_files_that_are_not_one_consistent_snapshot_are_never_uploaded(out, edit, err):
    edit(out)
    gh = FakeGitHub()
    with pytest.raises(err):
        RL.publish(gh, out, COMMIT, RUN1)
    assert gh.calls == []


def test_only_this_commits_and_this_runs_preparation_is_published(out):
    with pytest.raises(RL.ReleaseError, match="made at"):
        RL.publish(FakeGitHub(), out, PARENT, RUN1)
    with pytest.raises(RL.ReleaseError, match=f"run {RUN1}'s, not run 7's"):
        RL.publish(FakeGitHub(), out, COMMIT, "7")
    with pytest.raises(RL.ReleaseError, match="not a full commit sha"):
        RL.publish(FakeGitHub(), out, "main", RUN1)
    assert RL.publish(FakeGitHub(), out, COMMIT, RUN1)["result"] == RL.PUBLISHED


def test_a_symlinked_snapshot_file_is_refused(out, tmp_path):
    real = tmp_path / "elsewhere.tar"
    shutil.move(out / RL.TAR, real)
    (out / RL.TAR).symlink_to(real)
    with pytest.raises(RL.ReleaseError, match="missing"):
        RL.local_files(out)


# -- RT-1 again: the same commit verifies, a new commit publishes its own -------------------------------

def rerun(tmp_path: Path, name: str = "again", salt: str = "", run_id: str = RUN2, commit: str = COMMIT) -> Path:
    """Another RT-1 run's own cold preparation."""
    return snapshot_files(tmp_path, name, salt, run_id=run_id, commit=commit)


def view(gh: FakeGitHub, rel_id: int) -> str:
    return json.dumps(gh._view(gh.releases[rel_id]), sort_keys=True)


def test_rt1_again_at_the_same_commit_verifies_the_release_byte_for_byte_and_changes_nothing(out, tmp_path):
    gh = FakeGitHub()
    first = RL.publish(gh, out, COMMIT, RUN1)
    before, refs, n = view(gh, first["release_id"]), dict(gh.refs), len(gh.calls)
    again = rerun(tmp_path)
    assert (again / RL.RECORD).read_bytes() != (out / RL.RECORD).read_bytes()  # fresh, this run's own
    rec = RL.publish(gh, again, COMMIT, RUN2)
    assert rec["result"] == RL.VERIFIED_EXISTING and rec["published_by_run"] == int(RUN1)
    assert rec["release_id"] == first["release_id"] and rec["tag"] == first["tag"] and rec["tag_commit"] == COMMIT
    assert rec["facts"]["digests"][RL.MANIFEST] == first["facts"]["digests"][RL.MANIFEST]
    assert rec["facts"]["digests"][RL.TAR] == first["facts"]["digests"][RL.TAR]
    assert rec["facts"]["digests"][RL.RECORD] != rec["published_record_digest"] == first["published_record_digest"]
    assert [c for c in gh.writes() if gh.calls.index(c) >= n] == []  # nothing written, deleted or moved
    assert view(gh, first["release_id"]) == before and gh.refs == refs and len(gh.releases) == 1


def test_rt1_again_after_a_publication_that_then_failed_verifies_it(out, tmp_path):
    class LostAfterPublish(FakeGitHub):
        lose = True

        def api(self, method, path, body=None):
            if self.lose and method == "GET" and "/releases/tags/" in path:
                self.lose = False
                return 502, "gh: Bad Gateway (HTTP 502)"  # published; reading it back failed: the job fails
            return super().api(method, path, body)

    gh = LostAfterPublish()
    with pytest.raises(RL.ReleaseError, match="unreadable"):
        RL.publish(gh, out, COMMIT, RUN1)
    (rel,) = gh.releases.values()
    assert rel["draft"] is False and rel["immutable"] is True  # published, and it stays
    before, n = view(gh, rel["id"]), len(gh.calls)
    rec = RL.publish(gh, rerun(tmp_path), COMMIT, RUN2)
    assert rec["result"] == RL.VERIFIED_EXISTING and rec["published_by_run"] == int(RUN1)
    assert [c for c in gh.writes() if gh.calls.index(c) >= n] == [] and view(gh, rel["id"]) == before


def test_a_new_commit_publishes_its_own_release_and_the_earlier_one_stays_untouched_history(out, tmp_path):
    gh = FakeGitHub()
    old = RL.publish(gh, out, COMMIT, RUN1)
    before, n = view(gh, old["release_id"]), len(gh.calls)
    with pytest.raises(RL.ReleaseError, match="0 published snapshot release"):
        RL.the_snapshot(gh, NEW)  # the earlier commit's release never stands in for the new commit's
    new = RL.publish(gh, rerun(tmp_path, "new", run_id=RUN_NEW, commit=NEW), NEW, RUN_NEW)
    assert new["result"] == RL.PUBLISHED and new["published_by_run"] == int(RUN_NEW)  # cold, its own, published
    assert new["address"] == old["address"] and new["tag"] != old["tag"] and new["tag_commit"] == NEW
    assert RL.the_snapshot(gh, NEW)["id"] == new["release_id"] != old["release_id"]
    assert RL.the_snapshot(gh, COMMIT)["id"] == old["release_id"]
    assert view(gh, old["release_id"]) == before and gh.refs[old["tag"]] == COMMIT
    assert not any(str(old["release_id"]) in str(c) or old["tag"] in str(c[1:])
                   for c in gh.writes() if gh.calls.index(c) >= n)


def test_a_new_commits_rt1_never_takes_the_earlier_commits_verdict(out, tmp_path):
    """The earlier release is not even a candidate for verification at the new commit: only a release bound to
    the new commit can be, and none exists until the new RT-1 publishes it."""
    gh = FakeGitHub()
    RL.publish(gh, out, COMMIT, RUN1)
    stale = rerun(tmp_path, "stale", run_id=RUN_NEW, commit=COMMIT)  # a preparation made at the old commit
    with pytest.raises(RL.ReleaseError, match="made at"):
        RL.publish(gh, stale, NEW, RUN_NEW)
    assert RL.publish(gh, rerun(tmp_path, "n", run_id=RUN_NEW, commit=NEW), NEW, RUN_NEW)["result"] == RL.PUBLISHED


def test_a_second_snapshot_address_at_one_commit_is_refused(out, tmp_path):
    gh = FakeGitHub()
    RL.publish(gh, out, COMMIT, RUN1)
    n = len(gh.calls)
    with pytest.raises(RL.ReleaseError, match="SNAPSHOT_CONFLICT"):
        RL.publish(gh, rerun(tmp_path, salt="drifted"), COMMIT, RUN2)
    assert len(gh.releases) == 1 and [c for c in gh.writes() if gh.calls.index(c) >= n] == []


@pytest.mark.parametrize("edit, match", [
    (lambda r: r["assets"][1].update(size=r["assets"][1]["size"] + 1), "SNAPSHOT_MISMATCH"),
    (lambda r: r["assets"][1].update(digest="sha256:" + "0" * 64), "snapshot.tar: digest"),
    (lambda r: r["assets"][0].update(digest="sha256:" + "0" * 64), "not the tag's address"),
    (lambda r: r.update(immutable=False), "not immutable"),
    (lambda r: r.update(author={"login": "someone"}), "author"),
    (lambda r: r.update(target_commitish=PARENT), "targets"),
])
def test_rt1_again_refuses_a_release_that_is_not_its_own_cold_preparation(out, tmp_path, edit, match):
    gh = FakeGitHub()
    rel = gh.new_release(out)
    edit(rel)
    n = len(gh.calls)
    with pytest.raises(RL.ReleaseError, match=match):
        RL.publish(gh, rerun(tmp_path), COMMIT, RUN2)
    assert [c for c in gh.writes() if gh.calls.index(c) >= n] == []


def test_rt1_again_refuses_a_release_whose_tag_is_not_on_the_commit(out, tmp_path):
    gh = FakeGitHub()
    rel = gh.new_release(out)
    gh.refs[rel["tag_name"]] = PARENT
    with pytest.raises(RL.ReleaseError, match="points at"):
        RL.publish(gh, rerun(tmp_path), COMMIT, RUN2)


@pytest.mark.parametrize("record, run, match", [
    ({"run_id": "99"}, None, "unreadable"),                                    # no such run
    ({"run_id": "31"}, dict(commit=PARENT), "head_sha"),                      # a run at another commit
    ({"run_id": "31"}, dict(commit=COMMIT, test="RT-2"), "display_title"),    # not an RT-1 run
    ({"run_id": "31"}, dict(commit=COMMIT, head_branch="feature"), "head_branch"),
    ({"run_id": "31"}, dict(commit=COMMIT, path=".github/workflows/x.yml"), "path"),
    ({"run_id": "31"}, dict(commit=COMMIT, run_attempt=0), "unreadable"),     # no first attempt to read
    ({"run_id": RUN2}, None, "names this run"),                               # the verifying run itself
    ({"run_id": "local"}, None, "not a run id"),
    ({"commit": PARENT}, None, "commit"),                                     # a record of another commit
    ({"run_attempt": "2"}, None, "attempt"),
])
def test_rt1_again_refuses_a_release_another_session_published(tmp_path, record, run, match):
    """Cross-session evidence mixing: the release's own record must be an earlier RT-1 run's, at this commit."""
    gh = FakeGitHub()
    if run:
        gh.add_run("31", run.pop("commit"), test=run.pop("test", "RT-1"), **run)
    src = snapshot_files(tmp_path, "src")
    rec = {**json.loads((src / RL.RECORD).read_text()), **record}
    (src / RL.RECORD).write_text(json.dumps(rec, sort_keys=True) + "\n")
    rel = gh.new_release(src, extra={"tag_name": RL.tag_for(rec["address"], COMMIT), "target_commitish": COMMIT})
    gh.refs = {rel["tag_name"]: COMMIT}
    n = len(gh.calls)
    with pytest.raises(RL.ReleaseError, match=match):
        RL.publish(gh, rerun(tmp_path), COMMIT, RUN2)
    assert [c for c in gh.writes() if gh.calls.index(c) >= n] == []


def test_rt1_again_still_verifies_after_someone_clicked_re_run_on_the_publishing_run(out, tmp_path):
    """The gate refuses the re-run and its jobs are skipped, but the run's latest attempt moves to 2: what attempt
    1 published is still read as attempt 1's, so the commit is not locked out."""
    gh = FakeGitHub()
    RL.publish(gh, out, COMMIT, RUN1)
    gh.runs[int(RUN1)]["run_attempt"] = 2
    rec = RL.publish(gh, rerun(tmp_path), COMMIT, RUN2)
    assert rec["result"] == RL.VERIFIED_EXISTING and rec["published_by_run"] == int(RUN1)
    assert any(c[1].endswith(f"/actions/runs/{RUN1}/attempts/1") for c in gh.calls if c[0] == "GET")


@pytest.mark.parametrize("asset", RL.ASSETS)
def test_rt1_again_hashes_every_downloaded_asset_not_only_githubs_digest(out, tmp_path, asset):
    gh = FakeGitHub()
    rel = gh.new_release(out)
    next(a for a in rel["assets"] if a["name"] == asset)["_bytes"] += b" "   # served bytes, unchanged digest
    n = len(gh.calls)
    with pytest.raises(RL.ReleaseError, match=f"SNAPSHOT_MISMATCH: {re.escape(asset)}: the downloaded bytes"):
        RL.publish(gh, rerun(tmp_path), COMMIT, RUN2)
    assert [c for c in gh.writes() if gh.calls.index(c) >= n] == []


@pytest.mark.parametrize("fail_release, fail_tag, left", [
    (False, False, None), (True, False, "the mutable release"), (False, True, "the tag"),
])
def test_a_failed_cleanup_of_a_mutable_release_says_exactly_what_is_left(out, fail_release, fail_tag, left):
    class Stubborn(FakeGitHub):
        def api(self, method, path, body=None):
            if method == "DELETE" and ((fail_release and "/releases/" in path) or (fail_tag and "/git/refs/" in path)):
                self.calls.append((method, path, body))
                return 500, "gh: Server Error (HTTP 500)"
            return super().api(method, path, body)

    gh = Stubborn(immutable_setting=False)
    with pytest.raises(RL.ReleaseError, match="IMMUTABLE_RELEASES_NOT_ENABLED") as exc:
        RL.publish(gh, out, COMMIT, RUN1)
    msg = str(exc.value)
    if left is None:
        assert "It and its tag were removed" in msg and gh.releases == {} and gh.refs == {}
    else:
        assert f"still there: {left}" in msg and "were removed" not in msg


def test_a_release_whose_immutability_github_does_not_state_is_never_deleted(out):
    gh = FakeGitHub()
    gh.publish_hook = lambda r: r.pop("immutable")
    with pytest.raises(RL.ReleaseError, match="not immutable"):
        RL.publish(gh, out, COMMIT, RUN1)
    assert len(gh.releases) == 1 and not any(c[0] == "DELETE" for c in gh.calls)


def test_rt1_again_refuses_a_record_asset_whose_bytes_are_not_its_digest(out, tmp_path):
    gh = FakeGitHub()
    rel = gh.new_release(out)
    next(a for a in rel["assets"] if a["name"] == RL.RECORD)["_bytes"] += b" "
    with pytest.raises(RL.ReleaseError, match="downloaded bytes"):
        RL.publish(gh, rerun(tmp_path), COMMIT, RUN2)


# -- readers (RT-4) -----------------------------------------------------------------------------------

def test_download_checks_every_byte_against_githubs_digests(out, tmp_path):
    gh = FakeGitHub()
    RL.publish(gh, out, COMMIT, RUN1)
    got = RL.download(gh, tmp_path / "dl", COMMIT, address(out))
    assert got["address"] == address(out) and got["commit"] == COMMIT
    for n in RL.ASSETS:
        assert (tmp_path / "dl" / n).read_bytes() == (out / n).read_bytes()
    gh.fail.add("tamper_download")
    with pytest.raises(RL.ReleaseError, match="snapshot.tar: downloaded bytes"):
        RL.download(gh, tmp_path / "dl2", COMMIT)
    with pytest.raises(RL.ReleaseError, match="not empty"):
        RL.download(gh, tmp_path / "dl", COMMIT)
    gh.fail = {"download_rc"}
    with pytest.raises(RL.ReleaseError, match="downloading"):
        RL.download(gh, tmp_path / "dl3", COMMIT)


def test_readers_never_read_another_commits_release(out, tmp_path):
    """Stale-release rejection: a readiness run at a new commit finds no snapshot until its own RT-1 publishes."""
    gh = FakeGitHub()
    RL.publish(gh, out, COMMIT, RUN1)
    for read in (lambda: RL.the_snapshot(gh, NEW), lambda: RL.download(gh, tmp_path / "d", NEW),
                 lambda: RL.probe_immutable(gh, out, NEW), lambda: RL.probe_read_only(gh, "42", NEW)):
        with pytest.raises(RL.ReleaseError, match=f"0 published snapshot release\\(s\\) for the readiness commit {NEW}"):
            read()
    rel = next(iter(gh.releases.values()))
    assert any(x.startswith("STALE_RELEASE") for x in RL.release_problems(gh._view(rel), commit=NEW))
    for bad in (None, "main", "A" * 40):
        with pytest.raises(RL.ReleaseError, match="not a full commit sha"):
            RL.the_snapshot(gh, bad)


@pytest.mark.parametrize("edit, match", [
    (lambda r: r.update(immutable=False), "not immutable"),
    (lambda r: r.update(immutable=None), "not immutable"),
    (lambda r: r.update(prerelease=True), "prerelease"),
    (lambda r: r["assets"].pop(), "assets are"),
    (lambda r: r["assets"].append(dict(r["assets"][0], id=999, name="extra.bin")), "assets are"),
    (lambda r: r["assets"].append(dict(r["assets"][0], id=999)), "assets are"),
    (lambda r: r["assets"][0].update(digest=None), "no sha256 digest"),
    (lambda r: r["assets"][0].update(digest="sha1:" + "0" * 40), "no sha256 digest"),
    (lambda r: r["assets"][1].update(state="starter"), "state"),
    (lambda r: r["assets"][1].update(size=0), "size"),
    (lambda r: r["assets"][0].update(digest="sha256:" + "0" * 64), "not the tag's address"),
    (lambda r: r.update(target_commitish=PARENT), "targets"),
    (lambda r: r.update(target_commitish="main"), "targets"),
    (lambda r: r.update(author={"login": "someone"}), "author"),
])
def test_the_snapshot_is_only_ever_read_from_one_published_immutable_complete_release(out, edit, match):
    gh = FakeGitHub()
    rel = gh.new_release(out)
    edit(rel)
    with pytest.raises(RL.ReleaseError, match=match):
        RL.the_snapshot(gh, COMMIT)


def test_a_release_whose_tag_is_not_on_its_commit_is_never_read(out):
    gh = FakeGitHub()
    rel = gh.new_release(out)
    gh.refs[rel["tag_name"]] = PARENT
    with pytest.raises(RL.ReleaseError, match="does not point at the readiness commit"):
        RL.the_snapshot(gh, COMMIT)
    del gh.refs[rel["tag_name"]]
    with pytest.raises(RL.ReleaseError, match="does not point at the readiness commit"):
        RL.the_snapshot(gh, COMMIT)


def test_a_tag_ref_that_is_an_annotated_tag_object_is_not_a_tag_on_the_commit(out, tmp_path):
    gh = FakeGitHub()
    rel = gh.new_release(out)
    gh.ref_types[rel["tag_name"]] = "tag"   # its sha is a tag object's, not the commit's
    with pytest.raises(RL.ReleaseError, match="does not point at the readiness commit"):
        RL.the_snapshot(gh, COMMIT)
    with pytest.raises(RL.ReleaseError, match="points at None"):
        RL.publish(gh, rerun(tmp_path), COMMIT, RUN2)


def test_a_release_that_is_not_plainly_a_draft_is_never_cleared_as_one(out, tmp_path):
    gh = FakeGitHub()
    rel = gh.new_release(out, extra={"draft": None})
    n = len(gh.calls)
    with pytest.raises(RL.ReleaseError, match="draft"):
        RL.publish(gh, rerun(tmp_path), COMMIT, RUN2)
    assert rel["id"] in gh.releases and [c for c in gh.writes() if gh.calls.index(c) >= n] == []


def test_zero_or_two_published_snapshots_are_refused_and_drafts_are_invisible_to_readers(out, tmp_path):
    gh = FakeGitHub(write=False)
    with pytest.raises(RL.ReleaseError, match="0 published"):
        RL.the_snapshot(gh, COMMIT)
    gh.new_release(out, draft=True)
    with pytest.raises(RL.ReleaseError, match="0 published"):
        RL.the_snapshot(gh, COMMIT)
    gh.new_release(out)
    assert RL.the_snapshot(gh, COMMIT, address(out))["tag_name"] == RL.tag_for(address(out), COMMIT)
    with pytest.raises(RL.ReleaseError, match="not the snapshot"):
        RL.the_snapshot(gh, COMMIT, "sha256:" + "f" * 64)
    gh.new_release(snapshot_files(tmp_path, "two", salt="2"))  # an ambiguous second snapshot at the commit
    with pytest.raises(RL.ReleaseError, match="2 published"):
        RL.the_snapshot(gh, COMMIT)


def test_more_than_one_page_of_releases_is_read(out):
    gh = FakeGitHub(write=False)
    for i in range(150):
        gh.releases[i] = {"id": i, "tag_name": f"v{i}", "draft": False, "prerelease": False, "immutable": True,
                          "assets": []}
    gh.new_release(out)
    assert RL.the_snapshot(gh, COMMIT)["tag_name"] == RL.tag_for(address(out), COMMIT)
    assert sum(1 for c in gh.calls if c[1].startswith(f"/repos/{SLUG}/releases?")) == 2


# -- RT-3 ---------------------------------------------------------------------------------------------

def published(out: Path, **kw) -> FakeGitHub:
    gh = FakeGitHub(**kw)
    RL.publish(gh, out, COMMIT, RUN1)
    return gh


def test_a_publish_github_carried_out_but_reported_as_failed_is_judged_never_deleted(out):
    class LostResponse(FakeGitHub):
        def api(self, method, path, body=None):
            status, got = super().api(method, path, body)
            if method == "PATCH" and isinstance(body, dict) and body.get("draft") is False:
                return 502, "gh: Bad Gateway (HTTP 502)"  # published on GitHub's side; the answer was lost
            return status, got

    gh = LostResponse()
    rec = RL.publish(gh, out, COMMIT, RUN1)
    assert rec["result"] == RL.PUBLISHED and rec["immutable"] is True
    assert not any(c[0] == "DELETE" for c in gh.calls) and len(gh.releases) == 1


def test_an_upload_that_fails_without_an_http_refusal_is_not_counted_refused(out):
    gh = published(out)
    gh.upload = lambda tag, path: (1, "error connecting to uploads.github.com")
    rec = RL.probe_immutable(gh, out, COMMIT)
    assert rec["probes"]["attach_new_asset"]["refused"] is False and rec["result"] != "PASS"


def test_rt3_every_change_to_an_immutable_release_is_refused(out):
    gh = published(out)
    before = json.dumps(gh._view(next(iter(gh.releases.values()))), sort_keys=True)
    rec = RL.probe_immutable(gh, out, COMMIT)
    assert rec["result"] == "PASS" and rec["release_unchanged"] is True
    assert set(rec["probes"]) == {"attach_new_asset", "rename_asset", "delete_record_asset", "move_tag"}
    assert all(v["refused"] for v in rec["probes"].values())
    assert json.dumps(gh._view(next(iter(gh.releases.values()))), sort_keys=True) == before
    assert set(gh.refs.values()) == {COMMIT}
    assert not any(c[0] == "DELETE" and "/releases/" in c[1] and "/assets/" not in c[1] for c in gh.calls)


def test_rt3_a_release_github_wrongly_lets_change_fails_and_is_put_back(out):
    gh = published(out, enforce=False)  # reports immutable: true, yet allows changes
    rec = RL.probe_immutable(gh, out, COMMIT)
    assert rec["result"] == "FAIL"
    assert not any(v["refused"] for v in rec["probes"].values())
    (rel,) = gh.releases.values()
    assert sorted(a["name"] for a in rel["assets"]) == sorted(RL.ASSETS)  # probe asset gone, record back
    rec_asset = next(a for a in rel["assets"] if a["name"] == RL.RECORD)
    assert rec_asset["digest"] == _sha((out / RL.RECORD).read_bytes())
    assert gh.refs[rel["tag_name"]] == COMMIT
    assert rec["release_unchanged"] is False  # the record came back as a new asset


def test_rt3_probes_need_the_releases_own_record(out, tmp_path):
    gh = published(out)
    (out / RL.RECORD).write_text("{}\n")
    with pytest.raises(RL.ReleaseError, match="download the release first"):
        RL.probe_immutable(gh, out, COMMIT)


def test_rt3_a_read_only_token_cannot_write_anything(out):
    gh = published(out)
    gh.write = False
    rec = RL.probe_read_only(gh, "42", COMMIT)
    assert rec["result"] == "PASS"
    assert set(rec["probes"]) == {"create_blob", "create_tag", "create_draft_release", "edit_release_notes"}
    assert all(v["refused"] and v["status"] == 403 for v in rec["probes"].values())


def test_rt3_a_token_that_can_write_fails_and_its_writes_are_undone(out):
    gh = published(out)
    rel_before = json.dumps(gh._view(next(iter(gh.releases.values()))), sort_keys=True)
    rec = RL.probe_read_only(gh, "42", COMMIT)
    assert rec["result"] == "FAIL"
    assert rec["probes"]["create_tag"]["reverted"] is True
    assert rec["probes"]["create_draft_release"]["reverted"] is True
    assert len(gh.releases) == 1 and set(gh.refs) == {RL.tag_for(address(out), COMMIT)}
    assert json.dumps(gh._view(next(iter(gh.releases.values()))), sort_keys=True) == rel_before


# -- gh and the CLI -----------------------------------------------------------------------------------

def test_gh_reads_http_status_and_never_passes_the_billing_token(monkeypatch):
    monkeypatch.setenv("AUTH2_BILLING_TOKEN", "github_pat_secret")
    monkeypatch.setenv("GH_TOKEN", "workflow-token")
    g = RL.GH(SLUG)
    env = g._env()
    assert "AUTH2_BILLING_TOKEN" not in env and env["GH_TOKEN"] == "workflow-token"
    seen = []

    def fake(args):
        seen.append(args)
        return fake.ret

    monkeypatch.setattr(g, "run", fake)
    fake.ret = (1, "", "gh: Not Found (HTTP 404)\n")
    assert g.api("GET", "/x")[0] == 404
    fake.ret = (1, "", "gh: Validation Failed (HTTP 422)\n")
    assert g.api("PATCH", "/x", {"a": 1})[0] == 422
    fake.ret = (1, "", "connection reset")
    assert g.api("GET", "/x")[0] is None
    fake.ret = (0, '{"a": 1}', "")
    assert g.api("GET", "/x") == (200, {"a": 1})
    fake.ret = (0, "", "")
    assert g.api("DELETE", "/x") == (200, None)
    assert all("github_pat_secret" not in " ".join(a) for a in seen)
    assert RL._refused(404) and RL._refused(422) and not RL._refused(None) and not RL._refused(500) \
        and not RL._refused(200)


def test_the_cli_reports_pass_and_fail(out, tmp_path, monkeypatch, capsys):
    gh = FakeGitHub()
    monkeypatch.setattr(RL, "GH", lambda slug: gh)
    monkeypatch.setenv("GITHUB_RUN_ID", RUN1)
    rc = RL.main(["publish", "--repo-slug", SLUG, "--dir", str(out), "--commit", COMMIT,
                  "--out", str(tmp_path / "pub.json")])
    assert rc == 0 and "RELEASE_PUBLISH = PASS" in capsys.readouterr().out
    assert json.loads((tmp_path / "pub.json").read_text())["result"] == RL.PUBLISHED
    monkeypatch.setenv("GITHUB_RUN_ID", RUN2)
    rc = RL.main(["publish", "--repo-slug", SLUG, "--dir", str(rerun(tmp_path)), "--commit", COMMIT,
                  "--out", str(tmp_path / "again.json")])
    assert rc == 0 and "RELEASE_PUBLISH = PASS" in capsys.readouterr().out
    assert json.loads((tmp_path / "again.json").read_text())["result"] == RL.VERIFIED_EXISTING
    rc = RL.main(["verify", "--repo-slug", SLUG, "--commit", COMMIT, "--out", str(tmp_path / "v.json")])
    assert rc == 0 and "RELEASE_VERIFY = PASS" in capsys.readouterr().out
    rc = RL.main(["verify", "--repo-slug", SLUG, "--commit", NEW, "--out", str(tmp_path / "v3.json")])
    assert rc == 3 and "RELEASE_VERIFY = FAIL" in capsys.readouterr().out
    rc = RL.main(["publish", "--repo-slug", SLUG, "--dir", str(out), "--commit", "abc",
                  "--out", str(tmp_path / "bad.json")])
    text = capsys.readouterr().out
    assert rc == 3 and "::error::RELEASE_REFUSED" in text and "RELEASE_PUBLISH = FAIL" in text
    rc = RL.main(["verify", "--repo-slug", SLUG, "--commit", COMMIT, "--address", "sha256:" + "f" * 64,
                  "--out", str(tmp_path / "v2.json")])
    assert rc == 3 and "RELEASE_VERIFY = FAIL" in capsys.readouterr().out
    rc = RL.main(["probe-immutable", "--repo-slug", SLUG, "--commit", COMMIT, "--dir", str(out),
                  "--out", str(tmp_path / "p.json")])
    assert rc == 0 and "RELEASE_PROBE_IMMUTABLE = PASS" in capsys.readouterr().out
    gh.enforce = False
    rc = RL.main(["probe-immutable", "--repo-slug", SLUG, "--commit", COMMIT, "--dir", str(out),
                  "--out", str(tmp_path / "p2.json")])
    assert rc == 3 and "RELEASE_PROBE_IMMUTABLE = FAIL" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        RL.main(["verify", "--repo-slug", SLUG, "--out", str(tmp_path / "v4.json")])  # --commit is required
