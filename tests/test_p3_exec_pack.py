"""P3-PLN-11 execution pack structure generator (research/p3/exec_pack.py).

Synthetic Git repositories only. The generator reads Git objects at a commit, so the same commit gives the same
pack; it never writes over a pack, never marks it frozen, and records missing inputs instead of skipping them.
PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from p3 import exec_pack  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "PATH": "/usr/bin:/bin"}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=env).stdout


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    files = {
        "CLAUDE.md": "# rules\n",
        "docker-compose.yml": "services:\n  ft:\n    image: ${FREQTRADE_IMAGE:-freqtradeorg/freqtrade:2026.7}\n"
                              "  graf:\n    image: grafana/grafana:13.2.0\n  bad:\n    image: busybox\n",
        "requirements-dev.txt": "pytest==8.4.2\njsonschema==4.26.0\nnot-pinned>=1\n",
        "docs/p3/PLN_04_REBOOT_ACCEPTANCE_RUNBOOK.md": "# Reboot acceptance runbook\n",
        "docs/p3/PLN_03_BACKUP_RESTORE.md": "# PLN-03 record\nPLN_03_ACCEPTANCE = PASS\n",
        "docs/p3/P3_CONTRACT.md": "# contract\n",
        "research/p3/acceptance.py": 'ACCEPTANCE_MATRIX = {\n    "PLN-02.inventory_complete": {\n    },\n'
                                     '    "PLN-08.kill_bounded": {\n    },\n}\n',
    }
    for rel, text in files.items():
        p = r / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "fixture")
    return r


def test_the_pack_is_draft_not_frozen_and_reproducible_from_git(repo: Path, tmp_path: Path):
    m1 = exec_pack.build(repo, "HEAD", tmp_path / "p1")
    (repo / "CLAUDE.md").write_text("# working-tree edit must not leak\n", encoding="utf-8")
    m2 = exec_pack.build(repo, "HEAD", tmp_path / "p2")
    assert m1["status"] == "DRAFT_NOT_FROZEN" and m1["frozen"] is False and m1["p3_closed"] is False
    assert m1["real_money_authorized"] is False
    assert m1["files"] == m2["files"], "the pack depends only on the commit, not the working tree"


def test_inventory_reads_images_and_pins_and_flags_unpinned(repo: Path, tmp_path: Path):
    exec_pack.build(repo, "HEAD", tmp_path / "p")
    inv = json.loads((tmp_path / "p" / "version_inventory.json").read_text())["data"]
    imgs = inv["images"]["docker-compose.yml"]
    assert any(i.startswith("freqtradeorg/freqtrade:2026.7") for i in imgs)
    assert "grafana/grafana:13.2.0" in imgs
    assert inv["unpinned_images"] == ["docker-compose.yml: busybox"]
    assert inv["python_pins"]["requirements-dev.txt"] == {"pytest": "8.4.2", "jsonschema": "4.26.0"}
    assert inv["images"]["docker-compose.fp.yml"] == ["MISSING"]


def test_missing_governed_paths_are_recorded_not_skipped(repo: Path, tmp_path: Path):
    exec_pack.build(repo, "HEAD", tmp_path / "p")
    dig = json.loads((tmp_path / "p" / "source_digests.json").read_text())["data"]
    assert set(dig) == set(exec_pack.GOVERNED_PATHS)
    assert dig["docs/p3"]["type"] == "tree" and len(dig["docs/p3"]["object"]) == 40
    assert dig["scripts/p3"] == {"object": "MISSING", "type": "MISSING"}


def test_indexes_and_acceptance_mapping(repo: Path, tmp_path: Path):
    exec_pack.build(repo, "HEAD", tmp_path / "p")
    rb = json.loads((tmp_path / "p" / "runbook_index.json").read_text())["data"]
    assert [r["path"] for r in rb] == ["docs/p3/PLN_04_REBOOT_ACCEPTANCE_RUNBOOK.md"]
    ev = json.loads((tmp_path / "p" / "evidence_index.json").read_text())["data"]
    assert any(r["path"] == "docs/p3/PLN_03_BACKUP_RESTORE.md" and r["declared_status_lines"] for r in ev)
    am = json.loads((tmp_path / "p" / "acceptance_mapping.json").read_text())["data"]
    assert am["criteria"] == {"PLN-02.inventory_complete": "PENDING_EVIDENCE", "PLN-08.kill_bounded": "PENDING_EVIDENCE"}


def test_without_the_acceptance_program_the_mapping_is_pending(repo: Path, tmp_path: Path):
    _git(repo, "rm", "-q", "research/p3/acceptance.py")
    _git(repo, "commit", "-q", "-m", "drop")
    exec_pack.build(repo, "HEAD", tmp_path / "p")
    am = json.loads((tmp_path / "p" / "acceptance_mapping.json").read_text())["data"]
    assert am["criteria"] == "PENDING" and am["source"].startswith("MISSING")


def test_a_pack_is_never_written_over_another(repo: Path, tmp_path: Path):
    exec_pack.build(repo, "HEAD", tmp_path / "p")
    with pytest.raises(exec_pack.ExecPackError):
        exec_pack.build(repo, "HEAD", tmp_path / "p")


def test_the_handoff_template_grants_nothing(repo: Path, tmp_path: Path):
    exec_pack.build(repo, "HEAD", tmp_path / "p")
    text = (tmp_path / "p" / "POST_BETA_HANDOFF_TEMPLATE.md").read_text()
    assert "REAL_MONEY_AUTHORIZED    = NO" in text and "NOT AUTHORIZED" in text and "DRAFT_NOT_FROZEN" in text


def test_an_unknown_ref_is_an_error(repo: Path, tmp_path: Path):
    with pytest.raises(exec_pack.ExecPackError):
        exec_pack.build(repo, "no-such-ref", tmp_path / "p")


def test_the_real_repository_builds_a_draft_pack(tmp_path: Path):
    head = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
    if head.returncode != 0:
        pytest.skip("no git history in this checkout")
    m = exec_pack.build(REPO_ROOT, "HEAD", tmp_path / "real")
    assert m["status"] == "DRAFT_NOT_FROZEN" and m["frozen"] is False
    dig = json.loads((tmp_path / "real" / "source_digests.json").read_text())["data"]
    assert dig["docs/p3"]["type"] == "tree"
