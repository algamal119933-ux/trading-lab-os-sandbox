#!/usr/bin/env bash
# P3-PLN-03 host installation steps H2 and H4 (docs/p3/PLN_03_HOST_INSTALL_H2_H7.md), guarded. Run only under the
# Owner's authorization for that step. It never touches a unit, a timer, the runtime or a backup set.
#
#   backup_host_install.sh checkout <40-hex merge SHA>   H2: move the tools checkout, fast-forward only, detached
#   backup_host_install.sh install                       H4: replace the host wrapper with the governed copy
#   backup_host_install.sh rollback <rollback copy>      put the original wrapper back
#
# Guards, for every subcommand:
# - It holds the backup wrapper's own lock ($XDG_RUNTIME_DIR/tlos-p3-backup.lock), so a governed backup run cannot
#   start while files change under it. A run already holding the lock means exit 75.
# - The ORIGINAL (legacy) wrapper takes no lock, so the lock does not protect it. Three checks do:
#   tlos-p3-backup.service must be inactive or failed (a oneshot is "activating" while it runs); the timer's next
#   firing must be more than TLOS_TIMER_MARGIN_S (900 s) away (read-only: NextElapseUSecRealtime; the firing itself
#   may come up to RandomizedDelaySec=300 s later, which only widens the gap); and the unit is checked again after
#   the change. A run that started during the change is reported (exit 4), never hidden.
# - A replacement goes to a verified temporary file in the same directory, then one atomic rename. The wrapper
#   is never half-written.
# - install requires the current wrapper to be exactly the 2026-11-03 original (sha256 below) and keeps a verified
#   rollback copy beside it. rollback accepts only a copy with that sha256.
# Exit: 0 done · 2 usage · 3 refused (state, timer, hash, tree), nothing changed · 4 the change was made but a backup
# run started during it (read its journal before going on) · 75 lock held. PAPER / RESEARCH ONLY.
set -euo pipefail
umask 077
H="${TLOS_HOME:-/home/hamza}"
P3="${TLOS_P3:-$H/projects/trading/tlos-p3}"
W="${TLOS_WRAPPER:-$H/projects/trading/tlos-runtime/backup.sh}"
SRC="$P3/scripts/p3/ops/tlos_runtime_backup.sh"
ORIG_SHA=561c44d2c0602a7a0471b60a024bc3d7a25ef5d98457391f1ea6c5c17413b531
RUNDIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

refuse() { echo "REFUSED: $*" >&2; exit 3; }
sha() { sha256sum "$1" | cut -d' ' -f1; }

[ $# -ge 1 ] || { echo "usage: $0 checkout <sha> | install | rollback <copy>" >&2; exit 2; }
exec 9>"$RUNDIR/tlos-p3-backup.lock"
flock -n 9 || { echo "REFUSED: a backup run holds $RUNDIR/tlos-p3-backup.lock" >&2; exit 75; }
unit_state() { systemctl --user show -p ActiveState --value tlos-p3-backup.service; }
state="$(unit_state)"
case "$state" in inactive|failed) ;; *) refuse "tlos-p3-backup.service is '$state'; wait until it is inactive" ;; esac
next="$(systemctl --user show -p NextElapseUSecRealtime --value --timestamp=unix tlos-p3-backup.timer)"
case "$next" in @[0-9]*) next="${next#@}" ;; *) next="$(date -d "$next" +%s 2>/dev/null || true)" ;; esac
[[ "$next" =~ ^[0-9]+$ ]] || refuse "cannot read when tlos-p3-backup.timer fires next"
left=$(( next - $(date +%s) ))
[ "$left" -gt "${TLOS_TIMER_MARGIN_S:-900}" ] \
  || refuse "tlos-p3-backup.timer fires in ${left} s; the legacy wrapper takes no lock: wait until that run is over"
after_check() {  # the legacy wrapper may still have started during the change: say so
  local now
  now="$(unit_state)"
  case "$now" in inactive|failed) ;; *)
    echo "RACE: tlos-p3-backup.service became '$now' during the change; let it finish and read its journal" >&2
    exit 4 ;;
  esac
}

TMP=""
replace_wrapper() {  # $1 = verified source, $2 = its expected sha256
  TMP="$(mktemp "$(dirname "$W")/.backup.sh.XXXXXX")"
  trap 'rm -f "$TMP"' EXIT     # any refusal below leaves no temporary file behind
  cp "$1" "$TMP"
  chmod 0700 "$TMP"
  [ "$(sha "$TMP")" = "$2" ] || refuse "the temporary copy does not hash to $2"
  bash -n "$TMP" || refuse "the temporary copy does not parse"
  mv -f "$TMP" "$W"          # same directory, same filesystem: one atomic rename
  trap - EXIT
  [ "$(sha "$W")" = "$2" ] || refuse "$W does not hash to $2 after the rename"
}

case "$1" in
  checkout)
    [ $# -eq 2 ] && [[ "$2" =~ ^[0-9a-f]{40}$ ]] || { echo "usage: $0 checkout <40-hex sha>" >&2; exit 2; }
    [ -z "$(git -C "$P3" status --porcelain)" ] || refuse "$P3 has local changes"
    before="$(git -C "$P3" rev-parse HEAD)"
    git -C "$P3" fetch -q origin main
    git -C "$P3" merge-base --is-ancestor "$2" origin/main || refuse "$2 is not on origin/main"
    git -C "$P3" merge-base --is-ancestor "$before" "$2" || refuse "$2 is not a fast-forward of $before"
    git -C "$P3" -c advice.detachedHead=false checkout -q --detach "$2"
    [ "$(git -C "$P3" rev-parse HEAD)" = "$2" ] || refuse "HEAD is not $2 after the checkout"
    echo "CHECKOUT $before -> $2 · ROLLBACK git -C $P3 checkout --detach $before (service inactive first)"
    after_check
    ;;
  install)
    [ -f "$SRC" ] || refuse "$SRC missing"
    new_sha="$(sha "$SRC")"
    cur_sha="$(sha "$W")"
    if [ "$cur_sha" = "$new_sha" ]; then echo "ALREADY_INSTALLED $W sha256 $new_sha"; exit 0; fi
    [ "$cur_sha" = "$ORIG_SHA" ] || refuse "$W is sha256 $cur_sha, not the original $ORIG_SHA"
    keep="$W.pre-p3-$(date -u +%Y%m%dT%H%M%SZ)"
    [ ! -e "$keep" ] || refuse "$keep exists"
    cp -p "$W" "$keep"
    [ "$(sha "$keep")" = "$ORIG_SHA" ] || refuse "the rollback copy does not hash to the original"
    replace_wrapper "$SRC" "$new_sha"
    echo "INSTALLED $W sha256 $new_sha (mode $(stat -c %a "$W")) · ROLLBACK_COPY $keep sha256 $ORIG_SHA"
    after_check
    ;;
  rollback)
    [ $# -eq 2 ] || { echo "usage: $0 rollback <copy>" >&2; exit 2; }
    [ "$(sha "$2")" = "$ORIG_SHA" ] || refuse "$2 is not the original wrapper"
    replace_wrapper "$2" "$ORIG_SHA"
    echo "ROLLED_BACK $W sha256 $ORIG_SHA"
    after_check
    ;;
  *) echo "usage: $0 checkout <sha> | install | rollback <copy>" >&2; exit 2 ;;
esac
