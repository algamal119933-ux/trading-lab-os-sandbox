"""AUTH-2-DISCOVERY-QUALIFICATION-2 readiness (RT-1, RT-3, RT-4): the snapshot's immutable release
(research/auth2q2/release.py), against an in-memory GitHub.

The release is published draft-first and checked against the digests GitHub computes; a release that comes out
mutable is the repository setting being off, and only that job's own release and tag are removed. Readers take
the snapshot only from the one published, immutable, complete release and check every byte. The RT-3 probes
must find every write refused, and undo anything GitHub wrongly allowed.

PAPER / RESEARCH ONLY. Nothing here opens a connection.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from auth2 import archive as A
from auth2q2 import release as RL
from auth2q2 import snapshot as SN

SLUG = "owner/repo"
COMMIT = "a" * 40
PARENT = "b" * 40


# -- the snapshot files ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _outside_actions(monkeypatch):
    """The CLIs stamp GitHub Actions' run identity into their records; in CI those variables belong to the CI
    run, not to the fixtures, so every test here starts without them and sets what it needs."""
    for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "GITHUB_EVENT_PATH"):
        monkeypatch.delenv(k, raising=False)


def snapshot_files(tmp: Path, name: str = "out", salt: str = "") -> Path:
    """manifest.json, snapshot.tar and prepare-record.json as the preparation writes them."""
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
                                             "tar_sha256": tar_sha, "run_id": name, "commit": COMMIT},
                                            sort_keys=True) + "\n")
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
        self.blobs = 0
        self.commits = {COMMIT: [PARENT], PARENT: []}
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

    def new_release(self, out: Path, *, draft=False, immutable=True, extra: dict | None = None) -> dict:
        """A release put there directly, as if published earlier."""
        rec = json.loads((out / RL.RECORD).read_text())
        tag = RL.tag_for(rec["address"])
        rel = {"id": self._id(), "tag_name": tag, "draft": draft, "prerelease": False, "immutable": immutable,
               "target_commitish": COMMIT, "author": {"login": RL.BOT}, "body": "notes",
               "published_at": None if draft else "2026-10-13T00:00:00Z",
               "assets": [self._asset(n, (out / n).read_bytes()) for n in RL.ASSETS]}
        rel.update(extra or {})
        self.releases[rel["id"]] = rel
        if not draft:
            self.refs[tag] = COMMIT
        return rel

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
            return (200, {"object": {"sha": self.refs[tag]}}) if tag in self.refs else \
                (404, "gh: Not Found (HTTP 404)")
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


# -- tags ---------------------------------------------------------------------------------------------

def test_the_tag_is_the_snapshot_address_and_nothing_else():
    a = "sha256:" + "e" * 64
    assert RL.tag_for(a) == "auth2q2-snapshot-sha256-" + "e" * 64
    assert RL.address_of(RL.tag_for(a)) == a
    for bad in ("sha256:" + "E" * 64, "e" * 64, "sha256:" + "e" * 63, "", None):
        with pytest.raises(RL.ReleaseError):
            RL.tag_for(bad)
    for bad in ("auth2q2-snapshot-sha256-" + "e" * 63, "auth2q2-snapshot-sha256-" + "e" * 64 + "x",
                "v1.0", None, "x" + RL.tag_for(a)):
        assert RL.address_of(bad) is None


# -- publish (RT-1) -----------------------------------------------------------------------------------

def test_publish_goes_draft_first_and_ends_immutable_at_the_commit(out):
    gh = FakeGitHub()
    rec = RL.publish(gh, out, COMMIT)
    assert rec["result"] == "PUBLISHED" and rec["immutable"] is True and rec["draft"] is False
    assert rec["tag"] == RL.tag_for(address(out)) and rec["tag_commit"] == COMMIT
    assert gh.refs == {rec["tag"]: COMMIT}
    (rel,) = gh.releases.values()
    for a in rel["assets"]:
        assert a["digest"] == _sha((out / a["name"]).read_bytes())
    order = [c[0] for c in gh.calls]
    assert order.index("create_draft") < next(i for i, c in enumerate(gh.calls)
                                              if c[0] == "PATCH" and c[2] == {"draft": False, "make_latest": "false"})
    assert RL.the_snapshot(gh)["id"] == rel["id"]
    assert RL.publish(gh, out, COMMIT)["result"] == "ALREADY_PUBLISHED"
    assert len(gh.releases) == 1


def test_a_mutable_release_means_the_setting_is_off_and_only_this_jobs_release_and_tag_are_removed(out):
    gh = FakeGitHub(immutable_setting=False)
    other = snapshot_files(out.parent, "other", salt="other")
    keep = gh.new_release(other, immutable=False, extra={"tag_name": "v-unrelated"})
    with pytest.raises(RL.ReleaseError, match="IMMUTABLE_RELEASES_NOT_ENABLED"):
        RL.publish(gh, out, COMMIT)
    assert list(gh.releases) == [keep["id"]] and RL.tag_for(address(out)) not in gh.refs
    gh.immutable_setting = True
    assert RL.publish(gh, out, COMMIT)["result"] == "PUBLISHED"  # the tag was left usable


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
        RL.publish(gh, out, COMMIT)
    assert gh.releases == {} and gh.refs == {}


def test_without_github_digests_nothing_is_published(out):
    gh = FakeGitHub(digests=False)
    with pytest.raises(RL.ReleaseError, match="no sha256 digest"):
        RL.publish(gh, out, COMMIT)
    assert gh.releases == {} and gh.refs == {}


def test_a_draft_written_by_anyone_but_the_workflow_bot_is_deleted(out):
    gh = FakeGitHub(author="someone")
    with pytest.raises(RL.ReleaseError, match="author"):
        RL.publish(gh, out, COMMIT)
    assert gh.releases == {}


def test_a_tag_that_already_exists_stops_publication_before_any_draft(out):
    gh = FakeGitHub()
    gh.refs[RL.tag_for(address(out))] = PARENT
    with pytest.raises(RL.ReleaseError, match="already exists"):
        RL.publish(gh, out, COMMIT)
    assert gh.releases == {} and not any(c[0] == "create_draft" for c in gh.calls)


def test_a_published_release_whose_tag_moved_is_refused(out):
    gh = FakeGitHub()
    gh.publish_hook = lambda r: gh.refs.__setitem__(r["tag_name"], PARENT)
    with pytest.raises(RL.ReleaseError, match="not the publishing commit"):
        RL.publish(gh, out, COMMIT)


def test_an_existing_release_for_the_tag_is_never_overwritten(out, tmp_path):
    gh = FakeGitHub()
    gh.new_release(out, draft=True)
    with pytest.raises(RL.ReleaseError, match="already exist"):
        RL.publish(gh, out, COMMIT)
    assert len(gh.releases) == 1
    gh2 = FakeGitHub()
    RL.publish(gh2, out, COMMIT)
    (out / RL.RECORD).write_text((out / RL.RECORD).read_text().replace('"run_id": "out"', '"run_id": "again"'))
    with pytest.raises(RL.ReleaseError, match=f"another {RL.RECORD}"):
        RL.publish(gh2, out, COMMIT)
    assert len(gh2.releases) == 1


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
        RL.publish(gh, out, COMMIT)
    assert gh.calls == []


def test_only_this_commits_and_this_runs_preparation_is_published(out):
    with pytest.raises(RL.ReleaseError, match="made at"):
        RL.publish(FakeGitHub(), out, PARENT)
    with pytest.raises(RL.ReleaseError, match="run out's, not run 7's"):
        RL.publish(FakeGitHub(), out, COMMIT, "7")
    assert RL.publish(FakeGitHub(), out, COMMIT, "out")["result"] == "PUBLISHED"


def test_a_symlinked_snapshot_file_is_refused(out, tmp_path):
    real = tmp_path / "elsewhere.tar"
    shutil.move(out / RL.TAR, real)
    (out / RL.TAR).symlink_to(real)
    with pytest.raises(RL.ReleaseError, match="missing"):
        RL.local_files(out)


# -- readers (RT-4) -----------------------------------------------------------------------------------

def test_download_checks_every_byte_against_githubs_digests(out, tmp_path):
    gh = FakeGitHub()
    RL.publish(gh, out, COMMIT)
    got = RL.download(gh, tmp_path / "dl", address(out))
    assert got["address"] == address(out)
    for n in RL.ASSETS:
        assert (tmp_path / "dl" / n).read_bytes() == (out / n).read_bytes()
    gh.fail.add("tamper_download")
    with pytest.raises(RL.ReleaseError, match="snapshot.tar: downloaded bytes"):
        RL.download(gh, tmp_path / "dl2")
    with pytest.raises(RL.ReleaseError, match="not empty"):
        RL.download(gh, tmp_path / "dl")
    gh.fail = {"download_rc"}
    with pytest.raises(RL.ReleaseError, match="downloading"):
        RL.download(gh, tmp_path / "dl3")


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
])
def test_the_snapshot_is_only_ever_read_from_one_published_immutable_complete_release(out, edit, match):
    gh = FakeGitHub()
    rel = gh.new_release(out)
    edit(rel)
    with pytest.raises(RL.ReleaseError, match=match):
        RL.the_snapshot(gh)


def test_zero_or_two_published_snapshots_are_refused_and_drafts_are_invisible_to_readers(out, tmp_path):
    gh = FakeGitHub(write=False)
    with pytest.raises(RL.ReleaseError, match="0 published"):
        RL.the_snapshot(gh)
    gh.new_release(out, draft=True)
    with pytest.raises(RL.ReleaseError, match="0 published"):
        RL.the_snapshot(gh)
    gh.new_release(out)
    assert RL.the_snapshot(gh, address(out))["tag_name"] == RL.tag_for(address(out))
    with pytest.raises(RL.ReleaseError, match="0 published"):
        RL.the_snapshot(gh, "sha256:" + "f" * 64)
    gh.new_release(snapshot_files(tmp_path, "two", salt="2"))
    with pytest.raises(RL.ReleaseError, match="2 published"):
        RL.the_snapshot(gh)


def test_more_than_one_page_of_releases_is_read(out):
    gh = FakeGitHub(write=False)
    for i in range(150):
        gh.releases[i] = {"id": i, "tag_name": f"v{i}", "draft": False, "prerelease": False, "immutable": True,
                          "assets": []}
    gh.new_release(out)
    assert RL.the_snapshot(gh)["tag_name"] == RL.tag_for(address(out))
    assert sum(1 for c in gh.calls if c[1].startswith(f"/repos/{SLUG}/releases?")) == 2


# -- RT-3 ---------------------------------------------------------------------------------------------

def published(out: Path, **kw) -> FakeGitHub:
    gh = FakeGitHub(**kw)
    RL.publish(gh, out, COMMIT)
    return gh


def test_a_publish_github_carried_out_but_reported_as_failed_is_judged_never_deleted(out):
    class LostResponse(FakeGitHub):
        def api(self, method, path, body=None):
            status, got = super().api(method, path, body)
            if method == "PATCH" and isinstance(body, dict) and body.get("draft") is False:
                return 502, "gh: Bad Gateway (HTTP 502)"  # published on GitHub's side; the answer was lost
            return status, got

    gh = LostResponse()
    rec = RL.publish(gh, out, COMMIT)
    assert rec["result"] == "PUBLISHED" and rec["immutable"] is True
    assert not any(c[0] == "DELETE" for c in gh.calls) and len(gh.releases) == 1


def test_an_upload_that_fails_without_an_http_refusal_is_not_counted_refused(out):
    gh = published(out)
    gh.upload = lambda tag, path: (1, "error connecting to uploads.github.com")
    rec = RL.probe_immutable(gh, out)
    assert rec["probes"]["attach_new_asset"]["refused"] is False and rec["result"] != "PASS"


def test_rt3_every_change_to_an_immutable_release_is_refused(out):
    gh = published(out)
    before = json.dumps(gh._view(next(iter(gh.releases.values()))), sort_keys=True)
    rec = RL.probe_immutable(gh, out)
    assert rec["result"] == "PASS" and rec["release_unchanged"] is True
    assert set(rec["probes"]) == {"attach_new_asset", "rename_asset", "delete_record_asset", "move_tag"}
    assert all(v["refused"] for v in rec["probes"].values())
    assert json.dumps(gh._view(next(iter(gh.releases.values()))), sort_keys=True) == before
    assert set(gh.refs.values()) == {COMMIT}
    assert not any(c[0] == "DELETE" and "/releases/" in c[1] and "/assets/" not in c[1] for c in gh.calls)


def test_rt3_a_release_github_wrongly_lets_change_fails_and_is_put_back(out):
    gh = published(out, enforce=False)  # reports immutable: true, yet allows changes
    rec = RL.probe_immutable(gh, out)
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
        RL.probe_immutable(gh, out)


def test_rt3_a_read_only_token_cannot_write_anything(out):
    gh = published(out)
    gh.write = False
    rec = RL.probe_read_only(gh, "42")
    assert rec["result"] == "PASS"
    assert set(rec["probes"]) == {"create_blob", "create_tag", "create_draft_release", "edit_release_notes"}
    assert all(v["refused"] and v["status"] == 403 for v in rec["probes"].values())


def test_rt3_a_token_that_can_write_fails_and_its_writes_are_undone(out):
    gh = published(out)
    rel_before = json.dumps(gh._view(next(iter(gh.releases.values()))), sort_keys=True)
    rec = RL.probe_read_only(gh, "42")
    assert rec["result"] == "FAIL"
    assert rec["probes"]["create_tag"]["reverted"] is True
    assert rec["probes"]["create_draft_release"]["reverted"] is True
    assert len(gh.releases) == 1 and set(gh.refs) == {RL.tag_for(address(out))}
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
    rc = RL.main(["publish", "--repo-slug", SLUG, "--dir", str(out), "--commit", COMMIT,
                  "--out", str(tmp_path / "pub.json")])
    assert rc == 0 and "RELEASE_PUBLISH = PASS" in capsys.readouterr().out
    assert json.loads((tmp_path / "pub.json").read_text())["result"] == "PUBLISHED"
    rc = RL.main(["verify", "--repo-slug", SLUG, "--out", str(tmp_path / "v.json")])
    assert rc == 0 and "RELEASE_VERIFY = PASS" in capsys.readouterr().out
    rc = RL.main(["publish", "--repo-slug", SLUG, "--dir", str(out), "--commit", "abc",
                  "--out", str(tmp_path / "bad.json")])
    text = capsys.readouterr().out
    assert rc == 3 and "::error::RELEASE_REFUSED" in text and "RELEASE_PUBLISH = FAIL" in text
    rc = RL.main(["verify", "--repo-slug", SLUG, "--address", "sha256:" + "f" * 64,
                  "--out", str(tmp_path / "v2.json")])
    assert rc == 3 and "RELEASE_VERIFY = FAIL" in capsys.readouterr().out
    rc = RL.main(["probe-immutable", "--repo-slug", SLUG, "--dir", str(out), "--out", str(tmp_path / "p.json")])
    assert rc == 0 and "RELEASE_PROBE_IMMUTABLE = PASS" in capsys.readouterr().out
    gh.enforce = False
    rc = RL.main(["probe-immutable", "--repo-slug", SLUG, "--dir", str(out), "--out", str(tmp_path / "p2.json")])
    assert rc == 3 and "RELEASE_PROBE_IMMUTABLE = FAIL" in capsys.readouterr().out
