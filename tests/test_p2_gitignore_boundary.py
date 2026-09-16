"""An ignore rule must not hide a lane nobody authorised.

`freqtrade/user_data` is the only host tree any container mounts, and
`git status` on it is the signal the forward-paper protocol's own clean-worktree
stop condition depends on. So every ignore rule covering that directory is a
decision about what an operator will never be shown.

A prefix pattern `fp-control-*/` was written during S2 and withdrawn here. It
covered the two declared lanes — and also `fp-control-3`, `fp-control-A` and
`fp-control-PRODUCTION`, which the registry does not declare and whose role
names the schema's closed enum cannot even express. A second runtime writing
evidence nobody authorised is precisely the thing that must stay visible, and
that pattern would have hidden it.

These tests are the boundary made executable: exactly the declared lanes and one
test-only namespace are hidden, that namespace can never name a real instance,
and every other sibling under `user_data` — undeclared lane, foreign role,
arbitrary directory — remains visible to `git status` and to repository hygiene.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import verify_repo
from fp import lane as fp_lane

USER_DATA = Path("freqtrade/user_data")
REGISTRY_PATH = Path("research/fp/records/forward_paper_cohort_registry.json")
REGISTRY_SCHEMA = Path("research/schema/forward_paper_cohort_registry.schema.json")
TEST_NAMESPACE = "fp-testlane-"

# Lanes the registry actually declares. Anything else under user_data is
# unauthorised by construction.
DECLARED_LANES = ("fp-control-1", "fp-control-2")

# Each of these is a directory an operator must be shown if it ever appears.
UNAUTHORISED_SIBLINGS = (
    "fp-control-3",              # an undeclared successor
    "fp-control-PRODUCTION",     # an unexpected production lane
    "fp-control-A",              # a plausible-looking typo of a real lane
    "fp-candidate-a",            # a foreign role's lane
    "fp-candidate-b",
    "evidence",                  # an evidence path outside any lane
    "shadow-run",                # an arbitrary sibling
    "tmp",
)


def _check_ignore(path: str) -> bool:
    """Does git ignore this path? Asks git, not a reimplementation of its rules."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", path],
        capture_output=True, text=True, timeout=60,
    )
    return result.returncode == 0


@pytest.fixture
def sibling(request, tmp_path_factory):
    """Create a real directory under user_data and always remove it."""
    name = request.param
    root = USER_DATA / name
    created = not root.exists()
    (root).mkdir(parents=True, exist_ok=True)
    (root / "paper_input_ledger.jsonl").write_text("{}\n", encoding="utf-8")
    try:
        yield root
    finally:
        if created:
            import shutil

            shutil.rmtree(root, ignore_errors=True)


# -- unauthorised siblings stay visible ------------------------------------


@pytest.mark.parametrize("sibling", UNAUTHORISED_SIBLINGS, indirect=True)
def test_an_unauthorised_sibling_under_user_data_is_not_ignored(sibling):
    assert not _check_ignore(str(sibling)), (
        f"{sibling} is ignored. An ignore rule that hides an undeclared lane hides "
        "a second runtime writing evidence nobody authorised"
    )


@pytest.mark.parametrize("sibling", UNAUTHORISED_SIBLINGS, indirect=True)
def test_an_unauthorised_sibling_is_visible_to_git_status(sibling):
    """Visible to the signal the clean-worktree stop condition actually reads."""
    out = subprocess.run(
        ["git", "status", "--porcelain", "--", str(sibling)],
        capture_output=True, text=True, check=True, timeout=60,
    ).stdout
    assert out.strip(), f"{sibling} does not appear in git status"


@pytest.mark.parametrize("sibling", ("fp-control-PRODUCTION", "fp-candidate-a"), indirect=True)
def test_repository_hygiene_reports_an_unauthorised_sibling(sibling):
    """verify_repo's untracked check is the gate that must see it."""
    problems: list[str] = []
    verify_repo.check_untracked(problems)
    assert any(str(sibling) in problem or sibling.name in problem for problem in problems), problems


# -- the declared lanes, and only those, are hidden ------------------------


@pytest.mark.parametrize("name", DECLARED_LANES)
def test_each_declared_lane_is_ignored(name):
    """A live evidence lane must not keep the worktree permanently dirty."""
    assert _check_ignore(f"{USER_DATA}/{name}/paper_input_ledger.jsonl")


def test_the_ignore_rules_name_exactly_the_declared_lanes_and_the_test_namespace():
    text = Path(".gitignore").read_text(encoding="utf-8")
    rules = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("freqtrade/user_data/fp-")
    ]
    assert sorted(rules) == sorted(
        [f"freqtrade/user_data/{name}/" for name in DECLARED_LANES]
        + [f"freqtrade/user_data/{TEST_NAMESPACE}*/"]
    ), rules


def test_no_ignore_rule_covers_user_data_wholesale():
    """A rule broad enough to hide the directory hides every lane in it."""
    text = Path(".gitignore").read_text(encoding="utf-8")
    for line in text.splitlines():
        rule = line.strip()
        if not rule or rule.startswith("#"):
            continue
        assert rule not in (
            "freqtrade/user_data/",
            "freqtrade/user_data/*",
            "freqtrade/user_data/**",
            "freqtrade/",
        ), rule
        assert not rule.startswith("freqtrade/user_data/fp-control-*"), rule


# -- the test namespace can never name a real instance ---------------------


def test_every_declared_lane_is_outside_the_test_namespace():
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    for row in registry["instances"]:
        lane = fp_lane.resolve_lane(row["role"], registry)
        assert not lane.instance_dir.startswith(TEST_NAMESPACE), lane.instance_dir


def test_the_role_enum_cannot_express_a_test_namespace_lane():
    """The registry's role enum is closed, so no future row can claim one either."""
    schema = json.loads(REGISTRY_SCHEMA.read_text(encoding="utf-8"))
    roles = schema["properties"]["instances"]["items"]["properties"]["role"]["enum"]
    assert roles == ["FP-CONTROL-1", "FP-CONTROL-2", "FP-CANDIDATE-A", "FP-CANDIDATE-B"]
    for role in roles:
        assert not role.lower().startswith(TEST_NAMESPACE)


def test_the_test_namespace_is_ignored_so_a_failed_test_cannot_dirty_the_tree():
    assert _check_ignore(f"{USER_DATA}/{TEST_NAMESPACE}s2archive/evidence/x.jsonl")


def test_the_s2_tests_build_lanes_only_inside_the_test_namespace():
    for path in (
        "tests/test_p2_archival.py",
        "tests/test_p2_activation.py",
        "tests/test_p2_watch_and_seal.py",
    ):
        text = Path(path).read_text(encoding="utf-8")
        line = next(line for line in text.splitlines() if line.startswith("TEST_LANE = "))
        assert TEST_NAMESPACE in line, (path, line)
