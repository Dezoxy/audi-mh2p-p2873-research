#!/bin/ksh
# Card-root failsafe.sh for the diagnostic card. ModKit's persistence chain runs
# it early on every boot while the card is inserted. It only appends a line to a
# file on the card, which proves that the early-boot recovery hook is reached
# on this unit. It reads and writes nothing on the unit.
media=$(cd "$(dirname "$0")" && pwd -P)
# Never write anywhere but the card: stop if the card path could not be resolved.
case "$media" in /fs/*|/*/*) ;; *) exit 0;; esac
[[ -d "$media" && -f "$media/failsafe.sh" ]] || exit 0
print "$(date) failsafe hook reached; uname=$(uname -r 2>/dev/null)" >> "$media/AudiP2873-failsafe-heartbeat.txt"
