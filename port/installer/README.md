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
  Persist/install.sh     starts the cluster daemon only when state is COMMITTED
```

State and journal live on the unit under `/mnt/app/eso/.audi-cluster/`.
Backups are written to `<media>/AudiClusterIntegration-backup/<txid>/` and
are never reused or overwritten. Environment variables
`AUDI_CLUSTER_FIXTURE_ROOT` and `AUDI_CLUSTER_FAULT` exist for host tests only;
fault injection is inert without a fixture root.

Build with `tools/build_cluster_installer.py --payload-dir DIR`. The module is
assembled under `build/` and deliberately not placed in `dist/`.
