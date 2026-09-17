"""The FP-CONTROL-1 compose overlay guard.

The overlay decides what the forward-paper control actually runs. These tests
exist because a guard that cannot fail is not a guard: each one injects the
specific defect the check claims to catch, and requires it to be caught.
"""

from __future__ import annotations

import copy

import pytest
import yaml

import check_fp_overlay

# The role the guard is asked about. FP-CONTROL-1 is closed, so the only
# instance a rendered stack may describe is the pre-T0 successor.
ROLE = "FP-CONTROL-2"
LANE = "/freqtrade/user_data/fp-control-2"

SAFE = {
    "services": {
        "freqtrade": {
            "command": [
                "trade",
                "--logfile", f"{LANE}/logs/freqtrade.log",
                "--db-url", f"sqlite:///{LANE}/tradesv3.sqlite",
                "--config", "/freqtrade/user_data/config.json",
                "--strategy", "BaselineEmaRegimeV1",
            ],
            "environment": {
                "FREQTRADE__API_SERVER__JWT_SECRET_KEY": "local-only",
                "FREQTRADE__BOT_NAME": "fp-control-2",
            },
            "volumes": [
                {"source": "./freqtrade/user_data", "target": "/freqtrade/user_data", "read_only": True},
                {"source": "./freqtrade/user_data/fp-control-2", "target": LANE, "read_only": False},
            ],
        },
        "fp-capture": {
            "command": [
                "python", "/app/research/fp/capture.py",
                f"--role={ROLE}", f"--evidence-dir={LANE}/evidence",
            ],
            "volumes": [
                {"source": "./research", "target": "/app/research", "read_only": True},
                {"source": "./freqtrade", "target": "/app/freqtrade", "read_only": True},
                {
                    "source": "./freqtrade/user_data/fp-control-2",
                    "target": LANE,
                    "read_only": False,
                },
            ],
        },
    }
}


@pytest.fixture
def rendered() -> dict:
    return copy.deepcopy(SAFE)


def test_the_safe_overlay_passes(rendered):
    assert check_fp_overlay.check(rendered, ROLE) == []


def test_local_api_secrets_are_not_mistaken_for_exchange_credentials(rendered):
    """The stack passes its own REST-API secrets between services legitimately."""
    rendered["services"]["freqtrade"]["environment"]["FREQTRADE__API_SERVER__PASSWORD"] = "x"
    assert check_fp_overlay.check(rendered, ROLE) == []


def test_the_smoke_strategy_is_rejected(rendered):
    command = rendered["services"]["freqtrade"]["command"]
    command[command.index("BaselineEmaRegimeV1")] = "PlumbingSmokeStrategy"
    problems = check_fp_overlay.check(rendered, ROLE)
    assert any("BASELINE-1" in p for p in problems)
    assert any("smoke strategy" in p for p in problems)


def test_shared_paths_are_rejected(rendered):
    """The control must not write into the base stack's database."""
    rendered["services"]["freqtrade"]["command"] = [
        "trade", "--db-url", "sqlite:////freqtrade/user_data/tradesv3.sqlite",
        "--strategy", "BaselineEmaRegimeV1",
    ]
    problems = check_fp_overlay.check(rendered, ROLE)
    # The guard now names the declared path it did not find, which is a more
    # precise complaint than "isolated paths" was.
    assert any("declared db_path" in p or "writes outside" in p for p in problems), problems


def test_a_writable_code_mount_is_rejected(rendered):
    rendered["services"]["fp-capture"]["volumes"][0]["read_only"] = False
    problems = check_fp_overlay.check(rendered, ROLE)
    assert any("writable mount" in p for p in problems)


def test_a_missing_capture_service_is_rejected(rendered):
    del rendered["services"]["fp-capture"]
    problems = check_fp_overlay.check(rendered, ROLE)
    assert any("no fp-capture" in p for p in problems)


@pytest.mark.parametrize("endpoint", ["forcebuy", "forceenter", "forcesell", "forceexit"])
def test_an_execution_endpoint_anywhere_is_rejected(rendered, endpoint):
    rendered["services"]["freqtrade"]["command"].append(f"--{endpoint}")
    problems = check_fp_overlay.check(rendered, ROLE)
    assert any(endpoint in p for p in problems)


def test_an_exchange_credential_is_rejected(rendered):
    rendered["services"]["freqtrade"]["environment"]["BINANCE_API_SECRET"] = "nope"
    problems = check_fp_overlay.check(rendered, ROLE)
    assert any("exchange credential" in p for p in problems)


def test_a_live_trading_flag_is_rejected(rendered):
    rendered["services"]["freqtrade"]["command"].extend(["--dry-run", "false"])
    problems = check_fp_overlay.check(rendered, ROLE)
    assert any("live-trading flag" in p for p in problems)


# -- the committed overlay file itself -------------------------------------


def test_the_committed_overlay_declares_baseline_and_the_capture_loop(repo_root):
    overlay = yaml.safe_load((repo_root / "docker-compose.fp.yml").read_text(encoding="utf-8"))
    services = overlay["services"]
    assert "fp-capture" in services
    assert "BaselineEmaRegimeV1" in services["freqtrade"]["command"]
    assert "PlumbingSmokeStrategy" not in services["freqtrade"]["command"]


def test_the_overlay_paths_match_the_frozen_registry(repo_root):
    """The overlay and the registry must not drift apart.

    If they do, the runtime writes its database somewhere the registry does not
    describe, and preflight's hash and isolation checks are comparing against a
    declaration that no longer refers to the running instance.
    """
    import json

    overlay = yaml.safe_load((repo_root / "docker-compose.fp.yml").read_text(encoding="utf-8"))
    registry = json.loads(
        (repo_root / "research" / "fp" / "records" / "forward_paper_cohort_registry.json").read_text(
            encoding="utf-8"
        )
    )
    # The overlay is parameterised by the instance the launcher selects, so the
    # check is that it *renders* onto the selected instance's declared paths —
    # a template that drifted would land the runtime somewhere the registry
    # never described, which is the drift this test exists to catch.
    instance = next(i for i in registry["instances"] if i["role"] == ROLE)
    identity = instance["runtime_identity"]
    # The subject here is path drift between the overlay template and the
    # registry, which is a question about the declared paths and not about the
    # instance's status. Requiring NOT_STARTED made this test fail the moment a
    # lawful T0 was frozen, on a claim it was never making.
    assert instance["status"] in ("NOT_STARTED", "RUNNING"), instance["status"]
    instance_dir = identity["evidence_dir"].rsplit("/", 2)[-2]

    # The variables are required-with-message (`${VAR:?...}`), so the overlay
    # refuses to render at all when no instance has been selected. Substituting
    # them here mimics what compose does once the launcher has selected one.
    import re as _re

    values = {
        "FP_INSTANCE_DIR": instance_dir,
        "FP_BOT_NAME": identity["bot_name"],
        "FP_ROLE": instance["role"],
        "FP_DB_PATH": identity["db_path"],
        "FP_LOG_PATH": identity["log_path"],
        "FP_EVIDENCE_DIR": identity["evidence_dir"],
    }

    def render(text: str) -> str:
        def substitute(match):
            return values[match.group(1)]

        return _re.sub(r"\$\{(FP_INSTANCE_DIR|FP_BOT_NAME|FP_ROLE|FP_DB_PATH|FP_LOG_PATH|FP_EVIDENCE_DIR)(?::\?[^}]*)?\}", substitute, text)

    raw_overlay = (repo_root / "docker-compose.fp.yml").read_text(encoding="utf-8")
    for variable in ("FP_ROLE", "FP_INSTANCE_DIR", "FP_BOT_NAME", "FP_DB_PATH", "FP_LOG_PATH"):
        assert f"${{{variable}:?" in raw_overlay, (
            f"{variable} must be required, not defaulted: an unset variable renders an unnamed lane "
            "with the whole of user_data writable"
        )

    command = render(overlay["services"]["freqtrade"]["command"])
    assert identity["db_path"] in command
    assert identity["log_path"] in command

    capture_command = render(" ".join(overlay["services"]["fp-capture"]["command"]))
    assert identity["evidence_dir"] in capture_command
    assert "--role=FP-CONTROL-2" in capture_command, "the capture service must name its instance explicitly"

    # And the closed instance's paths must appear nowhere in the template.
    closed = next(i for i in registry["instances"] if i["role"] == "FP-CONTROL-1")["runtime_identity"]
    raw = (overlay["services"]["freqtrade"]["command"]
           + " ".join(overlay["services"]["fp-capture"]["command"]))
    assert closed["evidence_dir"] not in raw
    assert closed["db_path"] not in raw


def test_the_capture_service_never_restarts_into_a_different_strategy(repo_root):
    overlay = yaml.safe_load((repo_root / "docker-compose.fp.yml").read_text(encoding="utf-8"))
    capture = overlay["services"]["fp-capture"]
    # It must come back by itself: the runtime has to survive the session that
    # started it.
    assert capture["restart"] == "unless-stopped"
    container = overlay["services"]["freqtrade"].get("container_name") or ""
    assert container.startswith("tradinglab-${FP_BOT_NAME"), container
    assert container.endswith("-freqtrade"), container
