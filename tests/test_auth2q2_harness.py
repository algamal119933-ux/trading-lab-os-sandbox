"""AUTH-2-DISCOVERY-QUALIFICATION-2 readiness jobs (research/auth2q2/harness.py): restore with the cache as an
accelerator and the release as the authority, the check before science, the offline science paths, the RT-6
corruptions, the RT-6/RT-7/RT-10 classifiers and the verdicts, against the in-memory GitHub of
test_auth2q2_release.py and the Actions jobs API's own record shapes.

PAPER / RESEARCH ONLY. Nothing here opens a connection: the network probe is stubbed, and the science stubs make
their requests through the archive's own opener, which the replay answers or refuses.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from auth2 import archive as A
from auth2 import dataset_v3 as D
from auth2 import market_io as MI
from auth2 import run_node as RN
from auth2q2 import attempts as AT
from auth2q2 import harness as H
from auth2q2 import listing as L
from auth2q2 import offline as OFF
from auth2q2 import release as RL
from auth2q2 import snapshot as SN
from test_auth2q2_release import COMMIT, NEW, RUN1, RUN2, FakeGitHub, snapshot_files

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _outside_actions(monkeypatch):
    """The CLIs stamp GitHub Actions' run identity into their records; in CI those variables belong to the CI
    run, not to the fixtures, so every test here starts without them and sets what it needs."""
    for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "GITHUB_EVENT_PATH"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture()
def snap(tmp_path):
    """A published snapshot: its local files and the GitHub that holds its release."""
    out = snapshot_files(tmp_path)
    gh = FakeGitHub()
    RL.publish(gh, out, COMMIT, RUN1)
    address = json.loads((out / RL.RECORD).read_text())["address"]
    return out, gh, address


@pytest.fixture()
def offline(monkeypatch):
    monkeypatch.setattr(OFF, "probe", lambda timeout=3.0: {"network_removed": True, "reached": [], "dns": {},
                                                           "tcp": {}})


def cache_of(out: Path, where: Path) -> Path:
    where.mkdir(parents=True)
    for n in RL.ASSETS:
        shutil.copyfile(out / n, where / n)
    return where


# -- restore --------------------------------------------------------------------------------------------

def test_a_whole_cache_restores_without_the_release(snap, tmp_path):
    out, gh, address = snap
    calls = len(gh.calls)
    rec = H.restore(address, tmp_path / "data", tmp_path / "rel", commit=COMMIT, cache_dir=cache_of(out, tmp_path / "c"), gh=gh,
                    manifest_out=tmp_path / "m.json")
    assert rec["source"] == H.CACHE and rec["fallback_reason"] is None and len(gh.calls) == calls
    assert rec["files"] == 7 and rec["tree_digest"] == SN.tree_digest(tmp_path / "data")
    assert (tmp_path / "m.json").read_bytes() == (out / RL.MANIFEST).read_bytes()
    assert SN.verify_tree(tmp_path / "data", SN.load_manifest((out / RL.MANIFEST).read_bytes(), address)) == []


def test_a_missing_cache_falls_back_to_the_release_and_can_refill_it(snap, tmp_path):
    out, gh, address = snap
    rec = H.restore(address, tmp_path / "data", tmp_path / "rel", commit=COMMIT, cache_dir=tmp_path / "c", gh=gh,
                    refill_cache=True, expect_source=H.RELEASE)
    assert rec["source"] == H.RELEASE and rec["fallback_reason"].startswith(H.CACHE_MISS)
    assert rec["release"]["immutable"] is True and set(rec["asset_digests"]) == set(RL.ASSETS)
    for n in RL.ASSETS:
        assert (tmp_path / "c" / n).read_bytes() == (out / n).read_bytes()
    warm = H.restore(address, tmp_path / "data2", tmp_path / "rel2", commit=COMMIT, cache_dir=tmp_path / "c", gh=gh,
                     expect_source=H.CACHE)
    assert warm["tree_digest"] == rec["tree_digest"]


@pytest.mark.parametrize("damage", [
    lambda c: (c / RL.TAR).write_bytes((c / RL.TAR).read_bytes()[:-2048] + b"\1" * 2048),
    lambda c: (c / RL.MANIFEST).write_bytes((c / RL.MANIFEST).read_bytes().replace(b'"files"', b'"filez"')),
    lambda c: (c / RL.TAR).unlink(),
    lambda c: (c / RL.TAR).write_bytes(b""),
])
def test_a_broken_cache_is_discarded_for_the_release_and_nothing_of_it_survives(snap, tmp_path, damage):
    out, gh, address = snap
    c = cache_of(out, tmp_path / "c")
    damage(c)
    rec = H.restore(address, tmp_path / "data", tmp_path / "rel", commit=COMMIT, cache_dir=c, gh=gh)
    assert rec["source"] == H.RELEASE and rec["fallback_reason"].startswith(H.CACHE_INVALID)
    assert SN.verify_tree(tmp_path / "data", SN.load_manifest((out / RL.MANIFEST).read_bytes(), address)) == []


def test_a_cache_holding_another_snapshot_is_not_this_one(snap, tmp_path):
    out, gh, address = snap
    other = snapshot_files(tmp_path, "other", salt="x")
    rec = H.restore(address, tmp_path / "data", tmp_path / "rel", commit=COMMIT, cache_dir=cache_of(other, tmp_path / "c"), gh=gh)
    assert rec["source"] == H.RELEASE and "not the snapshot address" in rec["fallback_reason"]


def test_an_asset_changed_after_download_stops_the_restore_and_is_named(snap, tmp_path):
    out, gh, address = snap
    RL.download(gh, tmp_path / "rel", COMMIT, address)
    t = H.tamper(tmp_path / "rel")
    assert t["sha256_before"] != t["sha256_after"]
    with pytest.raises(RL.ReleaseError, match="snapshot.tar: sha256 .* is not the release's digest"):
        H.restore(address, tmp_path / "data", tmp_path / "rel", commit=COMMIT, gh=gh)
    assert not (tmp_path / "data").exists() or not any((tmp_path / "data").iterdir())


def test_restore_refuses_what_it_cannot_prove(snap, tmp_path):
    out, gh, address = snap
    with pytest.raises(H.HarnessError, match="no release"):
        H.restore(address, tmp_path / "d1", tmp_path / "r1", commit=COMMIT, cache_dir=tmp_path / "none")
    with pytest.raises(H.HarnessError, match="not the cache"):
        H.restore(address, tmp_path / "d2", tmp_path / "r2", commit=COMMIT, cache_dir=tmp_path / "none", gh=gh,
                  expect_source=H.CACHE)
    with pytest.raises(RL.ReleaseError):
        H.restore("sha256:" + "0" * 64, tmp_path / "d3", tmp_path / "r3", commit=COMMIT, gh=gh)
    with pytest.raises(RL.ReleaseError):
        H.restore("not-an-address", tmp_path / "d4", tmp_path / "r4", commit=COMMIT, gh=gh)
    (tmp_path / "d5").mkdir()
    (tmp_path / "d5" / "stray").write_text("x")
    with pytest.raises(SN.SnapshotError, match="not a new or empty"):
        H.restore(address, tmp_path / "d5", tmp_path / "r5", commit=COMMIT, gh=gh)


def test_restore_never_clears_a_destination_that_held_files_whatever_the_cache_holds(snap, tmp_path):
    out, gh, address = snap
    dest = tmp_path / "work"
    dest.mkdir()
    (dest / "keep.txt").write_text("not the snapshot's")
    for cache in (cache_of(out, tmp_path / "good"), tmp_path / "missing"):
        with pytest.raises(SN.SnapshotError, match="not a new or empty directory"):
            H.restore(address, dest, tmp_path / f"rel-{cache.name}", commit=COMMIT, cache_dir=cache, gh=gh)
        assert (dest / "keep.txt").read_text() == "not the snapshot's"


def test_a_cache_directory_overlapping_the_tree_or_the_assets_is_refused(snap, tmp_path):
    out, gh, address = snap
    with pytest.raises(H.HarnessError, match="overlaps"):
        H.restore(address, tmp_path / "d1", tmp_path / "r1", commit=COMMIT, cache_dir=tmp_path, gh=gh)
    with pytest.raises(H.HarnessError, match="overlaps"):
        H.restore(address, tmp_path / "d2", tmp_path / "r2", commit=COMMIT, cache_dir=tmp_path / "r2", gh=gh, refill_cache=True)
    assert not (tmp_path / "r2").exists() or all(p.name in RL.ASSETS for p in (tmp_path / "r2").iterdir())


def test_restore_verifies_the_unpacked_tree_itself_not_only_the_unpacker(snap, tmp_path, monkeypatch):
    out, gh, address = snap
    unpack = H._from_dir

    def unpack_then_damage(d, addr, dest):
        got = unpack(d, addr, dest)
        victim = sorted(p for p in dest.rglob("*") if p.is_file())[0]
        victim.write_bytes(victim.read_bytes() + b"x")  # a fault after the strict unpack, before use
        return got

    monkeypatch.setattr(H, "_from_dir", unpack_then_damage)
    with pytest.raises(SN.SnapshotError, match="1 restored file\\(s\\) differ from the manifest; first: "):
        H.restore(address, tmp_path / "data", tmp_path / "rel", commit=COMMIT, gh=gh)


# -- the check before science (RT-6) ---------------------------------------------------------------------

def test_a_corrupted_restored_file_is_caught_and_named_before_science(snap, tmp_path, capsys):
    out, gh, address = snap
    H.restore(address, tmp_path / "data", tmp_path / "rel", commit=COMMIT, gh=gh, manifest_out=tmp_path / "m.json")
    assert H.verify(address, tmp_path / "m.json", tmp_path / "data")["problem_count"] == 0
    c = H.corrupt(address, tmp_path / "m.json", tmp_path / "data")
    assert SN.data_kind(c["file"]) == "kline" and c["now_sha256"] != c["manifest_sha256"]
    rc = H.main(["verify", "--address", address, "--manifest", str(tmp_path / "m.json"), "--dest",
                 str(tmp_path / "data"), "--out", str(tmp_path / "v.json")])
    text = capsys.readouterr().out
    assert rc == 3 and f"::error::SNAPSHOT_VERIFY: {c['file']}: sha256" in text
    assert json.loads((tmp_path / "v.json").read_text())["problem_count"] == 1


def test_the_restore_cli_names_the_tampered_asset(snap, tmp_path, capsys, monkeypatch):
    out, gh, address = snap
    monkeypatch.setattr(H.RL, "GH", lambda slug: gh)
    RL.download(gh, tmp_path / "rel", COMMIT, address)
    H.tamper(tmp_path / "rel")
    rc = H.main(["restore", "--address", address, "--commit", COMMIT, "--dest", str(tmp_path / "data"), "--assets-dir",
                 str(tmp_path / "rel"), "--repo-slug", gh.slug, "--out", str(tmp_path / "r.json")])
    text = capsys.readouterr().out
    assert rc == 3 and "::error::RESTORE_REFUSED: snapshot.tar: sha256" in text
    shutil.rmtree(tmp_path / "rel")
    rc = H.main(["restore", "--address", address, "--commit", COMMIT, "--dest", str(tmp_path / "data2"),
                 "--assets-dir", str(tmp_path / "rel"), "--cache-dir", str(tmp_path / "c"), "--repo-slug", gh.slug,
                 "--out", str(tmp_path / "r.json")])
    assert rc == 0 and "from the release; CACHE_MISS" in capsys.readouterr().out
    rc = H.main(["restore", "--address", address, "--commit", NEW, "--dest", str(tmp_path / "data3"),
                 "--assets-dir", str(tmp_path / "rel3"), "--repo-slug", gh.slug, "--out", str(tmp_path / "r3.json")])
    assert rc == 3 and "0 published snapshot release(s) for the readiness commit" in capsys.readouterr().out


def test_a_restore_at_another_commit_never_reads_this_commits_release(snap, tmp_path):
    """Stale-release rejection: the release of an earlier readiness commit never feeds a later one's restore,
    though its content (the address) is the same."""
    out, gh, address = snap
    with pytest.raises(RL.ReleaseError, match=f"0 published snapshot release\\(s\\) for the readiness commit {NEW}"):
        H.restore(address, tmp_path / "d", tmp_path / "r", commit=NEW, gh=gh)
    with pytest.raises(RL.ReleaseError, match="not a full commit sha"):
        H.restore(address, tmp_path / "d2", tmp_path / "r2", commit="main", gh=gh)
    rec = H.restore(address, tmp_path / "d3", tmp_path / "r3", commit=COMMIT, gh=gh)
    assert rec["commit"] == COMMIT and rec["release"]["commit"] == COMMIT
    # assets already downloaded (from this commit's release) are still judged against the named commit's release
    with pytest.raises(RL.ReleaseError, match=f"for the readiness commit {NEW}"):
        H.restore(address, tmp_path / "d4", tmp_path / "r3", commit=NEW, gh=gh)


# -- science, offline ------------------------------------------------------------------------------------

def tiny_repo(tmp_path: Path, files: dict[str, bytes]) -> Path:
    repo = tmp_path / "repo"
    for rel, body in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_bytes(body)
    return repo


LISTING = {"schema": L.LISTING_SCHEMA, "list_base": A.LIST_BASE, "last_month": D.LAST_MONTH,
           "delimited": {D.SPOT_PREFIX: [f"{D.SPOT_PREFIX}AAAUSDT/"]},
           "keys": {f"{D.SPOT_PREFIX}AAAUSDT/1h/": [f"{D.SPOT_PREFIX}AAAUSDT/1h/AAAUSDT-1h-2020-01.zip"],
                    f"{D.FUNDING_PREFIX}BTCUSDT/": [], f"{D.FUNDING_PREFIX}ETHUSDT/": []}}


def cache_with_listing(tmp_path: Path) -> Path:
    c = tmp_path / "cache"
    (c / SN.LISTING_REL).parent.mkdir(parents=True, exist_ok=True)
    (c / SN.LISTING_REL).write_bytes(L.dumps(LISTING))
    return c


def build_stub(files: dict[str, bytes], extra=None):
    def build(cache_dir, base, out_root):
        found = D.discover(base)  # through the replayed listing
        assert found[0] == ["AAAUSDT"]
        if extra:
            extra()
        return dict(files)
    return build


def test_d0_passes_only_offline_byte_identical_and_without_a_request(tmp_path, monkeypatch, offline):
    files = {D.LOCK_REL: b'{"lock": 1}\n', f"{D.TABLE_DIR_REL}/a.json": b"[]\n"}
    repo = tiny_repo(tmp_path, files)
    cache = cache_with_listing(tmp_path)
    monkeypatch.setattr(D, "build", build_stub(files))
    rec = H.science_d0(repo, cache)
    assert all(rec["checks"].values()) and rec["files_compared"] == 2 and rec["listing_pages_served"] >= 2
    monkeypatch.setattr(D, "build", build_stub({**files, D.LOCK_REL: b'{"lock": 2}\n'}))
    rec = H.science_d0(repo, cache)
    assert rec["checks"]["lock_byte_identical"] is False and rec["not_identical"] == [D.LOCK_REL]


def test_d0_records_and_fails_on_any_request_the_snapshot_cannot_answer(tmp_path, monkeypatch, offline):
    files = {D.LOCK_REL: b"{}\n"}
    repo = tiny_repo(tmp_path, files)
    cache = cache_with_listing(tmp_path)
    monkeypatch.setattr(D, "build", build_stub(files, lambda: A._get(f"{A.DEFAULT_BASE}/data/x.zip")))
    rec = H.science_d0(repo, cache)
    assert rec["checks"]["no_refused_request"] is False and rec["checks"]["rebuilt"] is False
    assert "ReplayRefused" in rec["error"] and rec["refused"] == [f"{A.DEFAULT_BASE}/data/x.zip"]
    import socket

    monkeypatch.setattr(D, "build", build_stub(files, lambda: socket.create_connection(("1.1.1.1", 443))))
    rec = H.science_d0(repo, cache)
    assert rec["checks"]["no_socket_call"] is False and "NetworkRemoved" in rec["error"]


def test_science_refuses_to_start_with_the_network_present(tmp_path, monkeypatch):
    monkeypatch.setattr(OFF, "probe", lambda timeout=3.0: {"network_removed": False, "reached": ["1.1.1.1:443"]})
    with pytest.raises(H.HarnessError, match="network is not removed"):
        H.science_d0(tiny_repo(tmp_path, {}), cache_with_listing(tmp_path))
    with pytest.raises(H.HarnessError, match="network is not removed"):
        H.science_engine(REPO, cache_with_listing(tmp_path), tmp_path / "w")


def engine_stub(symbols: list[str], *, drop: int = 0, status: str = "PASS", raise_exit: bool = False,
                funding: tuple = D.A3_ASSETS, extra=None):
    def real_market(fam, repo, cache, work):
        D.discover(A.DEFAULT_BASE)
        if raise_exit:
            raise SystemExit("DATA_TRUTH FAIL: AAAUSDT 4h content differs from the lock")
        if extra:
            extra()
        out = work / "engine_data"
        out.mkdir(parents=True, exist_ok=True)
        for s in funding:
            (out / f"{s}-funding.csv").write_text("calc_time,last_funding_rate\n")
        written = {s: "0" * 64 for s in symbols[drop:]}
        return None, None, None, {"status": status, "symbols": len(written), "content_sha256_4h": written,
                                  "lock_sha256": "c" * 64}
    return real_market


def test_engine_checks_every_a2_symbol_and_both_funding_series(tmp_path, monkeypatch, offline):
    want = MI.family_symbols("A2", MI.tables(REPO))
    assert len(want) == 86  # the lock's engine symbols: A2's universe is the largest family's
    cache = cache_with_listing(tmp_path)
    monkeypatch.setattr(RN, "real_market", engine_stub(want))
    rec = H.science_engine(REPO, cache, tmp_path / "w")
    assert all(rec["checks"].values()) and rec["symbols_checked"] == 86
    monkeypatch.setattr(RN, "real_market", engine_stub(want, drop=1))
    assert H.science_engine(REPO, cache, tmp_path / "w2")["checks"]["every_family_symbol_checked"] is False
    monkeypatch.setattr(RN, "real_market", engine_stub(want, status="FAIL"))
    assert H.science_engine(REPO, cache, tmp_path / "w3")["checks"]["data_truth_pass"] is False
    monkeypatch.setattr(RN, "real_market", engine_stub(want, raise_exit=True))
    rec = H.science_engine(REPO, cache, tmp_path / "w4")
    assert rec["checks"]["data_truth_pass"] is False and "DATA_TRUTH FAIL" in rec["error"]
    monkeypatch.setattr(RN, "real_market", engine_stub(want, funding=D.A3_ASSETS[:1]))
    rec = H.science_engine(REPO, cache, tmp_path / "w5")
    assert [k for k, v in rec["checks"].items() if v is not True] == ["funding_checked"]


def test_engine_fails_on_any_request_the_snapshot_cannot_answer_or_any_socket(tmp_path, monkeypatch, offline):
    import socket

    want = MI.family_symbols("A2", MI.tables(REPO))
    cache = cache_with_listing(tmp_path)
    monkeypatch.setattr(RN, "real_market", engine_stub(want, extra=lambda: A._get(f"{A.DEFAULT_BASE}/data/y.zip")))
    rec = H.science_engine(REPO, cache, tmp_path / "w")
    assert rec["checks"]["no_refused_request"] is False and rec["refused"] == [f"{A.DEFAULT_BASE}/data/y.zip"]
    assert rec["checks"]["no_socket_call"] is True and "ReplayRefused" in rec["error"]
    monkeypatch.setattr(RN, "real_market", engine_stub(want, extra=lambda: socket.create_connection(("1.1.1.1", 443))))
    rec = H.science_engine(REPO, cache, tmp_path / "w2")
    assert rec["checks"]["no_socket_call"] is False and rec["checks"]["no_refused_request"] is True
    assert "NetworkRemoved" in rec["error"] and rec["sockets"]


# -- classifiers ---------------------------------------------------------------------------------------

def step(n: int, name: str, conclusion: str = "success", t: str = "2026-10-20T10:00:00Z") -> dict:
    return {"number": n, "name": name, "status": "completed", "conclusion": conclusion, "started_at": t,
            "completed_at": t}


def probe_job(name: str, fail_at: str | None, *, jid: int = 1, conclusion: str = "failure") -> dict:
    names = ["Set up job", "Run actions/checkout@v4", H.RESTORE_STEP, H.VERIFY_STEP, AT.SCIENCE_STEP, "Complete job"]
    if name.startswith("RT-7"):
        names = ["Set up job", "Run actions/checkout@v4", H.INFRA_STEP, AT.SCIENCE_STEP, "Complete job"]
    steps, ended = [], False
    for i, s in enumerate(names, 1):
        if s == "Complete job":
            steps.append(step(i, s))
        elif ended:
            steps.append(step(i, s, "skipped"))
        elif s == fail_at:
            steps.append(step(i, s, "failure"))
            ended = True
        else:
            steps.append(step(i, s))
    return {"id": jid, "name": name, "status": "completed", "conclusion": conclusion if fail_at else "success",
            "started_at": "2026-10-20T10:00:00Z", "completed_at": "2026-10-20T10:01:00Z", "steps": steps,
            "run_attempt": 1}


def rt6_jobs(corrupt_at=H.VERIFY_STEP, digest_at=H.RESTORE_STEP):
    return [probe_job("RT-6 corrupted restored file", corrupt_at, jid=1),
            probe_job("RT-6 asset with the wrong digest", digest_at, jid=2)]


FILE = "data/spot/monthly/klines/AAAUSDT/1h/AAAUSDT-1h-2020-01.zip"
NOTES = {"RT-6 corrupted restored file": [f"SNAPSHOT_VERIFY: {FILE}: sha256 1 is not the manifest's 2"],
         "RT-6 asset with the wrong digest": ["RESTORE_REFUSED: snapshot.tar: sha256 x is not the release's digest"]}


def test_rt6_both_corruptions_stop_before_science_as_infra_and_name_the_file():
    checks, seen = H.classify_rt6(rt6_jobs(), NOTES, {"file": FILE})
    assert all(checks.values()) and seen["corrupt"]["class"] == AT.INFRA and seen["digest"]["class"] == AT.INFRA


@pytest.mark.parametrize("jobs, notes, expect, failed", [
    (rt6_jobs(corrupt_at=AT.SCIENCE_STEP), NOTES, {"file": FILE}, "corrupt_is_infra"),
    (rt6_jobs(corrupt_at=H.RESTORE_STEP), NOTES, {"file": FILE}, "corrupt_stopped_at_verify"),
    (rt6_jobs(digest_at=H.VERIFY_STEP), NOTES, {"file": FILE}, "digest_stopped_at_restore"),
    (rt6_jobs(digest_at=None), NOTES, {"file": FILE}, "digest_stopped_at_restore"),
    (rt6_jobs(), {**NOTES, "RT-6 corrupted restored file": ["Process completed with exit code 3."]}, {"file": FILE},
     "corrupt_names_the_file"),
    (rt6_jobs(), NOTES, {}, "corrupt_names_the_file"),
    (rt6_jobs()[:1], NOTES, {"file": FILE}, "digest_is_infra"),
    (rt6_jobs() + rt6_jobs()[1:], NOTES, {"file": FILE}, "digest_is_infra"),
])
def test_rt6_fails_on_any_other_outcome(jobs, notes, expect, failed):
    checks, _ = H.classify_rt6(jobs, notes, expect)
    assert checks[failed] is False


def test_rt7_tells_an_infra_failure_from_a_science_failure():
    jobs = [probe_job("RT-7 probe infra", H.INFRA_STEP, jid=1), probe_job("RT-7 probe science", AT.SCIENCE_STEP, jid=2)]
    checks, seen = H.classify_rt7(jobs)
    assert all(checks.values()) and (seen["infra"]["class"], seen["science"]["class"]) == (AT.INFRA, AT.SCIENCE)
    swapped = [probe_job("RT-7 probe infra", AT.SCIENCE_STEP, jid=1), probe_job("RT-7 probe science", H.INFRA_STEP)]
    checks, _ = H.classify_rt7(swapped)
    assert not any(checks.values())
    passed = [probe_job("RT-7 probe infra", None, jid=1), probe_job("RT-7 probe science", None, jid=2)]
    checks, _ = H.classify_rt7(passed)
    assert checks["probe_infra_classified_INFRA"] is False and checks["probe_science_classified_SCIENCE"] is True
    assert checks["probe_science_failed_in_science"] is False


def rt10_job(seconds: int, conclusion: str = "cancelled") -> dict:
    return {"id": 3, "name": "RT-10 probe", "status": "completed", "conclusion": conclusion,
            "started_at": "2026-10-20T10:00:00Z",
            "completed_at": f"2026-10-20T10:{seconds // 60:02d}:{seconds % 60:02d}Z", "steps": [], "run_attempt": 1}


@pytest.mark.parametrize("seconds, conclusion, ok", [
    (125, "cancelled", True), (179, "cancelled", True), (180, "cancelled", False),
    (181, "cancelled", False), (120, "cancelled", False), (100, "cancelled", False), (125, "success", False),
    (125, "failure", False),
])
def test_rt10_a_job_at_its_two_minute_timeout_bills_three(seconds, conclusion, ok):
    checks, meas = H.classify_rt10([rt10_job(seconds, conclusion)])
    assert all(checks.values()) is ok, (checks, meas)
    assert H.classify_rt10([])[0] == {"probe_found": False}


@pytest.mark.parametrize("seconds, past, billed", [(100, False, False), (120, False, True), (121, True, True),
                                                   (179, True, True), (180, True, False), (181, True, False)])
def test_rt10_each_check_stands_on_its_own(seconds, past, billed):
    checks, meas = H.classify_rt10([rt10_job(seconds)])
    assert (checks["ran_past_the_timeout"], checks["billed_timeout_plus_one"]) == (past, billed), meas


class JobsAPI:
    slug = "o/r"

    def __init__(self, jobs, notes):
        self.jobs, self.notes = jobs, notes

    def api(self, method, path, body=None):
        if "/attempts/1/jobs" in path:
            return 200, {"jobs": self.jobs}
        if "/check-runs/" in path:
            jid = int(path.split("/check-runs/")[1].split("/")[0])
            name = next(j["name"] for j in self.jobs if j["id"] == jid)
            return 200, [{"message": m} for m in self.notes.get(name, [])]
        return 500, "unexpected"


def test_classify_reads_the_jobs_and_annotations_api_into_one_result(tmp_path, monkeypatch, capsys):
    rec = H.classify("RT-6", JobsAPI(rt6_jobs(), NOTES), 42, {"file": FILE})
    assert rec["result"] == "PASS" and rec["test"] == "RT-6" and rec["schema"] == H.RESULT_SCHEMA
    monkeypatch.setattr(H.RL, "GH", lambda slug: JobsAPI(rt6_jobs(corrupt_at=AT.SCIENCE_STEP), NOTES))
    (tmp_path / "e.json").write_text(json.dumps({"file": FILE}))
    rc = H.main(["classify", "--test", "RT-6", "--repo-slug", "o/r", "--run-id", "42", "--expect",
                 str(tmp_path / "e.json"), "--out", str(tmp_path / "rt.json")])
    assert rc == 3 and json.loads((tmp_path / "rt.json").read_text())["result"] == "FAIL"
    monkeypatch.setattr(H.RL, "GH", lambda slug: type("Down", (), {"slug": "o/r",
                                                                    "api": lambda *a, **k: (502, "down")})())
    rc = H.main(["classify", "--test", "RT-7", "--repo-slug", "o/r", "--run-id", "42", "--out",
                 str(tmp_path / "rt2.json")])
    assert rc == 3 and json.loads((tmp_path / "rt2.json").read_text())["result"] == "FAIL"


# -- verdicts --------------------------------------------------------------------------------------------

def test_a_result_passes_only_when_every_check_is_exactly_true():
    assert H.result("RT-4", "j", {"a": True})["result"] == "PASS"
    for bad in ({"a": True, "b": False}, {"a": 1}, {"a": None}, {}):
        assert H.result("RT-4", "j", bad)["result"] == "FAIL"
    assert H.result("RT-4", "j", {"a": True}, problems=["x"])["result"] == "FAIL"


def prep_record(repo: Path, **kw) -> dict:
    lock = json.loads((repo / D.LOCK_REL).read_text())
    rec = {"counts": {"kline_archive_files": lock["counts"]["kline_archive_files"],
                      "funding_archive_files": lock["counts"]["funding_archive_files"], "checksum_files": 1, "files": 1},
           "checksum_failures": 0, "replay_equivalent": True, "workers": 32,
           "lock_sha256": hashlib.sha256((repo / D.LOCK_REL).read_bytes()).hexdigest(),
           "seconds": {"list": 3, "fetch": 1200}, "address": "sha256:" + "d" * 64, "tar_sha256": "e" * 64}
    rec.update(kw)
    return rec


def rt1_docs(**pub_change) -> tuple[dict, dict]:
    """RT-1's two documents at COMMIT, run RUN1: its own cold preparation and the publication."""
    rec = prep_record(REPO, commit=COMMIT, run_id=RUN1, run_attempt="1")
    tag = RL.tag_for(rec["address"], COMMIT)
    pub = {"result": RL.PUBLISHED, "immutable": True, "tag": tag, "commit": COMMIT, "tag_commit": COMMIT,
           "address": rec["address"], "published_by_run": int(RUN1), "release_id": 7,
           "assets": {RL.MANIFEST: {"digest": rec["address"]}, RL.TAR: {"digest": f"sha256:{rec['tar_sha256']}"}}}
    pub.update(pub_change)
    return rec, pub


def rt1_verdict(tmp_path, rec, pub) -> dict:
    (tmp_path / "r.json").write_text(json.dumps(rec))
    (tmp_path / "p.json").write_text(json.dumps(pub))
    return H.verdict("RT-1", "Snapshot release (contents: write)", [tmp_path / "r.json", tmp_path / "p.json"], REPO)


def test_rt1_verdict_binds_the_preparation_the_lock_and_the_published_release(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", COMMIT)
    monkeypatch.setenv("GITHUB_RUN_ID", RUN1)
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    rec, pub = rt1_docs()
    got = rt1_verdict(tmp_path, rec, pub)
    assert got["result"] == "PASS", got["problems"]
    assert got["measurements"]["commit"] == COMMIT and got["measurements"]["publication"] == RL.PUBLISHED
    assert got["measurements"]["release"]["tag"] == RL.tag_for(rec["address"], COMMIT)
    for edit in (lambda r, p: r.update(checksum_failures=1), lambda r, p: r["counts"].update(kline_archive_files=1),
                 lambda r, p: r.update(lock_sha256="0" * 64), lambda r, p: r.update(workers=8),
                 lambda r, p: p.update(immutable=False), lambda r, p: p.update(tag_commit="b" * 40),
                 lambda r, p: p.update(result="ALREADY_PUBLISHED"), lambda r, p: p.update(address="sha256:" + "0" * 64),
                 lambda r, p: r.update(seconds={}),
                 # wrong commit, stale release, another session's preparation, another run's publication
                 lambda r, p: r.update(commit="b" * 40), lambda r, p: r.update(run_id=RUN2),
                 lambda r, p: r.update(run_attempt="2"), lambda r, p: p.update(commit=NEW),
                 lambda r, p: p.update(tag=RL.tag_for(r["address"], NEW)), lambda r, p: p.update(published_by_run=12),
                 lambda r, p: p.update(published_by_run=None), lambda r, p: p.update(published_by_run=True),
                 lambda r, p: p["assets"][RL.MANIFEST].update(digest="sha256:" + "0" * 64),
                 lambda r, p: p["assets"][RL.TAR].update(digest="sha256:" + "0" * 64)):
        r2, p2 = json.loads(json.dumps(rec)), json.loads(json.dumps(pub))
        edit(r2, p2)
        assert rt1_verdict(tmp_path, r2, p2)["result"] == "FAIL", (r2, p2)
    monkeypatch.setenv("GITHUB_SHA", NEW)  # this run is at another commit than its documents
    assert rt1_verdict(tmp_path, rec, pub)["result"] == "FAIL"


def test_rt1_verdict_again_at_the_same_commit_passes_on_a_verified_release_and_fresh_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", COMMIT)
    monkeypatch.setenv("GITHUB_RUN_ID", RUN2)
    rec, pub = rt1_docs(result=RL.VERIFIED_EXISTING, published_by_run=int(RUN1))
    rec["run_id"] = RUN2  # this run's own cold preparation
    got = rt1_verdict(tmp_path, rec, pub)
    assert got["result"] == "PASS", got["problems"]
    assert got["measurements"]["publication"] == RL.VERIFIED_EXISTING and got["run_id"] == RUN2
    assert got["measurements"]["published_by_run"] == int(RUN1)
    for edit in (lambda r, p: p.update(published_by_run=int(RUN2)),  # "verified" its own publication
                 lambda r, p: p.update(published_by_run=True), lambda r, p: p.update(published_by_run="11"),
                 lambda r, p: r.update(run_id=RUN1),                 # the earlier run's evidence, not fresh
                 lambda r, p: p.update(tag_commit="b" * 40)):
        r2, p2 = json.loads(json.dumps(rec)), json.loads(json.dumps(pub))
        edit(r2, p2)
        assert rt1_verdict(tmp_path, r2, p2)["result"] == "FAIL"
    monkeypatch.delenv("GITHUB_RUN_ID")
    assert rt1_verdict(tmp_path, rec, pub)["result"] == "FAIL"


def test_a_release_is_bound_to_a_commit_only_when_its_summary_and_its_tag_both_name_it():
    address = "sha256:" + "d" * 64
    rel = {"address": address, "commit": COMMIT, "tag": RL.tag_for(address, COMMIT), "release_id": 7}
    assert H.bound_to(rel, COMMIT)
    assert not H.bound_to(rel, NEW)                               # another readiness commit
    assert not H.bound_to({**rel, "commit": NEW}, COMMIT)         # the summary names another commit than its tag
    assert not H.bound_to({**rel, "tag": RL.tag_for(address, NEW)}, COMMIT)
    assert not H.bound_to({**rel, "address": "sha256:" + "0" * 64}, COMMIT)
    for rid in (None, True, "7"):
        assert not H.bound_to({**rel, "release_id": rid}, COMMIT)
    assert not H.bound_to(None, COMMIT) and not H.bound_to(rel, "x" * 40)


def test_rt1_checks_its_preparation_before_it_publishes_anything(tmp_path, capsys):
    lock = H.lock_counts(REPO)
    rec = {"checksum_failures": 0, "replay_equivalent": True, "workers": 32, "seconds": {"fetch": 600},
           "counts": {k: lock[k] for k in ("kline_archive_files", "funding_archive_files")},
           "lock_sha256": hashlib.sha256((REPO / D.LOCK_REL).read_bytes()).hexdigest()}
    good = tmp_path / "good.json"
    good.write_text(json.dumps(rec))
    assert H.main(["prep-check", "--record", str(good), "--repo", str(REPO)]) == 0
    assert "PREPARATION_CHECK = PASS (7/7)" in capsys.readouterr().out
    for change in ({"workers": 31}, {"replay_equivalent": None}, {"lock_sha256": "0" * 64},
                   {"counts": {**rec["counts"], "funding_archive_files": 159}}, {"seconds": {}}):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({**rec, **change}))
        assert H.main(["prep-check", "--record", str(bad), "--repo", str(REPO)]) == 3
        out = capsys.readouterr().out
        assert "::error::PREPARATION_CHECK: " in out and "nothing is published" in out


def test_rt2_a_second_preparation_must_be_the_published_snapshot(snap, tmp_path, monkeypatch):
    out, gh, address = snap
    monkeypatch.setenv("GITHUB_SHA", COMMIT)
    monkeypatch.setenv("GITHUB_RUN_ID", "13")
    again = snapshot_files(tmp_path, "rt2", run_id="13")  # RT-2's own cold preparation, same bytes
    rec = json.loads((again / RL.RECORD).read_text())
    rec.update(prep_record(REPO, address=address, tar_sha256=rec["tar_sha256"]))
    (again / RL.RECORD).write_text(json.dumps(rec))
    got = H.compare_release(again, REPO, gh, COMMIT)
    assert got["result"] == "PASS", got["problems"]
    assert got["measurements"]["commit"] == COMMIT and got["measurements"]["release"]["commit"] == COMMIT
    other = snapshot_files(tmp_path, "again", salt="different bytes", run_id="13")
    rec2 = json.loads((other / RL.RECORD).read_text())
    rec2.update(prep_record(REPO, address=rec2["address"], tar_sha256=rec2["tar_sha256"]))
    (other / RL.RECORD).write_text(json.dumps(rec2))
    got = H.compare_release(other, REPO, gh, COMMIT)
    assert got["result"] == "FAIL" and not got["checks"]["same_manifest_digest"]
    assert not got["checks"]["same_tar_sha256"]
    monkeypatch.setenv("GITHUB_RUN_ID", "14")  # a preparation that is not this run's own
    got = H.compare_release(again, REPO, gh, COMMIT)
    assert got["result"] == "FAIL" and not got["checks"]["prepared_cold_by_this_run_at_this_commit"]
    with pytest.raises(RL.ReleaseError, match="0 published"):  # never compared with another commit's release
        H.compare_release(again, REPO, gh, NEW)
    monkeypatch.setenv("GITHUB_RUN_ID", "13")
    monkeypatch.setenv("GITHUB_SHA", NEW)  # the run is at another commit than the one it names
    got = H.compare_release(again, REPO, gh, COMMIT)
    assert got["result"] == "FAIL" and not got["checks"]["prepared_cold_by_this_run_at_this_commit"]


def test_rt3_rt4_rt5_and_rt11_verdicts(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_SHA", COMMIT)
    rel = {"address": "sha256:" + "d" * 64, "commit": COMMIT, "tag": RL.tag_for("sha256:" + "d" * 64, COMMIT),
           "release_id": 7, "immutable": True}

    def files(*docs):
        paths = []
        for i, d in enumerate(docs):
            p = tmp_path / f"{len(list(tmp_path.iterdir()))}-{i}.json"
            p.write_text(json.dumps(d))
            paths.append(p)
        return paths

    probe = {"result": "PASS", "part": "immutability", "release_unchanged": True, "release": rel,
             "probes": {k: {"refused": True} for k in ("a", "b", "c", "d")}}
    assert H.verdict("RT-3", "x", files(probe), REPO)["result"] == "PASS"
    assert H.verdict("RT-3", "x", files({**probe, "release_unchanged": False}), REPO)["result"] == "FAIL"
    assert H.verdict("RT-3", "x", files({**probe, "probes": {"a": {"refused": True}}}), REPO)["result"] == "FAIL"
    one_got_through = {**probe["probes"], "d": {"refused": False}}
    rec = H.verdict("RT-3", "x", files({**probe, "probes": one_got_through}), REPO)
    assert rec["result"] == "FAIL" and rec["checks"]["every_write_refused"] is False
    ro = {"result": "PASS", "part": "read-only", "release": rel, "probes": {k: {"refused": True} for k in "abcd"}}
    got = H.verdict("RT-3", "x", files(ro), REPO)
    assert got["result"] == "PASS" and got["measurements"]["snapshot_release"] == {
        k: rel[k] for k in H.SNAPSHOT_BINDING}
    old = {**rel, "commit": NEW, "tag": RL.tag_for(rel["address"], NEW)}
    for bad_rel in (old, {**rel, "tag": old["tag"]}, {**rel, "release_id": None}, None):
        assert H.verdict("RT-3", "x", files({**ro, "release": bad_rel}), REPO)["result"] == "FAIL", bad_rel
    receipt = {"source": H.RELEASE, "fallback_reason": None, "seconds": {"download": 9.0}, "files": 7,
               "tree_digest": "sha256:" + "1" * 64, "commit": COMMIT, "release": rel}
    sci = {"checks": {"network_removed": True, "lock_byte_identical": True}, "seconds": 400}
    assert H.verdict("RT-4", "x", files(receipt, sci), REPO)["result"] == "PASS"
    for bad in ({**receipt, "commit": NEW}, {**receipt, "release": old}, {**receipt, "release": None}):
        for t in ("RT-4", "RT-11"):  # restored, but not this commit's release
            assert H.verdict(t, "x", files(bad, sci), REPO)["result"] == "FAIL", (t, bad)
    cached = {**receipt, "seconds": {"cache": 1.0, "download": 9.0},
              "fallback_reason": "CACHE_MISS: no cached snapshot in c"}
    assert H.verdict("RT-4", "x", files(cached, sci), REPO)["result"] == "FAIL"
    assert H.verdict("RT-4", "x", files({**receipt, "source": H.CACHE}, sci), REPO)["result"] == "FAIL"
    bad = {**sci, "checks": {**sci["checks"], "no_socket_call": False}}
    assert H.verdict("RT-11", "x", files(receipt, bad), REPO)["result"] == "FAIL"
    assert H.verdict("RT-11", "x", files(cached, sci), REPO)["result"] == "PASS"  # RT-11 may use the cache
    cold = {**cached, "address": "sha256:" + "d" * 64}
    warm = {"source": H.CACHE, "fallback_reason": None, "seconds": {"cache": 2.0}, "files": 7,
            "tree_digest": cold["tree_digest"], "address": cold["address"], "commit": COMMIT}
    assert H.verdict("RT-5", "x", files(cold, warm), REPO)["result"] == "PASS"
    for c, w in (({**cold, "release": old}, warm), ({**cold, "commit": NEW}, warm), (cold, {**warm, "commit": NEW})):
        assert H.verdict("RT-5", "x", files(c, w), REPO)["result"] == "FAIL"
    for c2, w2 in (({**cold, "fallback_reason": "CACHE_INVALID: x"}, warm), (cold, {**warm, "source": H.RELEASE}),
                   (cold, {**warm, "tree_digest": "sha256:" + "2" * 64}), ({**cold, "files": 6}, warm),
                   (cold, {**warm, "address": None}), ({**cold, "tree_digest": None}, {**warm, "tree_digest": None})):
        assert H.verdict("RT-5", "x", files(c2, w2), REPO)["result"] == "FAIL"


class LaggingAPI(JobsAPI):
    """The jobs API trailing the probes' end: in progress for ``lag`` reads, annotations for ``note_lag``."""

    def __init__(self, jobs, notes, lag=0, note_lag=0):
        super().__init__(jobs, notes)
        self.lag, self.note_lag, self.reads, self.note_reads = lag, note_lag, 0, 0

    def api(self, method, path, body=None):
        if "/attempts/1/jobs" in path:
            self.reads += 1
            if self.reads <= self.lag:
                return 200, {"jobs": [{**j, "status": "in_progress", "conclusion": None} for j in self.jobs]}
        if "/check-runs/" in path:
            self.note_reads += 1
            if self.note_reads <= self.note_lag:
                return 200, []
        return super().api(method, path, body)


def test_a_classifier_waits_a_bounded_time_for_the_api_to_show_the_probes_ended():
    naps = []
    api = LaggingAPI(rt6_jobs(), NOTES, lag=2, note_lag=2)
    rec = H.classify("RT-6", api, 42, {"file": FILE}, sleep=naps.append)
    assert rec["result"] == "PASS", rec["problems"]
    assert api.reads == 3 and naps.count(H.SETTLE_SECONDS) >= 3
    naps.clear()
    api = LaggingAPI(rt6_jobs(), NOTES, lag=99)
    rec = H.classify("RT-6", api, 42, {"file": FILE}, sleep=naps.append)
    assert rec["result"] == "FAIL" and api.reads == H.SETTLE_TRIES  # never more than SETTLE_TRIES reads
    assert len(naps) <= 2 * (H.SETTLE_TRIES - 1)
    assert H.SETTLE_TRIES * H.SETTLE_SECONDS <= 60  # within the classify jobs' 10-minute timeout
    jobs = [probe_job("RT-7 probe infra", H.INFRA_STEP, jid=1), probe_job("RT-7 probe science", AT.SCIENCE_STEP, jid=2)]
    api = LaggingAPI(jobs, {}, lag=1)
    assert H.classify("RT-7", api, 42, sleep=naps.append)["result"] == "PASS" and api.reads == 2
    with pytest.raises(H.HarnessError, match="no classifier"):
        H.classify("RT-4", api, 42, sleep=naps.append)


def test_a_test_that_did_not_finish_still_publishes_a_fail_verdict(tmp_path, capsys):
    out = tmp_path / "f.json"
    rc = H.main(["fail", "--test", "RT-2", "--job", "Cold preparation", "--reason", "it did not finish",
                 "--out", str(out)])
    rec = json.loads(out.read_text())
    assert rc == 3 and rec["result"] == "FAIL" and rec["test"] == "RT-2" and rec["job"] == "Cold preparation"
    assert rec["problems"][0] == "it did not finish" and rec["schema"] == H.RESULT_SCHEMA
    with pytest.raises(SystemExit):
        H.main(["fail", "--test", "RT-12", "--job", "x", "--reason", "y", "--out", str(out)])
