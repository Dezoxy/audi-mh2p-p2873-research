# AudiClusterIntegration ModKit module

Implementation of `CONTRACT.md`; see `reports/06-installer-transaction.md`.
Not vehicle-tested and not approved for installation.

```
Mods/AudiClusterIntegration/
  Update/install.sh      journaled install (loader runs it during the SD update)
  Update/uninstall.sh    journaled removal (loader runs it when uninstall.txt exists)
  Update/common.sh       integrity check, journal, rollback helpers
  Update/manifest.txt    generated: releases, payload/factory sizes, CRC-32, SHA-256, ops
  Update/selftest.bin    generated: known file for the on-unit hash self-test
  Update/payload/        generated: JAR, native files, gal.wrapper, dio_manager.wrapper
  Persist/install.sh     COMMITTED: starts the daemon; any uncommitted state: unattended rollback
  Persist/common.sh, manifest.txt, selftest.bin   generated copies that rollback needs at boot
failsafe.sh              card root; early-boot rollback when AudiClusterIntegration-RECOVER exists
```

Precondition: ModKit's persistence chain must already be installed (run the
plain ModKit SD update once and confirm a normal boot first). The install stops
otherwise, so the cluster transaction never coincides with ModKit's own first
install. Recovery without the HMI: create `AudiClusterIntegration-RECOVER` in
the card root, insert the card, boot; read `AudiClusterIntegration-failsafe.log`.
See `reports/07-recovery-launch-path.md`.

State and journal live on the unit under `/mnt/app/eso/.audi-cluster/`.
Backups are written to `<media>/AudiClusterIntegration-backup/<txid>/` and
are never reused or overwritten. Environment variables
`AUDI_CLUSTER_FIXTURE_ROOT` and `AUDI_CLUSTER_FAULT` exist for host tests only;
fault injection is inert without a fixture root.

Build with `tools/build_cluster_installer.py --payload-dir DIR`. The module is
assembled under `build/` and deliberately not placed in `dist/`.
