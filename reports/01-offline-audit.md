# First offline audit — 2026-09-16

Historical application-only snapshot. See [phase 2](02-graphics-and-porting-audit.md) for graphics extraction, expanded nested-checksum coverage, corrected dynamic-symbol scanning, and the later user confirmation that this package was installed successfully on the G35S vehicle about one year ago. Identity concerns below describe the information available during the initial audit.

The supplied Audi package is readable and exposes several interfaces needed by the cluster project. There is enough evidence to continue the Audi port investigation, but not to build or install a vehicle-ready package. Graphics routing, native ABI details, complete Java compatibility, and the actual vehicle identity remain open.

## Package identity

| Item | Observed value |
|---|---|
| Main release | `MH2p_ER_AUG35_P2873` |
| Package version / MU | `2873.1.0` / `2873` |
| Application component | `2343.18.0` |
| Payload directory label | `CLU28_MMX2P_AU_ER_G35_011PROD` |
| OEM / region | `AU` / `ER` |
| HMI | `HMI_AU_MIB2P_H_ER_G35_C27_214801` |
| OS | `QNX 6.6.0` |
| Toolchain label | `MAIN_QNX_OS_660_MMX2P_23.42.04B` |
| Key native binaries | 32-bit ARM ELF |

Evidence: original `Meta/main.mnf`, `Meta/MMX2P/2343.18.0.mnf`, extracted `analysis/app/files/version_info.txt`, and `evidence/elf-inventory.json`.

The original research document records `CLU28_MMX2P_AU_ER_G35S_006PROD-1` for the vehicle. This differs from the downloaded package's payload label. That is an unresolved identity difference, not proof that the download is wrong or that it matches the installed system. Vehicle 5F/17 IDs and the full MMI version remain necessary before any deployment decision.

## Integrity and extraction

- Inventoried 3,073 package files, totaling 8,031,259,198 bytes; `.DS_Store` excluded.
- All 22 installer records with explicit block-checksum lists passed SHA-1 block comparison and declared file-size checks.
- The application image is 2,147,418,112 bytes. Its QNX6 headers occur at byte offsets 8,192 and 2,147,414,016 and are identical over 512 bytes.
- The observed data block size and data start are both 16,384 bytes. The upstream Dissect parser assumes a layout that does not work unchanged for this image. The local wrapper supplies the observed data offset without altering the source image or upstream parser.
- Traversed 12,798 entries; including the root inode, all 12,799 allocated inodes were accounted for. Symlinks were recorded rather than followed or created.
- Extracted 402 regular files; their sizes and SHA-256 hashes were recorded.
- All 62 extracted JARs passed ZIP CRC validation. Inspected 322 ELF files and parsed seven relevant Java classes/interfaces.
- Repeated the application-image SHA-256 after extraction; it matches the initial inventory.

Evidence: `evidence/package-inventory.json`, `installer-checks.json`, `extraction-summary.json`, `jar-validation.json`, `provenance.json`, and `analysis/app/filesystem-inventory.json`.

These checks establish internal consistency and a reproducible local baseline. Publisher signature verification has not been performed. No firmware code or installer was executed.

## Static interface comparison

Compared against `fifthBro/mh2p-cluster` commit `a37c917c1b1479e11684e158efc0e1be3c07faa7`, which matches the initial research document. The parser checkout is `fox-it/dissect.qnxfs` commit `b3a0f3e2be75e75418e99453a72cb11c43ca3f00`.

| Surface | Observed result | Interpretation |
|---|---|---|
| CarPlay native hook | 10/10 literal `dlsym` call sites have corresponding exported definitions in the extracted ELF set | Promising symbol-name compatibility; object layout, call ABI, loader scope/order, and behavior remain unverified |
| Android Auto native hook | 40/61 literal lookup call sites have exported definitions in the extracted set | Partial positive match; several unresolved names are graphics/runtime dependencies outside the extracted set |
| Renderer | 5/26 literal lookup call sites match | Graphics audit incomplete; cannot establish rendering compatibility |
| `IMapClusterService` | All five methods used by the upstream hide/restore controller exist with matching descriptors | Static API agreement for this narrow controller surface |
| BAP navigation | `CombiBAPServiceNavi` and listener exist | Method inventory captured; complete integration comparison still needed |
| Phone integration | `CarPlayDSIManager` and `AndroidAuto2DSIManager` exist | Existing integration points located; replacement/patch safety not established |

Counts represent literal call sites, including repeated lookups. They exclude variable-generated symbol names, fallback resolver strings, directly linked imports, complete dependency closure, and process-specific resolution. A symbol found anywhere in the extracted set does not prove it will resolve in the intended process.

The five map-service descriptors are:

```text
suspendSetup()V
switchKombiMapToHiddenContext()V
switchKombiMapToAShownContext()V
notifyViewSizeChanged(Z)V
resumeSetupAndStore()V
```

They are present in `de/audi/tghu/navi/app/cluster/IMapClusterService` inside the Audi `lsd.jar`. The inspected Java classes use classfile major version 48; a compatible build must account for this old runtime. A local Java runtime/toolchain was not available, so class signatures were read directly without executing Java.

Evidence: `evidence/native-symbol-checks.json`, `java-interfaces.json`, `elf-inventory.json`, and `interface-summary.txt`.

## Graphics boundary

`gal` and `dio_manager` both declare dependencies on `libnvmedia.so`, `libnvparser.so`, and `libscreen.so.1`. The application extraction contains `libnvparser.so` but does not establish the exports of the NvMedia and Screen providers. Unresolved graphics names must not be reported as absent from the firmware as a whole.

The next image to investigate is `main_stage2.img` (32,505,856 bytes), which starts with `LZ4_`. Its container format and decompression have not yet been validated. `efs-system.img` also remains unextracted. Displayable 33, Q3 display dimensions, active vehicle-specific routing, and factory-map focus/recovery remain unproven.

## Next implementation gates

1. Decode boot/system images offline, validate extraction, and locate NvMedia, Screen, startup files, and display configuration. Extend export checks to the actual dependency closure.
2. Compare all Java types/method descriptors used by the proposed integration, plus source assumptions about native structs, protobuf versions, callbacks, and ARM ABI. Build success alone will not establish runtime compatibility.
3. Confirm vehicle software/hardware identity and existing cockpit factory-map support. Do not derive the installed version from the downloaded package.
4. Establish a pinned QNX 6.6-compatible toolchain and old-Java-compatible build. No build or flashable installer has been produced.
5. Prove bench recovery and display ownership before attempting a manually started prototype. The separate CarPlay map remains an independent research task; mirror support does not satisfy that requirement.

No car changes, FEC/component-protection changes, deployment, or network access to a vehicle took place.

## External sources

- [Cluster source and license](https://github.com/fifthBro/mh2p-cluster/tree/a37c917c1b1479e11684e158efc0e1be3c07faa7)
- [Dissect QNX filesystem parser](https://github.com/fox-it/dissect.qnxfs/tree/b3a0f3e2be75e75418e99453a72cb11c43ca3f00)
