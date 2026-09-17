#!/bin/sh
# ModKit Update adapter: diagnostic probe and file capture only, no persistent payload.
# Both stages only read the unit and write to the card, so neither is gated on the release
# string; the collector records the release for the host verifier to judge.
set -eu
: "${MOD_PATH:?ModKit must supply MOD_PATH}"
: "${MEDIA_PATH:?ModKit must supply MEDIA_PATH}"
rc=0
ksh "$MOD_PATH/probe.sh" "$MEDIA_PATH/AudiP2873-probe" || rc=$?
sh "$MOD_PATH/collect.sh" "$MEDIA_PATH/AudiP2873-capture" || rc=$?
exit $rc
