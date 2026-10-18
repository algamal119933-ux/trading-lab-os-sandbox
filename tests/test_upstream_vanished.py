"""The vanished-upstream rule of pin_upstream.py: a 404 is recorded, never a weaker identity.

Hermetic: ``fetch`` is replaced, so nothing reaches the network. Every test here is
an attempt to get bytes, or a PASS, past the gate that the pins would not allow.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import urllib.error
from pathlib import Path

import pytest

import pin_upstream as pin

REPO_ROOT = Path(__file__).resolve().parents[1]
GONE = b"pinned bytes that the upstream no longer serves\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://raw.example/x", code, "x", {}, io.BytesIO())


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """A repository with one vanished source, its record in place, and a fetch that 404s."""
    record = tmp_path / "records" / "GONE.md"
    record.parent.mkdir()
    record.write_bytes(b"the upstream answered 404\n")
    pins = {"sources": {"gone": {
        "repo": "someone/gone", "commit": "c" * 40,
        "upstream_vanished": {"state": "VANISHED", "authority": "Owner directive (test)",
                              "repo": "someone/gone", "commit": "c" * 40,
                              "records": {"records/GONE.md": sha(record.read_bytes())}},
        "files": [{"path": "a.py", "sha256": sha(GONE), "size_bytes": len(GONE),
                   "git_blob_sha1": pin.git_blob_sha1(GONE)}]}}}
    monkeypatch.setattr(pin, "REPO_ROOT", tmp_path)
    served: dict[str, object] = {"a.py": http_error(404)}

    def fetch(url: str) -> bytes:
        result = served[url.rsplit("/", 1)[-1]]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(pin, "fetch", fetch)
    return {"root": tmp_path, "pins": pins, "served": served, "record": record,
            "cache": tmp_path / "cache"}


def run(repo, pins=None):
    return pin.process(pins or repo["pins"], repo["cache"], refresh=False)[0]


def test_a_404_on_a_vanished_source_with_its_record_passes_and_caches_nothing(repo):
    assert run(repo) == []
    assert not (repo["cache"] / "gone" / "a.py").exists()


def test_a_tampered_record_fails(repo):
    repo["record"].write_bytes(b"edited\n")
    assert any("does not match its pinned sha256" in f for f in run(repo))


def test_a_missing_record_fails(repo):
    repo["record"].unlink()
    assert any("is not a file in this repository" in f for f in run(repo))


def test_a_symlinked_record_fails(repo, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "GONE.md"
    outside.write_bytes(repo["record"].read_bytes())
    repo["record"].unlink()
    repo["record"].symlink_to(outside)
    assert any("is not a file in this repository" in f for f in run(repo))


def test_a_record_outside_the_repository_fails(repo, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "GONE.md"
    outside.write_bytes(b"x\n")
    pins = copy.deepcopy(repo["pins"])
    pins["sources"]["gone"]["upstream_vanished"]["records"] = {"../" + outside.parent.name + "/GONE.md": sha(b"x\n")}
    assert any("is not a file in this repository" in f for f in run(repo, pins))


@pytest.mark.parametrize("field, value, message", [
    ("state", "PRESENT", "not 'VANISHED'"),
    ("commit", "d" * 40, "not the pinned"),
    ("repo", "someone/else", "not the pinned"),
    ("authority", "", "names no authority"),
    ("records", {}, "names no record"),
])
def test_an_incomplete_vanished_block_fails(repo, field, value, message):
    pins = copy.deepcopy(repo["pins"])
    pins["sources"]["gone"]["upstream_vanished"][field] = value
    assert any(message in f for f in run(repo, pins))


@pytest.mark.parametrize("dropped", ["sha256", "git_blob_sha1", "size_bytes"])
def test_a_vanished_file_must_keep_its_full_pin(repo, dropped):
    pins = copy.deepcopy(repo["pins"])
    del pins["sources"]["gone"]["files"][0][dropped]
    assert any("keeps a full pin" in f for f in run(repo, pins))


def test_expect_missing_cannot_hide_inside_a_vanished_source(repo):
    pins = copy.deepcopy(repo["pins"])
    pins["sources"]["gone"]["files"][0]["expect_missing"] = True
    assert any("cannot be combined" in f for f in run(repo, pins))


def test_bytes_that_reappear_must_still_match_the_pin(repo):
    repo["served"]["a.py"] = b"different bytes at the same commit\n"
    assert any("mismatch" in f for f in run(repo))
    assert not (repo["cache"] / "gone" / "a.py").exists()


def test_bytes_that_reappear_unchanged_are_verified_and_cached(repo):
    repo["served"]["a.py"] = GONE
    assert run(repo) == []
    assert (repo["cache"] / "gone" / "a.py").read_bytes() == GONE


@pytest.mark.parametrize("error", [http_error(403), http_error(500), urllib.error.URLError("dns"), TimeoutError()])
def test_anything_but_a_404_still_fails(repo, error):
    repo["served"]["a.py"] = error
    assert run(repo) != []


def test_a_404_without_a_vanished_block_still_fails(repo):
    pins = copy.deepcopy(repo["pins"])
    del pins["sources"]["gone"]["upstream_vanished"]
    assert any("HTTP 404" in f for f in run(repo, pins))


def test_a_vanished_block_with_a_broken_record_does_not_excuse_the_404(repo):
    repo["record"].write_bytes(b"edited\n")
    assert any("HTTP 404" in f for f in run(repo))


def test_materialise_refuses_a_vanished_file(repo, tmp_path):
    assert run(repo) == []
    with pytest.raises(SystemExit, match="upstream has vanished"):
        pin.materialize(repo["pins"], repo["cache"], tmp_path / "ws")


def test_a_vanished_entry_for_an_unpinned_source_fails(repo, tmp_path):
    listing = tmp_path / "vanished.json"
    listing.write_text(json.dumps({"authority": "x", "sources": {"nobody": {"state": "VANISHED"}}}))
    assert pin.attach_vanished(copy.deepcopy(repo["pins"]), listing) == ["nobody: listed in vanished.json but not pinned"]


def test_refresh_never_writes_a_vanished_entry_into_the_pins(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(pin, "PINS_PATH", tmp_path / "pins.json")
    pin.save_pins(repo["pins"])
    assert "upstream_vanished" not in (tmp_path / "pins.json").read_text()
    assert "upstream_vanished" in repo["pins"]["sources"]["gone"]


# -- the real manifest --------------------------------------------------------


def real_pins() -> dict:
    pins = json.loads((REPO_ROOT / "research" / "external" / "upstream_pins.json").read_text())
    assert pin.attach_vanished(pins, REPO_ROOT / "research" / "external" / "upstream_vanished.json") == []
    return pins


def test_the_pins_file_carries_no_vanished_entry():
    assert "upstream_vanished" not in (REPO_ROOT / "research" / "external" / "upstream_pins.json").read_text()


def test_only_btc_strategy_lab_is_marked_vanished_and_its_records_hold():
    pins = real_pins()
    marked = [k for k, s in pins["sources"].items() if "upstream_vanished" in s]
    assert marked == ["btc_strategy_lab"]
    assert pin.vanished_problems("btc_strategy_lab", pins["sources"]["btc_strategy_lab"], REPO_ROOT) == []
    assert pins["sources"]["btc_strategy_lab"]["commit"] == "b68a5518b4a3eba2fde1733160d7d7de356023b5"


def test_the_h1_identity_pins_are_unchanged_by_the_vanished_marking():
    pins = real_pins()
    by_path = {e["path"]: e["sha256"] for e in pins["sources"]["btc_strategy_lab"]["files"]}
    assert by_path["user_data/strategies/EmaCross.py"] == "387cf39f58d266bb63d06865a0784bc2e08676edf54f4610c7d7709bb2a95f24"
    assert by_path["user_data/strategies/EmaCross.json"] == "9209a90e5092216af166fd10b9e7415690ab16af0fb3010c7e94e162c027e3ee"
    assert by_path["LICENSE"] == "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"


def test_reappearing_bytes_are_also_held_to_the_blob_sha_a_human_read(repo):
    pins = copy.deepcopy(repo["pins"])
    pins["sources"]["gone"]["files"][0]["git_blob_sha1"] = "0" * 40
    repo["served"]["a.py"] = GONE
    assert any("git blob SHA mismatch" in f for f in run(repo, pins))
