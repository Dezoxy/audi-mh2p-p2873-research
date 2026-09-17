#!/bin/ksh
# Audi cluster integration: journaled install transaction (ModKit Update stage).
# Implements port/installer/CONTRACT.md. Not vehicle-tested.
set -u
here=$(cd "$(dirname "$0")" && pwd -P)
. "$here/common.sh"
MANIFEST="$here/manifest.txt"
[[ -f "$MANIFEST" ]] || fail 'manifest.txt missing'
require_env
SCRATCH="$MEDIA_PATH/.audi-cluster-scratch.$$"
mkdir -p "$SCRATCH" || fail 'cannot create scratch on media'
trap 'rm -rf "$SCRATCH"' EXIT

check_release
selftest_hash_tool
[[ -d "$APP_ROOT/eso" ]] || fail "application filesystem not present at $APP_ROOT"
check_recovery_chain
TXID=$(date +%Y%m%dT%H%M%S).$$
BACKUP_ROOT="$MEDIA_PATH/${MODULE_NAME}-backup"
BACKUP_DIR="$BACKUP_ROOT/$TXID"

# 1. Prior state. Committed with this manifest: nothing to do. Anything else
#    in progress means an interrupted transaction; recover, then stop.
manifest_crc=$(file_crc32 "$MANIFEST") || fail 'cannot checksum manifest'
case "$(current_state)" in
    NONE|RESTORED) ;;
    COMMITTED)
        if [[ -f "$STATE_DIR/manifest.crc" && "$(cat "$STATE_DIR/manifest.crc")" == "$manifest_crc" ]]; then
            log 'already installed with this manifest; nothing changed'; exit 0
        fi
        fail 'a different version is installed; uninstall it first'
        ;;
    *)
        log 'interrupted transaction found; rolling back before anything else'
        BACKUP_DIR=$(awk '$2 == "BEGIN" { print $3 }' "$JOURNAL" | tail -1)
        [[ -f "$BACKUP_DIR/manifest.txt" ]] && MANIFEST="$BACKUP_DIR/manifest.txt"
        rollback_from_journal
        if [[ "$ROLLBACK_FAILED" -eq 0 ]]; then
            set_state RESTORED; fail 'previous interrupted install was rolled back; review logs and rerun'
        fi
        set_state ROLLBACK_INCOMPLETE; fail 'rollback incomplete; manual review required'
        ;;
esac

# 2. Factory files must match the supplied firmware exactly; no wrappers,
#    no stray cluster JARs, no leftover .real copies, no targets pre-existing.
while read -r kind path size crc sha mode; do
    [[ "$kind" == factory ]] || continue
    verify_file "$(tgt "$path")" "$size" "$crc" || fail "factory file differs from the P2873 baseline: $path"
    [[ -e "$(tgt "$path").real" ]] && fail "unexpected existing wrapper state: $path.real"
done < "$MANIFEST"
while read -r kind op path payload mode; do
    [[ "$kind" == op && "$op" == new ]] || continue
    [[ -e "$(tgt "$path")" ]] && fail "target already exists; unknown prior state: $path"
done < "$MANIFEST"
for j in "$APP_ROOT"/eso/hmi/lsd/jars/ClusterIntegration_* "$APP_ROOT"/eso/hmi/lsd/jars/AndroidAutoCluster_*; do
    [[ -e "$j" ]] && fail "existing cluster JAR found: $j"
done

# 3. Payload on the card must match the pinned manifest.
payload_bytes=0
while read -r kind name size crc sha mode; do
    [[ "$kind" == payload ]] || continue
    verify_file "$(payload_path "$name")" "$size" "$crc" || fail "payload does not match manifest: $name"
    payload_bytes=$((payload_bytes + size))
done < "$MANIFEST"

# 4. Space on both media, then an exclusive backup directory (never reused).
check_space "$APP_ROOT" $((payload_bytes / 1024 + MIN_FREE_KB))
check_space "$MEDIA_PATH" $((payload_bytes / 1024 + MIN_FREE_KB))
mkdir -p "$BACKUP_ROOT" || fail 'cannot create backup root on media'
mkdir "$BACKUP_DIR" || fail "backup directory already exists: $BACKUP_DIR"
mkdir -p "$STATE_DIR" || fail "cannot write to $APP_ROOT; is it mounted read-write?"
[[ -f "$JOURNAL" ]] && { mv -f "$JOURNAL" "$JOURNAL.$TXID.previous" || fail 'cannot rotate journal'; }
journal_write BEGIN "$BACKUP_DIR" "$manifest_crc"
set_state BACKING_UP

# 5. Back up every file that will be replaced, then reread and verify.
while read -r kind path size crc sha mode; do
    [[ "$kind" == factory ]] || continue
    dest="$BACKUP_DIR/files$path"
    mkdir -p "$(dirname "$dest")" || fail 'backup mkdir failed'
    cp "$(tgt "$path")" "$dest" || fail "backup copy failed for $path"
    verify_file "$dest" "$size" "$crc" || fail "backup reread mismatch for $path"
    ls -ld "$(tgt "$path")" >> "$BACKUP_DIR/original-modes.txt"
    journal_write BACKUP_OK "$path" "$crc"
done < "$MANIFEST"
cp "$MANIFEST" "$BACKUP_DIR/manifest.txt" || fail 'cannot record manifest with backup'
set_state BACKUP_COMPLETE

# 6. Stage on the destination filesystem and verify before any switch.
maybe_fault before-staging
while read -r kind op path payload mode; do
    [[ "$kind" == op ]] || continue
    rec=$(manifest_lookup payload "$payload"); set -- $rec
    file=$(tgt "$path")
    mkdir -p "$(dirname "$file")" || fail "cannot create $(dirname "$path")"
    cp "$(payload_path "$payload")" "$file.staging" || fail "staging copy failed for $path"
    verify_file "$file.staging" "$1" "$2" || fail "staged file mismatch for $path"
    chmod "$mode" "$file.staging" || fail "chmod failed for $path.staging"
    journal_write STAGED "$path"
done < "$MANIFEST"
maybe_fault after-staging
set_state REPLACING

# 7. Quiesce, then switch files one by one with a journal record per switch.
for proc in cluster gal dio_manager; do slay -f "$proc" 2>/dev/null; done
n=0
while read -r kind op path payload mode; do
    [[ "$kind" == op ]] || continue
    n=$((n + 1))
    file=$(tgt "$path")
    journal_write REPLACE_BEGIN "$op" "$path" "$payload" "$mode"
    maybe_fault "before-move-original-$n"
    if [[ "$op" == wrap ]]; then
        [[ -e "$file.real" ]] && fail "refusing to overwrite $path.real"
        mv "$file" "$file.real" || fail "cannot move original $path"
        sync
        maybe_fault "mid-switch-$n"
    fi
    mv -f "$file.staging" "$file" || fail "switch failed for $path"
    sync
    journal_write REPLACE_DONE "$op" "$path" "$payload" "$mode"
    maybe_fault "after-replace-$n"
done < "$MANIFEST"

# 8. Reread every final file; only then record commit and the Persist gate.
while read -r kind op path payload mode; do
    [[ "$kind" == op ]] || continue
    rec=$(manifest_lookup payload "$payload"); set -- $rec
    verify_file "$(tgt "$path")" "$1" "$2" || fail "post-switch verification failed for $path"
done < "$MANIFEST"
print "$manifest_crc" > "$STATE_DIR/manifest.crc"
set_state COMMITTED
log "installed; transaction $TXID, backup at $BACKUP_DIR"
log 'The ModKit loader itself still installs its own persistence wrapper; that is outside this module.'
