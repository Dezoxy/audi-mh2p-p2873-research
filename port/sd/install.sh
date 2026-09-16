#!/bin/sh
# ModKit Update adapter: diagnostic probe and capture only, no persistent payload.
set -eu
: "${MOD_PATH:?ModKit must supply MOD_PATH}"
: "${MEDIA_PATH:?ModKit must supply MEDIA_PATH}"
case "${RELEASE_VERSION:-}" in
    MH2p_ER_AUG35_P2873|MH2p_ER_AUG35S_P2873) ;;
    *) echo 'Unsupported or unknown release; preflight stopped.' >&2; exit 2;;
esac
rc=0
ksh "$MOD_PATH/probe.sh" "$MEDIA_PATH/AudiP2873-probe" || rc=$?
sh "$MOD_PATH/collect.sh" "$MEDIA_PATH/AudiP2873-capture" || rc=$?
exit $rc
