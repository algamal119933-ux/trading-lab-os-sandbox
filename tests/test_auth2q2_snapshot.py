"""AUTH-2-DISCOVERY-QUALIFICATION-2 readiness (RT-0): the content-addressed snapshot, the listing replay and the
network guard (research/auth2q2/snapshot.py, listing.py, offline.py).

The snapshot's address is the sha256 of its canonical manifest; the tar is canonical too, so the same files give
the same bytes anywhere; and a restore reads only that one form, checking every file before anything can use it.
Each refusal below is a way a snapshot could be wrong (a flipped byte, a reordered or extra member, a link, a
path that climbs out, bytes after the end) and must stop the restore, naming the file.

PAPER / RESEARCH ONLY. Nothing here opens a connection.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import socket
import subprocess
import tarfile
import time
import urllib.parse
from pathlib import Path

import pytest

from auth2 import archive as A
from auth2 import dataset_v3 as D
from auth2q2 import listing as L
from auth2q2 import offline as OFF
from auth2q2 import snapshot as SN

LOCK_SHA = "c" * 64
KL = "data/spot/monthly/klines"
FU = "data/futures/um/monthly/fundingRate"
LONG = "1000000000000000000000000000000000000000000000000000000000000000LONGUSDT"  # every path of it needs pax
UNICODE = "币安人生USDT"  # the archive lists such symbols; their paths need pax too


def kline(sym: str, month: str) -> str:
    return f"{KL}/{sym}/1h/{sym}-1h-{month}.zip"


def funding(sym: str, month: str) -> str:
    return f"{FU}/{sym}/{sym}-fundingRate-{month}.zip"


def zips() -> list[str]:
    return [kline("AAAUSDT", "2020-01"), kline("AAAUSDT", "2020-02"), kline(LONG, "2021-05"),
            kline(UNICODE, "2025-03"), kline("BTCUSDT", "2019-12"), kline("ETHUSDT", "2019-12"),
            funding("BTCUSDT", "2020-01"), funding("ETHUSDT", "2020-01")]


def make_tree(root: Path, keys: list[str] | None = None, empty: str | None = None) -> list[str]:
    """A small archive cache: each zip, its checksum file as fetch_verified writes it, and a listing file."""
    keys = zips() if keys is None else keys
    paths = []
    for i, k in enumerate(keys):
        body = b"" if k == empty else (f"zip {i} {k}\n".encode() * (i * 37 + 1))
        p = root / k
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
        Path(str(p) + SN.CHECKSUM_SUFFIX).write_text(f"{hashlib.sha256(body).hexdigest()}  {Path(k).name}\n")
        paths += [k, k + SN.CHECKSUM_SUFFIX]
    (root / SN.LISTING_REL).parent.mkdir(parents=True, exist_ok=True)
    (root / SN.LISTING_REL).write_bytes(b'{"listing": "a test listing"}\n')
    return paths + [SN.LISTING_REL]


def pack(tmp: Path, name: str = "a", **kw) -> tuple[Path, Path, dict, bytes, str]:
    root = tmp / f"tree-{name}"
    paths = make_tree(root, **kw)
    out = tmp / f"{name}.tar"
    entries, tar_sha, _n = SN.write_tar(root, paths, out)
    man, raw = SN.build_manifest(entries, lock_sha256=LOCK_SHA, last_month="2026-08", archive=A.LIST_BASE)
    return root, out, man, raw, tar_sha


# -- the manifest and the address --------------------------------------------------------------------

def test_the_same_files_give_the_same_tar_and_address_wherever_they_are(tmp_path):
    _r1, t1, _m1, raw1, s1 = pack(tmp_path, "a")
    _r2, t2, _m2, raw2, s2 = pack(tmp_path, "b")
    os.utime(_r2 / zips()[0], (1, 1))  # timestamps, owners and modes are not part of the snapshot
    os.chmod(_r2 / zips()[1], 0o600)
    _e, s3, _n = SN.write_tar(_r2, make_tree(tmp_path / "unused"), tmp_path / "c.tar")
    assert raw1 == raw2 and s1 == s2 == s3
    assert t1.read_bytes() == t2.read_bytes() == (tmp_path / "c.tar").read_bytes()
    assert SN.address(raw1) == "sha256:" + hashlib.sha256(raw1).hexdigest()
    assert hashlib.sha256(t1.read_bytes()).hexdigest() == s1


def test_the_manifest_is_canonical_sorted_and_counted(tmp_path):
    _r, _t, man, raw, _s = pack(tmp_path)
    assert raw == SN.dumps(man) and raw.endswith(b"\n")
    paths = [f["path"] for f in man["files"]]
    assert paths == sorted(paths)
    assert man["counts"] == {"kline_archive_files": 6, "funding_archive_files": 2, "checksum_files": 8, "files": 17}
    assert man["listing"] == next(f for f in man["files"] if f["path"] == SN.LISTING_REL)
    assert SN.load_manifest(raw, SN.address(raw)) == man


def test_the_tar_is_readable_by_standard_tools(tmp_path):
    root, tar, man, _raw, _s = pack(tmp_path)
    with tarfile.open(tar) as tf:
        members = tf.getmembers()
        assert [m.name for m in members] == [f["path"] for f in man["files"]]
        assert all(m.isreg() and m.mode == 0o644 and m.mtime == 0 and m.uid == m.gid == 0 for m in members)
        for m in members:
            assert tf.extractfile(m).read() == (root / m.name).read_bytes()
    if shutil.which("tar"):
        listed = subprocess.run(["tar", "-tf", str(tar)], capture_output=True, text=True, check=True).stdout
        assert listed.splitlines() == [f["path"] for f in man["files"]]


@pytest.mark.parametrize("digest", ["", "sha256:" + "0" * 64, "SHA256:" + "a" * 64, "sha256:" + "A" * 64,
                                    "sha256:" + "a" * 63, "a" * 64, None, 5])
def test_a_manifest_that_does_not_hash_to_the_address_is_refused(tmp_path, digest):
    _r, _t, _m, raw, _s = pack(tmp_path)
    with pytest.raises(SN.SnapshotError):
        SN.load_manifest(raw, digest)


def _first_kline(man: dict) -> dict:
    return next(f for f in man["files"] if "/1h/" in f["path"])


def _reserialized(man: dict, edit) -> bytes:
    m = json.loads(SN.dumps(man))
    edit(m)
    return SN.dumps(m)


@pytest.mark.parametrize("edit,why", [
    (lambda m: m.update(schema="OTHER"), "schema"),
    (lambda m: m.update(program="AUTH-2-DISCOVERY-QUALIFICATION-1"), "program"),
    (lambda m: m.update(extra=1), "fields"),
    (lambda m: m["dataset"].update(lock_sha256="x"), "dataset identity"),
    (lambda m: m["dataset"].update(archive="http://insecure"), "dataset identity"),
    (lambda m: m["files"].reverse(), "sorted"),
    (lambda m: m["files"].append(dict(m["files"][-1])), "sorted"),
    (lambda m: m["files"][0].update(path="../etc/passwd"), "not a snapshot path"),
    (lambda m: m["files"][0].update(path="/" + m["files"][0]["path"]), "not a snapshot path"),
    (lambda m: m["files"][0].update(path=m["files"][0]["path"].replace("/", "\\", 1)), "not a snapshot path"),
    (lambda m: _first_kline(m).update(path=_first_kline(m)["path"].replace("/1h/", "/1h\n/")), "not a snapshot path"),
    (lambda m: _first_kline(m).update(path=_first_kline(m)["path"].replace("/1h/", "/./1h/")), "not a snapshot path"),
    (lambda m: _first_kline(m).update(path=_first_kline(m)["path"].replace("/1h/", "//1h/")), "not a snapshot path"),
    (lambda m: _first_kline(m).update(path=_first_kline(m)["path"].replace("/1h/", "/1h\x7f/")), "not a snapshot path"),
    (lambda m: m["files"][0].update(path="README.md"), "not a snapshot path"),
    (lambda m: m["files"][0].update(sha256="A" * 64), "sha256"),
    (lambda m: m["files"][0].update(size=-1), "size"),
    (lambda m: m["files"][0].update(size=True), "size"),
    (lambda m: m["files"][0].update(size=1.0), "size"),
    (lambda m: m["counts"].update(files=99), "counts"),
    (lambda m: m["listing"].update(size=1), "listing"),
    (lambda m: m.update(files=[f for f in m["files"] if not f["path"].endswith(SN.CHECKSUM_SUFFIX)]), "pair"),
])
def test_a_malformed_manifest_is_refused_even_at_its_own_address(tmp_path, edit, why):
    _r, _t, man, _raw, _s = pack(tmp_path)
    raw = _reserialized(man, edit)
    with pytest.raises(SN.SnapshotError, match="malformed") as exc:
        SN.load_manifest(raw, SN.address(raw))
    assert why in str(exc.value)


def test_a_month_after_the_last_month_is_refused(tmp_path):
    _r, _t, man, _raw, _s = pack(tmp_path)
    raw = _reserialized(man, lambda m: m["dataset"].update(last_month="2020-01"))
    with pytest.raises(SN.SnapshotError, match="after the last month"):
        SN.load_manifest(raw, SN.address(raw))


@pytest.mark.parametrize("variant", [
    lambda raw: raw.replace(b"\n", b"\r\n"),
    lambda raw: raw.rstrip(b"\n"),
    lambda raw: json.dumps(json.loads(raw), sort_keys=True).encode() + b"\n",
    lambda raw: raw.replace(b'"schema"', b'"schema": "X", "schema"', 1),
    lambda raw: b"\xef\xbb\xbf" + raw,
])
def test_only_the_canonical_bytes_are_a_manifest(tmp_path, variant):
    _r, _t, _m, raw, _s = pack(tmp_path)
    other = variant(raw)
    assert other != raw
    with pytest.raises(SN.SnapshotError):
        SN.load_manifest(other, SN.address(other))


# -- restore ---------------------------------------------------------------------------------------

def test_a_manifest_with_a_repeated_key_is_refused_by_name(tmp_path):
    _root, _tar, _man, raw, _s = pack(tmp_path)
    dup = raw.replace(b'"counts": {', b'"counts": {\n  "files": 0,', 1)
    assert dup != raw
    with pytest.raises(SN.SnapshotError, match="duplicate keys \\['files'\\]"):
        SN.load_manifest(dup, SN.address(dup))


@pytest.mark.parametrize("path", [
    f"{KL}/../1h/..-1h-2020-01.zip", f"{KL}/./1h/.-1h-2020-01.zip", f"{FU}/../..-fundingRate-2020-01.zip",
    f"{KL}/../1h/..-1h-2020-01.zip.CHECKSUM",
])
def test_a_dot_segment_is_never_a_snapshot_path_though_the_layout_pattern_would_take_it(path):
    assert SN.data_kind(path) is not None  # the symbol pattern alone would accept "." and ".."
    assert SN.valid_path(path) is False


def test_a_file_that_changes_while_it_is_packed_stops_the_pack(tmp_path, monkeypatch):
    root = tmp_path / "tree"
    paths = make_tree(root)
    victim = str(root / zips()[0])
    real_stat = os.stat

    def stale_stat(path, *a, **k):
        st = real_stat(path, *a, **k)
        if str(path) == victim:
            return os.stat_result((st.st_mode, st.st_ino, st.st_dev, st.st_nlink, st.st_uid, st.st_gid,
                                   st.st_size + 1, st.st_atime, st.st_mtime, st.st_ctime))
        return st
    monkeypatch.setattr(SN.os, "stat", stale_stat)
    with pytest.raises(SN.SnapshotError, match=f"{zips()[0]}: changed while it was being packed"):
        SN.write_tar(root, paths, tmp_path / "x.tar")


def test_restore_writes_exactly_the_manifest_and_verifies_it(tmp_path):
    root, tar, man, _raw, tar_sha = pack(tmp_path)
    dest = tmp_path / "restored"
    assert SN.restore(tar, man, dest, tar_sha) == tar_sha
    assert SN.verify_tree(dest, man) == []
    assert SN.tree_digest(dest) == SN.tree_digest(root)
    assert all(stat_mode(p) == 0o644 for p in dest.rglob("*") if p.is_file())


def stat_mode(p: Path) -> int:
    return p.stat().st_mode & 0o777


def test_restore_refuses_a_directory_that_is_not_new_or_empty(tmp_path):
    _root, tar, man, _raw, _s = pack(tmp_path)
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "x").write_text("x")
    with pytest.raises(SN.SnapshotError, match="never writes over"):
        SN.restore(tar, man, busy)
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    with pytest.raises(SN.SnapshotError, match="symlink"):
        SN.restore(tar, man, link)


def test_restore_refuses_a_tar_with_another_sha256(tmp_path):
    _root, tar, man, _raw, _s = pack(tmp_path)
    with pytest.raises(SN.SnapshotError, match="hashes to"):
        SN.restore(tar, man, tmp_path / "d", "0" * 64)


def _mutated(tar: Path, at: int, value: bytes) -> bytes:
    b = bytearray(tar.read_bytes())
    b[at:at + len(value)] = value
    return bytes(b)


def _offset_of(tar: Path, man: dict, path: str) -> int:
    """Byte offset of ``path``'s data in the canonical tar."""
    with tarfile.open(tar) as tf:
        return next(m.offset_data for m in tf.getmembers() if m.name == path)


def _scan(data: bytes, man: dict) -> None:
    SN.scan_tar(io.BytesIO(data), man["files"])


def test_one_flipped_byte_stops_the_restore_and_names_the_file(tmp_path):
    _root, tar, man, _raw, _s = pack(tmp_path)
    victim = zips()[3]  # the non-ASCII symbol's file, behind a pax header
    at = _offset_of(tar, man, victim) + 5
    data = bytearray(tar.read_bytes())
    data[at] ^= 0x01
    with pytest.raises(SN.SnapshotError, match="sha256") as exc:
        _scan(bytes(data), man)
    assert victim in str(exc.value)
    dest = tmp_path / "partial"
    bad = tmp_path / "bad.tar"
    bad.write_bytes(bytes(data))
    with pytest.raises(SN.SnapshotError, match=victim.split("/")[-1].split(".")[0]):
        SN.restore(bad, man, dest)


@pytest.mark.parametrize("damage,why", [
    ("truncate", "ends early"),
    ("trailing", "follow the end"),
    ("extra_end", "does not list"),
    ("nonzero_padding", "padding"),
    ("mtime", "non-canonical"),
    ("mode", "non-canonical"),
    ("owner", "non-canonical"),
    ("symlink", "not a regular file"),
    ("directory", "not a regular file"),
    ("hardlink", "not a regular file"),
])
def test_anything_but_the_canonical_form_is_refused(tmp_path, damage, why):
    _root, tar, man, _raw, _s = pack(tmp_path)
    data = tar.read_bytes()
    first = 0  # the first member's header: an ASCII path, no pax record
    assert not SN._needs_pax(man["files"][0]["path"])
    if damage == "truncate":
        data = data[:-1500]
    elif damage == "trailing":
        data = data + b"x"
    elif damage == "extra_end":
        data = data[:-1024] + SN._header(b"data/extra", 0, b"0") + SN.ZERO * 2
    elif damage == "nonzero_padding":
        size = man["files"][0]["size"]
        assert size % 512
        data = _mutated(tar, 512 + size, b"\x01")
    else:
        field = {"mtime": (136, b"00000000001\0"), "mode": (100, b"0000755\0"), "owner": (265, b"root\0"),
                 "symlink": (156, b"2"), "directory": (156, b"5"), "hardlink": (156, b"1")}[damage]
        h = bytearray(data[first:first + 512])
        h[field[0]:field[0] + len(field[1])] = field[1]
        h[148:156] = b" " * 8
        h[148:156] = f"{sum(h):06o}".encode() + b"\0 "
        data = data[:first] + bytes(h) + data[first + 512:]
    with pytest.raises(SN.SnapshotError, match=why):
        _scan(data, man)


def test_members_out_of_manifest_order_or_missing_are_refused(tmp_path):
    root, tar, man, _raw, _s = pack(tmp_path)
    files = man["files"]
    swapped = [files[1], files[0], *files[2:]]
    with pytest.raises(SN.SnapshotError, match="the manifest lists"):
        SN.scan_tar(io.BytesIO(tar.read_bytes()), swapped)
    with pytest.raises(SN.SnapshotError, match="missing"):
        SN.scan_tar(io.BytesIO(tar.read_bytes()), [*files, {"path": "z" * 3, "sha256": "0" * 64, "size": 0}])
    with pytest.raises(SN.SnapshotError, match="does not list"):
        SN.scan_tar(io.BytesIO(tar.read_bytes()), files[:-1])
    other = dict(files[0], size=files[0]["size"] + 1)
    with pytest.raises(SN.SnapshotError, match="bytes in the tar"):
        SN.scan_tar(io.BytesIO(tar.read_bytes()), [other, *files[1:]])


def test_a_tampered_pax_record_is_refused(tmp_path):
    _root, tar, man, _raw, _s = pack(tmp_path)
    with tarfile.open(tar) as tf:
        m = next(m for m in tf.getmembers() if UNICODE in m.name)
    data = tar.read_bytes()
    start = m.offset  # tarfile reports a pax member at its pax header: that block, then a one-block record
    rec = data[start + 512:start + 1024]
    forged = rec.replace(UNICODE.encode(), "X安人生USDT".encode()[:len(UNICODE.encode())], 1)
    assert forged != rec
    with pytest.raises(SN.SnapshotError):
        _scan(data[:start + 512] + forged + data[start + 1024:], man)


@pytest.mark.parametrize("where, value, why", [
    (136, b"00000000001\0", "non-canonical pax header"),   # the pax header block's mtime
    (265, b"root\0", "non-canonical pax header"),          # its owner
    (1023, b"\x01", "pax padding is not zero"),            # the last byte of the record's block
])
def test_a_pax_header_or_its_padding_in_any_other_form_is_refused(tmp_path, where, value, why):
    _root, tar, man, _raw, _s = pack(tmp_path)
    with tarfile.open(tar) as tf:
        m = next(m for m in tf.getmembers() if UNICODE in m.name)
    data = bytearray(tar.read_bytes())
    start = m.offset
    assert data[start + 156:start + 157] == b"x" and len(SN._pax_record("path", m.name)) < 512
    data[start + where:start + where + len(value)] = value
    if where < 512:
        h = data[start:start + 512]
        h[148:156] = b" " * 8
        data[start + 148:start + 156] = f"{sum(h):06o}".encode() + b"\0 "
    with pytest.raises(SN.SnapshotError, match=why):
        _scan(bytes(data), man)


def test_restore_never_follows_or_replaces_a_link(tmp_path):
    _root, tar, man, _raw, _s = pack(tmp_path)
    dest = tmp_path / "dest"
    dest.mkdir()
    target = tmp_path / "outside"
    target.mkdir()
    # A restore only writes into an empty directory; a link planted inside it after that check is refused by
    # O_EXCL | O_NOFOLLOW rather than followed.
    first = man["files"][0]["path"]
    with pytest.raises(FileExistsError):
        (dest / first).parent.mkdir(parents=True)
        (dest / first).symlink_to(target / "x")
        SN._create(dest, first)
    assert not (target / "x").exists()


# -- verify-tree ------------------------------------------------------------------------------------

def test_verify_tree_names_every_difference(tmp_path):
    root, tar, man, _raw, _s = pack(tmp_path)
    dest = tmp_path / "d"
    SN.restore(tar, man, dest)
    first, second = zips()[0], zips()[1]
    b = bytearray((dest / first).read_bytes())
    b[0] ^= 0xFF
    (dest / first).write_bytes(bytes(b))
    (dest / second).unlink()
    (dest / "data" / "stray.txt").write_text("x")
    (dest / "data" / "link").symlink_to(dest / first)
    third = zips()[2]
    (dest / third).write_bytes((dest / third).read_bytes() + b"x")
    (dest / "data" / "linkdir").symlink_to(dest / "data" / "spot", target_is_directory=True)
    problems = SN.verify_tree(dest, man)
    text = "\n".join(problems)
    assert f"{first}: sha256" in text and f"{second}: missing" in text
    assert "data/stray.txt: not in the manifest" in text and "data/link: not a regular file" in text
    assert f"{third}: {man['files'][[f['path'] for f in man['files']].index(third)]['size'] + 1} bytes, the " \
        "manifest says" in text
    assert "data/linkdir: a symlink" in text


def test_tree_digest_sees_content_not_metadata(tmp_path):
    root, _tar, _man, _raw, _s = pack(tmp_path)
    d1 = SN.tree_digest(root)
    os.utime(root / zips()[0], (5, 5))
    assert SN.tree_digest(root) == d1
    (root / zips()[0]).write_bytes(b"changed")
    assert SN.tree_digest(root) != d1


def test_write_tar_refuses_links_and_paths_outside_the_layout(tmp_path):
    root = tmp_path / "t"
    paths = make_tree(root)
    (root / zips()[0]).unlink()
    (root / zips()[0]).symlink_to(root / zips()[1])
    with pytest.raises(SN.SnapshotError, match="not a regular file"):
        SN.write_tar(root, paths, tmp_path / "x.tar")
    with pytest.raises(SN.SnapshotError, match="not a snapshot path"):
        SN.write_tar(root, ["data/../../etc/passwd"], tmp_path / "y.tar")
    with pytest.raises(SN.SnapshotError, match="twice"):
        SN.write_tar(root, [zips()[1], zips()[1]], tmp_path / "z.tar")


def test_the_cli_checks_restores_and_verifies(tmp_path, capsys):
    _root, tar, _man, raw, tar_sha = pack(tmp_path)
    mf = tmp_path / "manifest.json"
    mf.write_bytes(raw)
    addr = SN.address(raw)
    assert SN.main(["address", "--manifest", str(mf)]) == 0
    assert capsys.readouterr().out.strip() == addr
    assert SN.main(["check", "--manifest", str(mf), "--digest", addr, "--tar", str(tar), "--tar-sha256",
                    tar_sha]) == 0
    dest = tmp_path / "out"
    receipt = tmp_path / "receipt.json"
    assert SN.main(["restore", "--manifest", str(mf), "--digest", addr, "--tar", str(tar), "--dest", str(dest),
                    "--receipt", str(receipt)]) == 0
    assert json.loads(receipt.read_text())["tar_sha256"] == tar_sha
    assert SN.main(["verify-tree", "--manifest", str(mf), "--digest", addr, "--dir", str(dest)]) == 0
    (dest / zips()[2]).write_bytes(b"x")
    assert SN.main(["verify-tree", "--manifest", str(mf), "--digest", addr, "--dir", str(dest)]) == 3
    out = capsys.readouterr().out
    assert "SNAPSHOT = FAIL" in out and zips()[2] in out
    wrong = "sha256:" + "1" * 64
    assert SN.main(["check", "--manifest", str(mf), "--digest", wrong]) == 3


# -- the listing replay ----------------------------------------------------------------------------

def found_fixture() -> tuple:
    kl = {"AAAUSDT": [kline("AAAUSDT", "2020-01"), kline("AAAUSDT", "2020-02")],
          "BTCUSDT": [kline("BTCUSDT", "2019-12")], "ETHUSDT": [kline("ETHUSDT", "2019-12")],
          UNICODE: [kline(UNICODE, "2025-03")]}
    fu = {"BTCUSDT": [funding("BTCUSDT", "2020-01")], "ETHUSDT": [funding("ETHUSDT", "2020-01")]}
    return sorted(kl), kl, fu


def test_discover_under_the_replayed_listing_returns_what_was_recorded():
    found = found_fixture()
    listing = L.from_discover(found)
    raw = L.dumps(listing)
    assert L.load(raw) == listing
    log: list = []
    with OFF.guard(log), L.replay(listing) as opener:
        again = D.discover(A.DEFAULT_BASE)
    assert again == found and opener.refused == [] and log == []
    assert len(opener.served) == 1 + len(found[0]) + len(D.A3_ASSETS)
    assert L.data_keys(listing) == [k for s in found[0] for k in found[1][s]] + \
        [k for s in D.A3_ASSETS for k in found[2][s]]


def test_the_replay_refuses_every_other_url_at_once_and_archive_cannot_retry_it():
    listing = L.from_discover(found_fixture())
    with L.replay(listing) as opener:
        t0 = time.monotonic()
        with pytest.raises(L.ReplayRefused):
            A._get(f"{A.DEFAULT_BASE}/{urllib.parse.quote(kline('AAAUSDT', '2020-01'))}")
        with pytest.raises(L.ReplayRefused):
            A.list_bucket("data/spot/monthly/klines/ZZZUSDT/1h/", False)
        assert time.monotonic() - t0 < 1.0  # archive._get sleeps between retries; a refusal is never retried
    assert len(opener.refused) == 2
    assert A._OPENER is not opener  # the real opener is back


def test_replay_pages_are_complete_s3_pages_that_archive_parses():
    found = found_fixture()
    listing = L.from_discover(found)
    with L.replay(listing):
        assert A.list_bucket(D.SPOT_PREFIX, True) == [f"{D.SPOT_PREFIX}{s}/" for s in found[0]]
        assert A.list_bucket(f"{D.SPOT_PREFIX}{UNICODE}/1h/", False) == found[1][UNICODE]


@pytest.mark.parametrize("edit,why", [
    (lambda x: x.update(schema="X"), "schema"),
    (lambda x: x.update(last_month="2026-09"), "last month"),
    (lambda x: x["keys"].pop(f"{D.FUNDING_PREFIX}ETHUSDT/"), "exactly one listing"),
    (lambda x: x["keys"][f"{D.SPOT_PREFIX}AAAUSDT/1h/"].reverse(), "sorted"),
    (lambda x: x["keys"][f"{D.SPOT_PREFIX}AAAUSDT/1h/"].append(kline("AAAUSDT", "2026-09")), "after LAST_MONTH"),
    (lambda x: x["keys"][f"{D.SPOT_PREFIX}AAAUSDT/1h/"].append(kline("BBBUSDT", "2020-03")), "not an archive"),
    (lambda x: x["keys"][f"{D.SPOT_PREFIX}AAAUSDT/1h/"].append(kline("AAAUSDT", "2020-03") + ".CHECKSUM"),
     "not an archive"),
    (lambda x: x["keys"].__setitem__(f"{D.SPOT_PREFIX}AAAUSDT/1h/", []), "without keys"),
    (lambda x: x["delimited"][D.SPOT_PREFIX].append(f"{D.SPOT_PREFIX}AAABTC/"), "USDT symbol"),
    (lambda x: x["delimited"][D.SPOT_PREFIX].reverse(), "sorted"),
])
def test_a_malformed_listing_is_refused(edit, why):
    listing = json.loads(L.dumps(L.from_discover(found_fixture())))
    edit(listing)
    problems = L.listing_problems(listing)
    assert problems and why in "; ".join(problems)
    with pytest.raises(SN.SnapshotError):
        L.load(L.dumps(listing))


def test_a_listing_in_any_but_its_canonical_form_or_with_a_repeated_key_is_refused():
    listing = L.from_discover(found_fixture())
    with pytest.raises(SN.SnapshotError, match="canonical form"):
        L.load(json.dumps(listing).encode())
    raw = L.dumps(listing)
    with pytest.raises(SN.SnapshotError, match="duplicate keys"):
        L.load(raw.replace(b'"last_month": ', b'"last_month": "2026-08",\n "last_month": ', 1))


def test_the_replay_refuses_a_request_object_even_for_a_recorded_page():
    import urllib.request

    listing = L.from_discover(found_fixture())
    opener = L.ReplayOpener(listing)
    url = L.page_url(D.SPOT_PREFIX, True)
    assert opener.open(url).read().startswith(b"<?xml")
    with pytest.raises(L.ReplayRefused):
        opener.open(urllib.request.Request(url))
    assert opener.served == [url] and len(opener.refused) == 1


def test_a_listing_item_that_cannot_be_written_into_a_page_is_refused():
    with pytest.raises(SN.SnapshotError):
        L.page("p/", ["a<b"], False)
    with pytest.raises(SN.SnapshotError):
        L.page("p/", ["a&b"], True)


# -- the network guard -----------------------------------------------------------------------------

def test_the_guard_refuses_every_socket_call_and_restores_them_after():
    before = {n: getattr(socket, n) for n in ("create_connection", "getaddrinfo")}
    log: list = []
    with OFF.guard(log):
        with pytest.raises(OFF.NetworkRemoved):
            socket.create_connection(("192.0.2.1", 443), timeout=1)
        with pytest.raises(OFF.NetworkRemoved):
            socket.getaddrinfo("example.com", 443)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(OFF.NetworkRemoved):
                s.connect(("192.0.2.1", 443))
            with pytest.raises(OFF.NetworkRemoved):
                s.connect_ex(("192.0.2.1", 443))
        finally:
            s.close()
        try:
            A._get("https://example.invalid/x")
        except OFF.NetworkRemoved:
            pass  # archive._get catches Exception only: the refusal escapes its retry loop at once
        else:
            pytest.fail("archive._get reached the network inside the guard")
    assert len(log) == 5
    assert {n: getattr(socket, n) for n in before} == before
    assert "connect" not in socket.socket.__dict__ and "connect_ex" not in socket.socket.__dict__


def test_the_guard_also_refuses_name_lookups_and_datagrams_and_puts_them_back():
    before = {n: getattr(socket, n) for n in OFF.GUARDED_FUNCTIONS}
    log: list = []
    with OFF.guard(log):
        for call in (lambda: socket.gethostbyname("localhost"), lambda: socket.gethostbyname_ex("localhost"),
                     lambda: socket.gethostbyaddr("127.0.0.1"), lambda: socket.getnameinfo(("127.0.0.1", 80), 0)):
            with pytest.raises(OFF.NetworkRemoved):
                call()
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            with pytest.raises(OFF.NetworkRemoved):
                u.sendto(b"x", ("127.0.0.1", 9))
            with pytest.raises(OFF.NetworkRemoved):
                u.sendmsg([b"x"], [], 0, ("127.0.0.1", 9))
        finally:
            u.close()
    assert len(log) == 6 and log[-1].startswith("socket.sendmsg ('127.0.0.1', 9)")
    assert {n: getattr(socket, n) for n in before} == before
    assert not set(OFF.GUARDED_METHODS) & set(socket.socket.__dict__)


def test_the_probe_reports_network_removed_only_when_nothing_is_reached(monkeypatch):
    def nothing(*_a, **_k):
        raise OSError("Network is unreachable")
    monkeypatch.setattr(socket, "getaddrinfo", nothing)
    monkeypatch.setattr(socket, "create_connection", nothing)
    rec = OFF.probe(timeout=0.1)
    assert rec["network_removed"] is True and rec["reached"] == []

    def resolves(host, *_a, **_k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.7", 443))]
    monkeypatch.setattr(socket, "getaddrinfo", resolves)
    rec = OFF.probe(timeout=0.1)
    assert rec["network_removed"] is False and set(rec["reached"]) == set(OFF.PROBE_HOSTS)


def test_the_probe_reports_a_reachable_address_even_with_no_name_resolving(monkeypatch):
    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def nothing(*_a, **_k):
        raise OSError("Temporary failure in name resolution")
    monkeypatch.setattr(socket, "getaddrinfo", nothing)
    monkeypatch.setattr(socket, "create_connection", lambda addr, timeout=None: Conn())
    rec = OFF.probe(timeout=0.1)
    assert rec["network_removed"] is False
    assert rec["reached"] == [f"{ip}:{port}" for ip, port in OFF.PROBE_ADDRESSES]


def test_the_probe_cli_fails_the_step_when_anything_is_reached(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(OFF, "probe", lambda timeout=OFF.PROBE_TIMEOUT: {"dns": {}, "tcp": {}, "reached": [],
                                                                          "network_removed": True})
    assert OFF.main(["probe", "--out", str(tmp_path / "p.json")]) == 0
    assert json.loads((tmp_path / "p.json").read_text())["network_removed"] is True
    monkeypatch.setattr(OFF, "probe", lambda timeout=OFF.PROBE_TIMEOUT: {"dns": {}, "tcp": {}, "reached": ["x"],
                                                                          "network_removed": False})
    assert OFF.main(["probe"]) == 3
    assert "NETWORK_REMOVED = FAIL" in capsys.readouterr().out
