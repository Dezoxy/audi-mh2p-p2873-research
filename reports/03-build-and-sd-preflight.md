# Java build and SD preflight — 2026-09-16

The Audi-adapted Java sources now compile against the downloaded P2873 firmware.
A separate SD diagnostic addon is built and tested on the host. Neither artifact
has been run on the vehicle. A writable cluster installer and rollback procedure
are still unfinished; the diagnostic addon is not presented as that installer.

## Delivered files

| Artifact | Purpose | Status |
|---|---|---|
| `build/java/ClusterIntegration-Audi-P2873-experimental.jar` | Experimental Java port, seven source files, 61 class files | Compiled, classfile major 48; vehicle installation not approved |
| `dist/Audi-P2873-preflight-addon.zip` | SD layout with `Mods/AudiP2873Preflight/Update` collector | Host tested; requires an existing script launcher/ModKit setup |
| `port/java/` | Editable derivative sources | Upstream attribution retained; CC BY-NC-SA 4.0 |
| `tools/build_java_port.py` | Firmware-classpath build and provenance | Records source/library hashes and patch |
| `tools/build_sd_preflight.py` | Deterministic addon packager | Contains no loader, native payload, or Java payload |
| `tools/verify_capture.py` | Host comparison of live capture with offline baseline | Missing files, unknown releases, changed bytes, and symlinked captures fail |

Current hashes and input provenance are recorded in `evidence/build/`.

## Java changes and checks

Upstream reference: [fifthBro/mh2p-cluster](https://github.com/fifthBro/mh2p-cluster),
commit `a37c917c1b1479e11684e158efc0e1be3c07faa7`. Original checkout unchanged.

- Removed the Porsche `StorageMountHandler` construction/imports/setter. Android
  Auto log destination selection now stays in `/tmp`; no external remount helper.
- Removed nine decompiler `Object` casts in enum comparisons which conflict with
  the Audi firmware's typed API. No new replacement API was invented.
- Excluded three unused experimental classes: `ClusterAAMirror` (unresolved
  widget interface), `AndroidAutoClusterActivator` (calls nonexistent
  `setClusterMapController`), and its unused `ClusterMapController`.
- Built using Eclipse ECJ 4.6.1 with source/target 1.4. Both boot classes and
  application classes come from extracted firmware, not desktop Java libraries.
  The desktop Java 17 runtime only runs the compiler.
- All 61 generated classes have classfile major version 48. Only generated port
  classes, manifest, notice, and license are in the JAR; no firmware classes.
- All 48 public/protected methods checked in the three replaced top-level
  classes remain present. Public/protected fields, direct interfaces, and
  superclass checks also pass. This does not compare every behavioral detail,
  package-private coupling, reflection target, or native contract.

The upstream rendering logic remains experimental and is not approved for the
Audi. The JAR is deliberately excluded from the SD package. CarPlay remains
upstream-style screen mirroring, not an independently rendered navigation map.

## SD capture behavior

The collector reads eight explicit application targets: version information,
image version, target properties, `gal`, `dio_manager`, `libesoiap2.so`,
`libautoreceiver.so`, and `lsd.jar`. Total reference size: 113,351,165 bytes.
It writes a new directory on SD/USB, refuses overwrites, retains incomplete
captures without a COMPLETE marker, and never remounts or changes unit files.
It also records loader environment and the filenames of extra HMI JARs if present.
Those filenames need manual review; matching the eight targets does not rule
out an existing mod elsewhere.

The Update adapter accepts loader-reported `MH2p_ER_AUG35_P2873` or
`MH2p_ER_AUG35S_P2873`. The vehicle's G35S identity and its successful use of the
downloaded firmware are accepted as user-reported facts. The package's G35 label
is not an incompatibility verdict. Unknown release is never silently accepted.
With manual shell invocation outside the loader, the release may be UNKNOWN;
raw `pc` output is captured when available and must be reviewed before proceeding.

The addon has no Post/Persist stage and no automatic failsafe. There is nothing
installed by this addon to roll back. Its captured files are useful baseline
evidence, not a full backup or proven recovery image. A rollback implementation
for the actual port still needs validated target writes and a working recovery
launch path.

The reviewed [MH2p SD ModKit](https://github.com/LawPaul/MH2p_SD_ModKit) revision
is `82f9452401022a4a5deadbbb4aaa86fdf7ce71fb`. Its own loader modifies internal
storage. The addon does not include it, and the addon's read-only behavior does
not imply that installing/running the base framework is read-only.

## Validation completed

- 16 unit/integration tests pass, including the seven existing extraction/audit
  tests and nine new preflight tests.
- A separate end-to-end host fixture used all eight full-size extracted files.
  The collector and host verifier matched every byte against the reference.
- JAR and ZIP rebuilt twice with identical SHA-256 values.
- ZIP contents verified: no base updater, native binaries, JAR, or persistence.
- No firmware executable was run. No SD card or vehicle storage was modified.

Evidence: `java-build.json`, `java-api-check.json`, `java-port.patch`,
`sd-build.json`, `capture-reference.json`, `offline-capture-test.json`, and
`reproducibility.json`, all under `evidence/build/`.

## Remaining work before installation

1. Confirm the car's existing ModKit/script access and recovery entry point.
2. Obtain the live version/file capture and check existing mods, active display
   configuration, and navigation coding.
3. Build native code with a suitable licensed QNX 6.6 ARM SDK. None was located
   in the toolchain search. Exported-name matching alone does not verify ABI,
   hard-coded offsets, loader scope, or the graphics pipeline.
4. Adapt and validate map handover/restoration for the actual Audi configuration.
5. Implement and fault-test the precise install/rollback transaction, then
   validate recovery and behavior on hardware before a usable SD release.

## Reproduce locally

The local Java runtime and ECJ compiler are under `build-tools/`; download URLs
and checksums are in `evidence/build/toolchain-downloads.json`. They are not a
QNX SDK. Python API inspection uses the existing `.venv` with `jawa==2.2.0`.

```sh
python3 tools/build_java_port.py
.venv/bin/python tools/check_port_api.py
python3 tools/build_sd_preflight.py
.venv/bin/python -m unittest discover -s tests -v
```

For the SD addon layout and collection instructions, see `port/sd/README.md`.
