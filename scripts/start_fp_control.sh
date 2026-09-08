#!/usr/bin/env bash
# Start the FP-CONTROL-1 paper runtime: BASELINE-1 as operational control.
#
# Fails closed at every step. The paper guard runs before anything starts, the
# strategy and config are checked against the hashes frozen in the cohort
# registry, and the runtime refuses to start if either has moved — a control
# whose identity drifted is not a control.
#
# PAPER / DRY-RUN ONLY. REAL_MONEY_AUTHORIZED = NO.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.fp.yml)
FP_DIR="freqtrade/user_data/fp-control-1"

if [[ ! -f .env ]]; then
  echo "Missing .env. Run: cp .env.example .env and change the placeholder passwords." >&2
  exit 2
fi

if grep -q "CHANGE_ME" .env; then
  echo "Refusing to start: .env still contains CHANGE_ME placeholders." >&2
  exit 2
fi

# The runtime config must exist and be paper-safe before a container is created.
require_paper_config

# The control's identity must match what the registry froze. This is the same
# comparison preflight check 5 makes; doing it here too means an identity drift
# stops the runtime rather than being discovered in a later report.
python3 - <<'PY' || exit 3
import hashlib, json, pathlib, sys

registry = json.loads(
    pathlib.Path("research/fp/records/forward_paper_cohort_registry.json").read_text(encoding="utf-8")
)
instance = next(i for i in registry["instances"] if i["role"] == "FP-CONTROL-1")
identity = instance["runtime_identity"]

expected = {
    "strategy_sha256": "freqtrade/user_data/strategies/BaselineEmaRegimeV1.py",
    "config_sha256": "freqtrade/user_data/config.paper.json.example",
}
problems = []
for field, path in expected.items():
    declared = identity.get(field)
    actual = hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    if not declared:
        problems.append(f"{field} is not bound in the registry")
    elif declared != actual:
        problems.append(f"{field}: registry {declared[:12]}... but {path} hashes to {actual[:12]}...")

for field in ("bot_name", "db_path", "log_path", "evidence_dir", "paper_fill_model_version"):
    if not identity.get(field):
        problems.append(f"{field} must be bound before T0")

if problems:
    for problem in problems:
        print(f"FP_IDENTITY_FAIL: {problem}", file=sys.stderr)
    sys.exit(3)
print("FP_IDENTITY_PASS: strategy, config and runtime paths match the frozen registry")
PY

mkdir -p "$FP_DIR/logs" "$FP_DIR/evidence"

# Stamped into the capture container, which has no git of its own.
FP_SOURCE_COMMIT="$(git rev-parse HEAD)"
export FP_SOURCE_COMMIT
echo "FP_SOURCE_COMMIT=$FP_SOURCE_COMMIT"

docker compose "${COMPOSE_FILES[@]}" up -d

echo
echo "Started FP-CONTROL-1 (dry_run=true, paper only)."
echo "  status:   docker compose ${COMPOSE_FILES[*]} ps"
echo "  capture:  docker compose ${COMPOSE_FILES[*]} logs -f fp-capture"
echo "  evidence: $FP_DIR/evidence"
