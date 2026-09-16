#!/bin/ksh
# ModKit early-boot fail-safe for the Audi cluster module. Copy to the card
# root as failsafe.sh. modkit_persist.sh runs it on every boot before any mod;
# it does nothing unless the operator has created AudiClusterIntegration-RECOVER
# next to it. With the marker present it rolls the module back from the
# on-unit journal and the card backup, logs to the card, and removes the marker
# only after every factory file verified. It never installs anything.
set -u
media=$(cd "$(dirname "$0")" && pwd -P)
marker="$media/AudiClusterIntegration-RECOVER"
[[ -e "$marker" ]] || exit 0
module="$media/Mods/AudiClusterIntegration/Update"
logfile="$media/AudiClusterIntegration-failsafe.log"
exec >> "$logfile" 2>&1
print "----- failsafe $(date) -----"
[[ -f "$module/common.sh" ]] || { print 'module scripts not on this card; cannot recover'; exit 1; }
. "$module/common.sh"
MANIFEST="$module/manifest.txt"
MOD_PATH=$module
MEDIA_PATH=$media
SCRATCH="$media/.audi-cluster-scratch.$$"
mkdir -p "$SCRATCH" || { print 'card not writable'; exit 1; }
trap 'rm -rf "$SCRATCH"' EXIT
# At normal boot /mnt/app is read-only; the update stage remounts it, the fail-safe must.
[[ -z "$FIXTURE_ROOT" ]] && mount -uw /mnt/app
selftest_hash_tool
case "$(current_state)" in
    NONE) print 'nothing recorded as installed; marker left for the operator'; exit 0;;
    RESTORED) print 'already restored; marker removed'; rm -f "$marker"; exit 0;;
esac
if perform_rollback; then
    rm -f "$marker"
    print 'recovery complete; marker removed'
else
    print 'recovery incomplete; marker kept, review the log and card backup'
    exit 1
fi
