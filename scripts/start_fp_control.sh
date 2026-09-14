#!/usr/bin/env bash
# Start an FP control paper runtime: BASELINE-1 as operational control.
#
# Usage: scripts/start_fp_control.sh FP-CONTROL-2
#
# The role is required and never defaulted. scripts/fp_instance.py is the one
# place that decides which instance may run, and it refuses a closed one, so a
# terminated cohort's paths can never be started into.
#
# Fails closed at every step. The paper guard runs before anything starts, the
# strategy and config are checked against the hashes frozen in the cohort
# registry, and the runtime refuses to start if either has moved — a control
# whose identity drifted is not a control.
#
# PAPER / DRY-RUN ONLY. REAL_MONEY_AUTHORIZED = NO.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.fp.yml)

if [[ $# -ne 1 ]]; then
  echo "usage: scripts/start_fp_control.sh FP-CONTROL-ROLE" >&2
  echo "  no default role: a default would select whichever row came first, including a closed one." >&2
  exit 2
fi

# Fail-closed selection before anything else runs.
# The substitution's exit status must be checked before eval sees it: `eval
# "$(...)"` reports eval's success, not the selector's, and a refusal would then
# surface as an unbound variable several lines later instead of as a refusal.
if ! FP_SELECTION="$(python3 scripts/fp_instance.py "$1")"; then
  exit 3
fi
eval "$FP_SELECTION"
export FP_ROLE FP_INSTANCE_DIR FP_BOT_NAME FP_DB_PATH FP_LOG_PATH FP_EVIDENCE_DIR
FP_DIR="freqtrade/user_data/$FP_INSTANCE_DIR"
echo "FP_ROLE=$FP_ROLE FP_INSTANCE_DIR=$FP_INSTANCE_DIR FP_BOT_NAME=$FP_BOT_NAME T0=$FP_T0"

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
import hashlib, json, os, pathlib, sys

registry = json.loads(
    pathlib.Path("research/fp/records/forward_paper_cohort_registry.json").read_text(encoding="utf-8")
)
sys.path.insert(0, "research")
from fp.capture import InstanceSelectionError, select_instance

try:
    instance = select_instance(os.environ["FP_ROLE"], registry)
except InstanceSelectionError as exc:
    print(f"FP_IDENTITY_FAIL: {exc}", file=sys.stderr)
    sys.exit(3)
identity = instance["runtime_identity"]

# The *runtime* config is what the engine reads. Hashing the committed example
# instead let sizing or risk drift in config.json reach `compose up` unnoticed,
# because the file being checked was not the file being run.
expected = {
    "strategy_sha256": "freqtrade/user_data/strategies/BaselineEmaRegimeV1.py",
    "config_sha256": os.environ.get("HOST_CONFIG", "freqtrade/user_data/config.json"),
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

# The lane is validated before anything is created. Creating the directories
# first meant a symlinked lane was materialised — and, in one reproduction,
# written — before the check that would have refused it ran.
python3 - "$FP_ROLE" "$FP_DIR" <<'PY' || exit 3
import sys
from pathlib import Path

sys.path.insert(0, "research")
from fp.lane import LaneError, resolve_lane  # noqa: E402

role, lane_dir = sys.argv[1], Path(sys.argv[2])
try:
    lane = resolve_lane(role)
except LaneError as exc:
    print(f"FP_LANE_FAIL: {exc}", file=sys.stderr)
    raise SystemExit(3)

# resolve() follows every existing symlink component, so a lane that points
# somewhere else resolves somewhere else and is refused here, before mkdir.
resolved = lane_dir.resolve()
if resolved != lane.host_instance_dir.resolve():
    print(
        f"FP_LANE_FAIL: {lane_dir} resolves to {resolved}, not the declared "
        f"{lane.host_instance_dir}",
        file=sys.stderr,
    )
    raise SystemExit(3)
for parent in (lane_dir / "logs", lane_dir / "evidence"):
    if parent.exists() and parent.resolve() != (lane.host_instance_dir / parent.name):
        print(f"FP_LANE_FAIL: {parent} resolves outside the lane", file=sys.stderr)
        raise SystemExit(3)
print(f"FP_LANE_PASS: {resolved}")
PY

mkdir -p "$FP_DIR/logs" "$FP_DIR/evidence"

# Stamped into the capture container, which has no git of its own.
FP_SOURCE_COMMIT="$(git rev-parse HEAD)"
export FP_SOURCE_COMMIT
echo "FP_SOURCE_COMMIT=$FP_SOURCE_COMMIT"

# The rendered stack — not the source file — is what the engine runs, so that is
# what gets checked, against the instance actually selected.
RENDERED="$(mktemp)"
docker compose "${COMPOSE_FILES[@]}" config > "$RENDERED"
python3 scripts/check_fp_overlay.py "$RENDERED" "$FP_ROLE" || { rm -f "$RENDERED"; exit 4; }
rm -f "$RENDERED"

docker compose "${COMPOSE_FILES[@]}" up -d

echo
echo "Started $FP_ROLE (dry_run=true, paper only)."
echo "  status:   docker compose ${COMPOSE_FILES[*]} ps"
echo "  capture:  docker compose ${COMPOSE_FILES[*]} logs -f fp-capture"
echo "  evidence: $FP_DIR/evidence"
