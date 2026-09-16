# Licensing and third-party notices

The MIT license in `LICENSE` covers the original work in this repository:
`tools/`, `tests/`, `reports/`, `docs/`, `evidence/`, `port/sd/`, and
`port/installer/`.

The following parts are **not** MIT and are **not for commercial use**:

- `port/java/` is a derivative work of
  [fifthBro/mh2p-cluster](https://github.com/fifthBro/mh2p-cluster)
  (commit `a37c917c1b1479e11684e158efc0e1be3c07faa7`), licensed
  [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
  The adaptation is released under the same license, as ShareAlike requires.
  See `port/NOTICE.md` for the list of local changes.
- The installer module in `port/installer/` is designed to run inside
  [LawPaul/MH2p_SD_ModKit](https://github.com/LawPaul/MH2p_SD_ModKit)
  (CC BY-NC-SA 4.0). No ModKit code is included here; the loader must be
  obtained separately and its license applies to it.
- `port/installer/Update/*.wrapper` follow the wrapper approach of
  mh2p-cluster's release scripts and are treated as CC BY-NC-SA 4.0.

Third-party projects referenced as pinned git submodules under `third_party/`
(their content is fetched from the upstream repositories, not stored here;
see `third_party/CATALOG.md`):

| Project | Revision | License |
|---|---|---|
| fifthBro/mh2p-cluster | a37c917 | CC BY-NC-SA 4.0 |
| LawPaul/MH2p_SD_ModKit | 82f9452 | CC BY-NC-SA 4.0 |
| LawPaul/MH2p_CarPlay_FullScreen | 3aeecd5 | CC BY-NC-SA 4.0 |
| LawPaul/MH2p_CarPlay_WindowedFullScreen | 3b6e513 | CC BY-NC-SA 4.0 |
| LawPaul/MH2p_NavCompassIgnore | 1dc404c | CC BY-NC-SA 4.0 |
| LawPaul/MH2p_GreenEngineeringMenu | cc47ec5 | CC BY-NC-SA 4.0 |
| fifthBro/mh2p-ssh-access | cb0e543 | CC BY-NC-SA 4.0 |
| t0chk/Q3Team-MH2p-GEM | ba1fe0b | CC BY-NC-SA 4.0 |

Analysis tooling checked out locally under `vendor/` (not part of this repository):

| Project | Revision | License |
|---|---|---|
| fox-it/dissect.qnxfs | b3a0f3e | see upstream |
| NetherlandsForensicInstitute/qnxmount | 0379c06 | see upstream |
| lclevy/dumpifs | bb77c71 | see upstream |
| jtang613/qnx_dumpers | 68424a6 | see upstream |

## What is deliberately not in this repository

- The Audi firmware package `4K0906961AB_MH2p_ER_AUG35_P2873` and every file
  extracted or decoded from it (`analysis/`).
- Compiled artifacts (`build/`, `dist/`) and downloaded toolchains
  (`build-tools/`).
- Upstream checkouts (`vendor/`).

`evidence/` contains only metadata derived from the firmware: file names,
sizes, hashes, ELF dependency names, exported symbol names, Java class and
method descriptors, and constant values. It contains no code, string tables,
or binary content from the firmware. Audi, Porsche, MH2P and related names are
trademarks of their owners; this project is not affiliated with or endorsed by
them.
