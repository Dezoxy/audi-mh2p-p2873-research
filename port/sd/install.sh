#!/bin/sh
# ModKit Update adapter: diagnostic probe and capture only, no persistent payload.
set -eu
: "${MOD_PATH:?ModKit must supply MOD_PATH}"
: "${MEDIA_PATH:?ModKit must supply MEDIA_PATH}"
rc=0
# The probe only reads, and it is what explains an unexpected release string, so it runs first
# and regardless of the release check.
ksh "$MOD_PATH/probe.sh" "$MEDIA_PATH/AudiP2873-probe" || rc=$?
case "${RELEASE_VERSION:-}" in
    MH2p_ER_AUG35_P2873|MH2p_ER_AUG35S_P2873) ;;
    *) echo 'Unsupported or unknown release; capture skipped.' >&2; exit 2;;
esac
sh "$MOD_PATH/collect.sh" "$MEDIA_PATH/AudiP2873-capture" || rc=$?
exit $rc
