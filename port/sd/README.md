# Audi P2873 SD preflight addon

This addon runs a tool probe and captures selected files for offline
comparison. The probe settles the installer's remaining on-unit assumptions
without shell access: it runs the real installer library functions on the
unit (`hd` output format, `df -kP` layout, the gzip-trailer CRC-32 pipeline,
the pure-shell directory test, ELF detection), records which utilities exist,
the ksh version, mounts, and whether ModKit's persistence chain is installed.
Results go to `AudiP2873-probe/` on the card; judge them on the host with:

```sh
python3 tools/verify_probe.py /Volumes/YOUR_CARD/AudiP2873-probe
```

`assumptions_hold: true` means the installer's tool assumptions are confirmed
for this unit. It is not an installation approval.

## Preparing the card (no SSH needed)

1. Format an SD card as FAT32 and copy the contents of the
   [MH2p SD ModKit](https://github.com/LawPaul/MH2p_SD_ModKit) repository at
   revision `82f9452` to the card root (`Meta/`, `Data/`, `Mods/`, `Logs/`).
   ModKit is not bundled here; its license is CC BY-NC-SA 4.0.
2. Unzip `dist/Audi-P2873-preflight-addon.zip` onto the card so that
   `Mods/AudiP2873Preflight/Update/` exists next to ModKit's own folders.
3. Insert the card and start the software update from the MMI menu as for a
   normal SD update. ModKit runs, executes this addon, and writes
   `Logs/AudiP2873Preflight.log`, `AudiP2873-probe/` and `AudiP2873-capture/`.
4. Take the card back to the host and run `verify_probe.py` and
   `verify_capture.py`.

Running ModKit is itself a modification: its loader replaces
`/mnt/app/eso/bin/servicemgrmibhigh` with a wrapper script and keeps the
factory binary as `servicemgrmibhigh0`. That is the persistence chain the
cluster installer later requires and the early-boot fail-safe depends on. This
addon adds nothing persistent of its own.

This addon captures selected files for offline comparison. It does not enable
cluster integration. It has no native payload, JAR, Post/Persist scripts,
firmware update, activation, or rollback writes. Removing the addon folder
removes the addon; captured evidence is retained until manually deleted.

This ZIP is **not a standalone SD installer**. It contains only
`Mods/AudiP2873Preflight/Update`. It requires an existing, verified way to run
scripts, such as MH2p SD ModKit. The ModKit loader itself can modify internal
storage, even when this addon only reads it. Do not initiate a firmware update
with this ZIP or install a loader merely to try it. Confirm the existing loader
and recovery access first. No automatic early-boot failsafe script is supplied.

With confirmed ModKit setup, the Update adapter checks the loader-reported
release (AUG35 or AUG35S P2873), then writes `AudiP2873-capture` to the card.
It refuses to overwrite that directory. Read its COMPLETE marker and host
comparison result; the loader's update-success message is not sufficient.

With an existing shell, the collector can instead be invoked explicitly:

```sh
sh /fs/sdb0/Mods/AudiP2873Preflight/Update/collect.sh /fs/sdb0/AudiP2873-capture
```

Only use the actual mounted media path. Have at least 256 MB free. The script
does not remount media. If the card is read-only, it stops. A second argument
is for host test fixtures only and must never be supplied on the vehicle.

Bring the card back to the host and run from the research workspace:

```sh
python3 tools/verify_capture.py /Volumes/YOUR_CARD/AudiP2873-capture
```

The collector copies the live JAR and selected binaries/libraries as private
evidence. Keep these files private. They are not a full unit backup or a proven
recovery image. The host checks their exact bytes against the downloaded
firmware. Unknown live release, missing files, changed wrappers, and mismatched
hashes fail that check. Even matching files do not validate display routing,
native ABI, coding, injected JAR precedence, or rollback feasibility.

Nothing is automatically installed after a successful comparison. The
experimental Java build is deliberately kept outside this SD package.
