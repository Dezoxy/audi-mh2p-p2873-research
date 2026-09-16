# Experimental Audi P2873 adaptation

Derived from fifthBro/mh2p-cluster, commit a37c917c1b1479e11684e158efc0e1be3c07faa7.
Upstream: https://github.com/fifthBro/mh2p-cluster
Copyright (c) 2026 fifthBro. CC BY-NC-SA 4.0; not for commercial use.
The upstream license is included in the compiled JAR.

Local changes dated 2026-09-16 remove the Porsche StorageMountHandler dependency,
restrict Android Auto log destination selection to /tmp, and remove decompiler
Object casts rejected by the Audi firmware's typed enum API. Seven source files
are built. The unused ClusterAAMirror placeholder, standalone activator (which
calls a nonexistent setter), and its unused ClusterMapController are excluded.
Original sources remain intact under vendor/mh2p-cluster.

This is a compileable research artifact, not a vehicle-tested port. Upstream
rendering behavior is not yet adapted or approved. Do not copy this JAR into
the vehicle's HMI classpath. No OEM firmware classes are bundled in this JAR.
