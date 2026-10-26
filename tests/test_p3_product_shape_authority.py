"""P3-PLN-09: the product-shape authority committed in docs/p3/product_shape/ is exactly the hashed set."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SHAPE = REPO / "docs" / "p3" / "product_shape"
PROTOTYPE = "Trading_Lab_OS_Prototype_v0.2.5_FINAL.html"
PROTOTYPE_SHA256 = "e17d50dc9c8d0e6f6a629c4f215441ba4d00457d0e18a6eb5b45261c6651e3d9"


def _sums() -> dict[str, str]:
    out = {}
    for line in (SHAPE / "SOURCES.sha256").read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        out[name.lstrip("*")] = digest
    return out


@pytest.mark.parametrize("name", sorted(_sums()))
def test_each_authority_source_matches_its_recorded_digest(name):
    assert hashlib.sha256((SHAPE / name).read_bytes()).hexdigest() == _sums()[name]


def test_the_frozen_prototype_is_the_owner_identified_one():
    assert _sums()[PROTOTYPE] == PROTOTYPE_SHA256
    level_a = (SHAPE / "Trading_Lab_OS_LEVEL_A_FREEZE_RECORD_v1.0.md").read_text()
    assert f"FINAL_PROTOTYPE_SHA256 = {PROTOTYPE_SHA256}" in level_a
    assert "PRODUCT_SHAPE  = CLOSED" in level_a and "NO_REOPEN_LAW  = ACTIVE" in level_a


def test_the_prototype_is_offline_and_has_the_twelve_frozen_screens():
    html = (SHAPE / PROTOTYPE).read_text()
    assert "connect-src 'none'" in html
    screens = re.search(r"const SCREENS=\{([^}]*)\}", html).group(1).split(",")
    assert len(screens) == 12


def test_the_shape_lock_v1_2_is_embedded_in_the_session_pack():
    pack = (SHAPE / "Trading_Lab_OS_CLAUDE_NEW_SESSION_PACK_v1.0.md").read_text()
    assert "# APPENDIX A — FINAL MASTER PRODUCT SHAPE LOCK v1.2" in pack
    assert "# 63. v1.2 FINAL FREEZE GATE — SUPERSEDING ORDER" in pack


def test_no_planning_draft_is_committed_as_authority():
    assert not any(p.name.startswith("P3_") for p in SHAPE.iterdir())
