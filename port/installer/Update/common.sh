#!/bin/ksh
# Shared library for the Audi cluster integration ModKit module.
# Sourced by install.sh and uninstall.sh. Uses only utilities present in the
# P2873 app image: gzip dd hd wc cp mv rm mkdir chmod ls df sync awk sed.
# No hash utility exists on the unit; integrity is size + CRC-32 taken from
# the gzip trailer (RFC 1952). This detects wrong versions and corruption,
# not deliberate tampering. SHA-256 in the manifest is for host verification.

MODULE_NAME=AudiClusterIntegration
MANIFEST_VERSION=1
MIN_FREE_KB=16384

# Fixture mode keeps every path under one host directory and skips mounts.
if [[ -n "${AUDI_CLUSTER_FIXTURE_ROOT:-}" ]]; then
    case "$AUDI_CLUSTER_FIXTURE_ROOT" in /*) ;; *) print -u2 'fixture root must be absolute'; exit 2;; esac
    FIXTURE_ROOT=$AUDI_CLUSTER_FIXTURE_ROOT
else
    FIXTURE_ROOT=
fi
APP_ROOT="$FIXTURE_ROOT/mnt/app"
OTA_ROOT="$FIXTURE_ROOT/mnt/ota"
STATE_DIR="$APP_ROOT/eso/.audi-cluster"
JOURNAL="$STATE_DIR/journal"
STATE_FILE="$STATE_DIR/state"

fail() { print -u2 "STOP: $*"; exit 2; }
log() { print "$*"; }

require_env() {
    [[ -n "${MOD_PATH:-}" ]] || fail 'MOD_PATH not supplied by loader'
    [[ -n "${MEDIA_PATH:-}" ]] || fail 'MEDIA_PATH not supplied by loader'
    [[ -d "$MOD_PATH" ]] || fail "MOD_PATH missing: $MOD_PATH"
    [[ -d "$MEDIA_PATH" ]] || fail "MEDIA_PATH missing: $MEDIA_PATH"
}

# Loader-reported release only; this module never runs pc itself.
check_release() {
    typeset accepted=0 line kind value
    while read -r kind value; do
        [[ "$kind" == release && "$value" == "${RELEASE_VERSION:-}" ]] && accepted=1
    done < "$MANIFEST"
    (( accepted == 1 )) || fail "release '${RELEASE_VERSION:-UNKNOWN}' is not accepted by the manifest"
}

file_size() { set -- $(wc -c < "$1"); print "$1"; }

# Prints the CRC-32 of a file as 8 lowercase hex digits, or returns nonzero.
file_crc32() {
    typeset f=$1 tmp size hex
    [[ -f "$f" ]] || return 1
    tmp="$SCRATCH/crc.$$"
    gzip -1 -c < "$f" > "$tmp" || { rm -f "$tmp"; return 1; }
    size=$(file_size "$tmp")
    (( size >= 18 )) || { rm -f "$tmp"; return 1; }
    hex=$(dd if="$tmp" bs=1 skip=$((size - 8)) count=4 2>/dev/null | hd | awk '
        NR == 1 { n = 0; for (i = 2; i <= NF && n < 4; i++) {
            if ($i ~ /^[0-9a-fA-F][0-9a-fA-F]$/) { b[n++] = tolower($i) } else { break } }
            if (n == 4) print b[3] b[2] b[1] b[0]; }')
    rm -f "$tmp"
    case "$hex" in
        [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) print "$hex"; return 0;;
    esac
    return 1
}

# verify_file PATH SIZE CRC -> 0 when both match. Symlinks are never accepted.
verify_file() {
    typeset f=$1 want_size=$2 want_crc=$3 have_size have_crc
    [[ -f "$f" && ! -L "$f" ]] || return 1
    have_size=$(file_size "$f") || return 1
    [[ "$have_size" == "$want_size" ]] || return 1
    have_crc=$(file_crc32 "$f") || return 1
    [[ "$have_crc" == "$want_crc" ]]
}

# The selftest line in the manifest names a shipped file with known values.
selftest_hash_tool() {
    typeset kind name size crc found=0
    while read -r kind name size crc; do
        [[ "$kind" == selftest ]] || continue
        found=1
        verify_file "$MOD_PATH/$name" "$size" "$crc" || fail 'hash self-test failed; no usable integrity check on this unit'
    done < "$MANIFEST"
    (( found == 1 )) || fail 'manifest has no selftest entry'
    # An equal-size copy with its last byte changed must be rejected, or the
    # CRC path is blind. The shipped selftest file ends with a zero byte.
    dd if="$MOD_PATH/$name" of="$SCRATCH/selftest.copy" bs=1 count=$((size - 1)) 2>/dev/null
    print -n y >> "$SCRATCH/selftest.copy"
    verify_file "$SCRATCH/selftest.copy" "$size" "$crc" && fail 'hash self-test accepted altered data'
    rm -f "$SCRATCH/selftest.copy"
}

# Pure-shell emptiness test; the unit's ls flag set is unconfirmed.
dir_is_empty() {
    typeset f
    for f in "$1"/* "$1"/.*; do
        case "$f" in */.|*/..) continue;; esac
        [[ -e "$f" || -L "$f" ]] && return 1
    done
    return 0
}

free_kb() {
    typeset kb
    # Exactly one data row is required; a wrapped or multi-row result is rejected.
    kb=$(df -kP "$1" 2>/dev/null | awk 'NR == 2 { v = $4 } END { if (NR == 2) print v }')
    case "$kb" in ''|*[!0-9]*) return 1;; esac
    print "$kb"
}

check_space() {
    typeset kb
    kb=$(free_kb "$1") || fail "cannot determine free space on $1"
    (( kb >= $2 )) || fail "insufficient space on $1: ${kb} KiB free, need $2"
}

journal_write() {
    print "$(date +%Y%m%dT%H%M%S) $*" >> "$JOURNAL" || fail 'journal write failed'
    sync
}

set_state() {
    print "$1" > "$STATE_FILE.tmp" && mv -f "$STATE_FILE.tmp" "$STATE_FILE" || fail 'state write failed'
    sync
    # Mirror to the card for the operator; the unit copy is authoritative.
    [[ -d "$BACKUP_DIR" ]] && { cp -f "$STATE_FILE" "$BACKUP_DIR/state" 2>/dev/null; cp -f "$JOURNAL" "$BACKUP_DIR/journal" 2>/dev/null; }
    return 0
}

current_state() { [[ -f "$STATE_FILE" ]] && cat "$STATE_FILE" || print NONE; }

# Manifest accessors. Formats (whitespace separated, one record per line):
#   release <name>
#   selftest <file> <size> <crc32>
#   payload <file> <size> <crc32> <sha256> <mode>
#   factory <abs-path> <size> <crc32> <sha256> <mode>
#   op new <abs-path> <payload-file> <mode>
#   op wrap <abs-path> <payload-file> <mode>   (factory file moves to <path>.real)
manifest_lookup() {
    # manifest_lookup KIND KEY -> prints the rest of the matching record
    awk -v k="$1" -v key="$2" '$1 == k && $2 == key { $1 = ""; $2 = ""; sub(/^  /, ""); print; exit }' "$MANIFEST"
}

payload_path() { print "$MOD_PATH/payload/$1"; }

# Manifest and journal hold unit paths; every file operation goes through tgt.
tgt() { print "$FIXTURE_ROOT$1"; }

# The only early-boot recovery path is ModKit's persistence chain:
# servicemgrmibhigh (script) -> servicemgrmibhigh0 (factory ELF) -> modkit_persist.sh
# -> card-root failsafe.sh. It must already be installed and intact, so the
# cluster install never shares a transaction with ModKit's own first install.
is_elf() { [[ -f "$1" ]] && [[ "$(dd if="$1" bs=1 skip=1 count=3 2>/dev/null)" == ELF ]]; }
check_recovery_chain() {
    typeset bin="$APP_ROOT/eso/bin"
    [[ -f "$OTA_ROOT/modkit/modkit_persist.sh" ]] || fail 'ModKit persistence is not installed yet; run the plain ModKit SD update first, confirm a normal boot, then rerun with this module'
    is_elf "$bin/servicemgrmibhigh" && fail 'servicemgrmibhigh is still the factory binary; ModKit persistence wrapper is not active'
    is_elf "$bin/servicemgrmibhigh0" || fail 'servicemgrmibhigh0 is not the factory binary; unknown loader state'
    [[ -f "$bin/servicemgrmibhigh" ]] || fail 'servicemgrmibhigh wrapper missing'
}

# Shared by uninstall.sh and failsafe.sh. Expects MANIFEST, JOURNAL and state
# present. Prints progress; returns 0 only after every factory file verifies.
perform_rollback() {
    typeset kind path size crc sha mode cluster_dir
    [[ -f "$JOURNAL" ]] || { print -u2 'state present but journal missing; manual review required'; return 1; }
    BACKUP_DIR=$(awk '$2 == "BEGIN" { print $3 }' "$JOURNAL" | tail -1)
    [[ -n "$BACKUP_DIR" ]] || { print -u2 'journal has no BEGIN record'; return 1; }
    if [[ -f "$BACKUP_DIR/manifest.txt" ]]; then
        MANIFEST="$BACKUP_DIR/manifest.txt"
    else
        log "warning: card backup $BACKUP_DIR not present; relying on on-unit .real originals"
    fi
    for proc in cluster gal dio_manager; do slay -f "$proc" 2>/dev/null; done
    set_state ROLLING_BACK
    rollback_from_journal
    if (( ROLLBACK_FAILED != 0 )); then
        set_state ROLLBACK_INCOMPLETE
        print -u2 'some files were not restored; backup and journal retained for manual review'
        return 1
    fi
    while read -r kind path size crc sha mode; do
        [[ "$kind" == factory ]] || continue
        verify_file "$(tgt "$path")" "$size" "$crc" || { set_state ROLLBACK_INCOMPLETE; print -u2 "restored file does not match baseline: $path"; return 1; }
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
}

# Test-only fault injection. Inert unless a fixture root is active.
maybe_fault() {
    [[ -n "$FIXTURE_ROOT" ]] || return 0
    [[ "${AUDI_CLUSTER_FAULT:-}" == "$1" ]] || return 0
    print -u2 "FAULT: simulated interruption at $1"
    exit 99
}

# Restore one journaled replacement. Arguments: kind unit-path payload mode.
# Returns 0 on verified restoration, 1 when the current file is not ours.
restore_entry() {
    typeset kind=$1 path=$2 payload=$3 mode=$4 rec psize pcrc fsize fcrc fmode real file
    file=$(tgt "$path")
    rec=$(manifest_lookup payload "$payload"); set -- $rec; psize=${1:-}; pcrc=${2:-}
    [[ -n "$psize" && -n "$pcrc" ]] || { print -u2 "unknown payload $payload in journal"; return 1; }
    if [[ -e "$file" ]] && ! verify_file "$file" "$psize" "$pcrc"; then
        print -u2 "refusing to touch $path: bytes differ from the installed payload"
        return 1
    fi
    case "$kind" in
        new)
            rm -f "$file" || return 1
            journal_write RESTORE_DONE "$kind" "$path"
            ;;
        wrap)
            rec=$(manifest_lookup factory "$path"); set -- $rec; fsize=${1:-}; fcrc=${2:-}; fmode=${4:-}
            [[ -n "$fsize" && -n "$fcrc" && -n "$fmode" ]] || { print -u2 "no factory record for $path"; return 1; }
            real="$file.real"
            if verify_file "$real" "$fsize" "$fcrc"; then
                mv -f "$real" "$file" || return 1
            elif verify_file "$BACKUP_DIR/files$path" "$fsize" "$fcrc"; then
                cp "$BACKUP_DIR/files$path" "$file.restore" || return 1
                verify_file "$file.restore" "$fsize" "$fcrc" || return 1
                mv -f "$file.restore" "$file" || return 1
                rm -f "$real"
            else
                print -u2 "no verified original for $path in $real or the card backup"
                return 1
            fi
            chmod "$fmode" "$file" || return 1
            verify_file "$file" "$fsize" "$fcrc" || return 1
            journal_write RESTORE_DONE "$kind" "$path"
            ;;
        *) return 1;;
    esac
}

# Remove staged copies that were never switched in. Safe on any state.
clean_staging() {
    typeset kind op path payload mode
    while read -r kind op path payload mode; do
        [[ "$kind" == op ]] || continue
        rm -f "$(tgt "$path").staging" "$(tgt "$path").restore"
    done < "$MANIFEST"
}

# Walk REPLACE_BEGIN records newest first and undo each; a record without a
# matching REPLACE_DONE is a switch interrupted midway and is handled the same
# way, because restore_entry tolerates a missing target. Sets ROLLBACK_FAILED.
rollback_from_journal() {
    typeset lines line stamp event kind path payload mode n
    ROLLBACK_FAILED=0
    clean_staging
    [[ -f "$JOURNAL" ]] || return 0
    lines=$(awk '$2 == "REPLACE_BEGIN" { print NR }' "$JOURNAL" | sed '1!G;h;$!d')
    for n in $lines; do
        line=$(sed -n "${n}p" "$JOURNAL"); set -- $line
        stamp=$1; event=$2; kind=$3; path=$4; payload=$5; mode=$6
        if awk -v p="$path" '$2 == "RESTORE_DONE" && $4 == p { f = 1 } END { exit !f }' "$JOURNAL"; then
            continue
        fi
        restore_entry "$kind" "$path" "$payload" "$mode" || ROLLBACK_FAILED=1
    done
}
