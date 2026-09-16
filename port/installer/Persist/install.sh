#!/bin/ksh
# Startup entry copied to /mnt/ota by the ModKit loader regardless of the
# Update result. It therefore gates on the transaction state written only
# after every payload file was verified in place.
root=${AUDI_CLUSTER_FIXTURE_ROOT:-}
state="$root/mnt/app/eso/.audi-cluster/state"
daemon="$root/mnt/app/eso/bin/apps/cluster/cluster"
[[ -f "$state" && "$(cat "$state")" == COMMITTED ]] || exit 0
[[ -x "$daemon" ]] || exit 0
if [[ -n "$root" ]]; then print "would start $daemon"; exit 0; fi
"$daemon" daemon verbose=2 &
