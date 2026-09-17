# Installer transaction implementation — 2026-09-16

The installer contract in `port/installer/CONTRACT.md` now has an implementation:
a ModKit module `Mods/AudiClusterIntegration` with a journaled install, a
conditional uninstall and a gated startup entry. It runs on the host against
fixture directories with a PATH limited to utilities that exist in the P2873
app image. It has not been run on a vehicle or under the unit's own ksh.
Nothing was written to any vehicle, card, or firmware file.

## Finding that shaped the design: no hash utility on the unit

The P2873 app image and the six boot images contain no `cksum`, `md5sum`,
`sha*`, `sum`, `cmp`, `printf` or `rmdir`. The upstream Porsche installer
compares with `sum` and, when it is absent, accepts equal byte counts as
identical. The contract forbids that fallback.

The module instead reads the CRC-32 that `gzip` writes into the last eight
bytes of every stream (RFC 1952), using `gzip`, `dd`, `hd` and `wc`, all of
which are present. Every run first checks a shipped 4096-byte file against
its recorded size and CRC, and then checks that an equal-size copy with one
changed byte is rejected. If either check fails the run stops before any write.
CRC-32 plus size detects wrong versions, partial copies and corruption. It is
not collision resistant and does not defend against deliberate tampering;
SHA-256 values are in the manifest for host verification only.

## Transaction

Order of `install.sh`, run by the loader during the SD update stage:

1. Loader-supplied `MOD_PATH`, `MEDIA_PATH` and `RELEASE_VERSION` required.
   Accepted releases are `MH2p_ER_AUG35_P2873` and `MH2p_ER_AUG35S_P2873`.
   The module never runs `pc` itself.
2. Hash self-test as above.
3. Prior state: `COMMITTED` with the same manifest is a no-op. Any in-progress
   state is treated as an interrupted transaction, rolled back from the
   journal, marked `RESTORED`, and the run stops so the operator reruns.
4. Read-only checks: `img_ver.txt`, `gal` and `dio_manager` must match the
   supplied firmware; no `.real` copies, no pre-existing targets, no
   `ClusterIntegration_*` or `AndroidAutoCluster_*` JARs may exist.
5. Every payload file on the card must match the manifest.
6. Free space on both filesystems is read from `df -kP`; an unparseable
   result stops the run.
7. An exclusive per-transaction backup directory is created on the card. The
   journal is rotated, never truncated. Each factory file is copied, reread
   and verified before `BACKUP_COMPLETE` is recorded.
8. The complete recovery package is copied to a staging directory outside
   ModKit's `Mods` discovery tree, checked against recovery manifest records,
   synced, and published with one directory rename. The installed manifest is
   checked against the current Update manifest. An existing identical package
   can be reused; an unknown package stops the install. Only then is each
   payload copied to `<target>.staging` on the destination filesystem, verified
   and chmodded.
9. `cluster`, `gal` and `dio_manager` are stopped; each switch is one rename
   with `REPLACE_BEGIN` and `REPLACE_DONE` journal records. Wrapper swaps
   rename the original to `.real` first.
10. Every final file is reread. Only then are `manifest.crc` and `COMMITTED`
    written; `Persist/install.sh` starts the daemon only in that state.

`uninstall.sh` walks `REPLACE_BEGIN` records newest first. A file whose bytes
are neither the installed payload nor absent is refused and left in place.
Originals are restored from the on-unit `.real` copy, or from the card backup
when `.real` is missing or mismatched, and verified again. Only a fully
verified restoration writes `RESTORED`; otherwise `ROLLBACK_INCOMPLETE` is
recorded and the backup and journal are retained. The module also removes its
own `/mnt/ota/modkit/Mods/AudiClusterIntegration` copy, because the loader
only propagates `uninstall.txt` to that copy when a `Post` stage exists.
The loader's `servicemgrmibhigh` wrapper is never touched.

## Fault tests

`tests/test_cluster_installer.py` runs the shipped scripts under `/bin/ksh`
with a PATH containing only symlinks to the unit's tool set plus shims for
`hd`, `slay`, `df`, `cp` and `sync`. Covered, per the contract list:

| Case | Result |
|---|---|
| Wrong or unknown release | stops, nothing written |
| Wrong factory hash | stops before backup |
| Tampered payload | stops before backup |
| Backup copy failure | `BACKING_UP`; next run recovers; third run succeeds with a new backup directory |
| Full card | stops before backup |
| Missing hash utility | self-test fails, nothing written |
| Interrupted before and after staging | recovered, staged copies removed, factory bytes intact |
| Interruption after each of the seven replacements | each recovered to byte-exact factory state, then reinstalled |
| Interruption between the two renames of a wrapper swap | recovered |
| Repeat install | no-op, no new backup |
| Partial uninstall (corrupt `.real` and corrupt backup) | `ROLLBACK_INCOMPLETE`, other files restored, backup retained; completes after the backup is repaired |
| Rollback against a subsequently changed file | refused for that file only, `ROLLBACK_INCOMPLETE` |
| Existing cluster JAR or pre-existing target | stops |
| Startup entry without transaction state | does nothing |
| Uncommitted transaction with the entire card absent | ModKit discovers the on-unit package and restores the baseline |
| Recovery copy/permission failure or corrupt source | stops before payload staging |
| Uninstall with the card backup absent | restored from on-unit `.real` originals |
| Unrelated file left in the cluster directory | directory kept, file untouched |
| Restored permissions | factory mode (fixture uses 750 for `gal`, wrapper is 755) |

Current isolated-worktree validation: 70 workspace tests discovered, 57 passed
and 13 skipped because proprietary firmware and generated artifacts are absent.
Both changed shell scripts pass `ksh -n`. CI runs the suite under ksh93 and mksh.

## Independent review

A code review of the scripts found three high and two medium issues, all fixed
and covered by tests: the startup entry launched a hard-coded `/eso/...` path
instead of the validated `/mnt/app/...` path; wrapper rollback restored the
wrapper's mode instead of the factory mode; an `ls -A` result gated a
directory removal and would have deleted unrelated files if the flag were
unsupported (replaced by a pure-shell emptiness test); interrupted-install
recovery now uses the manifest recorded with the transaction's backup; and
`df -kP` parsing rejects anything other than one data row. Because extracted
firmware copies lose their permission bits, the builder now takes factory
modes from `analysis/app/filesystem-inventory.json` and stops if a mode is
missing. No ksh93-only constructs were found.

## Second review (2026-09-17)

An external static review found four must-fix items and one improvement;
all are fixed and tested on the `fix/installer-review-gaps` branch:

- **Rollback could get stuck after a legitimate interruption.** A crash after
  `REPLACE_BEGIN` but before the original was moved, or after a restoration
  but before its `RESTORE_DONE` record, left the factory binary in place and
  rollback refused it as "not ours". Rollback now recognises a target that
  already verifies as the factory file, removes a matching leftover `.real`,
  and records it as restored. The before-move fault runs for every
  operation; the restoration fault was first tested for one step only and
  now runs per step for all seven (third review).
- **The commit gate did not cover activation.** The wrappers now load the
  hook only while the state file says `COMMITTED`, so a reboot during
  install or rollback runs the factory binaries unmodified. The JAR is now
  the last file switched, immediately before the state write. A crash
  between that rename and the state write leaves the JAR on the live
  classpath. The first fix left it there until an operator acted; the
  startup entry now rolls back any uncommitted transaction unattended at the
  next boot if recovery executes successfully (see "Fourth review"). There
  is no proven bound on exposure on hardware; removal does not unload classes
  that an already-running HMI has loaded.
- **The chain check was presence only.** The manifest now records the exact
  size and hashes of ModKit's wrapper script and persist script at the pinned
  revision, and the check demands those bytes plus the factory ELF next to
  them. It still cannot prove the chain executes at boot from inside the
  update stage.
- **The builder could delete an arbitrary output directory.** It now refuses
  a non-empty directory unless it carries the marker of a previous build.
- **The card assembler ignored local changes in submodules.** It now refuses
  any submodule with modified or untracked files and validates every
  submodule before writing a single file.

## Third review (2026-09-17)

- **JAR left active after a crash.** `Persist/install.sh` runs on every boot
  from the copy ModKit keeps under `/mnt/ota`. It now ships with its own
  `common.sh`, `manifest.txt` and `selftest.bin`; when the recorded state is
  neither `COMMITTED` nor `RESTORED` it remounts `/mnt/app` writable and runs
  the shared rollback from the on-unit `.real` originals, with no card and no
  marker. The initial test removed only the backup and still executed the
  entry from the card; the fourth review corrects that gap. Ordering relative
  to HMI start is unverified, so the JAR may load before removal.
- **Ignored `chmod` failure.** Both restoration branches now fail when the
  factory mode cannot be set and check the execute bit for executable modes,
  since byte verification cannot see permissions. Tested with a failing
  `chmod` shim: the state becomes `ROLLBACK_INCOMPLETE`, and a later run
  completes.
- **Coverage claim.** A per-step fault counter exercises a crash before each
  of the seven `RESTORE_DONE` records.
- **Early-boot recovery was undemonstrated.** See report 07: the card now
  carries a heartbeat `failsafe.sh`.

## Fourth review (2026-09-17)

The base ModKit loader runs Update before copying Persist. The previous
implementation therefore had no module-specific recovery on the unit if the
first cluster install lost power before returning. Update now publishes the
complete recovery package itself before payload staging. Its code and self-test
bytes are pinned in the manifest, and all copies plus the manifest and entry
permissions are verified before proceeding. A crash before publication leaves
factory files untouched and the partial package outside boot discovery.

The boot test uses the pinned ModKit dispatcher with hardware paths, media
waiting and release discovery adapted for the host fixture. It removes the
**entire card** and exercises recovery after publication, staging, each of seven
replacements, and both wrapper rename gaps. It starts with no cluster Persist
package and never simulates the loader's later copy. Copy/permission failures,
corrupt recovery source and unknown existing recovery packages block writes.
These tests demonstrate host discovery and restoration, not QNX boot ordering,
filesystem power-loss durability or a vehicle recovery guarantee. The heartbeat
only proves that the card hook was reached.

## Build and evidence

`tools/build_cluster_installer.py --payload-dir DIR` assembles the module
into `build/installer/` from an explicitly named payload directory and the
experimental JAR, writing `evidence/build/installer-build.json`. It was run
against the four native files from the pinned upstream v0034 ZIP. The factory
sizes and SHA-256 values in the manifest equal those in
`capture-reference.json`. The report records `approved_for_vehicle: false`;
the upstream native payload is still unapproved (report 05), and the module
is not packaged into `dist/`.

## Limitations

- The unit's ksh is pdksh-derived; host tests use ksh93. No pdksh-family
  shell is on this Mac, so dialect differences are unverified. Only common
  constructs were used and `printf` was avoided.
- `hd` and `df -kP` output formats on QNX are assumed similar to POSIX. The
  self-test guards `hd`; `df` parsing stops on non-numeric output. Both are
  cheap to confirm on the unit before any install.
- Stopping `gal` and `dio_manager` during the update stage follows upstream;
  the interaction with the update-mode process set is unverified.
- The base ModKit loader still installs its persistence wrapper regardless
  of this module's result, as documented in the contract.
- The transaction does not cover Audi map handover, native ABI review or
  hardware validation. Those remain open.

## Reproduce

```sh
.venv/bin/python tools/build_cluster_installer.py --payload-dir /path/to/v0034/Update
.venv/bin/python -m unittest tests.test_cluster_installer -v
.venv/bin/python -m unittest discover -s tests
```
