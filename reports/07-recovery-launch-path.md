# Recovery launch path — 2026-09-16

Contract item 6 asked for an independently usable recovery launch path. It is
now implemented and tested on the host; it has not run on a vehicle.

## Design

ModKit's persistence chain is the only early-boot hook available without the
HMI: the factory `servicemgrmibhigh` is replaced by a script that starts the
factory binary as `servicemgrmibhigh0` and then runs `modkit_persist.sh`,
which runs a card-root `failsafe.sh` before any mod. The module uses that hook.

- `failsafe.sh` (card root, shipped by the builder) does nothing unless the
  operator has created `AudiClusterIntegration-RECOVER` next to it. With the
  marker it remounts `/mnt/app` writable, runs the same rollback core as
  `uninstall.sh` from the on-unit journal and the card backup, logs to
  `AudiClusterIntegration-failsafe.log` on the card, and deletes the marker
  only after every factory file verified. An incomplete recovery keeps the
  marker and the state `ROLLBACK_INCOMPLETE`.
- `install.sh` now refuses to run unless that chain is already installed and
  intact: `modkit_persist.sh` present under `/mnt/ota/modkit`,
  `servicemgrmibhigh` not an ELF file, `servicemgrmibhigh0` an ELF file. On a
  first-ever ModKit run the loader installs its wrapper only after the addons
  have executed, so the check fails by design. The required procedure is
  therefore: run the plain ModKit SD update once, confirm a normal boot, then
  rerun with this module. The cluster install never shares a transaction with
  ModKit's own first install.
- `uninstall.sh` and `failsafe.sh` share `perform_rollback` in `common.sh`,
  so the two recovery paths cannot drift apart.

## Demonstrating that the hook is reached

Matching ModKit's script bytes shows the chain is installed, not that it
executes. The diagnostic card therefore carries a card-root `failsafe.sh`
(`port/sd/failsafe-heartbeat.sh`) that only appends a timestamp line to
`AudiP2873-failsafe-heartbeat.txt` on the card. After the SD update, one
further normal boot with the card inserted must add a line; `verify_probe.py`
reports the lines as `failsafe_heartbeats`. This proves hook execution only,
not ordering before HMI class loading or successful rollback. The cluster
module's own `failsafe.sh` writes the same heartbeat before its marker check.

## Unattended rollback at boot

Update publishes and verifies the complete recovery package before payload
staging. It cannot rely on ModKit's later copy of Persist, because power loss
during Update prevents that copy. Independent of the card, the startup entry
rolls back any transaction whose state is not `COMMITTED` or `RESTORED` (report 06, third
and fourth reviews). The card fail-safe remains the route for a committed
install that misbehaves, and for an unattended rollback that reports incomplete.

## What this does and does not guarantee

The fail-safe is reachable only while `servicemgrmibhigh` still starts and
`modkit_persist.sh` still runs. Those files are ModKit's, are not touched by
this module, and the precondition checks them before any write. It does not
recover from damage outside this module's journal, and it is not a substitute
for a full unit backup.

## Tests

The original five recovery host tests cover rollback via marker after an interrupted install, no-op
without the marker, marker kept when a file was changed after install, marker
left for the operator when nothing is installed, and install refusal when the
persistence chain is missing or incomplete. Current coverage also includes
ModKit discovering the preinstalled recovery entry with the whole card absent;
see report 06 for validation results.

## On-unit checks: collected by SD card

Shell access to the unit is not available, so the two remaining tool-format
assumptions are collected by the preflight addon instead. `port/sd/probe.sh`
runs inside ModKit's update stage, sources the real `common.sh`, and records
the outputs and pass/fail of `file_crc32`, `verify_file`, `free_kb`,
`dir_is_empty` and `is_elf` on the unit, together with raw `hd`, `df`, `ls`,
`mount`, tool presence and the ksh version. `tools/verify_probe.py` judges
the result on the host and applies the same `hd` parsing rule as the
installer. Three host tests cover the probe: a conforming fixture is accepted,
a wrong `hd` format and a missing tool are rejected, and an existing output
directory is never overwritten. Card preparation is in `port/sd/README.md`.

With shell access, the equivalent manual commands would be:

```sh
gzip -1 -c /mnt/app/img_ver.txt | dd bs=1 skip=$(( $(gzip -1 -c /mnt/app/img_ver.txt | wc -c) - 8 )) count=4 2>/dev/null | hd
df -kP /mnt/app
df -kP /fs/sdb0
```

The first must print one line whose first four hex tokens after the offset
are the bytes `d7 20 ca 7f` (CRC-32 `7fca20d7` of the P2873 `img_ver.txt`,
little-endian). The `df` commands must print exactly one header and one data
row with the free-space number in column four.
