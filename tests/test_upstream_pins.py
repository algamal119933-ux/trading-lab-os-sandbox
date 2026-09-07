"""External benchmark sprint — upstream pinning and license invariants.

These tests are hermetic: they never reach the network. What they protect is the
bookkeeping that makes a network fetch meaningful — that the registry, the claims
snapshot and the pin manifest agree on which bytes each candidate is, that no
unlicensed source has quietly become vendorable, and that nobody has copied
upstream code into the tree. The fetch itself is gated separately in CI by
`pin_upstream.py --verify`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import pin_upstream as pin

REPO_ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = REPO_ROOT / "research" / "external"

# Transcribed by the owner from the GitHub UI in the v1.2 pinning addendum. They are
# the human link in the provenance chain: if a pin stops matching one of these, the
# repository is no longer measuring the bytes that were actually reviewed.
ADDENDUM_BLOB_SHAS = {
    "user_data/strategies/EmaCrossFunding.py": "893f43c5b81cc2e9ab5e2e8f70ad461ea8f18345",
    "GeneticEngineV1.py": "99a11d0b8d53711c75984356c7e59cfd52c8de3b",
    "strategies/e0v1e/E0V1E.py": "1c04d59421ebd4a9779c554064625c38d4989da5",
    "strategies/e0v1e/E0V1E.json": "ce7a8fb846b47d91f7b365779a35c46bb48205b7",
    "config/config.json": "e6f930f1476c8aebc8a3a7f6100e431f711b5fe3",
}

ADDENDUM_COMMITS = {
    "btc_strategy_lab": "b68a5518b4a3eba2fde1733160d7d7de356023b5",
    "kronos_gauntlet": "67a47713be6e9ec1ec279640f9ef2e0340ee91eb",
    "genetic_engine_v1": "937fefc25ef209120fa2a59d2f520f52d991f26b",
    "e0v1e_historical": "ebc58b15c279d20d923c38bd2691d34f8be0aaa5",
}


@pytest.fixture(scope="module")
def pins() -> dict:
    return json.loads((EXTERNAL / "upstream_pins.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def registry() -> dict:
    return json.loads((EXTERNAL / "candidate_registry.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def claims() -> dict:
    return json.loads((EXTERNAL / "claims_snapshot.json").read_text(encoding="utf-8"))


def all_files(pins: dict):
    for key, source in pins["sources"].items():
        for entry in source.get("files", []):
            yield key, source, entry


def test_git_blob_sha1_matches_git(tmp_path):
    """Our blob hash must be git's, or every cross-check against GitHub is meaningless."""
    assert pin.git_blob_sha1(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"

    payload = b"funding_max_pct = 55\n"
    expected = subprocess.run(
        ["git", "hash-object", "--stdin"], input=payload, capture_output=True, check=True
    ).stdout.decode().strip()
    assert pin.git_blob_sha1(payload) == expected


def test_every_addendum_commit_is_pinned_unchanged(pins):
    for key, commit in ADDENDUM_COMMITS.items():
        assert pins["sources"][key]["commit"] == commit, (
            f"{key} is pinned to a different commit than the addendum fixed. "
            "Re-pinning after seeing a result is forbidden by directive v1.1 section 7."
        )


def test_every_addendum_blob_sha_is_carried(pins):
    seen = {
        entry["path"]: entry.get("git_blob_sha1")
        for _, _, entry in all_files(pins)
        if entry["path"] in ADDENDUM_BLOB_SHAS
    }
    assert seen == ADDENDUM_BLOB_SHAS


def test_every_present_file_has_a_content_hash(pins):
    for key, _, entry in all_files(pins):
        if entry.get("expect_missing"):
            assert "sha256" not in entry, f"{key}:{entry['path']} is pinned absent but carries a hash"
        else:
            assert len(entry.get("sha256", "")) == 64, f"{key}:{entry['path']} has no sha256"


def test_no_source_is_authorised_for_vendoring(pins):
    """No directive has authorised copying any of this into the tree."""
    for key, source, _ in all_files(pins):
        assert source["license"]["vendoring_authorised"] is False, key


def test_unlicensed_sources_are_marked_and_expect_no_license_file(pins):
    """A source with no license grants no copying rights, so the pin must say so."""
    for key, source, _ in all_files(pins):
        licence = source["license"]
        if licence["spdx"] is None:
            assert licence["license_file_present"] is False, key
            license_entries = [
                entry for _, s, entry in all_files(pins)
                if s is source and entry["path"] == "LICENSE"
            ]
            assert license_entries, f"{key} claims no license but never checks for one"
            assert license_entries[0].get("expect_missing") is True, key


def test_frozen_configuration_hashes_match_the_pin_manifest(registry, pins):
    by_path = {(key, entry["path"]): entry.get("sha256") for key, _, entry in all_files(pins)}
    configs = {c["configuration_id"]: c for c in registry["hypothesis_families"][0]["frozen_configurations"]}
    assert configs["H1_EMACROSS"]["strategy_sha256"] == by_path[
        ("btc_strategy_lab", "user_data/strategies/EmaCross.py")]
    assert configs["H2_EMACROSSFUNDING"]["strategy_sha256"] == by_path[
        ("btc_strategy_lab", "user_data/strategies/EmaCrossFunding.py")]

    demoted = {c["candidate_id"]: c for c in registry["claim_and_method_reference_track"]["candidates"]}
    assert demoted["GENETICENGINEV1_CLAIM_CHALLENGE"]["strategy_sha256"] == by_path[
        ("genetic_engine_v1", "GeneticEngineV1.py")]


def test_claims_snapshot_readme_hashes_match_the_pin_manifest(claims, pins):
    by_source_readme = {}
    for key, _, entry in all_files(pins):
        if entry["path"].endswith("README.md"):
            by_source_readme.setdefault(key, entry.get("sha256"))

    for claim_key, source_key in [
        ("btc_strategy_lab", "btc_strategy_lab"),
        ("genetic_engine_v1", "genetic_engine_v1"),
        ("kronos_gauntlet", "kronos_gauntlet"),
        ("postmortem", "postmortem_negative_control"),
        ("e0v1e", "e0v1e_historical"),
    ]:
        assert claims[claim_key]["readme_sha256"] == by_source_readme[source_key], claim_key


def test_params_files_are_pinned_for_both_btclab_candidates(pins):
    """Freqtrade auto-loads <Strategy>.json. Omitting it tests different rules than the
    published claim: EmaCrossFunding.py defaults funding_max_pct to 90, its params file
    pins the README's 55."""
    paths = {entry["path"] for key, _, entry in all_files(pins) if key == "btc_strategy_lab"}
    assert "user_data/strategies/EmaCross.json" in paths
    assert "user_data/strategies/EmaCrossFunding.json" in paths


def test_no_upstream_source_is_committed_to_this_repository():
    """The whole point of pinning by hash is that we never carry the code."""
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    forbidden = {
        "EmaCross.py", "EmaCrossFunding.py", "GeneticEngineV1.py", "E0V1E.py",
        "E0V1E.json", "EmaCross.json", "EmaCrossFunding.json",
    }
    offenders = [p for p in tracked if Path(p).name in forbidden]
    assert not offenders, f"upstream source committed into the tree: {offenders}"


def test_registry_records_the_sprint_as_gated(registry):
    """Registration is pre-execution work. The gate must stay recorded as unmet until
    the BASELINE-1 closure commit is actually an ancestor of main."""
    activation = registry["sprint_activation"]
    assert "1dfb69604bb87856b75c8c90957f2acc8e1fab7f" in activation["requirement"]
    assert registry["invariants"]["real_money_authorized"] is False


# --- pre-registration invariants -------------------------------------------------
#
# A threshold chosen after seeing a result is commentary, not a threshold. These
# assert that the gates stay declared-in-advance and that they keep judging every
# candidate on the same scale the frozen control already faced.


@pytest.fixture(scope="module")
def gates() -> dict:
    return json.loads((EXTERNAL / "qualification_gates.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ablations() -> dict:
    return json.loads((EXTERNAL / "ablation_registry.json").read_text(encoding="utf-8"))


def test_gates_and_ablations_declare_themselves_pre_result(gates, ablations):
    assert gates["pre_registered_before_any_candidate_result"] is True
    assert ablations["pre_registered_before_any_candidate_result"] is True


def test_baseline_1_bands_are_a_lab_reference_not_a_universal_threshold(gates):
    """Sprint v1.3 section 17. The bands were calibrated on a 1h BTC+ETH long-only spot
    reference; applying them to a materially different strategy measures the difference
    in universe and exposure and calls it a verdict on the strategy."""
    pc = gates["performance_classification"]
    bands = pc["baseline_1_reference_bands"]
    assert "not a universal kill threshold" in bands["status"].lower()
    assert "own asset, universe, timeframe, exposure" in pc["rule"].lower()
    assert "inherited_without_change" not in gates, "the superseded inherit-verbatim block is gone"
    # the numeric bands are retained, just demoted
    assert bands["WEAK"] == "E < -10 pp OR profit factor < 0.8"


def test_each_candidate_gets_controls_from_its_own_universe(gates):
    controls = " ".join(gates["performance_classification"]["required_controls_per_candidate"]).lower()
    assert "own universe" in controls and "exposure-matched passive" in controls


def test_verdict_model_keeps_validity_and_quality_separate(gates):
    """A validly measured loser is a complete result, not a broken experiment."""
    model = gates["verdict_model"]
    assert set(model["MEASUREMENT_VALIDITY"]["values"]) == {"PASS", "FAIL", "BLOCKED"}
    assert set(model["CANDIDATE_QUALITY"]["values"]) == {
        "PASS", "FAIL", "FRAGILE", "DOMINATED", "INCONCLUSIVE"
    }
    assert "do NOT" in model["CANDIDATE_QUALITY"]["critical_rule"]


def test_every_gate_is_actionable(gates):
    for gate in gates["validity_gates"]["gates"]:
        assert gate["id"] and gate["question"] and gate["method"] and gate["fail_rule"]
        assert isinstance(gate["kill"], bool)


def test_the_gates_that_must_kill_do_kill(gates):
    """Source identity, safety, data integrity and lookahead are not advisory."""
    kills = {g["id"] for g in gates["validity_gates"]["gates"] if g["kill"]}
    assert {
        "V1_REPRODUCTION_IDENTITY",
        "V2_LOAD_AND_CONFIG",
        "V3_SAFETY_COMPATIBILITY",
        "V4_DATA_INTEGRITY",
        "V5_LOOKAHEAD",
        "V6_REALISTIC_COSTS",
        "V3B_EXECUTION_RIGHTS",
        "V7_WINDOW_PARITY",
    } <= kills


def test_prohibited_list_keeps_the_directive_s_hard_noes(gates):
    joined = " ".join(gates["prohibited"]).lower()
    assert "win rate as a primary success metric" in joined
    assert "raw return" in joined
    assert "validation" in joined


def test_funding_ablation_cannot_run_on_a_substitute_series(ablations):
    """A different settlement convention would silently change the component."""
    funding = next(a for a in ablations["ablations"] if a["ablation_id"] == "ABL_FUNDING_FILTER")
    assert funding["status"] == "PRE_REGISTERED_NOT_RUN"
    assert funding["predeclared_primary_axis"].startswith("max drawdown")
    assert "not approximated with a substitute series" in funding["kill_condition"]
    assert any("params files" in p for p in funding["prerequisites"])


# --- pre-Wave-1 review corrections -----------------------------------------------


def test_reproduction_identity_pins_every_component(registry):
    """Sprint v1.3 section 5 plus the addendum: nine components, not a source SHA."""
    required = {
        "strategy_source", "parameter_files", "config", "engine_version", "data_contract",
        "fee_model", "pair_universe", "timeframe", "position_semantics",
        "data_cutoff", "execution_invocation", "environment_overrides",
    }
    configs = registry["hypothesis_families"][0]["frozen_configurations"]
    assert configs, "fixture sanity: the family must carry frozen configurations"
    for config in configs:
        missing = required - set(config["reproduction_identity"])
        assert not missing, f"{config['configuration_id']} missing {missing}"


def test_executable_family_is_licensed(registry, pins):
    """V3B_EXECUTION_RIGHTS: a source with no recognised license leaves this lane."""
    unlicensed = {k for k, s in pins["sources"].items() if s["license"]["spdx"] is None}
    assert unlicensed, "fixture sanity: some pinned sources are expected to be unlicensed"
    unlicensed_projects = {pins["sources"][k]["project"].split(" (")[0] for k in unlicensed}

    executable_projects = {f["project"] for f in registry["hypothesis_families"]}
    executable_projects.add(registry["negative_control"]["project"])
    assert not (executable_projects & unlicensed_projects)
    assert registry["hypothesis_families"][0]["license"] == "GPL-3.0"


def test_no_license_candidates_are_demoted_not_deleted(registry):
    """Demotion is a rights finding. Reading and method extraction continue."""
    demoted = {c["candidate_id"] for c in registry["claim_and_method_reference_track"]["candidates"]}
    assert {
        "GENETICENGINEV1_CLAIM_CHALLENGE",
        "E0V1E_NATIVE_HISTORICAL_RECONSTRUCTION",
    } <= demoted
    for candidate in registry["claim_and_method_reference_track"]["candidates"]:
        assert candidate["track"] == "CLAIM_AND_METHOD_REFERENCE"
        assert "rights" in candidate["demotion_reason"].lower()
        assert "priority_order" not in candidate


def test_same_hour_funding_is_not_presumed_to_be_lookahead(gates):
    """The correction: prove funding_available_at <= signal_decision_time, do not
    treat a shared timestamp as guilt."""
    v5 = next(g for g in gates["validity_gates"]["gates"] if g["id"] == "V5_LOOKAHEAD")
    special = v5["special_case_funding"]
    assert "NOT automatically lookahead" in special
    assert "funding_available_at <= signal_decision_time" in special
    assert "STRICT_1H_DELAY" in special


def test_warmup_gate_forbids_lowering_the_declared_startup_count(gates):
    v7 = next(g for g in gates["validity_gates"]["gates"] if g["id"] == "V7_WINDOW_PARITY")
    assert v7["kill"] is True
    assert "never mutating Dataset V2" in v7["note"]
    assert "never lowering" in v7["note"]


def test_overlay_gate_is_candle_count_not_calendar_date():
    """Sprint v1.3 section 8.2: the date is the intent, the count is the gate."""
    lock = json.loads(
        (REPO_ROOT / "research" / "datasets" / "warmup_overlay.lock.json").read_text(encoding="utf-8")
    )
    assert lock["dataset_id"] == "dataset_v2_benchmark_warmup_overlay_v1"
    assert "not the requirement" in lock["gate_is_candle_count_not_calendar"]
    assert lock["warmup_budget"]["total_before_first_scored_candle"] >= 1300
    proofs = " ".join(lock["canonical_identity_gate"]["per_run_proofs"])
    assert "byte-identical" in proofs and "strictly pre-score" in proofs
    assert lock["overlap_policy"]["policy"] == "DISJOINT_BY_CONSTRUCTION"


# --- final pre-execution addendum -------------------------------------------------


def test_evaluation_lanes_are_not_counted_as_candidates(registry):
    """Re-evaluating one frozen configuration five ways is not five candidates."""
    family = registry["hypothesis_families"][0]
    configs = family["frozen_configurations"]
    assert [c["configuration_id"] for c in configs] == ["H1_EMACROSS", "H2_EMACROSSFUNDING"]
    assert all(c["counts_as_tested_configuration"] for c in configs)
    # the lanes exist, but live under a configuration rather than beside it
    assert len(configs[0]["evaluation_lanes"]) >= 4
    assert registry["candidates"] == []


def test_local_trial_count_counts_configurations_not_lanes(registry):
    accounting = registry["multiple_testing_accounting"]
    assert accounting["LOCAL_TRIAL_COUNT"]["value"] == 2
    assert "not an additional trial" in accounting["LOCAL_TRIAL_COUNT"]["excluded"]


def test_dsr_pbo_may_not_be_certified_from_local_trial_count(registry):
    """The configurations arrive pre-selected from a 42-way benchmark and a 21-point sweep."""
    total = registry["multiple_testing_accounting"]["TOTAL_SELECTION_PROVENANCE"]
    assert total["status"] == "PARTIALLY_DOCUMENTED"
    assert "Do NOT claim DSR or PBO certification from LOCAL_TRIAL_COUNT alone" in total["hard_rule"]
    debt = registry["multiple_testing_accounting"]["UPSTREAM_SELECTION_DEBT"]["basis"]
    assert any("42-strategy benchmark" in b for b in debt)


def test_negative_control_is_not_survivor_eligible(registry):
    assert registry["negative_control"]["survivor_eligible"] is False


def test_claim_snapshot_is_separated_from_current_replay(registry):
    """The upstream command is open-ended, so a run today is not the historical claim."""
    lanes = {
        lane["lane_id"]: lane
        for lane in registry["hypothesis_families"][0]["frozen_configurations"][0]["evaluation_lanes"]
    }
    assert "CLAIM_SNAPSHOT_RECONSTRUCTION" in lanes and "CURRENT_NATIVE_REPLAY" in lanes
    snapshot = lanes["CLAIM_SNAPSHOT_RECONSTRUCTION"]
    assert snapshot["data_cutoff"].startswith("UNKNOWN")
    assert "BELOW_EXACT" in snapshot["reproduction_grade_ceiling"]
    assert "NOT an exact reproduction" in snapshot["rule"]


def test_funding_parameter_selection_is_only_partially_documented(registry):
    """55 is the published value but is absent from the public sweep grid."""
    h2 = registry["hypothesis_families"][0]["frozen_configurations"][1]
    provenance = h2["parameter_provenance"]
    assert provenance["EXECUTION_PARAMETER_PROVENANCE"] == "VERIFIED"
    assert provenance["PARAMETER_SELECTION_PROVENANCE"] == "PARTIALLY_DOCUMENTED"
    assert "[40, 50, 60, 70, 80, 90, 100]" in provenance["selection_evidence"]
    assert "55 is NOT in that grid" in provenance["selection_evidence"]
    assert "Do not invent missing sweep evidence" in provenance["rule"]


def test_identity_records_cutoff_invocation_and_overrides(registry):
    """The upstream headline passes --fee 0.001 by CLI, so command identity is load-bearing."""
    for config in registry["hypothesis_families"][0]["frozen_configurations"]:
        identity = config["reproduction_identity"]
        assert {"data_cutoff", "execution_invocation", "environment_overrides"} <= set(identity)
        assert "--fee 0.001" in identity["execution_invocation"]
        assert "--timerange 20191001-" in identity["execution_invocation"]


def test_h1_is_not_blocked_on_funding_availability(registry):
    """Sprint v1.3 section 9: Track A and Track B run in parallel."""
    opening = registry["execution_order"]["parallel_opening"]
    assert "never blocks" in opening["track_B"]
    assert "immediately" in opening["track_A"]


def test_eth_generalization_is_a_lane_and_failure_classifies_rather_than_kills(registry):
    lanes = {
        lane["lane_id"]: lane
        for lane in registry["hypothesis_families"][0]["frozen_configurations"][0]["evaluation_lanes"]
    }
    eth = lanes["ETH_GENERALIZATION_CHALLENGE"]
    assert "does NOT automatically kill" in eth["rule"]
    assert set(eth["outcomes"]) == {"BTC_SPECIALIST", "UNIVERSAL", "PAIR_SPECIFIC"}


def test_mature_feature_truncates_both_sides_of_the_ablation():
    """Comparing a truncated H2 against a full-period H1 would read as a component effect."""
    reg = json.loads(
        (EXTERNAL / "ablation_registry.json").read_text(encoding="utf-8")
    )
    mature = next(
        s for s in reg["ablations"][0]["sensitivities"] if s["id"] == "MATURE_FEATURE"
    )
    assert mature["comparison"] == "H1_MATURE_INTERVAL vs H2_MATURE_INTERVAL"
    assert mature["forbidden"] == "truncated H2 vs full-period H1"
