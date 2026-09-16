# Existing MH2P modifications (catalog)

Pinned as git submodules; clone with `git clone --recurse-submodules` or run
`git submodule update --init`. Every entry is third-party work under its own
license (CC BY-NC-SA 4.0 unless noted, not for commercial use). Nothing here
has been run on the P2873 unit by this project; "Audi support" is what the
mod's own scripts declare. Assemble a card with `tools/prepare_sd_card.py`.

| Name (`--mod`) | Repository @ revision | What it writes on the unit | Audi support | Notes and risk |
|---|---|---|---|---|
| base `modkit` | LawPaul/MH2p_SD_ModKit @ 82f9452 | Replaces `/mnt/app/eso/bin/servicemgrmibhigh` with a wrapper, keeps the factory binary as `servicemgrmibhigh0`, installs `/mnt/ota/modkit/modkit_persist.sh`; runs `Mods/*` | yes (v2 exports OEM/TYPE) | Required loader for every mod below and for this project's installer. Uses the `fecswap` mechanism only to deliver its scripts. |
| base `q3team` | t0chk/Q3Team-MH2p-GEM @ ba1fe0b | Own `servicemgrmibhigh` wrapper (factory kept as `servicemgrmibhigh99`), Green Engineering Menu with Q3 Team pages: backups, logs, version dump, fullscreen CarPlay/AA, cockpit skins, compass, region and language tools; `Storage/installfecs/fecmanager` | Q3 F3 specific | ModKit **v1** layout (`mod.sh`, `install.sh`/`_uninstall.sh` at mod root); its mods do not run under ModKit v2 and its wrapper conflicts with v2 on the same file. Choose one base per unit. Includes an FEC manager; not used by this project. |
| `carplay-fullscreen` | LawPaul/MH2p_CarPlay_FullScreen @ 3aeecd5 | `fc.jar` into `/mnt/app/eso/hmi/lsd/jars/` (classpath override of `lsd.jar`) | yes: ships `fc-full-AUG35.jar` (same bytes as `fc-full-AU.jar`, not firmware-version specific) | Java override; wrong class signatures would break the HMI. See the P2873 override check below. Uninstall removes the JAR. |
| `carplay-windowed` | LawPaul/MH2p_CarPlay_WindowedFullScreen @ 3b6e513 | `fc.jar` as above (keeps side and top bars) | yes (`fc-full-AU*.jar`) | Mutually exclusive with `carplay-fullscreen` (same target file). |
| `navcompass` | LawPaul/MH2p_NavCompassIgnore @ 1dc404c | `NaviCompass.jar` into the same jars directory | Audi only | Lets the factory map show in the cluster while phone navigation runs. Relevant to the cluster project; interaction with the future cluster module untested. |
| `gem` | LawPaul/MH2p_GreenEngineeringMenu @ cc47ec5 | `fecswap -a 00000700` into `/mnt/persist_new/fec/granted.fecs` (backup kept), Post stage sets developer mode via `pc b:0x5F22:0x243F` | generic | Engineering menu, not a customer feature. GEM contains actions that can damage the unit or coding; use only for reading. Adds a FEC entry. |
| `ssh-access` | fifthBro/mh2p-ssh-access @ cb0e543 | Appends your public key to `/mnt/app/root/.ssh/authorized_keys`; Persist stage starts `sshd -p 2012` | yes (Audi/VW/Porsche) | Needs a D-Link DUB-E100 USB Ethernet adapter and your own key (`--ssh-pubkey`). This is the shell access the cluster work needs. |
| reference | fifthBro/mh2p-cluster @ a37c917 | Porsche-only cluster integration (source of this project's port) | no (installer exits on OEM != PO) | Not a card mod here; see `port/` and the reports. |

## P2873 override check (static, 2026-09-16)

The two Audi JAR mods were compared class by class with the P2873 `lsd.jar`
using the same class-file reader as the port's API check:

| JAR | Classes | Present in P2873 `lsd.jar` | Public/protected methods dropped | Classfile |
|---|---:|---:|---:|---|
| `fc-full-AUG35.jar` | 3 | 2 (one new helper class `TerminalModeScreenBag1`) | 0 | 48 |
| `NaviCompass.jar` | 3 | 3 | 0 | 48 |

Superclasses agree. This says the overrides fit the P2873 class layout; it
does not verify behaviour, private field access, or interaction with the
future cluster module.

## Listed, not included

- LawPaul/MH2p_AppleCarPlay, MH2p_AndroidAuto, MH2p_BaiduCarLife: activate
  paid smartphone-interface options by adding FEC codes and 5F coding. The
  P2873 unit in question already has the options in use; enabling paid
  features is outside this project's scope.
- Challenge/response tools for the engineering login (LawPaul/MH2p-Response,
  horrordash/mh2p_login, t0chk/mh2p-challenger, jiangbo2571/MH2P_MIB3_challenge-tools):
  useful with a telnet/serial session; no license or Windows-only; not needed
  once SSH works.
- jsonpoindexter/mh2p-lsd-mods: workflow for decompiling and patching
  `lsd.jar`; no license; development tooling, not a mod.
- JeniCzech92/MH2p_RSDB (radio station database), Anub1s0803 Touareg
  fullscreen (VW P2876): unrelated to this unit.
- Nothing published implements video-in-motion or the cluster feature for Audi.

## Conflicts and order

- One base per unit: `modkit` (v2) or `q3team` (v1). They replace the same
  file with different wrappers and keep the factory binary under different
  names. This project's installer precondition is written for the v2 layout.
- `carplay-fullscreen` and `carplay-windowed` both install `fc.jar`.
- Run the base once and confirm a normal boot before adding mods; a mod's
  failure does not stop ModKit from installing its wrapper (see
  `port/installer/CONTRACT.md`).
- To uninstall a v2 mod, place an empty `uninstall.txt` in its folder on the
  card and run the SD update again.
