#!/bin/sh
# Audi P2873 preflight. Reads the unit; writes only to a new output directory.
# Uses only shell builtins and tools from the boot image /bin (mkdir, cp, ls, uname), plus pc by
# absolute path: software-update mode has a short PATH that excludes the app partition.
# Usage: sh collect.sh /fs/sdb0/AudiP2873-capture [fixture-root]
set -eu
umask 077
case "$0" in */*) here=${0%/*};; *) here=.;; esac   # no dirname: it is not on the update-mode PATH
here=$(CDPATH= cd "$here" && pwd -P)
output=${1:?A new output directory on writable removable media is required}
source_root=${2:-}
case "$output" in /*) ;; *) echo 'Output must be absolute' >&2; exit 2;; esac
case "$output" in */.|*/..|*/) echo 'Invalid output directory' >&2; exit 2;; esac
pdir=${output%/*}; [ -n "$pdir" ] || pdir=/
parent=$(CDPATH= cd "$pdir" && pwd -P) || exit 2
output="$parent/${output##*/}"
if [ -n "$source_root" ]; then
    case "$source_root" in /*) ;; *) echo 'Fixture root must be absolute' >&2; exit 2;; esac
else
    # Never allow this collector to target the vehicle's internal partitions.
    case "$output" in /fs/sda0/*|/fs/sdb0/*|/fs/usb0_0/*) ;;
        *) echo 'Live output must be on SD or USB media' >&2; exit 2;;
    esac
fi
[ -d "$parent" ] || { echo 'Output parent missing' >&2; exit 2; }
# mkdir is deliberately exclusive: previous captures are never overwritten.
mkdir "$output" || exit 2
trap 'echo "Capture interrupted; no COMPLETE marker means incomplete" >&2; exit 1' HUP INT TERM
echo 'Audi P2873 preflight v1; no installation performed' > "$output/status.txt"
echo "${RELEASE_VERSION:-UNKNOWN}" > "$output/release.txt"
if [ -z "$source_root" ] && [ -x /mnt/app/armle/usr/bin/pc ]; then
    # Record raw evidence as well as the loader's version; do not guess its format.
    /mnt/app/armle/usr/bin/pc b:46924065:401 > "$output/release-pc.txt" 2>&1 || :
fi
{ echo "OEM=${OEM:-UNKNOWN}"; echo "TYPE=${TYPE:-UNKNOWN}"; echo "HMI_TYPE=${HMI_TYPE:-UNKNOWN}"; echo "MODKIT_VERSION=${MODKIT_VERSION:-UNKNOWN}"; } > "$output/loader-environment.txt"
uname -a > "$output/uname.txt"
failed=0
while IFS= read -r target; do
    [ -n "$target" ] || continue
    case "$target" in /mnt/app/*|/lib/*|/usr/lib/*) ;; *) echo 'Unexpected capture target' >&2; exit 2;; esac
    case "$target" in *..*|*'|'*) echo 'Invalid capture target' >&2; exit 2;; esac
    source="$source_root$target"
    destination="$output/files$target"
    mkdir -p "${destination%/*}"
    if [ -f "$source" ] && cp "$source" "$destination"; then
        echo "COPIED $target" >> "$output/status.txt"
    else
        echo "MISSING_OR_UNREADABLE $target" >> "$output/status.txt"
        failed=1
    fi
done < "$here/targets.txt"
# List only filenames, not contents, of existing classpath additions.
if [ -d "$source_root/mnt/app/eso/hmi/lsd/jars" ]; then
    ls -la "$source_root/mnt/app/eso/hmi/lsd/jars" > "$output/extra-jars.txt"
fi
if [ "$failed" -ne 0 ]; then
    echo 'Incomplete capture. No unit files were changed.' >&2
    exit 1
fi
echo 'capture-complete-v1' > "$output/COMPLETE"
echo 'Capture complete. Compare on the host; this is not installation approval.'
