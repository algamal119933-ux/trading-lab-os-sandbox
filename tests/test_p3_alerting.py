"""P3 PLN-06 §19 alert leg: rules, ops-plane compose and Alertmanager template, checked offline.

No container, exporter or network is touched. The rules may only read metrics the health job
actually emits (or node-exporter's own textfile metrics); the ops plane must stay loopback-only,
pinned and secret-free; the Alertmanager template must send nothing until the Owner chooses a
channel. When `promtool` / `amtool` are on PATH (or named by $PROMTOOL / $AMTOOL), the upstream
validators and the promtool rule unit tests run as well.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))

from p3 import health  # noqa: E402

P3 = REPO / "scripts" / "p3" / "ops"
RULES = P3 / "rules" / "tlos_p3_alerts.yml"
RULE_TESTS = P3 / "rules" / "tlos_p3_alerts.test.yml"
PROM = P3 / "prometheus.yml"
AM_TEMPLATE = P3 / "alertmanager.yml.template"
COMPOSE = P3 / "docker-compose.p3-ops.yml"
SCHEDULED_HEALTH = REPO / "scripts" / "p3" / "scheduled_health.sh"

NODE_EXPORTER_METRICS = {"node_textfile_mtime_seconds", "node_textfile_scrape_error", "up"}
PROMQL_WORDS = {"time", "absent", "vector", "and", "or", "unless", "by", "without", "on", "ignoring",
                "sum", "max", "min", "count", "rate", "increase", "offset", "bool"}


def _load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _rules() -> list[dict]:
    return [r for g in _load(RULES)["groups"] for r in g["rules"]]


def _metric_names(expr: str) -> set[str]:
    expr = re.sub(r'\{[^}]*\}', "", expr)          # drop label matchers
    expr = re.sub(r'"[^"]*"', "", expr)            # drop strings
    names = set(re.findall(r"[a-zA-Z_:][a-zA-Z0-9_:]*", expr))
    return {n for n in names if n not in PROMQL_WORDS and not n.isdigit()}


def _emitted_metrics() -> set[str]:
    text = health.prometheus_text([{"check": "x", "severity": health.CRITICAL, "detail": ""}])
    return {line.split("{")[0].split(" ")[0] for line in text.splitlines() if line and not line.startswith("#")}


def _tool(name: str) -> str | None:
    return os.environ.get(name.upper()) or shutil.which(name)


# ---------------------------------------------------------------- rules


def test_every_rule_metric_is_actually_emitted():
    allowed = _emitted_metrics() | NODE_EXPORTER_METRICS
    for rule in _rules():
        unknown = _metric_names(rule["expr"]) - allowed
        assert not unknown, f"{rule['alert']} reads metrics nobody emits: {unknown}"


def test_severity_thresholds_match_the_health_encoding():
    by_name = {r["alert"]: r for r in _rules()}
    crit = health.SEVERITY_VALUE[health.CRITICAL]
    warn = health.SEVERITY_VALUE[health.WARNING]
    assert by_name["TLOSHealthCritical"]["expr"].strip() == f"tlos_p3_health_check == {crit}"
    assert by_name["TLOSHealthCritical"]["labels"]["severity"] == "critical"
    assert by_name["TLOSHealthWarning"]["expr"].strip() == f"tlos_p3_health_check == {warn}"
    assert by_name["TLOSHealthWarning"]["labels"]["severity"] == "warning"


def test_every_rule_carries_a_known_severity_and_summary():
    for rule in _rules():
        assert rule["labels"]["severity"] in {"critical", "warning", "none"}, rule["alert"]
        assert rule["annotations"]["summary"], rule["alert"]


def test_staleness_rules_match_the_textfile_the_health_job_writes():
    default = re.search(r'TLOS_HEALTH_TEXTFILE:-([^}]+)\}', SCHEDULED_HEALTH.read_text(encoding="utf-8")).group(1)
    name = Path(default).name
    for alert in ("TLOSHealthTextfileStale", "TLOSHealthTextfileMissing"):
        expr = next(r["expr"] for r in _rules() if r["alert"] == alert)
        pattern = re.search(r'file=~"([^"]+)"', expr).group(1).replace("\\\\", "\\")
        assert re.fullmatch(pattern, default), (alert, pattern, default)
        assert name in pattern.replace("\\.", ".")


def test_stale_threshold_allows_one_missed_hourly_run_but_not_two():
    expr = next(r["expr"] for r in _rules() if r["alert"] == "TLOSHealthTextfileStale")
    seconds = int(re.search(r">\s*(\d+)", expr).group(1))
    assert 3600 < seconds and seconds < 3 * 3600


def test_watchdog_always_fires_and_has_no_paging_severity():
    rule = next(r for r in _rules() if r["alert"] == "TLOSWatchdog")
    assert rule["expr"].strip() == "vector(1)"
    assert rule["labels"]["severity"] == "none"


# ---------------------------------------------------------------- prometheus config + compose


def test_prometheus_config_scrapes_only_loopback_and_loads_the_mounted_rules():
    cfg = _load(PROM)
    targets = [t for job in cfg["scrape_configs"] for sc in job["static_configs"] for t in sc["targets"]]
    assert targets == ["127.0.0.1:9100"]
    assert cfg["rule_files"] == ["/etc/prometheus/rules/tlos_p3_alerts.yml"]
    am = cfg["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"]
    assert am == ["127.0.0.1:9093"]


def test_ops_plane_compose_is_separate_pinned_loopback_and_secret_free():
    compose = _load(COMPOSE)
    assert compose["name"] == "tlos-p3-ops"
    services = compose["services"]
    assert set(services) == {"p3-prometheus", "p3-alertmanager"}
    fp_images = {s["image"] for s in _load(REPO / "docker-compose.yml")["services"].values() if "prometheus" in s.get("image", "")}
    assert services["p3-prometheus"]["image"] in fp_images, "reuse the FP stack's Prometheus image"
    for name, svc in services.items():
        image = svc["image"]
        assert re.search(r":v\d+\.\d+\.\d+$", image), f"{name} image not pinned: {image}"
        assert "ports" not in svc, f"{name} must not publish ports"
        assert svc["network_mode"] == "host"
        listen = [a for a in svc["command"] if a.startswith("--web.listen-address=")]
        assert listen and all(a.split("=", 1)[1].startswith("127.0.0.1:") for a in listen), name
        assert "environment" not in svc and "env_file" not in svc, f"{name} must not carry secrets in env"
        for vol in svc["volumes"]:
            if vol.startswith((".", "$")):
                assert vol.endswith(":ro"), f"config mounts are read-only: {vol}"
        assert svc["restart"] == "unless-stopped"
    am_cmd = services["p3-alertmanager"]["command"]
    assert "--cluster.listen-address=" in am_cmd, "no gossip listener"
    prom_vols = services["p3-prometheus"]["volumes"]
    assert "./rules:/etc/prometheus/rules:ro" in prom_vols
    assert "./prometheus.yml:/etc/prometheus/prometheus.yml:ro" in prom_vols


def test_ops_plane_has_no_trading_component():
    text = COMPOSE.read_text(encoding="utf-8").lower()
    for word in ("freqtrade", "dry_run", "api_key", "secret_key", "binance"):
        assert word not in text


def test_secrets_live_outside_every_backup_root():
    compose_text = COMPOSE.read_text(encoding="utf-8")
    assert "${HOME:?HOME must be set}/.config/tlos-p3-ops/secrets:/etc/alertmanager/secrets:ro" in compose_text
    backup = (REPO / "scripts" / "p3" / "scheduled_backup.sh").read_text(encoding="utf-8")
    roots = re.findall(r'--root [\w-]+="([^"]+)"', backup)
    assert roots and not any(".config" in r for r in roots)


# ---------------------------------------------------------------- alertmanager template


def test_alertmanager_template_sends_nothing_until_the_owner_chooses():
    cfg = _load(AM_TEMPLATE)
    assert cfg["route"]["receiver"] == "null"
    assert all(r["receiver"] == "null" for r in cfg["route"]["routes"])
    names = {r["name"] for r in cfg["receivers"]}
    assert {"null", "telegram", "ntfy", "deadman"} <= names


def test_alertmanager_template_holds_no_secret_material():
    text = AM_TEMPLATE.read_text(encoding="utf-8")
    assert "__TELEGRAM_CHAT_ID__" in text
    assert not re.search(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b", text), "a Telegram bot token"
    assert not re.search(r"https?://(?!127\.0\.0\.1)[^\s]*", re.sub(r"#.*", "", text)), "a live URL outside comments"
    cfg = _load(AM_TEMPLATE)
    for r in cfg["receivers"]:
        for tg in r.get("telegram_configs", []):
            assert "bot_token" not in tg and tg["bot_token_file"].startswith("/etc/alertmanager/secrets/")
        for wh in r.get("webhook_configs", []):
            assert "url" not in wh and wh["url_file"].startswith("/etc/alertmanager/secrets/")


def test_inhibition_only_mutes_the_textfile_consequences_of_a_paging_exporter_outage():
    rules = {r["alert"]: r for r in _rules()}
    inhibits = _load(AM_TEMPLATE)["inhibit_rules"]
    assert inhibits
    for inh in inhibits:
        sources = [re.fullmatch(r'alertname="([^"]+)"', m).group(1) for m in inh["source_matchers"]]
        assert sources and all(rules[s]["labels"]["severity"] == "critical" for s in sources), sources
        assert len(inh["target_matchers"]) == 1
        pattern = re.fullmatch(r'alertname=~"([^"]+)"', inh["target_matchers"][0]).group(1)
        muted = {a for a in rules if re.fullmatch(pattern, a)}
        assert muted == {"TLOSHealthTextfileStale", "TLOSHealthTextfileMissing", "TLOSTextfileScrapeError"}
        # the health alerts, the dead-man and the source itself are never muted
        assert not muted & {"TLOSHealthCritical", "TLOSHealthWarning", "TLOSWatchdog", "TLOSDeliveryTest", *sources}


def test_critical_repeats_faster_than_warning():
    routes = {tuple(r["matchers"]): r for r in _load(AM_TEMPLATE)["route"]["routes"]}
    crit = routes[('severity="critical"',)]["repeat_interval"]
    warn = routes[('severity="warning"',)]["repeat_interval"]
    hours = lambda s: int(s.rstrip("h"))  # noqa: E731
    assert hours(crit) < hours(warn)


# ---------------------------------------------------------------- upstream validators (when available)


@pytest.mark.skipif(not _tool("promtool"), reason="promtool not installed")
def test_promtool_rule_unit_tests_pass():
    out = subprocess.run([_tool("promtool"), "test", "rules", RULE_TESTS.name], cwd=RULE_TESTS.parent,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr


@pytest.mark.skipif(not _tool("promtool"), reason="promtool not installed")
def test_promtool_checks_rules_and_config(tmp_path):
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    shutil.copy(RULES, rules_dir / RULES.name)
    cfg = PROM.read_text(encoding="utf-8").replace("/etc/prometheus/rules", str(rules_dir))
    (tmp_path / "prometheus.yml").write_text(cfg, encoding="utf-8")
    out = subprocess.run([_tool("promtool"), "check", "config", str(tmp_path / "prometheus.yml")],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr


@pytest.mark.skipif(not _tool("amtool"), reason="amtool not installed")
def test_amtool_accepts_the_rendered_template(tmp_path):
    rendered = AM_TEMPLATE.read_text(encoding="utf-8").replace("__TELEGRAM_CHAT_ID__", "123456789")
    (tmp_path / "alertmanager.yml").write_text(rendered, encoding="utf-8")
    out = subprocess.run([_tool("amtool"), "check-config", str(tmp_path / "alertmanager.yml")],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr


# ---------------------------------------------------------------- routing after the Owner's choice (§3 steps 4 and 7)


def _owner_rendered(channel: str) -> dict:
    """The template as the runbook tells the Owner to edit it: critical and warning to the chosen channel,
    TLOSWatchdog to the dead-man. No secret is involved: receivers read *_file paths only."""
    cfg = yaml.safe_load(AM_TEMPLATE.read_text(encoding="utf-8").replace("__TELEGRAM_CHAT_ID__", "123456789"))
    for route in cfg["route"]["routes"]:
        route["receiver"] = "deadman" if route["matchers"] == ['alertname="TLOSWatchdog"'] else channel
    cfg["route"]["receiver"] = channel  # §3 step 4: the default too, so no alert can fall through to "null"
    return cfg


ROUTING_CASES = [  # (labels, receiver once the Owner has chosen)
    ({"alertname": "TLOSWatchdog", "severity": "none"}, "deadman"),
    ({"alertname": "TLOSHealthCritical", "severity": "critical", "check": "unexpected_writer"}, "CHANNEL"),
    ({"alertname": "TLOSHealthTextfileStale", "severity": "critical"}, "CHANNEL"),
    ({"alertname": "TLOSHealthWarning", "severity": "warning", "check": "unexpected_writer"}, "CHANNEL"),
    ({"alertname": "TLOSDeliveryTest", "severity": "critical", "check": "owner-test"}, "CHANNEL"),
    # an alert whose severity is missing or not one of ours must still reach the Owner, never "null"
    ({"alertname": "TLOSDeliveryTest", "check": "no-severity"}, "CHANNEL"),
    ({"alertname": "TLOSFutureRule", "severity": "info"}, "CHANNEL"),
]


def test_watchdog_route_comes_first_and_does_not_fall_through_to_a_paging_route():
    routes = _load(AM_TEMPLATE)["route"]["routes"]
    assert routes[0]["matchers"] == ['alertname="TLOSWatchdog"'] and not routes[0].get("continue", False)
    assert not any(r.get("continue", False) for r in routes)


@pytest.mark.skipif(not _tool("amtool"), reason="amtool not installed")
@pytest.mark.parametrize("channel", ["telegram", "ntfy"])
def test_amtool_routes_each_alert_to_the_intended_receiver_after_the_owner_choice(tmp_path, channel):
    cfg_path = tmp_path / "alertmanager.yml"
    cfg_path.write_text(yaml.safe_dump(_owner_rendered(channel), sort_keys=False), encoding="utf-8")
    assert subprocess.run([_tool("amtool"), "check-config", str(cfg_path)], capture_output=True, text=True,
                          timeout=120).returncode == 0
    for labels, want in ROUTING_CASES:
        want = channel if want == "CHANNEL" else want
        out = subprocess.run([_tool("amtool"), "config", "routes", "test", f"--config.file={cfg_path}",
                              f"--verify.receivers={want}", *(f"{k}={v}" for k, v in labels.items())],
                             capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, (labels, want, out.stdout + out.stderr)


@pytest.mark.skipif(not _tool("amtool"), reason="amtool not installed")
def test_amtool_routes_everything_to_null_until_the_owner_chooses(tmp_path):
    cfg_path = tmp_path / "alertmanager.yml"
    cfg_path.write_text(AM_TEMPLATE.read_text(encoding="utf-8").replace("__TELEGRAM_CHAT_ID__", "123456789"),
                        encoding="utf-8")
    for labels, _ in ROUTING_CASES:
        out = subprocess.run([_tool("amtool"), "config", "routes", "test", f"--config.file={cfg_path}",
                              "--verify.receivers=null", *(f"{k}={v}" for k, v in labels.items())],
                             capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, (labels, out.stdout + out.stderr)
