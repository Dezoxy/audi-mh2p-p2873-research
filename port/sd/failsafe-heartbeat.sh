#!/bin/ksh
# Card-root failsafe.sh for the diagnostic card. ModKit's persistence chain runs
# it early on every boot while the card is inserted. It only appends a line to a
# file on the card, which proves that the early-boot recovery hook is reached
# on this unit. It reads and writes nothing on the unit.
case "$0" in */*) media=${0%/*};; *) media=.;; esac   # no dirname: it is not on the update-mode PATH
media=$(cd "$media" && pwd -P)
# Never write anywhere but the card: stop if the card path could not be resolved.
case "$media" in
    /fs/sda0|/fs/sdb0|/fs/usb0_0) ;;
    *) [[ -n "${AUDI_HEARTBEAT_TEST_DIR:-}" && "$media" == "$AUDI_HEARTBEAT_TEST_DIR" ]] || exit 0;;
esac
[[ -d "$media" && -f "$media/failsafe.sh" ]] || exit 0
print "$(date) failsafe hook reached; uname=$(uname -r 2>/dev/null)" >> "$media/AudiP2873-failsafe-heartbeat.txt"

# Normal-boot capture of the graphics libraries (they live in the stage-2 boot image, which may not
# be the root during the update stage). Reads /lib and /usr/lib; writes only into a new directory on
# the card, created exclusively so a second boot never overwrites a completed capture.
list="$media/Mods/AudiP2873Preflight/Update/bootlibs.txt"
root=${AUDI_BOOTLIBS_ROOT:-}
[[ -n "$root" && -z "${AUDI_HEARTBEAT_TEST_DIR:-}" ]] && exit 0   # the root override is for host tests only
[[ -f "$list" ]] || exit 0
# A completed capture is final. An incomplete one (interrupted boot, library missing) must not
# block retries, so each attempt uses the next free numbered directory.
out=""
for n in "" -2 -3 -4 -5 -6 -7 -8 -9; do
    cand="$media/AudiP2873-bootlibs$n"
    [[ -f "$cand/COMPLETE" ]] && exit 0
    [[ -e "$cand" ]] && continue
    out=$cand; break
done
[[ -n "$out" ]] || exit 0
mkdir "$out" || exit 0
failed=0
while read -r target; do
    [[ -n "$target" ]] || continue
    case "$target" in /lib/*|/usr/lib/*) ;; *) continue;; esac
    case "$target" in *..*) continue;; esac
    src="$root$target"; dest="$out/files$target"
    mkdir -p "${dest%/*}"
    if [[ -f "$src" ]] && cp "$src" "$dest"; then print "COPIED $target" >> "$out/status.txt"
    else print "MISSING_OR_UNREADABLE $target" >> "$out/status.txt"; failed=1; fi
done < "$list"
[[ "$failed" -eq 0 ]] && print 'capture-complete-v1' > "$out/COMPLETE"
