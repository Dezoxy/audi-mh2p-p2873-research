#!/bin/ksh
# Card-root failsafe.sh for the diagnostic card. ModKit's persistence chain runs
# it early on every boot while the card is inserted. It only appends a line to a
# file on the card, which proves that the early-boot recovery hook is reached
# on this unit. It reads and writes nothing on the unit.
media=$(cd "$(dirname "$0")" && pwd -P)
print "$(date) failsafe hook reached; uname=$(uname -r 2>/dev/null)" >> "$media/AudiP2873-failsafe-heartbeat.txt"
