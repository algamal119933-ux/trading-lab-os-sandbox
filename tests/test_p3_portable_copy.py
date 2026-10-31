"""P3-PLN-05 portable copy: backup.compare_hash_export on synthetic sets (no Windows, no Toshiba disk).

docs/p3/PLN_05_PORTABLE_COPY_DRILL.md §3.8 asks the Owner for a ``Get-FileHash | Export-Csv`` of the copy and
compares it, with verify_backup's own rules, against the original set's manifests. These tests build a real set
with ``backup.create_backup``, render the export exactly as Windows PowerShell 5.1 and PowerShell 7 write it, and
show each defect the comparison exists to catch failing it: a changed artifact, a missing one, a file Explorer
left behind, a regenerated manifest, a record that disagrees with its manifest, a short set, rows from outside the
copy, and an unreadable export. PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))

from p3 import backup  # noqa: E402

STAMP = "20261026T033318Z"
ROOT = rf"E:\tlos-backups\{STAMP}"


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True)


@pytest.fixture
def set_dir(tmp_path) -> Path:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    git(runtime, "init", "-q", "-b", "main")
    (runtime / "code.py").write_text("print(1)\n")
    git(runtime, "add", "code.py")
    git(runtime, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "c")
    (runtime / ".env").write_text("FREQTRADE_API_PASSWORD=synthetic-not-a-secret\n")
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "ledger.jsonl").write_text('{"x":1}\n')

    def exporter(volume: str, out: Path) -> None:
        out.write_bytes(f"volume {volume}\n".encode())

    backup.create_backup(tmp_path / "wdc", roots={"runtime": runtime, "evidence": evidence},
                         repos={"runtime": runtime}, volumes=("grafana_data",), stamp=STAMP,
                         volume_exporter=exporter)
    return tmp_path / "wdc" / STAMP


def rows_of(directory: Path, root: str = ROOT) -> list[tuple[str, str, str]]:
    """What ``Get-ChildItem -Recurse -File -Force | Get-FileHash -Algorithm SHA256`` reports for a copy."""
    out = []
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        rel = path.relative_to(directory).as_posix().replace("/", "\\")
        out.append(("SHA256", backup.sha256_file(path).upper(), f"{root}\\{rel}"))
    return out


def write_export(path: Path, rows, *, ps51: bool = True) -> Path:
    header = '"Algorithm","Hash","Path"'
    body = "\r\n".join(f'"{a}","{h}","{p}"' for a, h, p in rows)
    if ps51:   # Export-Csv -Encoding UTF8 in 5.1 writes a BOM, and #TYPE unless -NoTypeInformation
        path.write_bytes(b"\xef\xbb\xbf" + f"#TYPE Microsoft.Powershell.Utility.FileHash\r\n{header}\r\n{body}\r\n"
                         .encode("utf-8"))
    else:
        path.write_text(f"{header}\n{body}\n", encoding="utf-8")
    return path


def compare(set_dir: Path, rows, tmp_path: Path, root: str = ROOT, **kwargs) -> dict:
    return backup.compare_hash_export(set_dir, write_export(tmp_path / "export.csv", rows, **kwargs), root)


@pytest.mark.parametrize("ps51", [True, False])
def test_a_faithful_copy_matches_its_set(set_dir, tmp_path, ps51):
    report = compare(set_dir, rows_of(set_dir), tmp_path, ps51=ps51)
    assert report["PORTABLE_COPY_MATCHES_SET"] == "PASS", report["checks"]
    assert report["checks"]["listed_count"] == {"status": "PASS", "listed": 6, "expected_from_record": 6}
    assert report["real_money_authorized"] is False


def test_the_windows_root_is_matched_case_insensitively(set_dir, tmp_path):
    report = compare(set_dir, rows_of(set_dir), tmp_path, root=ROOT.lower().replace("\\", "/"))
    assert report["PORTABLE_COPY_MATCHES_SET"] == "PASS", report["checks"]


def _edit(rows, rel: str, digest: str):
    return [(a, digest if p.endswith(rel) else h, p) for a, h, p in rows]


def test_a_changed_artifact_fails(set_dir, tmp_path):
    report = compare(set_dir, _edit(rows_of(set_dir), r"roots\runtime.tar.zst", "AB" * 32), tmp_path)
    assert report["PORTABLE_COPY_MATCHES_SET"] == "FAIL"
    assert report["checks"]["artifacts"]["mismatched"] == ["roots/runtime.tar.zst"]


def test_a_missing_artifact_fails(set_dir, tmp_path):
    rows = [r for r in rows_of(set_dir) if not r[2].endswith("runtime.bundle")]
    report = compare(set_dir, rows, tmp_path)
    assert report["checks"]["artifacts"]["missing"] == ["git/runtime.bundle"]
    assert report["PORTABLE_COPY_MATCHES_SET"] == "FAIL"


def test_a_file_left_in_the_copy_by_the_pc_fails(set_dir, tmp_path):
    rows = rows_of(set_dir) + [("SHA256", "00" * 32, ROOT + r"\roots\Thumbs.db")]
    report = compare(set_dir, rows, tmp_path)
    assert report["checks"]["no_unlisted_file"]["extra"] == ["roots/Thumbs.db"]
    assert report["PORTABLE_COPY_MATCHES_SET"] == "FAIL"


def test_a_regenerated_manifest_on_the_copy_fails_even_if_self_consistent(set_dir, tmp_path):
    copy = tmp_path / "copy"
    shutil.copytree(set_dir, copy)
    (copy / backup.SUMS).write_text((copy / backup.SUMS).read_text() + "\n")   # rewritten in place
    report = compare(set_dir, rows_of(copy), tmp_path)
    assert report["checks"]["manifests_identical"]["SHA256SUMS"] is False
    assert report["PORTABLE_COPY_MATCHES_SET"] == "FAIL"


def test_a_record_that_disagrees_with_its_manifest_fails(set_dir, tmp_path):
    original = tmp_path / "original"
    shutil.copytree(set_dir, original)
    record = json.loads((original / backup.RECORD).read_text())
    record["sha256sums_digest"] = "0" * 64
    (original / backup.RECORD).write_text(json.dumps(record, indent=2) + "\n")
    report = compare(original, rows_of(original), tmp_path)
    assert report["checks"]["record_digest"]["status"] == "FAIL"
    assert report["PORTABLE_COPY_MATCHES_SET"] == "FAIL"


def test_a_short_set_fails_the_count_from_its_record(set_dir, tmp_path):
    original = tmp_path / "original"
    shutil.copytree(set_dir, original)
    record = json.loads((original / backup.RECORD).read_text())
    record["volumes"].append("a_volume_the_set_never_exported")
    (original / backup.RECORD).write_text(json.dumps(record, indent=2) + "\n")
    report = compare(original, rows_of(original), tmp_path)
    assert report["checks"]["listed_count"]["status"] == "FAIL"
    assert report["PORTABLE_COPY_MATCHES_SET"] == "FAIL"


def test_rows_from_outside_the_copy_or_twice_fail(set_dir, tmp_path):
    rows = rows_of(set_dir)
    outside = compare(set_dir, rows + [("SHA256", "00" * 32, r"C:\Users\x\Desktop\a.txt")], tmp_path)
    assert outside["checks"]["export_rows"]["status"] == "FAIL"
    twice = compare(set_dir, rows + [rows[0]], tmp_path)
    assert twice["checks"]["export_rows"]["duplicate_paths"]
    assert twice["PORTABLE_COPY_MATCHES_SET"] == "FAIL"


@pytest.mark.parametrize("bad", [("MD5", "AB" * 16, ROOT + r"\x"), ("SHA256", "zz" * 32, ROOT + r"\x")])
def test_an_unreadable_row_withholds_pass(set_dir, tmp_path, bad):
    report = compare(set_dir, rows_of(set_dir) + [bad], tmp_path)
    assert report["checks"]["export_rows"]["status"] == "UNPROVEN"
    assert report["PORTABLE_COPY_MATCHES_SET"] == "UNPROVEN"


def test_an_empty_or_absent_export_or_set_is_unproven(set_dir, tmp_path):
    assert compare(set_dir, [], tmp_path)["PORTABLE_COPY_MATCHES_SET"] == "UNPROVEN"
    assert backup.compare_hash_export(set_dir, tmp_path / "none.csv", ROOT)["PORTABLE_COPY_MATCHES_SET"] == "UNPROVEN"
    export = write_export(tmp_path / "e.csv", rows_of(set_dir))
    assert backup.compare_hash_export(tmp_path / "no-set", export, ROOT)["PORTABLE_COPY_MATCHES_SET"] == "UNPROVEN"


def _snapshot(directory: Path) -> dict[str, str]:
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob("*") if p.is_file()}


def test_cli_exit_codes_and_the_set_is_never_written(set_dir, tmp_path):
    cli = [sys.executable, str(REPO / "scripts" / "p3" / "backup.py"), "compare-export", "--set", str(set_dir)]
    before = _snapshot(set_dir)
    good = write_export(tmp_path / "good.csv", rows_of(set_dir))
    bad = write_export(tmp_path / "bad.csv", _edit(rows_of(set_dir), "git\\runtime.bundle", "CD" * 32))
    empty = write_export(tmp_path / "empty.csv", [])
    run = lambda *a: subprocess.run(cli + list(a), capture_output=True, text=True, timeout=120)  # noqa: E731
    ok = run("--export", str(good), "--export-root", ROOT, "--json", str(tmp_path / "r.json"))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert json.loads((tmp_path / "r.json").read_text())["PORTABLE_COPY_MATCHES_SET"] == "PASS"
    assert run("--export", str(bad), "--export-root", ROOT).returncode == 1
    assert run("--export", str(empty), "--export-root", ROOT).returncode == 2
    refused = run("--export", str(good), "--export-root", ROOT, "--json", str(set_dir / "r.json"))
    assert refused.returncode == 2 and "REFUSED" in refused.stderr
    assert _snapshot(set_dir) == before
