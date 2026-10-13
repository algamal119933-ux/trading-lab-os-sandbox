"""AUTH-2-DISCOVERY-QUALIFICATION-2 readiness (RT-0 for RT-1 and RT-2): the preparation stage
(research/auth2q2/prepare.py) against ``FakeArchive``, a synthetic Binance archive bucket that speaks the S3
listing protocol archive.list_bucket reads (pages, markers, common prefixes) and serves zips with their
published .CHECKSUM files.

A preparation must list once, prove the replayed listing gives discover exactly the live result, bind the file
counts and every symbol's archive identity to the committed lock, fetch every file checksum-verified with one
retry, and only then pack the canonical snapshot. Every refusal below stops it before anything is packed.

PAPER / RESEARCH ONLY. Nothing here opens a connection: the archive's opener is the fake for every test.
"""

from __future__ import annotations

import hashlib
import io
import json
import threading
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

from auth2 import archive as A
from auth2 import dataset_v3 as D
from auth2q2 import listing as L
from auth2q2 import prepare as P
from auth2q2 import snapshot as SN

KL, FU = D.SPOT_PREFIX, D.FUNDING_PREFIX
UNICODE = "币安人生USDT"


def kline(sym: str, month: str, tf: str = "1h") -> str:
    return f"{KL}{sym}/{tf}/{sym}-{tf}-{month}.zip"


def funding(sym: str, month: str) -> str:
    return f"{FU}{sym}/{sym}-fundingRate-{month}.zip"


KEPT = {  # what discover keeps: USDT symbols with 1h zips up to LAST_MONTH (2026-08)
    "AAAUSDT": [kline("AAAUSDT", "2020-01"), kline("AAAUSDT", "2020-02")],
    "BBBUSDT": [kline("BBBUSDT", "2026-07"), kline("BBBUSDT", "2026-08")],
    "BTCUSDT": [kline("BTCUSDT", "2017-08"), kline("BTCUSDT", "2017-09")],
    "ETHUSDT": [kline("ETHUSDT", "2017-08")],
    "NOROWUSDT": [kline("NOROWUSDT", "2024-01")],  # files but no on-grid rows: counted, no identity in the lock
    UNICODE: [kline(UNICODE, "2025-03")],
}
FUNDING = {"BTCUSDT": [funding("BTCUSDT", "2019-09"), funding("BTCUSDT", "2019-10")],
           "ETHUSDT": [funding("ETHUSDT", "2019-11")]}
IGNORED = [kline("BBBUSDT", "2026-09"),  # after LAST_MONTH
           kline("DDDUSDT", "2026-10"),  # a USDT symbol with nothing up to LAST_MONTH
           kline("AAABTC", "2020-01"),  # not USDT
           kline("AAAUSDT", "2020-01", "1d"),  # another timeframe
           funding("BTCUSDT", "2026-09"), funding("SOLUSDT", "2020-01")]  # after LAST_MONTH; not an A3 asset


def body(key: str) -> bytes:
    return (f"PK fake zip {key}\n" * (len(key) % 7 + 3)).encode()


def objects() -> dict[str, bytes]:
    out = {}
    for k in [k for ks in KEPT.values() for k in ks] + [k for ks in FUNDING.values() for k in ks] + IGNORED:
        out[k] = body(k)
        out[k + ".CHECKSUM"] = f"{hashlib.sha256(out[k]).hexdigest()}  {Path(k).name}".encode()  # as published
    return out


class FakeArchive:
    """archive._OPENER for a synthetic bucket: S3 ListBucketResult pages of ``page_size`` items (NextMarker on
    delimited pages only, as S3 does), and objects by key. ``corrupt`` serves altered bytes for a key, ``times``
    times (None: always), so its checksum never matches."""

    def __init__(self, objs: dict[str, bytes], page_size: int = 2) -> None:
        self.objs, self.page_size = dict(objs), page_size
        self.corrupt: dict[str, int | None] = {}
        self.requests: list[str] = []
        self._lock = threading.Lock()

    def open(self, url, timeout=None):  # noqa: ARG002
        with self._lock:
            self.requests.append(url)
        if url.startswith(A.LIST_BASE + "?"):
            return io.BytesIO(self._list(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)))
        if not url.startswith(A.DEFAULT_BASE + "/"):
            raise AssertionError(f"unexpected url {url}")
        key = urllib.parse.unquote(url[len(A.DEFAULT_BASE) + 1:])
        if key not in self.objs:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        with self._lock:
            left = self.corrupt.get(key, 0)
            if left is None or left > 0:
                if left:
                    self.corrupt[key] = left - 1
                return io.BytesIO(self.objs[key] + b"!")
        return io.BytesIO(self.objs[key])

    def _list(self, q: dict) -> bytes:
        prefix, delim, marker = q["prefix"][0], "delimiter" in q, q.get("marker", [""])[0]
        keys = sorted(k for k in self.objs if k.startswith(prefix))
        if delim:
            items = sorted({prefix + k[len(prefix):].split("/")[0] + "/" for k in keys if "/" in k[len(prefix):]})
        else:
            items = keys
        items = [x for x in items if x > marker]
        page, more = items[:self.page_size], len(items) > self.page_size
        xml = ['<?xml version="1.0" encoding="UTF-8"?>\n<ListBucketResult xmlns="http://s3.amazonaws.com/doc/'
               f'2006-03-01/"><Name>data.binance.vision</Name><Prefix>{prefix}</Prefix><Marker>{marker}</Marker>'
               f"<MaxKeys>{self.page_size}</MaxKeys>"]
        if delim:
            xml.append("<Delimiter>/</Delimiter>")
            if more:
                xml.append(f"<NextMarker>{page[-1]}</NextMarker>")
        xml.append(f"<IsTruncated>{'true' if more else 'false'}</IsTruncated>")
        for x in page:
            xml.append(f"<CommonPrefixes><Prefix>{x}</Prefix></CommonPrefixes>" if delim else
                       f"<Contents><Key>{x}</Key><LastModified>2026-09-01T00:00:00.000Z</LastModified>"
                       f"<ETag>&quot;{hashlib.md5(x.encode()).hexdigest()}&quot;</ETag><Size>1</Size></Contents>")
        xml.append("</ListBucketResult>")
        return "".join(xml).encode()


def identity(keys: list[str], objs: dict[str, bytes]) -> str:
    lines = [f"{Path(k).name} {hashlib.sha256(objs[k]).hexdigest()}" for k in keys]
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def lock_repo(root: Path, objs: dict[str, bytes], edit=None) -> Path:
    """The committed lock's counts and identity tables for the fake archive (as dataset_v3.build writes them)."""
    cands = {s: {"archive_months": [ks[0][-11:-4], ks[-1][-11:-4], len(ks)], "archive_sha256": identity(ks, objs)}
             for s, ks in KEPT.items() if s != "NOROWUSDT"}
    fund = {s: {"archive_files": len(ks), "archive_sha256": identity(ks, objs)} for s, ks in FUNDING.items()}
    lock = {"dataset_id": "dataset_v3", "counts": {"kline_archive_files": sum(map(len, KEPT.values())),
                                                   "funding_archive_files": sum(map(len, FUNDING.values()))}}
    tables = {"candidates": {"symbols": cands}, "engine": {"symbols": {}, "funding": fund}, "lock": lock}
    if edit:
        edit(tables)
    (root / D.TABLE_DIR_REL).mkdir(parents=True)
    (root / D.LOCK_REL).write_text(json.dumps(tables["lock"], indent=1, sort_keys=True) + "\n")
    (root / D.TABLE_DIR_REL / "candidates.json").write_text(json.dumps(tables["candidates"]))
    (root / D.TABLE_DIR_REL / "engine_data.json").write_text(json.dumps(tables["engine"]))
    return root


@pytest.fixture
def archive(monkeypatch):
    fake = FakeArchive(objects())
    monkeypatch.setattr(A, "_OPENER", fake)
    monkeypatch.setattr(A.time, "sleep", lambda _s: None)  # archive._get backs off between retries
    return fake


def run(tmp: Path, name: str, repo: Path, **kw) -> dict:
    return P.run(repo, tmp / f"work-{name}", tmp / f"out-{name}", log=lambda _m: None, **kw)


def found() -> tuple:
    return sorted(KEPT), dict(KEPT), dict(FUNDING)


# -- a preparation that passes ----------------------------------------------------------------------

def test_a_cold_preparation_binds_to_the_lock_and_reproduces_byte_for_byte(tmp_path, archive):
    repo = lock_repo(tmp_path / "repo", archive.objs)
    r1 = run(tmp_path, "a", repo)
    r2 = run(tmp_path, "b", repo, workers=3)
    assert r1["address"] == r2["address"] and r1["tar_sha256"] == r2["tar_sha256"]
    assert (tmp_path / "out-a" / P.TAR).read_bytes() == (tmp_path / "out-b" / P.TAR).read_bytes()
    n_kl, n_fu = sum(map(len, KEPT.values())), sum(map(len, FUNDING.values()))
    assert r1["counts"] == {"kline_archive_files": n_kl, "funding_archive_files": n_fu,
                            "checksum_files": n_kl + n_fu, "files": 2 * (n_kl + n_fu) + 1}
    assert r1["symbols"] == len(KEPT) and r1["symbols_with_lock_identity"] == len(KEPT) - 1
    assert r1["replay_equivalent"] is True and r1["checksum_failures"] == 0
    assert r1["lock_sha256"] == hashlib.sha256((repo / D.LOCK_REL).read_bytes()).hexdigest()
    rec = json.loads((tmp_path / "out-a" / P.RECORD).read_text())
    assert rec == r1 and rec["schema"] == P.RECORD_SCHEMA and rec["program"] == SN.PROGRAM_ID


def test_the_snapshot_restores_to_a_warm_cache_that_needs_no_network(tmp_path, archive):
    repo = lock_repo(tmp_path / "repo", archive.objs)
    rec = run(tmp_path, "a", repo)
    raw = (tmp_path / "out-a" / P.MANIFEST).read_bytes()
    man = SN.load_manifest(raw, rec["address"])
    dest = tmp_path / "restored"
    SN.restore(tmp_path / "out-a" / P.TAR, man, dest, rec["tar_sha256"])
    assert SN.verify_tree(dest, man) == []
    assert {f["path"] for f in man["files"]} >= set(L.data_keys(L.from_discover(found())))
    listing = L.load((dest / SN.LISTING_REL).read_bytes())
    before = len(archive.requests)
    with L.replay(listing) as opener:
        assert D.discover(A.DEFAULT_BASE) == found()
        for k in L.data_keys(listing):  # every zip is a cache hit: fetch_verified never asks the opener
            assert A.fetch_verified(k, dest) == archive.objs[k]
    assert opener.refused == [] and len(archive.requests) == before


def test_the_checksum_files_are_rewritten_canonically(tmp_path, archive):
    repo = lock_repo(tmp_path / "repo", archive.objs)
    run(tmp_path, "a", repo)
    k = KEPT["AAAUSDT"][0]
    got = (tmp_path / "work-a" / "cache" / (k + ".CHECKSUM")).read_bytes()
    assert got == f"{hashlib.sha256(archive.objs[k]).hexdigest()}  {Path(k).name}\n".encode()
    assert archive.objs[k + ".CHECKSUM"] != got  # published without the newline; the snapshot is canonical


def test_a_file_that_fails_once_is_retried_and_the_preparation_passes(tmp_path, archive):
    repo = lock_repo(tmp_path / "repo", archive.objs)
    archive.corrupt[KEPT["BBBUSDT"][1]] = 1
    logs: list[str] = []
    rec = P.run(repo, tmp_path / "w", tmp_path / "o", log=logs.append)
    assert rec["checksum_failures"] == 0 and any("retrying 1 file" in x for x in logs)


# -- refusals: nothing is packed --------------------------------------------------------------------

def _refused(tmp_path: Path, repo: Path, match: str) -> None:
    with pytest.raises(P.PreparationError, match=match):
        run(tmp_path, "x", repo)
    assert not (tmp_path / "out-x" / P.TAR).exists() and not (tmp_path / "out-x" / P.MANIFEST).exists()


def test_a_file_whose_checksum_never_matches_fails_the_preparation(tmp_path, archive):
    repo = lock_repo(tmp_path / "repo", archive.objs)
    archive.corrupt[FUNDING["ETHUSDT"][0]] = None
    _refused(tmp_path, repo, f"FETCH: 1 file.*{FUNDING['ETHUSDT'][0]}.*checksum mismatch")


def test_a_checksum_the_archive_does_not_publish_fails_the_preparation(tmp_path, archive):
    repo = lock_repo(tmp_path / "repo", archive.objs)
    del archive.objs[KEPT["ETHUSDT"][0] + ".CHECKSUM"]
    _refused(tmp_path, repo, "not published")


@pytest.mark.parametrize("edit,match", [
    (lambda t: t["lock"]["counts"].update(kline_archive_files=99), "BIND: kline_archive_files is 9, the lock says 99"),
    (lambda t: t["lock"]["counts"].update(funding_archive_files=2), "BIND: funding_archive_files"),
    (lambda t: t["candidates"]["symbols"]["AAAUSDT"].update(archive_sha256="0" * 64), "IDENTITY: AAAUSDT archive"),
    (lambda t: t["candidates"]["symbols"]["BTCUSDT"].update(archive_months=["2017-08", "2017-10", 3]),
     "IDENTITY: BTCUSDT months"),
    (lambda t: t["candidates"]["symbols"].update(GONEUSDT={"archive_months": [], "archive_sha256": ""}),
     "IDENTITY: GONEUSDT is in the lock but not in the archive listing"),
    (lambda t: t["engine"]["funding"]["BTCUSDT"].update(archive_files=3), "IDENTITY: BTCUSDT funding"),
])
def test_an_archive_that_is_not_the_one_the_lock_was_built_from_is_refused(tmp_path, archive, edit, match):
    _refused(tmp_path, lock_repo(tmp_path / "repo", archive.objs, edit), match)


def test_an_archive_file_that_changed_since_the_lock_is_refused(tmp_path, archive):
    repo = lock_repo(tmp_path / "repo", archive.objs)
    k = KEPT[UNICODE][0]
    archive.objs[k] = b"republished"
    archive.objs[k + ".CHECKSUM"] = f"{hashlib.sha256(b'republished').hexdigest()}  x".encode()
    _refused(tmp_path, repo, f"IDENTITY: {UNICODE} archive files differ")


def test_a_preparation_starts_cold(tmp_path, archive):
    repo = lock_repo(tmp_path / "repo", archive.objs)
    (tmp_path / "work-x" / "cache").mkdir(parents=True)
    (tmp_path / "work-x" / "cache" / "left-over").write_text("x")
    _refused(tmp_path, repo, "not empty; a preparation starts cold")


def test_a_listing_the_replay_cannot_reproduce_is_refused(tmp_path, archive, monkeypatch):
    repo = lock_repo(tmp_path / "repo", archive.objs)
    real = L.from_discover

    def lossy(f):
        out = real(f)
        out["keys"][f"{KL}AAAUSDT/1h/"] = out["keys"][f"{KL}AAAUSDT/1h/"][:1]
        return out
    monkeypatch.setattr(L, "from_discover", lossy)
    _refused(tmp_path, repo, "REPLAY: discover under the replayed listing does not return")


def test_a_replay_that_needs_the_network_is_refused(archive):
    listing = L.from_discover(found())
    del listing["keys"][f"{FU}ETHUSDT/"]  # discover would have to list it live
    got = P.replay_problems(listing, found())
    assert got and "cannot answer" in got[0]


def test_a_refusal_swallowed_inside_discover_still_fails_the_replay(archive, monkeypatch):
    real = D.discover

    def swallowing(base):
        try:
            A._get(f"{A.DEFAULT_BASE}/data/unlisted.zip")
        except BaseException:  # noqa: BLE001 - what a careless caller could do; the opener still logged it
            pass
        return real(base)
    monkeypatch.setattr(D, "discover", swallowing)
    got = P.replay_problems(L.from_discover(found()), found())
    assert got == [f"REPLAY: refused requests ['{A.DEFAULT_BASE}/data/unlisted.zip']"]


def test_a_stray_or_non_canonical_cache_file_is_never_packed(tmp_path, archive):
    repo = lock_repo(tmp_path / "repo", archive.objs)
    cache = tmp_path / "c"
    for k in P.data_keys(found()):
        A.fetch_verified(k, cache)
    (cache / "data" / "notes.txt").write_text("x")
    with pytest.raises(P.PreparationError, match="would not list"):
        P.build_snapshot(repo, cache, found(), tmp_path / "o1")
    (cache / "data" / "notes.txt").unlink()
    k = KEPT["AAAUSDT"][1] + ".CHECKSUM"
    (cache / k).write_text((cache / k).read_text().upper())
    with pytest.raises(P.PreparationError, match="CHECKSUM: .*AAAUSDT-1h-2020-02"):
        P.build_snapshot(repo, cache, found(), tmp_path / "o2")


def test_the_cli_reports_pass_and_fail(tmp_path, archive, capsys):
    repo = lock_repo(tmp_path / "repo", archive.objs)
    args = ["run", "--repo", str(repo), "--work", str(tmp_path / "w1"), "--out-dir", str(tmp_path / "o1")]
    assert P.main(args) == 0
    out = capsys.readouterr().out
    rec = json.loads((tmp_path / "o1" / P.RECORD).read_text())
    assert f"PREPARATION = PASS address={rec['address']} tar_sha256={rec['tar_sha256']}" in out
    archive.corrupt[KEPT["AAAUSDT"][0]] = None
    args = ["run", "--repo", str(repo), "--work", str(tmp_path / "w2"), "--out-dir", str(tmp_path / "o2")]
    assert P.main(args) == 3
    out = capsys.readouterr().out
    assert "::error::PREPARATION_REFUSED: FETCH" in out and "PREPARATION = FAIL" in out
