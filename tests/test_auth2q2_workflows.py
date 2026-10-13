"""The two readiness workflows hold to the readiness plan (research/auth2q2/plan.py) and to Owner decisions OD-S3
and OD-S4: manual dispatch only, one run at a time, the gate first, a token that can write only in the snapshot
release job, the billing token only in the gate step, every science step in a network namespace of its own, and
every job named, timed and conditioned exactly as the plan and the readiness ledger count it.

Static: nothing here dispatches a workflow. PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
for extra in (REPO / "research", REPO / ".github" / "gates"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import auth2q2_readiness as RG  # noqa: E402
from auth2q2 import attempts as AT  # noqa: E402
from auth2q2 import harness as H  # noqa: E402
from auth2q2 import plan as PL  # noqa: E402

OP = RG.OP
WF = REPO / ".github" / "workflows"
RELEASE_JOB = "Snapshot release (contents: write)"
UNSHARE = 'sudo unshare --net -- setpriv --reuid="$(id -u)" --regid="$(id -g)" --clear-groups -- '
ALLOWED_ACTIONS = {"actions/checkout@v4", "actions/setup-python@v5", "actions/cache/save@v4",
                   "actions/cache/restore@v4", "actions/upload-artifact@v4", "actions/download-artifact@v4"}


def load(name: str) -> dict:
    return yaml.safe_load((WF / name).read_text())


def text(name: str) -> str:
    return (WF / name).read_text()


def jobs(name: str) -> dict[str, dict]:
    """job display name -> job."""
    return {j["name"]: j for j in load(name)["jobs"].values()}


def for_tests(job_if: str) -> set[str]:
    return set(re.findall(r"inputs\.test == '(RT-\d+)'", job_if or ""))


@pytest.fixture(params=PL.WORKFLOWS)
def wf(request):
    return request.param


def test_both_workflows_exist_and_only_they_are_readiness_workflows():
    assert sorted(p.name for p in WF.glob("auth2q2*.yml")) == sorted(PL.WORKFLOWS)


def test_manual_dispatch_serial_and_titled_for_the_test(wf):
    doc = load(wf)
    on = doc.get("on", doc.get(True))
    assert list(on) == ["workflow_dispatch"]
    assert doc["run-name"] == PL.TITLE.format(test="${{ inputs.test }}")
    assert doc["concurrency"] == {"group": PL.CONCURRENCY_GROUP, "cancel-in-progress": False}
    assert doc["permissions"] == {}  # nothing by default: every job states its own
    assert doc["env"] == {"PYTHONPATH": "research"}
    for forbidden in ("pull_request", "schedule", "workflow_run", "repository_dispatch", "push:"):
        assert forbidden not in json.dumps(on)


def test_the_owner_states_billing_only_in_typed_dispatch_inputs(wf):
    inputs = load(wf).get("on", load(wf).get(True))["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"test", OP.MINUTES_INPUT, *OP.CONFIRMATIONS}
    tests = [t for t in PL.RUN_TESTS if PL.workflow_of(t) == wf]
    assert inputs["test"] == {"description": inputs["test"]["description"], "type": "choice", "required": True,
                              "options": tests}
    minutes = inputs[OP.MINUTES_INPUT]
    assert minutes["type"] == "string" and minutes["required"] is True and "default" not in minutes
    for key in OP.CONFIRMATIONS:
        assert inputs[key]["type"] == "choice" and inputs[key]["required"] is True
        assert inputs[key]["options"] == [OP.NOT_CONFIRMED, OP.CONFIRMED]
        assert inputs[key]["default"] == OP.NOT_CONFIRMED
    # read from the event GitHub delivered, never from a step, an environment value or an expression
    body = json.dumps(load(wf)["jobs"])
    for key in (OP.MINUTES_INPUT, *OP.CONFIRMATIONS):
        assert key not in body
    for forbidden in ("github.actor", "github.triggering_actor", "vars.", "github.event.inputs"):
        assert forbidden not in text(wf)


def test_every_job_is_the_plans_by_name_and_timeout(wf):
    got = {name: j["timeout-minutes"] for name, j in jobs(wf).items()}
    assert got == PL.JOBS[wf]
    assert all(j["runs-on"] == "ubuntu-24.04" for j in jobs(wf).values())
    assert len(jobs(wf)) == len(load(wf)["jobs"])  # no two jobs share a name


def test_each_job_runs_only_for_the_tests_the_plan_says(wf):
    for name, job in jobs(wf).items():
        if name == PL.GATE_JOB:
            assert "if" not in job and "needs" not in job
            continue
        want = {t for t, (w, run_jobs, _v) in PL.TESTS.items() if w == wf and name in run_jobs}
        assert for_tests(job["if"]) == want, name
        needs = job["needs"] if isinstance(job["needs"], list) else [job["needs"]]
        assert "gate" in needs, name
        if "always()" in job["if"]:  # a classifier or the release job: still only after the gate said DISPATCH
            assert "needs.gate.result == 'success'" in job["if"], name


def test_the_gate_job_is_the_same_in_both_workflows_and_publishes_its_record():
    a, b = (load(w)["jobs"]["gate"] for w in PL.WORKFLOWS)
    assert a == b
    assert a["name"] == PL.GATE_JOB and a["timeout-minutes"] == PL.GATE_TIMEOUT
    assert a["permissions"] == {"contents": "read", "actions": "read"}
    gate = next(s for s in a["steps"] if "readiness gate" in s.get("name", ""))
    assert "auth2q2_readiness.py gate" in gate["run"] and "--annotate" in gate["run"]
    assert gate["env"] == {"TEST": "${{ inputs.test }}", "GH_TOKEN": "${{ github.token }}",
                           "AUTH2_BILLING_TOKEN": "${{ secrets.AUTH2_BILLING_TOKEN }}"}
    upload = next(s for s in a["steps"] if s.get("uses") == "actions/upload-artifact@v4")
    assert upload["with"]["name"] == RG.GATE_ARTIFACT and upload["if"] == "always()"
    assert upload["with"]["retention-days"] >= 31  # a month's first gate record (A_m) outlives the month
    names = [s.get("name", s.get("uses")) for s in a["steps"]]
    assert names.index(gate["name"]) < names.index("The snapshot the gate admitted this run to read")
    assert "pip install" not in json.dumps(a)  # the gate is stdlib only: nothing installed before it decides


def test_the_billing_token_reaches_the_gate_step_and_nothing_else(wf):
    body = text(wf)
    assert set(re.findall(r"secrets\.([A-Z0-9_]+)", body)) == {"AUTH2_BILLING_TOKEN"}
    assert body.count("secrets.AUTH2_BILLING_TOKEN") == 1
    for name, job in jobs(wf).items():
        for step in job["steps"]:
            if "AUTH2_BILLING_TOKEN" in json.dumps(step):
                assert name == PL.GATE_JOB and "auth2q2_readiness.py gate" in step["run"]
    assert "GITHUB_TOKEN" not in body  # the workflow token only as GH_TOKEN from github.token


def test_only_the_release_job_can_write_and_every_job_states_its_permissions(wf):
    for name, job in jobs(wf).items():
        perms = job["permissions"]
        assert isinstance(perms, dict), name
        writes = {k for k, v in perms.items() if v != "read"}
        if name == RELEASE_JOB:
            assert perms == {"contents": "write"}
        else:
            assert writes == set(), (name, perms)
            assert set(perms) <= {"contents", "actions", "checks"}, (name, perms)
    writers = [n for n, j in jobs(wf).items() if any(v != "read" for v in j["permissions"].values())]
    assert writers == ([RELEASE_JOB] if wf == PL.PREPARE_WORKFLOW else [])
    assert all("permissions" not in s for j in jobs(wf).values() for s in j["steps"])


def test_the_write_token_is_used_only_to_publish_and_probe_the_release():
    job = jobs(PL.PREPARE_WORKFLOW)[RELEASE_JOB]
    body = json.dumps(job)
    assert "release publish" in body and "probe-immutable" in body
    for other_name, other in {**jobs(PL.PREPARE_WORKFLOW), **jobs(PL.READINESS_WORKFLOW)}.items():
        if other_name != RELEASE_JOB:
            assert "release publish" not in json.dumps(other) and "probe-immutable" not in json.dumps(other)
    assert "probe-read-only" in json.dumps(jobs(PL.PREPARE_WORKFLOW)["Read-only probe"])
    assert jobs(PL.PREPARE_WORKFLOW)["Read-only probe"]["permissions"] == {"contents": "read"}
    for forbidden in ("git push", "git commit", "git tag", "gh workflow run", "gh run rerun", "rerun",
                      "--append-ledger", "trial_ledger", "run_node --node", "dry_run\": false", "docker"):
        for w in PL.WORKFLOWS:
            assert forbidden not in text(w), (w, forbidden)


def test_every_checkout_keeps_no_credentials_and_every_action_is_pinned(wf):
    for name, job in jobs(wf).items():
        for step in job["steps"]:
            uses = step.get("uses")
            if uses is None:
                continue
            assert uses in ALLOWED_ACTIONS, (name, uses)
            if uses == "actions/checkout@v4":
                assert step["with"] == {"persist-credentials": False}, name


def test_expressions_reach_the_shell_only_as_environment_values(wf):
    for name, job in jobs(wf).items():
        for step in job["steps"]:
            assert "${{" not in step.get("run", ""), (name, step.get("name"))


def science_steps(job: dict) -> list[dict]:
    return [s for s in job["steps"] if s.get("name") == AT.SCIENCE_STEP]


def test_every_science_step_runs_in_its_own_network_namespace(wf):
    for name, job in jobs(wf).items():
        for step in science_steps(job):
            run = step["run"].strip()
            assert run.startswith(UNSHARE), (name, run)
            assert "sudo -E" not in run  # nothing of the job's environment crosses but PATH, PYTHONPATH and HOME
            assert "GH_TOKEN" not in json.dumps(step) and "env" not in step  # no token inside the namespace


def test_the_jobs_the_classifier_reads_have_one_science_step_and_the_named_phases():
    r = jobs(PL.READINESS_WORKFLOW)
    for name in ("RT-4 cold restore and D0 data path", "RT-6 corrupted restored file",
                 "RT-6 asset with the wrong digest", "RT-7 probe infra", "RT-7 probe science", "RT-11 engine data path"):
        steps = [s.get("name") for s in r[name]["steps"]]
        assert steps.count(AT.SCIENCE_STEP) == 1, name
        if name.startswith("RT-7"):
            assert steps.index(H.INFRA_STEP) < steps.index(AT.SCIENCE_STEP)
        else:  # restore, then the check right before science, then science
            assert steps.index(H.RESTORE_STEP) < steps.index(H.VERIFY_STEP) < steps.index(AT.SCIENCE_STEP), name
    assert "harness d0" in json.dumps(r["RT-4 cold restore and D0 data path"])
    assert "harness engine" in json.dumps(r["RT-11 engine data path"])
    infra, science = r["RT-7 probe infra"]["steps"], r["RT-7 probe science"]["steps"]
    assert "exit 1" in infra[0]["run"] and "exit 1" not in infra[1]["run"]
    assert "exit 1" not in science[0]["run"] and "exit 1" in science[1]["run"]
    for step in infra + science + r["RT-10 probe"]["steps"]:
        assert "harness" not in step["run"] and "python" not in step["run"]  # the probes are no-ops


def test_rt4_and_rt11_restore_cold_from_the_release_and_rt5_meets_no_cache_entry():
    r = jobs(PL.READINESS_WORKFLOW)
    for name in ("RT-4 cold restore and D0 data path", "RT-11 engine data path"):
        restore = next(s for s in r[name]["steps"] if s.get("name") == H.RESTORE_STEP)
        assert "--expect-source release" in restore["run"] and "--cache-dir" not in restore["run"]
        assert not any("actions/cache" in s.get("uses", "") for s in r[name]["steps"])
    cold, warm = r["RT-5 restore without a cache entry"], r["RT-5 restore from the warm cache"]
    assert cold["env"]["CACHE_KEY"] == warm["env"]["CACHE_KEY"]
    assert cold["env"]["CACHE_KEY"].endswith("-${{ github.run_id }}")  # a key no earlier run can have saved
    look = next(s for s in cold["steps"] if s.get("uses") == "actions/cache/restore@v4")
    assert "fail-on-cache-miss" not in look["with"]
    assert "--refill-cache" in json.dumps(cold) and "--expect-source release" in json.dumps(cold)
    hit = next(s for s in warm["steps"] if s.get("uses") == "actions/cache/restore@v4")
    assert hit["with"]["fail-on-cache-miss"] is True and "--expect-source cache" in json.dumps(warm)
    assert warm["needs"] == ["gate", "rt5-cold"]


def test_no_job_but_the_gate_runs_in_a_re_run_and_none_runs_after_a_cancel(wf):
    """GitHub re-runs failed jobs without re-running a gate that succeeded, reusing its result: every other job
    therefore requires attempt 1 itself, and none uses always(), which holds even after the Owner cancels."""
    for job in jobs(wf).values():
        if job["name"] == PL.GATE_JOB:
            assert "if" not in job
            continue
        assert "github.run_attempt == '1' && " in job["if"], job["name"]
        assert "always()" not in job["if"], job["name"]
        if "!cancelled()" in job["if"]:
            assert "needs.gate.result == 'success'" in job["if"], job["name"]
    assert "--init-groups" not in text(wf)  # no supplementary group (docker) inside the network namespace


def test_rt1_hands_the_snapshot_over_through_its_own_cache_entry_never_an_artifact():
    p = jobs(PL.PREPARE_WORKFLOW)
    save = next(s for s in p["Cold preparation"]["steps"] if s.get("uses") == "actions/cache/save@v4")
    take = next(s for s in p[RELEASE_JOB]["steps"] if s.get("uses") == "actions/cache/restore@v4")
    assert save["with"]["key"] == take["with"]["key"] == "auth2q2-prep-${{ github.run_id }}"
    assert save["with"]["path"] == take["with"]["path"] and take["with"]["fail-on-cache-miss"] is True
    steps = p["Cold preparation"]["steps"]
    check = next(i for i, s in enumerate(steps) if "auth2q2.harness prep-check" in s.get("run", ""))
    assert steps[check]["if"] == "inputs.test == 'RT-1'" and check < steps.index(save)  # checked, then handed on
    assert p[RELEASE_JOB]["needs"] == ["gate", "prepare"] and "needs.prepare.result == 'success'" in \
        p[RELEASE_JOB]["if"]
    for w in PL.WORKFLOWS:  # the ~1 GB snapshot never becomes artifact storage (500 MB on this plan)
        for job in jobs(w).values():
            for s in job["steps"]:
                if s.get("uses") == "actions/upload-artifact@v4":
                    assert "snapshot" not in str(s["with"]["path"]) and "assets" not in str(s["with"]["path"])
                    assert s["with"]["retention-days"] <= 90


def test_every_verdict_job_publishes_its_record_even_when_its_test_failed():
    """One publishing step per verdict job and test, which runs whatever the test's own steps did (the session
    reads verdicts only from annotations) and passes the test's exit status on."""
    for test, (wf, _jobs, verdicts) in PL.TESTS.items():
        for name in verdicts:
            publish = [s for s in jobs(wf)[name]["steps"] if f"annotate --title {RG.RT_TITLE}" in s.get("run", "")
                       and (not for_tests(s.get("if")) or test in for_tests(s.get("if")))]
            assert len(publish) == 1, (test, name)
            [s] = publish
            assert s.get("if") is None or "!cancelled()" in s["if"], (test, name)
            assert "rc=$?" in s["run"] or "harness fail" in s["run"], (test, name)
            assert test in s["run"] or "--test RT-" not in s["run"] or f"--test {test} " in s["run"], (test, name)


def test_the_rt10_probe_runs_past_its_timeout():
    probe = jobs(PL.READINESS_WORKFLOW)["RT-10 probe"]
    assert probe["timeout-minutes"] == PL.RT10_TIMEOUT
    sleep = int(re.search(r"sleep (\d+)", probe["steps"][0]["run"])[1])
    assert sleep > 60 * (PL.RT10_TIMEOUT + 1)


def test_jobs_that_read_the_jobs_api_hold_actions_read_and_rt6_reads_annotations():
    r = jobs(PL.READINESS_WORKFLOW)
    for name in ("RT-6 classify", "RT-7 classify", "RT-10 classify", "RT-8 storage, retention and billing",
                 "RT-9 billing guard"):
        assert r[name]["permissions"].get("actions") == "read", name
    assert r["RT-6 classify"]["permissions"].get("checks") == "read"
    assert all("checks" not in j["permissions"] for n, j in r.items() if n != "RT-6 classify")


def test_the_science_jobs_install_the_pinned_dependencies_before_the_science_phase():
    r = jobs(PL.READINESS_WORKFLOW)
    for name in ("RT-4 cold restore and D0 data path", "RT-11 engine data path"):
        steps = [s.get("name", s.get("uses")) for s in r[name]["steps"]]
        install = next(s for s in r[name]["steps"] if s.get("name", "").startswith("Install pinned"))
        assert "--require-hashes --no-deps -r research/auth2/requirements-auth2.txt" in install["run"]
        assert steps.index(install["name"]) < steps.index(H.RESTORE_STEP)


def test_the_plan_budget_arithmetic():
    """Each run's planned maximum (every job it can run at timeout + 1, its gate included) and the ledger check
    the gate makes before admitting it: ledger + planned maximum + one more gate run <= 300."""
    want = {"RT-1": 118, "RT-2": 102, "RT-3": 38, "RT-4": 72, "RT-5": 53, "RT-6": 54, "RT-7": 44, "RT-8": 22,
            "RT-9": 22, "RT-10": 25, "RT-11": 72}
    assert {t: PL.planned_max(t) for t in PL.RUN_TESTS} == want
    assert PL.totals() == {"planned_max": 622, "expected": 147, "cap": 300}
    ledger = 0
    for t in PL.DISPATCH_ORDER:  # in the order the Owner is asked, at the expected minutes, every run is admitted
        assert ledger + PL.planned_max(t) + PL.NEXT_GATE_RESERVE <= PL.READINESS_CAP, t
        ledger += PL.EXPECTED[t]
    assert ledger == 147 and PL.READINESS_CAP - ledger == 153
    assert sorted(PL.DISPATCH_ORDER) == sorted(PL.RUN_TESTS)
