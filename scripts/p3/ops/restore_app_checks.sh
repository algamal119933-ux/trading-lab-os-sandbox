#!/usr/bin/env bash
# P3-PLN-03 H7 / G8: application checks on a RESTORED copy (docs/p3/PLN_03_HOST_INSTALL_H2_H7.md). Run only under
# the Owner's authorization for H7. It reads the restored scratch copy and starts throwaway containers on it with
# --network none. It never touches production data, the runtime's containers, a unit or a timer.
#
#   restore_app_checks.sh <restored data dir, e.g. $X/data> <set stamp YYYYMMDDTHHMMSSZ> <evidence json>
#
# Each check has a fixed PASS condition; anything else is FAIL. Nothing depends on a sleep.
#   grafana_db  SQLITE_INTEGRITY  pragma integrity_check = ok and foreign_key_check empty (read-only). This is the
#                                 database file, not a started Grafana: Grafana's start is NOT checked here.
#   mlflow      APPLICATION_READ  the pinned MLflow image opens the restored mlflow.db with MlflowClient and lists
#                                 ≥ 1 experiment, exit 0.
#   prometheus  APPLICATION_READY the pinned Prometheus image, started on the restored TSDB, keeps running and
#                                 answers /-/ready before the deadline (polled; it is ready only after the TSDB has
#                                 opened and the WAL has been replayed).
#   prometheus  WAL_RECOVERY      its log says "WAL replay completed", has no line mentioning a repair or
#                                 corruption, and series with samples in the window before the set stamp are
#                                 queryable (new samples written after the start cannot satisfy this).
# Hash equality of files (verify, drill) is a separate gate and is never reported as application consistency.
# The Prometheus container is removed on every exit path: success, failure, error, SIGINT or SIGTERM.
# Exit: 0 all PASS · 1 a check FAILED · 2 usage. PAPER / RESEARCH ONLY.
set -euo pipefail
umask 077
[ $# -eq 3 ] || { echo "usage: $0 <restored data dir> <set stamp> <evidence json>" >&2; exit 2; }
DATA="$1"; STAMP="$2"; OUT="$3"
[[ "$STAMP" =~ ^([0-9]{4})([0-9]{2})([0-9]{2})T([0-9]{2})([0-9]{2})([0-9]{2})Z$ ]] || { echo "bad stamp $STAMP" >&2; exit 2; }
AT="$(date -u -d "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}T${BASH_REMATCH[4]}:${BASH_REMATCH[5]}:${BASH_REMATCH[6]}Z" +%s)"
[ -d "$DATA/prometheus" ] && [ -f "$DATA/grafana/grafana.db" ] && [ -f "$DATA/mlflow/mlflow.db" ] \
  || { echo "$DATA does not hold restored grafana/grafana.db, mlflow/mlflow.db and prometheus/" >&2; exit 2; }
[ ! -e "$OUT" ] || { echo "$OUT exists" >&2; exit 2; }
PY="${TLOS_PYTHON:-python3}"
PROM_IMAGE="${TLOS_PROM_IMAGE:-prom/prometheus:v3.14.0}"
MLFLOW_IMAGE="${TLOS_MLFLOW_IMAGE:-ghcr.io/mlflow/mlflow:v3.15.1}"
READY_S="${TLOS_PROM_READY_TIMEOUT_S:-300}"
POLL_S="${TLOS_PROM_POLL_S:-2}"
WINDOW="${TLOS_PROM_WINDOW:-15m}"
C="tlos-drill-prom-$STAMP-$$"
RESULTS=()

cleanup() { docker rm -f "$C" >/dev/null 2>&1 || true; }
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

record() {  # name check PASS|FAIL detail (one line: tabs and newlines become spaces)
  local d="${4//[$'\t\n\r']/ }"
  RESULTS+=("$1"$'\t'"$2"$'\t'"$3"$'\t'"$d")
  echo "CHECK $1 $2 = $3 ($d)"
}

# grafana_db: read-only integrity of the restored SQLite file.
if d="$("$PY" - "$DATA/grafana/grafana.db" <<'E' 2>&1
import sqlite3, sys
c = sqlite3.connect("file:" + sys.argv[1] + "?mode=ro", uri=True)
i = c.execute("pragma integrity_check").fetchall()
f = c.execute("pragma foreign_key_check").fetchall()
print("integrity=" + ",".join(r[0] for r in i) + " foreign_key_violations=" + str(len(f)))
sys.exit(0 if i == [("ok",)] and not f else 1)
E
)"; then record grafana_db SQLITE_INTEGRITY PASS "$d"; else record grafana_db SQLITE_INTEGRITY FAIL "$d"; fi

# mlflow: the application's own client reads the restored store.
rc=0
d="$(docker run --rm --network none --user "$(id -u):$(id -g)" -v "$DATA/mlflow:/mlflow" "$MLFLOW_IMAGE" \
  python -c "import json,mlflow;e=mlflow.MlflowClient('sqlite:////mlflow/mlflow.db').search_experiments();print(json.dumps({'experiments':len(e)}))" 2>&1)" || rc=$?
n="$(printf '%s\n' "$d" | "$PY" -c 'import json,sys
for l in sys.stdin.read().splitlines()[::-1]:
    try: print(int(json.loads(l)["experiments"])); break
    except Exception: pass
else: print(-1)')"
if [ "$rc" -eq 0 ] && [ "$n" -ge 1 ]; then record mlflow APPLICATION_READ PASS "experiments=$n"
else record mlflow APPLICATION_READ FAIL "exit=$rc experiments=$n $(printf '%s' "$d" | tail -c 300 | tr '\n' ' ')"; fi

# prometheus: start a throwaway server on the restored TSDB.
if docker inspect "$C" >/dev/null 2>&1; then echo "container $C already exists" >&2; exit 2; fi
ready=FAIL; detail="not started"
if docker run -d --name "$C" --network none --user "$(id -u):$(id -g)" -v "$DATA/prometheus:/prometheus" \
     "$PROM_IMAGE" --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus >/dev/null; then
  deadline=$(( $(date +%s) + READY_S )); detail="not ready within ${READY_S}s"
  while :; do
    if [ "$(docker inspect -f '{{.State.Running}}' "$C" 2>/dev/null)" != "true" ]; then detail="container exited"; break; fi
    if docker exec "$C" wget -qO- http://127.0.0.1:9090/-/ready >/dev/null 2>&1; then
      ready=PASS; detail="ready after $(( READY_S - (deadline - $(date +%s)) ))s"; break
    fi
    [ "$(date +%s)" -lt "$deadline" ] || break
    sleep "$POLL_S"
  done
fi
record prometheus APPLICATION_READY "$ready" "$detail"

if [ "$ready" = PASS ]; then
  logs="$(docker logs "$C" 2>&1)" || logs=""
  q="$("$PY" -c 'import sys,urllib.parse as u;print(u.quote(sys.argv[1]))' "count(count_over_time({__name__=~\".+\"}[$WINDOW]))")"
  body="$(docker exec "$C" wget -qO- "http://127.0.0.1:9090/api/v1/query?query=$q&time=$AT" 2>&1)" || body=""
  series="$(printf '%s' "$body" | "$PY" -c 'import json,sys
try:
    r = json.load(sys.stdin)
    print(int(float(r["data"]["result"][0]["value"][1])) if r.get("status") == "success" and r["data"]["result"] else 0)
except Exception:
    print(-1)')"
  why=()
  printf '%s\n' "$logs" | grep -q 'WAL replay completed' || why+=("no 'WAL replay completed' in the log")
  bad="$(printf '%s\n' "$logs" | grep -Eic 'repair|corrupt')" || true   # grep -c exits 1 on a count of 0
  [ "$bad" -eq 0 ] || why+=("$bad log line(s) mention a repair or corruption")
  [ "$series" -gt 0 ] || why+=("no series with samples in the $WINDOW before $STAMP (query result $series)")
  if [ ${#why[@]} -eq 0 ]; then record prometheus WAL_RECOVERY PASS "replay completed, series_before_stamp=$series"
  else record prometheus WAL_RECOVERY FAIL "$(IFS=';'; echo "${why[*]}")"; fi
else
  record prometheus WAL_RECOVERY FAIL "not evaluated: the server never became ready"
fi
cleanup

status=PASS
for r in "${RESULTS[@]}"; do [ "$(cut -f3 <<<"$r")" = PASS ] || status=FAIL; done
printf '%s\n' "${RESULTS[@]}" | "$PY" -c 'import json,sys
rows = [l.split("\t", 3) for l in sys.stdin.read().splitlines() if l]
out = {"version": "P3_RESTORE_APP_CHECKS_V1", "stamp": sys.argv[2], "data": sys.argv[3], "RESTORE_APP_CHECKS": sys.argv[4],
       "checks": [{"name": n, "check": c, "result": r, "detail": d} for n, c, r, d in rows],
       "note": "application checks on the restored copy; file-hash equality is a separate gate"}
open(sys.argv[1], "x").write(json.dumps(out, indent=2) + "\n")' "$OUT" "$STAMP" "$DATA" "$status" \
  || { echo "EVIDENCE_WRITE_FAILED $OUT" >&2; echo "RESTORE_APP_CHECKS = FAIL"; exit 1; }
echo "RESTORE_APP_CHECKS = $status"
[ "$status" = PASS ]
