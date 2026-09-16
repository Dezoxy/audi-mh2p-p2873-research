#!/bin/ksh
# Audi cluster integration: journaled removal (ModKit Update stage with uninstall.txt).
# Restores only what this module's journal recorded. Never touches the ModKit loader.
set -u
here=$(cd "$(dirname "$0")" && pwd -P)
. "$here/common.sh"
MANIFEST="$here/manifest.txt"
[[ -f "$MANIFEST" ]] || fail 'manifest.txt missing'
require_env
SCRATCH="$MEDIA_PATH/.audi-cluster-scratch.$$"
mkdir -p "$SCRATCH" || fail 'cannot create scratch on media'
trap 'rm -rf "$SCRATCH"' EXIT
selftest_hash_tool

case "$(current_state)" in
    NONE) log 'nothing recorded as installed by this module'; exit 0;;
    RESTORED) log 'already restored; journal retained'; exit 0;;
esac
[[ -f "$JOURNAL" ]] || fail 'state present but journal missing; manual review required'
BACKUP_DIR=$(awk '$2 == "BEGIN" { print $3 }' "$JOURNAL" | tail -1)
[[ -n "$BACKUP_DIR" ]] || fail 'journal has no BEGIN record'
if [[ -f "$BACKUP_DIR/manifest.txt" ]]; then
    MANIFEST="$BACKUP_DIR/manifest.txt"
else
    log "warning: card backup $BACKUP_DIR not present; relying on on-unit .real originals"
fi

for proc in cluster gal dio_manager; do slay -f "$proc" 2>/dev/null; done
set_state ROLLING_BACK
rollback_from_journal
if [[ "$ROLLBACK_FAILED" -ne 0 ]]; then
    set_state ROLLBACK_INCOMPLETE
    fail 'some files were not restored; backup and journal retained for manual review'
fi
# Verify every factory file again before claiming restoration.
while read -r kind path size crc sha mode; do
    [[ "$kind" == factory ]] || continue
    verify_file "$(tgt "$path")" "$size" "$crc" || { set_state ROLLBACK_INCOMPLETE; fail "restored file does not match baseline: $path"; }
done < "$MANIFEST"
cluster_dir="$APP_ROOT/eso/bin/apps/cluster"
if [[ -d "$cluster_dir" ]]; then
    if dir_is_empty "$cluster_dir"; then rm -rf "$cluster_dir"; else log "left non-empty $cluster_dir in place"; fi
fi
rm -rf "$OTA_ROOT/modkit/Mods/$MODULE_NAME"
rm -f "$STATE_DIR/manifest.crc"
set_state RESTORED
log 'module files restored to the P2873 baseline; the journal and any card backup are retained'
log 'The ModKit loader and its servicemgrmibhigh wrapper are not removed by this module.'
