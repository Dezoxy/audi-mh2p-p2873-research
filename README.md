# Audi MH2P P2873 offline compatibility research

Static research toward instrument-cluster navigation integration
(Android Auto / CarPlay) on an Audi Q3 F3 with the MH2P head unit, firmware
`MH2p_ER_AUG35_P2873`, building on the Porsche-only
[fifthBro/mh2p-cluster](https://github.com/fifthBro/mh2p-cluster) project.

**Status: research only.** Nothing here has run on a vehicle. There is no
flashable or installable release. Read [NOTICE.md](NOTICE.md) for licensing
and for what is intentionally kept out of this repository. If you try any of
this on a car, you accept the risk of a bricked head unit; the installer
module exists to make that risk explicit and recoverable, not to remove it.

Work started 2026-09-16 from `Audi-Q3-MH2P-kutatas.md` and the locally supplied firmware. See [the Java build and SD preflight report](reports/03-build-and-sd-preflight.md) for current status, [the graphics and porting audit](reports/02-graphics-and-porting-audit.md) for compatibility findings, and [the first audit](reports/01-offline-audit.md) for the initial application-only pass.

This workspace contains local firmware analysis, a compiled experimental Java port, and an SD preflight addon. It is not a flashable cluster port. No vehicle connection, installation, firmware patch, or firmware executable was run.

Current continuation: [recovery launch path](reports/07-recovery-launch-path.md), [installer transaction implementation and fault tests](reports/06-installer-transaction.md), [complete native dependency-name check](reports/05-native-runtime-closure.md), [native build readiness](reports/04-native-build-readiness.md) and [installer contract](port/installer/CONTRACT.md). No separate firmware-capture visit is required; the supplied firmware is the baseline, with checks planned inside installation. The user has no QNX SDK; native compilation and prebuilt reuse validation remain unresolved.

## Workspace

- Original package: `4K0906961AB_MH2p_ER_AUG35_P2873/` — kept unchanged.
- `tools/`: read-only inventory, extraction, and static interface comparison scripts.
- `evidence/`: hashes, installer checksum results, ELF dependencies, symbol comparisons, Java method descriptors, and JAR integrity results.
- `analysis/app/files/`: selected files extracted for private local analysis; no symlinks materialized.
- `vendor/`: upstream source checkouts, with revisions in `evidence/provenance.json`.
- `port/`: adapted Java sources, attribution, SD collector sources, and the journaled installer module (`port/installer/`).
- `build/java/`: experimental JAR; do not install on the vehicle.
- `dist/Audi-P2873-preflight-addon.zip`: diagnostic addon only (tool probe and file capture), without the ModKit loader or port payload.
- `evidence/build/`: build inputs, API retention checks, capture reference, and reproducibility results.

## Reproduce

Run from this directory. Python dependencies are isolated in `.venv`; the exact dependency snapshot is in `tools/requirements.lock.txt`, which pins the QNX6 parser to a public upstream revision. The firmware package must be supplied locally; it is not distributed. Phase 2 additionally uses `lz4==4.4.5`, `kaitaistruct==0.10`, and `jawa==2.2.0`; NFI qnxmount is read directly from its pinned source checkout.

```sh
uv venv .venv
uv pip install --python .venv/bin/python ./vendor/dissect.qnxfs dissect-cstruct==4.7 dissect-util==3.24 pyelftools==0.33
python3 tools/audit_firmware.py 4K0906961AB_MH2p_ER_AUG35_P2873 evidence
.venv/bin/python tools/inspect_app.py 4K0906961AB_MH2p_ER_AUG35_P2873/Data/MMX2P.app_CLU28_MMX2P_AU_ER_G35_011PROD/20/app.img analysis/fresh-app --extract '(^/eso/(lib/|bin/apps/(gal|dio_manager)$|.*\.jar$|etc/)|^/etc/|^/armle/.*(nv|screen|EGL|graphics)|^/(target.properties|version_info.txt|img_ver.txt)$)'
.venv/bin/python tools/compare_interfaces.py
```

The comparison script uses `analysis/app/files`. A fresh extraction is written to `analysis/fresh-app` above to prevent overwrites; point the script's `files` variable there to compare it instead. Extraction refuses existing output files. The extractor handles only the observed 16 KiB QNX6 application layout, requires identical primary/backup headers, and checks that every allocated inode is reachable. It is not a general QNX recovery tool.

Installer checks cover payloads with explicit block lists, not every package file. SHA-256 inventory establishes a local baseline; neither this nor unsigned checksum matching authenticates the publisher's signatures.

Do not publish the firmware or extracted proprietary files. Upstream source licenses remain applicable. Tests that need the firmware or files extracted from it skip when those inputs are absent, so the suite also runs on a clean checkout and in CI (`.github/workflows/tests.yml`, under both ksh93 and mksh).

The original research brief that started this work is `docs/Audi-Q3-MH2P-kutatas.md` (Hungarian).

## Phase 2: boot/system images and compatibility

Extraction commands require new destination directories and never overwrite firmware. If outputs already exist, use the comparison/test commands or select a fresh destination and update input paths accordingly.

```sh
uv pip install --python .venv/bin/python lz4==4.4.5 kaitaistruct==0.10 jawa==2.2.0
.venv/bin/python tools/inspect_app.py 4K0906961AB_MH2p_ER_AUG35_P2873/Data/MMX2P.app_CLU28_MMX2P_AU_ER_G35_011PROD/20/app.img analysis/restore --extract '^/img_restore/'
.venv/bin/python tools/extract_stage2.py analysis/restore/files/img_restore/main_stage2.ifs.lzo analysis/stage2-extracted
.venv/bin/python tools/inspect_efs.py 4K0906961AB_MH2p_ER_AUG35_P2873/Data/MMX2P.efs-system_CLU28_MMX2P_AU_ER_G35_011PROD/20/efs-system.img analysis/efs-system
python3 tools/audit_firmware.py 4K0906961AB_MH2p_ER_AUG35_P2873 evidence/phase2
.venv/bin/python tools/compare_interfaces.py --include-stage2 --output evidence/phase2
.venv/bin/python tools/inspect_java_routing.py
.venv/bin/python tools/check_java_imports.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/build_cluster_installer.py --payload-dir /path/to/native/payload
```

Current evidence reports 2,960 successful checksum records (2,098 distinct payloads), six validated QNX images, and 97/97 literal native lookup matches. This is static research, not runtime compatibility approval. The user confirms a G35S vehicle and successful installation of this package about one year ago. Its internal G35 label is not treated as proof of incompatibility. Use this package as the working reference, then verify the current release and target-file hashes before prototype installation.

## Licensing

Original tooling, tests, reports and the installer module: MIT (`LICENSE`).
`port/java/` and the process wrappers are derivative works under CC BY-NC-SA 4.0
and are not for commercial use. Details and upstream credits: [NOTICE.md](NOTICE.md).
