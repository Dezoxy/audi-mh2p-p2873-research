# Graphics and porting audit — 2026-09-16

This is the phase-2 research snapshot. The subsequent [build and SD preflight report](03-build-and-sd-preflight.md) records resolved Java compile blockers and the diagnostic addon; native/runtime gates remain open.

The downloaded firmware supplies every exported symbol named by the 97 literal `dlsym` call sites checked in the upstream CarPlay hook, Android Auto hook, and renderer. Audi also defines cluster-map displayable 33. There is no missing-symbol blocker in this specific check.

The user subsequently confirmed that the vehicle is G35S and that this firmware package was used to update its MMI successfully about one year ago. This is user-reported installation history, not an independently captured live version or file-hash comparison. It makes this package a relevant working reference; the G35/G35S label difference alone is not a reason to demand another firmware package.

Concrete porting gates remain: the Java source depends on two unavailable class names, native ABI details need validation, and the factory-map restore call has a vehicle-coding condition that the upstream controller does not check. No build, installer, or vehicle execution was attempted during this research.

## Boot and system extraction

The application's `/img_restore/main_stage2.ifs.lzo` is a **71,371,264-byte `LZ4_` container**, despite its `.lzo` suffix. The standalone update `main_stage2.img` is an exact **32,505,856-byte prefix** of that container. Treating the standalone prefix as the whole filesystem would produce an incomplete result.

The validated container layout has an 8 KiB header, a little-endian compressed-size table, a 2 MiB maximum decoded block size, and 512-byte alignment between compressed blocks. All 86 compressed blocks were consumed exactly, with no trailing bytes. Image boundaries were determined from declared image lengths, not merely from searching for magic bytes.

| Image | Decoded bytes | Directory entries | Internal additive checksum |
|---|---:|---:|---|
| 0 | 946,180 | 11 | Pass |
| 1 | 1,901,692 | 15 | Pass |
| 2 | 1,942,980 | 78 | Pass |
| 3 | 23,402,728 | 310 | Pass |
| 4 | 5,920,356 | 272 | Pass |
| 5 | 142,194,336 | 87 | Pass |

The images contain 773 entries, including 501 regular-file entries. Host-key entries were inventoried but omitted from individual-file extraction. Symlinks were recorded, never materialized. Duplicate paths remain explicit in the inventory. Extracted files live under `analysis/stage2-extracted/image-XX/files/`; the full entry inventory is `analysis/stage2-extracted/inventory.json`.

`efs-system.img` was also read without mounting, using the pinned NFI qnxmount EFS parser. It contains 153 entries, including 145 regular files, rooted at `/mnt/system`. The recovered phone-integration and encoder configuration is under `analysis/efs-system/partition-0/files/etc/eso/production/`. EFS structure traversal and source installer checks passed; a separate exhaustive per-extent checksum verifier was not implemented.

## Integrity-check coverage correction

The first audit checked 22 **top-level** installer checksum records. Inspection of stage-2 metadata revealed nested records that the original script skipped. The script now traverses nested objects/lists and recognizes `primary_installer.txt` and `recovery_installer.txt` as well as `installer.txt`.

**All 2,960 discovered checksum records passed, covering 2,098 distinct source payloads.** Repeated records are not distinct files. The original 3,073-file SHA-256 inventory is unchanged byte-for-byte. These are internal integrity checks, not publisher-signature authentication.

Evidence: `evidence/phase2-audit-summary.json`, `evidence/phase2/installer-checks.json`, and `evidence/phase2/provenance.json`.

## Native compatibility evidence

The second scanner reads `PT_DYNAMIC` as well as section metadata. This matters because the graphics libraries retain their runtime symbol tables while ordinary `.dynsym` section headers have been stripped. A section-only scan gave false missing-symbol results.

| Upstream source | Literal lookup sites matched | Principal providers |
|---|---:|---|
| `dio_manager_preload.c` | 10/10 | Audi `libesoiap2.so` |
| `gal_cluster.c` | 61/61 | `libautoreceiver.so`, protobuf libraries, `libscreen.so.1`, `libnvmedia.so`, `libnvparser.so`, `libssl.so.2` |
| `cluster.c` | 26/26 | `libnvmedia.so`, `libnvparser.so`, `libscreen.so.1` |

The scope remains exported-name matching across extracted files. It does **not** prove process-specific loader resolution, all directly linked imports, dynamically assembled names, callback signatures, native object layouts, or correct hardware behavior. Several native paths use hard-coded parser/surface offsets, for example `gal_cluster.c` around lines 455–480; those require ABI validation against this firmware.

The scan covers 616 ELF files and validates 72 JARs. Four non-target binaries have dynamic tables that this parser could not interpret: `clock_init`, `dd`, `tail`, and `devb-umass`. Their errors are recorded explicitly; none was used to establish the 97 matches. Full dependency closure remains unfinished.

Evidence: `evidence/phase2/native-symbol-checks.json`, `elf-inventory.json`, `jar-validation.json`, and `evidence/phase2-interface-summary.txt`.

## Audi display configuration and vehicle identity

The downloaded startup script explicitly exports:

```text
OEM=AU
REGION=ER
HMI_TYPE=G35
```

Its display-manager configuration declares `variant: AU_G35`. It describes a 1540×720 main display, a 1280×660 lower display, and cluster outputs. Those are **package configuration values**, not verified dimensions of the user's Q3.

The display startup script distinguishes the families: for Audi `G35S` it requests single-lane mode, while the other Audi branch requests dual-lane mode. This establishes that the G35/G35S distinction affects a startup branch. The user reports that this package already runs successfully on the G35S vehicle. The package label and this script therefore cannot, by themselves, establish an incompatibility or the active runtime display configuration. The current running version, selected configuration, and actual map dimensions should be checked before a display prototype.

The package's display-manager routing includes:

- `LVDS2` → `INTERNAL2`, with multiplexing.
- Display ID 4 → `Cluster Display`, optional, annotated, on `LVDS2`.
- Display ID 7 → `Virtual Cluster Display`, annotated, on `LVDS2`.

The Java `org/dsi/ifc/displaymanagement/Constants` class defines:

```text
DISPLAYABLE_KOMBI_MAP_VIEW = 33
DISPLAYABLE_GOOGLE_EARTH_KOMBI_MAP_VIEW = 58
DISPLAYID_CLUSTER = 4
DISPLAYID_CLUSTER_VIRTUAL1 = 7
```

This confirms the meaning of **33** in this Audi software. It does not establish the active context, dimensions, transport, or ownership on the user's car. Display IDs, displayable IDs, and QNX Screen display indices are different identifiers.

The EFS configuration also contains a cluster encoder path using `/dev/mlb/isoTX2`. Its presence is not proof that this car uses that path; Java coding selects among transport/cluster variants. Generic legacy `display.conf`/`dicluster.conf` files are therefore not treated as authoritative Q3 routing evidence.

Evidence locations:

- `analysis/stage2-extracted/image-01/files/usr/sbin/main_stage2.1.sh`: OEM/HMI selection.
- `analysis/stage2-extracted/image-02/files/usr/sbin/display-starter.sh`: variant-dependent initialization.
- `analysis/stage2-extracted/image-03/files/etc/eso/production/displaymanager.json`: output routing.
- `analysis/stage2-extracted/image-03/files/etc/graphics.conf`: QNX Screen classes/pipelines.
- `evidence/phase2/java-routing.json`: decoded Java constants and bytecode.

## Factory-map restore semantics

Bytecode inspection goes beyond the first audit's method-signature matching:

- `switchKombiMapToHiddenContext()` calls the map's `switchToHiddenContext()` and `exitMapScreen()` when a map exists. When it does not exist, it logs and returns normally.
- `switchKombiMapToAShownContext()` calls `startActivity(Intent.AUTO)` and `enterMapScreen()` when a map exists; it also returns normally when no map exists.
- `notifyViewSizeChanged(boolean)` calls the map's `viewSizeChanged()` **only when `isClusterMapFPKEntry()` is true**. Otherwise it logs an unexpected call.
- In this firmware, `isClusterMapFPKEntry()` requires navigation transmission mode `2` (the code's MOST test) **and** navigation map resolution coding `1`.

Consequently, a successful void call does not prove ownership changed, and the upstream controller's unconditional resize notification is not a general Audi window-recreation guarantee. A port needs variant-aware restore logic and observable confirmation that the factory view returns. These findings do not justify changing the car's coding.

## Java build obstacles

An explicit-import scan of all 10 upstream Java source files found 224 import occurrences in extracted JARs and two supplied by upstream source. Three occurrences refer to two unavailable class names:

| Missing class | Use | Porting implication |
|---|---|---|
| `de.audi.app.car.adi.legacy.sportchrono.StorageMountHandler` | Imported by `AndroidAuto2Subsystem` and `AndroidAutoClusterIntegration`; used to remount external storage for logging | Remove or replace this dependency in an Audi branch. A first prototype can log to the existing temporary path without storage remounting. |
| `de.esolutions.hmi.service.IWidgetContext` | Imported by `ClusterAAMirror`, which describes itself as a placeholder | Determine whether this placeholder belongs in the build. Audi provides `de.eso.widgets.utils.injector.IWidgetContext`, but a name change alone is not a validated adapter. |

The scan does not compile the source or validate every member reference. It searches extracted JARs and upstream sources; it does not claim the classes are absent from every possible external SDK. It does establish that the current local dependency set cannot compile every upstream Java file unchanged.

Evidence: `evidence/phase2/java-import-checks.json`; upstream references are recorded with source paths. No upstream files were modified.

## Next concrete work

1. **Use this package as the working firmware reference.** The user reports a successful installation on this G35S vehicle about one year ago. Before installing a prototype, confirm the current running release and the original files it would replace; the installer must check those exact targets. Do not require a different package solely because its internal label says G35. Active display routing and dimensions remain runtime questions.
2. **Complete ABI/dependency checks.** Check non-literal and directly linked symbols, provider selection, native structures, and ARM call conventions. Matching names are necessary but insufficient.
3. **Prepare the smallest Audi Java adaptation.** Drop the Sport Chrono logging dependency, settle the placeholder's build inclusion, and validate the remaining method contracts against Audi classes. Preserve upstream licensing and provenance.
4. **Build a variant-aware map-ownership prototype** only after the actual platform is known. It must handle missing services/maps, timeout, disconnect, and confirmed factory-view restoration.
5. **Keep a separate CarPlay second-screen workstream.** These checks support investigation of guidance/mirroring; they do not establish an independent CarPlay map while the MMI shows another app.

## Validation and reproducibility

Seven regression checks pass: nested checksum records and failure exit; all six real image checksums; truncated-container rejection; corrupted-image rejection; traversal rejection even with a recomputed valid checksum; correct symlink target decoding; and export lookup from the real stripped NvMedia library. All analysis scripts also pass Python syntax compilation.

`README.md` contains commands. `tools/requirements.lock.txt` pins Python dependencies. `evidence/phase2/provenance.json` pins source revisions and records the exact prefix match. The initial stage-2 extraction is retained at `analysis/stage2-extracted-initial/` as a superseded research artifact; use `analysis/stage2-extracted/` for the corrected symlink metadata.

External format references: [lclevy/dumpifs](https://github.com/lclevy/dumpifs), [NFI qnxmount](https://github.com/NetherlandsForensicInstitute/qnxmount), and [upstream cluster source](https://github.com/fifthBro/mh2p-cluster/tree/a37c917c1b1479e11684e158efc0e1be3c07faa7). All conclusions about the supplied firmware above come from the local artifacts.
