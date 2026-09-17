#!/bin/ksh
# Startup entry published to /mnt/ota by Update before payload staging, then
# discovered by ModKit on every boot. COMMITTED starts the daemon. Any other
# recorded state means a transaction was interrupted: the JAR may sit on the
# live classpath, so the module is rolled back here, unattended, from the
# on-unit originals. No card or operator marker is needed.
set -u
case "$0" in */*) here=${0%/*};; *) here=.;; esac   # no dirname: it is not on the update-mode PATH
here=$(cd "$here" && pwd -P)
root=${AUDI_CLUSTER_FIXTURE_ROOT:-}
state="$root/mnt/app/eso/.audi-cluster/state"
daemon="$root/mnt/app/eso/bin/apps/cluster/cluster"
[[ -f "$state" ]] || exit 0
case "$(cat "$state")" in
    COMMITTED)
        [[ -x "$daemon" ]] || exit 0
        if [[ -n "$root" ]]; then print "would start $daemon"; exit 0; fi
        "$daemon" daemon verbose=2 &
        exit 0;;
    RESTORED|NONE) exit 0;;
esac
print "uncommitted transaction state '$(cat "$state")' found at boot; rolling back unattended"
[[ -f "$here/common.sh" && -f "$here/manifest.txt" ]] || { print 'library or manifest missing beside the startup entry; cannot roll back'; exit 1; }
. "$here/common.sh"
MANIFEST="$here/manifest.txt"
MOD_PATH=$here
SCRATCH="$root/tmp/.audi-cluster-scratch.$$"
mkdir -p "$SCRATCH" || { print 'no scratch space'; exit 1; }
trap 'rm -r "$SCRATCH" 2>/dev/null' EXIT
[[ -z "$FIXTURE_ROOT" ]] && mount -uw /mnt/app
selftest_hash_tool
if perform_rollback; then print 'unattended rollback complete'; else print 'unattended rollback incomplete; use the card fail-safe marker'; exit 1; fi
