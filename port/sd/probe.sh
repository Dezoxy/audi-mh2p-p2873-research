#!/bin/ksh
# Audi P2873 tool probe: records how the unit's own utilities behave, using the
# real installer library functions. Reads the unit; writes only to a new output
# directory on the card. Usage: ksh probe.sh /fs/sdb0/AudiP2873-probe
set -u
case "$0" in */*) here=${0%/*};; *) here=.;; esac   # no dirname: it is not on the update-mode PATH
here=$(cd "$here" && pwd -P)
out=${1:?A new output directory on removable media is required}
mkdir "$out" || { print -u2 "refusing to overwrite $out"; exit 2; }
SCRATCH="$out/scratch"; mkdir "$SCRATCH" || exit 2
# Exactly what the update stage gave us, before common.sh appends the app-partition directories.
{ print "PATH_RECEIVED=${PATH:-unset}"; print "LD_LIBRARY_PATH_RECEIVED=${LD_LIBRARY_PATH:-unset}"; } > "$out/path-received.txt"
lookup_tools() {
    typeset t p
    for t in gzip dd hd wc cp mv rm mkdir chmod ls df sync awk sed date cat head tail dirname basename slay find expr mount ksh sh \
             printf cksum md5sum sum cmp od rmdir tee grep cut sockstat ifconfig pidin; do
        p=$(whence -p "$t" 2>/dev/null); print "$t ${p:-MISSING}"
    done
}
lookup_tools > "$out/tools-before.txt"
case "$out" in */*) media_default=${out%/*};; *) media_default=.;; esac
MOD_PATH=$here; MEDIA_PATH=${MEDIA_PATH:-$media_default}
. "$here/common.sh"
result() { print "check $*" >> "$out/result.txt"; }
run() { typeset name=$1; shift; "$@" > "$out/$name.txt" 2>&1; print "$name rc=$?" >> "$out/status.txt"; }

{
    print "RELEASE_VERSION=${RELEASE_VERSION:-unset} OEM=${OEM:-unset} TYPE=${TYPE:-unset} MODKIT_VERSION=${MODKIT_VERSION:-unset}"
    print "MOD_PATH=$MOD_PATH MEDIA_PATH=$MEDIA_PATH APP_ROOT=$APP_ROOT"
    print "KSH_VERSION=${KSH_VERSION:-unset} SHELL0=$0"
    print "PATH_NOW=$PATH"
    uname -a
} > "$out/env.txt" 2>&1

lookup_tools > "$out/tools.txt"   # after the append

run wc-raw sh -c "wc -c < '$here/selftest.bin'"
run hd-first8 sh -c "dd if='$here/selftest.bin' bs=1 count=8 2>/dev/null | hd"
run hd-last8 sh -c "dd if='$here/selftest.bin' bs=1 skip=4088 count=8 2>/dev/null | hd"
gzip -1 -c < "$here/selftest.bin" > "$SCRATCH/selftest.gz" 2> "$out/gzip-stderr.txt"
gzsize=$(file_size "$SCRATCH/selftest.gz")
run hd-gzip-trailer sh -c "dd if='$SCRATCH/selftest.gz' bs=1 skip=$((gzsize - 8)) count=8 2>/dev/null | hd"
run gzip-version sh -c "gzip -V 2>&1 | head -3; gzip -h 2>&1 | head -4"

# The library's own CRC pipeline against a shipped file and the factory version file.
while read -r name esize ecrc; do
    case "$name" in selftest) f="$here/selftest.bin";; img_ver) f="$APP_ROOT/img_ver.txt";; *) continue;; esac
    got=$(file_crc32 "$f") || got=ERROR
    size=$(file_size "$f" 2>/dev/null) || size=ERROR
    if [[ "$got" == "$ecrc" && "$size" == "$esize" ]]; then result "crc-$name PASS size=$size crc=$got"
    else result "crc-$name FAIL expected size=$esize crc=$ecrc got size=$size crc=$got"; fi
done < "$here/probe-expected.txt"
dd if="$here/selftest.bin" of="$SCRATCH/altered" bs=1 count=4095 2>/dev/null; print -n y >> "$SCRATCH/altered"
read -r _ esize ecrc < "$here/probe-expected.txt"
if verify_file "$SCRATCH/altered" "$esize" "$ecrc"; then result 'crc-altered-rejected FAIL altered copy accepted'; else result 'crc-altered-rejected PASS'; fi

run df-app df -kP "$APP_ROOT"
run df-media df -kP "$MEDIA_PATH"
run df-plain df
for target in "$APP_ROOT" "$MEDIA_PATH"; do
    kb=$(free_kb "$target") && result "free-kb PASS $target $kb" || result "free-kb FAIL $target unparseable"
done

mkdir "$SCRATCH/lsprobe" && : > "$SCRATCH/lsprobe/.hidden"
run ls-A ls -A "$SCRATCH/lsprobe"
run ls-a ls -a "$SCRATCH/lsprobe"
mkdir "$SCRATCH/empty"
if dir_is_empty "$SCRATCH/empty" && ! dir_is_empty "$SCRATCH/lsprobe"; then result 'dir-is-empty PASS'; else result 'dir-is-empty FAIL'; fi
run ls-ld ls -ld "$APP_ROOT/eso/bin/apps/gal" "$APP_ROOT/eso/bin/apps/dio_manager" "$APP_ROOT/eso/bin/servicemgrmibhigh" "$APP_ROOT/eso/bin/servicemgrmibhigh0"

is_elf "$APP_ROOT/eso/bin/servicemgrmibhigh" && a=elf || a=not-elf
is_elf "$APP_ROOT/eso/bin/servicemgrmibhigh0" && b=elf || b=not-elf
[[ -f "$OTA_ROOT/modkit/modkit_persist.sh" ]] && c=present || c=missing
result "modkit-chain INFO servicemgrmibhigh=$a servicemgrmibhigh0=$b modkit_persist=$c"
run mounts mount
# Network state: is there a hardware-free route to a shell (Wi-Fi AP or client)?
run net-ifconfig ifconfig -a
run net-sockstat sockstat -l
run net-sockstat-all sockstat
run net-processes sh -c "pidin ar 2>&1 | awk '/sshd|telnetd|inetd|hostapd|wpa_supplicant|dhcpd|io-pkt|ifwatchd/'"
run net-ssh-files sh -c "ls -la '$APP_ROOT/root/.ssh' '$APP_ROOT/etc/ssh' /etc/ssh '$APP_ROOT/armle/usr/sbin/sshd' '$APP_ROOT/armle/usr/sbin/telnetd' '$APP_ROOT/armle/usr/sbin/inetd' 2>&1"
run net-inetd sh -c "cat /etc/inetd.conf '$APP_ROOT/etc/inetd.conf' 2>&1"
run net-wifi-conf sh -c "ls -la /etc/hostapd* /etc/wpa* '$APP_ROOT/etc/hostapd'* '$APP_ROOT/etc/wpa'* /var/etc/hostapd* /ramdisk/pps/services/wifi* 2>&1"
rm -rf "$SCRATCH"
print 'probe-complete-v1' > "$out/COMPLETE"
print "Probe complete in $out; run tools/verify_probe.py on the host."
