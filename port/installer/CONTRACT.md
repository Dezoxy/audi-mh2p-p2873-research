# Audi cluster installer contract

Implemented on 2026-09-16 in `Update/` and `Persist/`; host fault tests in `tests/test_cluster_installer.py`. See `reports/06-installer-transaction.md`. Vehicle validation is still open.

The stock G35S vehicle uses the supplied P2873 update. That package is the
working baseline. A separate trip to collect the same firmware is not required.
The checks below belong inside the eventual installation process.

## Packaging and launch

Reuse MH2p SD ModKit's activation mechanism and add one module under
`Mods/AudiClusterIntegration`. Pin the loader revision and payload hashes.
The current diagnostic addon is optional research tooling, not a prerequisite.
No cluster installation package may be labelled ready while native payload
compatibility or recovery validation is unresolved.

The unmodified ModKit installer does not propagate an addon failure as a global
abort: it runs the addon, then continues installing its persistence wrapper.
Therefore our checks can prevent cluster writes, but cannot promise that a
failed addon leaves the stock vehicle completely untouched by the base loader.
This must be explicit in the eventual instructions. Do not silently modify the
loader's signed activation files to claim a stronger guarantee.

## Required checks before any cluster payload writes

1. Accept the expected P2873 release and Audi identity. Do not reject solely
   because package G35 and vehicle G35S labels differ.
2. Verify the exact relevant factory files against the supplied firmware.
   Verify the SD payload itself against the pinned release manifest. If a
   suitable target hash utility is unavailable, stop; do not fall back to
   filename, byte count, or a successful copy as proof of integrity.
3. Detect existing wrappers, additional cluster JARs and incomplete prior
   transactions. Stop on unknown state rather than overwrite it.
4. Verify available space and writable backup media. Capture every original
   file that will be replaced, plus whether each new path previously existed,
   its permissions, source hash, and backup hash. Never overwrite the first
   verified backup during retries.
5. Validate backups by rereading them. Write the backup-complete journal state
   only after all expected data is verified. A partial backup cannot authorize
   an installation. These selected-file backups are not a full recovery image.
6. Verify an independently usable recovery launch path. ModKit's early-boot
   failsafe depends on its own persistence wrapper functioning; it is not an
   unconditional recovery guarantee.

## Planned mutation set (not yet approved for execution)

- Add the adapted JAR under `/mnt/app/eso/hmi/lsd/jars/`.
- Add native payload/configuration under `/mnt/app/eso/bin/apps/cluster/`.
- Install the required process wrappers for `gal` and `dio_manager` only after
  their original executables are backed up and exact expected bytes verified.
- Install a module startup entry only after all payload files are committed.
- Keep changes to the ModKit loader itself separate in the manifest and backup
  record. Its `servicemgrmibhigh` wrapper is not a cluster-specific mutation.

The final payload decides the exact subset of these writes. Do not infer a
transaction from this document or deploy unvalidated upstream wrapper scripts.

## Failure and rollback behavior to implement and test

Stage verified files on the destination filesystem; quiesce affected processes
before switching their files. Journal each completed replacement. Renaming one
file is not an atomic multi-file transaction. Retain enough information to
recover from power loss between any two replacements.

On rollback, restore original bytes and permissions; remove only files whose
creation is recorded in this module's journal. Refuse to overwrite intervening
unknown changes. Preserve the backup and journal until restoration is verified.
Treat uninstall of the cluster module separately from removal of the base
ModKit loader. Do not report factory restoration merely because the module's
files are gone.

Required fault tests: wrong release, wrong factory hash, tampered payload,
backup copy failure, full card, missing hash utility, interrupted staging,
interruption after each replacement, repeat install, partial uninstall, and
rollback against a subsequently changed file.
