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
#   prometheus  WAL_RECOVERY      all of:
#                                 - the log has msg="WAL replay completed";
#                                 - no repair or corruption event: "repair"/"corrupt" in a line's msg= or err= field
#                                   (never in source=, so source=repair.go:54 msg="Found healthy block" is not one);
#                                 - no level=ERROR line;
#                                 - prometheus_tsdb_wal_corruptions_total and _mmap_chunk_corruptions_total read from
#                                   the server and both 0 (some mmap corruption paths log no such word; a counter
#                                   that cannot be read is a FAIL, never a pass);
#                                 - series with samples in the window before the set stamp are queryable:
#                                   count(last_over_time({__name__=~".+"}[15m])) at the stamp, HTTP 200, > 0.
#                                   last_over_time keeps the metric name; count_over_time drops it, so on real data
#                                   two metrics of one target collide and Prometheus rejects the query (HTTP 422).
#                                   New samples written after the start cannot satisfy this.
# Evidence kept beside <evidence json>, on PASS and FAIL: <base>.prometheus.log (complete, saved before the
# container is removed) and <base>.http/ (raw body, HTTP status, headers or transport error of /metrics and of the
# query, fetched by a helper container that shares only the throwaway's loopback; image identities).
# Hash equality of files (verify, drill) is a separate gate and is never reported as application consistency.
# The Prometheus container is removed on every exit path: success, failure, error, SIGINT or SIGTERM. Images are
# used only if present locally (--pull never).
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
LOG="${OUT%.json}.prometheus.log"
HTTP="${OUT%.json}.http"
[ ! -e "$LOG" ] && [ ! -e "$HTTP" ] || { echo "$LOG or $HTTP exists" >&2; exit 2; }
PY="${TLOS_PYTHON:-python3}"
PROM_IMAGE="${TLOS_PROM_IMAGE:-prom/prometheus:v3.14.0}"
MLFLOW_IMAGE="${TLOS_MLFLOW_IMAGE:-ghcr.io/mlflow/mlflow:v3.15.1}"
HELPER_IMAGE="${TLOS_HELPER_IMAGE:-python:3.12-slim}"
READY_S="${TLOS_PROM_READY_TIMEOUT_S:-300}"
POLL_S="${TLOS_PROM_POLL_S:-2}"
WINDOW="${TLOS_PROM_WINDOW:-15m}"
C="tlos-drill-prom-$STAMP-$$"
RESULTS=()

LOG_SAVED=0
save_log() {  # the complete log, once, before the container goes
  [ "$LOG_SAVED" = 0 ] || return 0
  docker logs --timestamps "$C" > "$LOG" 2>&1 && LOG_SAVED=1
}
cleanup() {
  if docker inspect "$C" >/dev/null 2>&1; then save_log || true; docker rm -f "$C" >/dev/null 2>&1 || true; fi
}
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
d="$(docker run --rm --pull never --network none --user "$(id -u):$(id -g)" -v "$DATA/mlflow:/mlflow" "$MLFLOW_IMAGE" \
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
if docker run -d --pull never --name "$C" --network none --user "$(id -u):$(id -g)" -v "$DATA/prometheus:/prometheus" \
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

Q="count(last_over_time({__name__=~\".+\"}[$WINDOW]))"
mkdir -m 700 "$HTTP"
for img in "$PROM_IMAGE" "$HELPER_IMAGE"; do
  docker image inspect "$img" --format '{{index .RepoTags 0}} id={{.Id}} digests={{json .RepoDigests}}' 2>&1 || true
done > "$HTTP/images.txt"
if [ "$ready" = PASS ]; then
  # Raw responses through a helper sharing only the throwaway's loopback (busybox wget hides error bodies).
  hrc=0
  docker run --rm --pull never --network "container:$C" --read-only --cap-drop ALL --security-opt no-new-privileges \
    --user "$(id -u):$(id -g)" -v "$HTTP:/out" -e OUT=/out -e PROM_URL=http://127.0.0.1:9090 -e QUERY="$Q" -e AT="$AT" \
    "$HELPER_IMAGE" python3 -c '
import datetime, json, os, urllib.error, urllib.parse, urllib.request
base, out = os.environ["PROM_URL"], os.environ["OUT"]
for name, path in (("metrics", "/metrics"),
                   ("query", "/api/v1/query?query=" + urllib.parse.quote(os.environ["QUERY"]) + "&time=" + os.environ["AT"])):
    meta, body = {"url": base + path, "requested_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}, b""
    try:
        r = urllib.request.urlopen(base + path, timeout=120)
        meta["status"], meta["headers"], body = r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        meta["status"], meta["headers"], body = e.code, dict(e.headers), e.read()
    except Exception as e:
        meta["status"], meta["transport_error"] = None, repr(e)
    open(os.path.join(out, name + ".body"), "wb").write(body)
    json.dump(meta, open(os.path.join(out, name + ".meta.json"), "w"), indent=2)
' > "$HTTP/helper.txt" 2>&1 || hrc=$?
  echo "helper_exit=$hrc" >> "$HTTP/helper.txt"
fi
save_log || true

if [ "$ready" = PASS ]; then
  verdict="$("$PY" - "$LOG" "$HTTP" "$WINDOW" "$STAMP" <<'P'
import json, os, re, sys
log_path, http, window, stamp = sys.argv[1:5]
FIELD = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)')
def fields(line):
    return {k: v[1:-1] if v.startswith('"') else v for k, v in FIELD.findall(line)}
why = []
try:
    lines = open(log_path, encoding="utf-8", errors="replace").read().splitlines()
except OSError:
    lines = None
    why.append("the Prometheus log could not be saved")
if lines is not None:
    parsed = [fields(l) for l in lines]
    if not any(f.get("msg") == "WAL replay completed" for f in parsed):
        why.append("no msg=\"WAL replay completed\" in the log")
    events, errors = [], []
    for line, f in zip(lines, parsed):
        text = (f.get("msg", "") + " " + f.get("err", "")) if "msg" in f else re.sub(r"source=\S+", "", line)
        if re.search(r"repair|corrupt", text, re.I):
            events.append(f.get("msg") or line.strip())
        if f.get("level", "").upper() == "ERROR":
            errors.append(f.get("msg") or line.strip())
    if events:
        why.append(f"{len(events)} repair/corruption event(s) in msg/err: {events[:3]}")
    if errors:
        why.append(f"{len(errors)} level=ERROR line(s): {errors[:3]}")
def capture(name):
    try:
        meta = json.load(open(os.path.join(http, name + ".meta.json")))
        body = open(os.path.join(http, name + ".body"), "rb").read().decode("utf-8", "replace")
        return meta, body
    except OSError:
        return None, ""
meta, body = capture("metrics")
counters = {}
if meta and meta.get("status") == 200:
    for l in body.splitlines():
        m = re.match(r"^prometheus_tsdb_(wal_corruptions_total|mmap_chunk_corruptions_total) (\S+)$", l)
        if m:
            counters[m.group(1)] = float(m.group(2))
for c in ("wal_corruptions_total", "mmap_chunk_corruptions_total"):
    if c not in counters:
        why.append(f"{c} not captured (metrics HTTP status {meta.get('status') if meta else None})")
    elif counters[c] != 0:
        why.append(f"{c}={counters[c]:g}")
meta, body = capture("query")
series = None
if not meta:
    why.append("QUERY_FAILED: no response captured")
elif meta.get("status") != 200:
    err = ""
    try:
        err = json.loads(body).get("error", "")
    except ValueError:
        err = body[:200]
    why.append(f"QUERY_FAILED: HTTP {meta.get('status')} {meta.get('transport_error') or err}")
else:
    try:
        j = json.loads(body)
        r = j["data"]["result"] if j.get("status") == "success" else None
        series = (int(float(r[0]["value"][1])) if r else 0) if r is not None else None
    except (ValueError, KeyError, IndexError, TypeError):
        series = None
    if series is None:
        why.append("QUERY_FAILED: HTTP 200 without a readable success result")
    elif series <= 0:
        why.append(f"no series with samples in the {window} before {stamp}")
counted = ", ".join(f"{k}={v:g}" for k, v in sorted(counters.items()))
if why:
    print("FAIL\t" + "; ".join(why))
else:
    print(f"PASS\treplay completed, no repair/corruption event, no ERROR line, {counted}, series_before_stamp={series}")
P
)" || verdict=$'FAIL\tthe WAL check itself failed to run'
  record prometheus WAL_RECOVERY "${verdict%%$'\t'*}" "${verdict#*$'\t'}"
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
       "evidence": {"prometheus_log": sys.argv[5], "http": sys.argv[6]},
       "note": "application checks on the restored copy; file-hash equality is a separate gate"}
open(sys.argv[1], "x").write(json.dumps(out, indent=2) + "\n")' "$OUT" "$STAMP" "$DATA" "$status" "$LOG" "$HTTP" \
  || { echo "EVIDENCE_WRITE_FAILED $OUT" >&2; echo "RESTORE_APP_CHECKS = FAIL"; exit 1; }
echo "RESTORE_APP_CHECKS = $status"
[ "$status" = PASS ]
