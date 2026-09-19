# Card 2 results: the car's real files (2026-09-19)

Card 2 ran in the car on 2026-09-19. ModKit logged "existing patch detected"
and re-applied its wrapper; the probe completed with the persistence chain now
reported present; the collector captured all eight target files. Raw results
are kept privately under `analysis/vehicle/2026-09-19-card2/` (gitignored).
Only sizes and hashes are recorded here.

## The car runs a different build than the analysed package

| File | Car bytes | Car SHA-256 | vs package |
|---|---:|---|---|
| `version_info.txt` | 2379 | `f0e76b21966b5c2a…` | differs |
| `img_ver.txt` | 42 | `05ac504a6641d49b…` | differs |
| `target.properties` | 803 | `ac0a8087ec24a724…` | differs |
| `eso/bin/apps/gal` | 1472868 | `a9260c5bc8490cc3…` | differs |
| `eso/bin/apps/dio_manager` | 958480 | `35bd98284215718d…` | differs |
| `eso/lib/libesoiap2.so` | 376176 | `0e0961990fa5a6dc…` | differs |
| `eso/lib/libautoreceiver.so` | 1079444 | `fb1ffd3196aa99bc…` | identical |
| `eso/hmi/lsd/lsd.jar` | 108154883 | `9e7f0a22f4fded54…` | differs |

- `img_ver.txt`: car `#CLU28_MMX2P_AU_ER_G35S_006PROD / 2205.10.0`; package
  `#CLU28_MMX2P_AU_ER_G35_011PROD / 2343.18.0`. The unit reports release
  `MH2p_ER_AU_P2873` (confirmed by the raw `pc` read). So "P2873" is the
  release train; the installed application build is the older G35S 006PROD.
- `version_info.txt` and `target.properties` differ only in the variant
  (`g35s`), build number (006 vs 011), the version (2205.10.0 vs 2343.18.0),
  one changelist (45095180 vs 45095182) and ERMA_ID (42052 vs 42051). All
  component versions on the car, including `IFS_MAIN_STAGE2` and
  `EFS_SYSTEM`, are 2205.10.0.

## HMI JAR: class-compatible with the port and the Audi mods

The car's `lsd.jar` has 85,969 entries; 85,967 are byte-identical to the
package's. It has no entries the package lacks. The package has 997 entries the
car lacks, almost all in `de/audi/app/phone/scon` (523) and the `sdis`
packages (car, media, navi, tuner, audio, tv), which are absent in the G35S
build. Only two resources differ: `resources/version.properties` (HMI version
string G35S, Jenkins tag 1616 vs 1613, diag-jar checksum) and
`resources/hmi_startup.json` (build configuration `MIB2P_Revo_High_EU_G35S`,
fewer startup components, no `PhoneScon`/`InitClimateTerminal`).

Every class the port compiles against or overrides, and every class the two
Audi JAR mods override, is byte-identical between car and package:
`AndroidAuto2Subsystem`, `AndroidAuto2NavHandler`, `CarPlayDSIManager`,
`IMapClusterService`, `CombiBAPServiceNavi`, `RevoTMConfiguration`,
`highg35/TerminalModeScreenBag1`, and `META-INF/MANIFEST.MF`. The Java API
check (report 03) and the override check (third_party catalog) therefore hold
for this car without re-basing.

## Natives: same interface, different build

`libautoreceiver.so` is byte-identical to the package. `gal`, `dio_manager`
and `libesoiap2.so` have exactly the package's sizes but differ in most of
their bytes (1.2 MB of 1.47 MB for `gal`). Their export sets, import sets and
`DT_NEEDED` lists are byte-for-byte identical to the package's (1286/488,
832/513 and 1123/90 symbols respectively); the differences are the GNU
build-id and symbol addresses shifted by a few bytes, which then shifts every
absolute address and branch offset in the code. That is the signature of the
same source rebuilt in a different build train, not of different code.

Consequences:
- The hooks attach by symbol name through the dynamic loader, so shifted
  addresses do not affect them. The 214/214 import match (report 05) and the
  three iAP2 symbols the CarPlay hook needs (report 08) are confirmed present
  in the **car's** `libesoiap2.so`.
- Struct layouts come from the source and compiler, which the identical symbol
  tables indicate are the same; this is not proof, and the earlier caveat
  stands that name matching is not layout matching.

## New caveat: the graphics libraries were not captured

ABI review part 2 (report 08) checked the mirror payload against the package's
stage-2 boot image libraries (`libscreen`, `libEGL`, `libGLESv2`,
`libnvmedia`). The car's stage-2 image is the 2205.10.0 build, and those
libraries live in the boot image, not under `/mnt/app`, so card 2 did not
capture them. They are readable at runtime from `/usr/lib` and `/lib`. Card 3
should capture them, which needs the collector's target allowlist widened from
`/mnt/app/` only; then part 2 is rerun against the car's copies.

## Probe: chain confirmed, tool assumptions unchanged

Same results as card 1 for every tool check, plus
`servicemgrmibhigh=not-elf servicemgrmibhigh0=elf modkit_persist=present`:
ModKit's persistence chain is installed and matched, as the installer's
precondition requires.

## Net

- Version question answered: G35S 006PROD, 2205.10.0.
- The Java side stands as built. Nothing to re-base.
- The native side's interface is identical; the ABI review's symbol-level
  conclusions transfer to the car. Layout is still unproven on hardware.
- One more capture (the four graphics libraries) closes the last static gap
  before the first controlled write to the cluster.
