"""Compose / stack shape tests.

These run without a Docker daemon: the structural assertions read the YAML
directly, and the renderer test shells out to ``docker compose config`` only when
the CLI is present. Nothing here pulls an image or starts a container.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest
import yaml

CI_DUMMY_ENV = {
    "FREQTRADE_API_USER": "ci_dummy_user",
    "FREQTRADE_API_PASSWORD": "ci_dummy_password",
    "FREQTRADE_JWT_SECRET": "ci_dummy_jwt_secret",
    "FREQTRADE_WS_TOKEN": "ci_dummy_ws_token",
    "GRAFANA_ADMIN_USER": "ci_admin",
    "GRAFANA_ADMIN_PASSWORD": "ci_dummy_grafana_password",
}


@pytest.fixture(scope="module")
def compose(request):
    root = request.config.rootpath
    return yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))


def test_expected_services_are_declared(compose):
    assert set(compose["services"]) == {
        "freqtrade",
        "mlflow",
        "freqtrade-exporter",
        "prometheus",
        "grafana",
    }


def test_every_published_port_is_bound_to_localhost(compose):
    for name, service in compose["services"].items():
        for mapping in service.get("ports", []):
            assert str(mapping).startswith("127.0.0.1:"), (
                f"{name} publishes {mapping} beyond localhost"
            )


def test_no_service_is_privileged_or_shares_the_host_network(compose):
    for name, service in compose["services"].items():
        assert not service.get("privileged"), f"{name} is privileged"
        assert service.get("network_mode") != "host", f"{name} uses host networking"
        assert not service.get("cap_add"), f"{name} adds capabilities"


def test_no_credential_is_hardcoded_in_compose(compose, request):
    text = (request.config.rootpath / "docker-compose.yml").read_text(encoding="utf-8")
    for service in compose["services"].values():
        for key, value in (service.get("environment") or {}).items():
            upper = key.upper()
            sensitive = any(hint in upper for hint in ("PASSWORD", "SECRET", "TOKEN")) or upper.endswith(
                ("_USER", "USERNAME")
            )
            if sensitive:
                assert str(value).startswith("${"), f"{key} must come from the environment"
    assert "CHANGE_ME" not in text


def test_freqtrade_runs_the_committed_paper_config_and_no_live_flags(compose):
    command = " ".join(str(compose["services"]["freqtrade"]["command"]).split())
    assert "--config /freqtrade/user_data/config.json" in command
    for forbidden in ("--dry-run false", "dry_run=false", "--leverage", "futures", "margin"):
        assert forbidden not in command


def test_exporter_receives_no_exchange_credentials(compose):
    env = compose["services"]["freqtrade-exporter"]["environment"]
    for key in env:
        assert "EXCHANGE" not in key.upper(), f"exporter must not see {key}"


def test_prometheus_and_grafana_mounts_are_read_only(compose):
    for name in ("prometheus", "grafana"):
        for mount in compose["services"][name].get("volumes", []):
            if isinstance(mount, str) and mount.startswith("./"):
                assert mount.endswith(":ro"), f"{name} mounts {mount} writable"


def test_images_are_pinned_to_explicit_versions(compose):
    """Every image resolves to an explicit tag, including the ${VAR:-default} form."""
    import re

    for name, service in compose["services"].items():
        image = service.get("image")
        if image is None:
            assert "build" in service, f"{name} has neither image nor build"
            continue
        match = re.fullmatch(r"\$\{[A-Z_][A-Z0-9_]*:-(?P<default>[^}]+)\}", image)
        resolved = match.group("default") if match else image
        assert "${" not in resolved, f"{name} has no default image tag: {image}"
        assert ":" in resolved and not resolved.endswith(":latest"), f"{name} is not pinned: {image}"


def test_env_example_covers_every_variable_compose_requires(compose, request):
    text = (request.config.rootpath / "docker-compose.yml").read_text(encoding="utf-8")
    import re

    referenced = {m.group(1) for m in re.finditer(r"\$\{([A-Z_][A-Z0-9_]*)", text)}
    example = (request.config.rootpath / ".env.example").read_text(encoding="utf-8")
    declared = {line.split("=", 1)[0].strip() for line in example.splitlines() if "=" in line and not line.startswith("#")}
    missing = referenced - declared
    assert not missing, f".env.example is missing: {sorted(missing)}"


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not available")
def test_compose_config_renders_with_dummy_local_values(request):
    import os

    env = {**os.environ, **CI_DUMMY_ENV}
    result = subprocess.run(
        ["docker", "compose", "config"],
        cwd=str(request.config.rootpath),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rendered = yaml.safe_load(result.stdout)
    assert rendered["services"]["freqtrade"]["environment"]["FREQTRADE__API_SERVER__USERNAME"] == "ci_dummy_user"
