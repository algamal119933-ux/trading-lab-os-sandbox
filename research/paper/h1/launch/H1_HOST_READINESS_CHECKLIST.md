# H1 host readiness checklist (H1-PAPER-COHORT-1)

**Status:** PREPARED. **H1_LAUNCH_AUTHORIZED = NO.** REAL_MONEY_AUTHORIZED = NO.
Companion to [`OWNER_H1_LAUNCH_AUTHORIZATION_1.md`](OWNER_H1_LAUNCH_AUTHORIZATION_1.md) (NOT GRANTED) and
[`H1_LAUNCH_BINDER.md`](H1_LAUNCH_BINDER.md). Prepared under the Owner directive of 2026-10-27 (Lane E).

## 0. Preparation is not authorization
- This checklist, the prepared record, a green card, a merged PR or a passing test authorize **nothing**.
- The only launch authority is a **separate Owner grant PR**. That PR changes `H1_LAUNCH_AUTHORIZED` to `YES`
  and fills the four `SET AT GRANT` fields, and the Owner merges it.
- Until then:
  - no materialisation in a cohort lane;
  - no container start;
  - no `COHORT_START` incident;
  - no PAPER_T0.
- Silence is not approval.

## 1. When this checklist may be run
Only after both of the following:
1. The Owner's **planned reboot acceptance** (PLN-04/07) has completed, per the P3 reboot runbook.
2. The Owner has lifted the **host freeze** that holds until that reboot acceptance.

Before then, nothing in §3 runs on the host. Running it would change no authority, but it is out of order.

**Monitoring coordination (recommended before any grant):** the PLN-06 alert leg should be live, with the
channel chosen and a test alert delivered, so a launched cohort is watched off the terminal. This is a
recommendation; the PLN-06 records hold the actual gate.

## 2. Items, each with its evidence
| # | Item | PASS condition | Evidence / how to verify | Current status |
|---|---|---|---|---|
| 1 | Frozen package | manifest sha256 = `ef9a3d0c5b5b9abe122faaa1bd4ef67feb0c3ec4437bed56cd6ef33d910bc43c` | `python3 research/paper/h1/package/h1_paper.py verify` on the checkout used; the card's package row | verified in the cloud at repo level (§4); host re-verify pending |
| 2 | dry_run / paper guard | the H1 config passes `scripts/paper_guard.py` (dry_run true, spot, no keys, no leverage) | paper-guard card row; the merged §19 `paper_guard` health check also covers any materialised H1 lane config | repo PASS; host pending |
| 3 | Host capacity | ≥ 20 GB free on the lane's filesystem (MATERIALISATION_PREFLIGHT) | `df -h /` and the card's preflight row | Owner-observed 162 GiB free on 2026-10-26 (HANDOFF, not re-checked) |
| 4 | Materialisation evidence | newest `MATERIALISATION_RECORD.json` = `H1_MATERIALISATION = PASS`, hash-verified copy of exactly three files | `h1_materialise.py` output under `~/tlos-paper/materialise/*/` | UNKNOWN until the host recheck |
| 5 | Second evidence store | an Owner-named directory on a **different device** from the lane | `findmnt`, `ls -ld` | **OPEN: the Owner must name it.** The candidate `/mnt/tlos-wdc/tlos-h1-evidence` is unconfirmed |
| 6 | Fresh launch card | `READY_FOR_OWNER_AUTHORIZATION`, at most 24 h old at grant time, card JSON sha256 recorded in the grant | `h1_launch_card.py --json …`, then `sha256sum` | today the card reads DENY in the cloud, because the 4 host rows cannot run there |
| 7 | Placement / isolation | HOST_PLACEMENT = PASS (no P2 container running); own project, container, network and port | card placement row; `docker ps -a` | host pending |
| 8 | Authority expiry | the grant names `EXPIRES_UTC`; an unused grant lapses then; the P3 authorization (expires 2027-01-31) is unaffected | the grant record | set at grant |
| 9 | Health-check coherence | the merged §19 check must not page a lawful H1 cohort as `unauthorized_execution` | `tests/test_h1_launch_authorization_record.py::test_the_health_check_and_the_record_agree_about_h1` | **grant-PR prerequisite** (§5) |
| 10 | T0 preconditions | all of the following hold:<br>• items 1–9 PASS<br>• the grant is merged<br>• the card is ≤ 24 h old and its sha256 matches the grant<br>• the lane is empty<br>• no P2 or FP container is running<br>• the second store is mounted and writable<br>• the monitoring leg is live (recommended) | binder §5 steps 4–8; PAPER_T0 = the `recorded_utc` of the lane's first `COHORT_START` incident | not reached; **no T0 may be set** |

## 3. Host recheck (read-only; run only after §1 holds)
It writes only into a new dated folder and prints the result. It changes no working tree. `git fetch` updates
refs only.

```bash
d=~/projects/trading/tlos-p3
out=~/tlos-paper/h1-card-checks/$(date -u +%Y%m%dT%H%M%SZ)
[ -e "$out" ] && echo "STOP: $out exists" || mkdir -p "$out"
{
echo "== code (card code must equal main) =="
git -C "$d" fetch -q origin main; git -C "$d" rev-parse HEAD origin/main
git -C "$d" diff --quiet HEAD origin/main -- research/paper/h1 scripts/paper_guard.py && echo "CARD_CODE = SAME_AS_MAIN" || echo "CARD_CODE DIFFERS - STOP"
echo "== capacity / WDC =="; df -h / /mnt/tlos-wdc; findmnt -no SOURCE,FSTYPE,OPTIONS /mnt/tlos-wdc
echo "== docker =="; docker ps -a --format '{{.Names}}|{{.State}}|{{.Label "com.docker.compose.project"}}'
echo "== lane (must be absent or empty) =="; ls -la ~/tlos-paper/h1-paper-cohort-1 2>&1
echo "== second store candidate =="; ls -ld /mnt/tlos-wdc/tlos-h1-evidence 2>&1
echo "== materialisation record =="; rec=$(ls -t ~/tlos-paper/materialise/*/MATERIALISATION_RECORD.json 2>/dev/null | head -1); echo "record=$rec"
echo "== authority on main =="; git -C "$d" show origin/main:CLAUDE.md | grep -o 'H1_LAUNCH_AUTHORIZED = [A-Z]*' | head -1
git -C "$d" show origin/main:docs/p3/OWNER_P3_EXECUTION_AUTHORIZATION.md | grep -E 'EXPIRES_UTC|REAL_MONEY'
echo "== card (read-only; writes only the JSON below) =="
(cd "$d" && python3 research/paper/h1/launch/h1_launch_card.py --ref origin/main \
   --materialisation-record "$rec" --lane-dir ~/tlos-paper/h1-paper-cohort-1 \
   --second-store /mnt/tlos-wdc/tlos-h1-evidence --json "$out/h1_launch_card.json"); echo "card_exit=$?"
sha256sum "$out/h1_launch_card.json"
} > "$out/h1_recheck.txt" 2>&1; cat "$out/h1_recheck.txt"
```

Send the printed `h1_recheck.txt` to Claude. A READY card is input to the Owner's decision, not the decision itself.

## 4. Repository-only rows (cloud)
The rows that need no host are re-run in the cloud on every head of this PR. The PR body records the results
and the commit they ran at. Host rows (capacity, placement, materialisation, second store) are never claimed from
the cloud.

## 5. What a future grant PR must also do
The merged §19 health check (PR #85, `research/p3/health.py::paper_runtime_vs_registry`) reports
`unauthorized_execution` **CRITICAL** for any running paper container that no RUNNING registry cohort backs.
H1 has no row in `research/fp/records/forward_paper_cohort_registry.json`, so a lawful H1 launch would page as
unauthorized. In the same change that sets `H1_LAUNCH_AUTHORIZED = YES`, the grant PR must give the health check
a governed way to recognise the granted H1 cohort, for example a RUNNING H1 entry the check reads, owned by the
monitoring workstream. It must not weaken the check for any other container. The coherence test in §2 item 9
fails until that is done, so a YES cannot merge with the two disagreeing.

PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · H1_LAUNCH_AUTHORIZED = NO
