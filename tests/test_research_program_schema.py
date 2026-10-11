"""CEA-1 §12: the AUTH-2 structure exists, refuses post-result designs, and opens nothing.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

from pathlib import Path

import cea_policy as cp
import check_research_program as crp

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_exactly_the_auth2_program_exists():
    # AUTH-2 (Owner-approved frozen package) adds the first and only program; any other
    # program file is a new authority act and must arrive in its own Owner-merged PR.
    programs = cp.programs_at(REPO_ROOT, None)
    assert sorted(programs) == ["AUTH-2-DISCOVERY-QUALIFICATION-1"]
    assert programs["AUTH-2-DISCOVERY-QUALIFICATION-1"]["schema_version"] == 2


def test_the_committed_tree_passes():
    assert crp.check(REPO_ROOT) == []


def test_every_refusal_fires_and_the_valid_program_passes():
    assert crp.self_test(REPO_ROOT) == []


def test_the_schema_pins_hyperopt_to_zero_and_terminal_edges_only():
    import json

    schema = json.loads((REPO_ROOT / crp.SCHEMA).read_text(encoding="utf-8"))
    assert schema["properties"]["caps"]["properties"]["hyperopt"] == {"const": 0}
    on = schema["properties"]["dag"]["properties"]["edges"]["items"]["properties"]["on"]["enum"]
    # v1 edges are terminal states only; v2 (AUTH-2) adds the frozen DAG's own terminals and
    # nothing else, and the schema's allOf keeps a v1 program to the v1 set.
    assert sorted(on) == ["ANY_TERMINAL", "HOLM_PASS", "INCONCLUSIVE", "PASS", "PRE_HOLM_PASS", "REJECTED",
                          "SURVIVED"]
    assert schema["properties"]["null_calibration_first"] == {"const": True}
