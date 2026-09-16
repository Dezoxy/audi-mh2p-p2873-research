# Native build and installer readiness — 2026-09-16

Update: [report 05](05-native-runtime-closure.md) resolves the four missing runtime images and records 214/214 native import matches. This report preserves the earlier investigation state.

The supplied P2873 firmware remains the working baseline. The user confirmed
no QNX SDK is available. A separate head-unit firmware capture is no longer a
prerequisite; installation-time checks are specified in
`port/installer/CONTRACT.md`.

## Work completed

- Added `tools/build_native_port.py`: a recorded build recipe for the renderer,
  Android Auto hook and CarPlay hook, with source hashes. Actual compilation
  requires a configured SDK, checks QNX 6.6 headers, checks ARM32 little-endian
  output, and rejects direct GLESv2 dependencies. It never deploys binaries.
- Corrected omissions in the short source-comment recipes: renderer zlib
  linkage and CarPlay `rgd_tlv.c`, `pps_writer.c`, `logging.c` translation units.
  The proposed Android Auto hook also links Screen explicitly. These commands
  have not been compiler-tested; there is no SDK or native build result yet.
- Added `tools/audit_native_payload.py`: checks the existing release ZIP's ELF
  architecture and strong imports against each host's declared dependency
  graph. Optional weak imports are kept separate; ambiguous library matches
  are not silently combined into a successful result.
- Extracted seven additional dependency libraries from the existing app image,
  into `analysis/native-deps/` and `analysis/native-deps-nme/`. Firmware unchanged.
- Added three tests; all 19 workspace tests pass. Missing SDK is tested to stop
  the build without publishing a native payload.

## What the prebuilt audit establishes

All three upstream native payloads are ARM32 little endian. Graphics imports
resolve by name against the extracted firmware dependency graph. The graph
still lacks four core library images: `libc.so.3`, `libm.so.2`, `libnvos.so`,
`libz.so.2`. They have not been recovered in the extraction set used here.
This does not mean they are missing on the vehicle, and is not a firmware
incompatibility finding.

| Payload | Strong imports matched in available graph | Audit complete? |
|---|---:|---|
| cluster | 36 / 111 | No |
| gal_cluster.so | 16 / 70 | No |
| dio_cluster.so | 0 / 33 | No; its strong imports need core libraries |

These direct-link imports are a different check from the earlier 97/97 literal
`dlsym` call-site matches. Neither test establishes C/C++ object layouts,
hard-coded field offsets, actual runtime search order or display behavior.
Prebuilt reuse remains a possible path, not an approved fallback. No upstream
binary has been copied into the SD addon or run locally.

## SDK route

QNX's [6.6 installation documentation](https://www.qnx.com/developers/articles/inst_5847_9.html)
describes its own package and license setup. Its
[build-host documentation](https://qnx.com/developers/docs/7.0.0/com.qnx.doc.hypervisor.nonsafety.user/topic/build/build_env.html)
states that pre-7.0 SDPs do not support macOS development hosts. A licensed
compatible Linux/Windows build environment would therefore be the supported
route. The availability or entitlement to obtain that old SDK has not been
established. A current QNX 8 installation is not assumed to substitute for 6.6.

No download, license acceptance, purchase, or external build service was used.

## Installation design finding

The existing ModKit loader runs addon scripts without treating their failure as
an overall abort, then installs its persistence wrapper. An addon compatibility
failure can prevent cluster changes but cannot guarantee zero base-loader
changes. The installer contract now explicitly distinguishes these scopes and
specifies verified backups, per-file journaling, power-loss recovery, and
conditional uninstall. This is a contract, not implemented rollback code.

## Reproduce

```sh
.venv/bin/python tools/build_native_port.py
.venv/bin/python tools/audit_native_payload.py
.venv/bin/python -m unittest discover -s tests -v
```

On a compatible build host, after configuring the licensed QNX 6.6 SDK:

```sh
.venv/bin/python tools/build_native_port.py --build
```

The latter command is untested against a real SDK. A successful build would
still need firmware ABI/dependency validation before installation packaging.

Evidence: `evidence/build/native-build-plan.json`, `native-payload-audit.json`
and `test-results.txt`. The existing Java build and diagnostic ZIP are unchanged.
