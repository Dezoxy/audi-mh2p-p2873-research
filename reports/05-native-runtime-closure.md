# Native runtime dependency check — 2026-09-16

All 214 required native imports in the three upstream compiled payloads now
match exported names within their firmware/host DT_NEEDED dependency graphs.
There are no missing dependency images or ambiguous providers in this check.
This resolves the extraction gap reported in report 04, without a vehicle dump.

| Payload | Required imports matched |
|---|---:|
| cluster | 111 / 111 |
| gal_cluster.so | 70 / 70 |
| dio_cluster.so | 33 / 33 |

Optional weak imports are recorded separately. This is distinct from the earlier
97 literal dlsym call-site checks. Neither count proves object-layout compatibility,
symbol version compatibility, actual loader search order, or successful execution.
The audit intentionally still records `reuse_approved: false`.

## Where the libraries were found

Stage-1 `loadimg.img` uses an Android boot wrapper with a 2048-byte page and a
zlib-compressed payload. The decoded payload contains startup code followed by
an imagefs filesystem. Searching for a bare `imagefs` string first encountered
startup messages; the actual header is `imagefs` followed by byte 0x04.

The actual filesystem begins at offset 119056 in the 4136964-byte decompressed
payload, and is 4017908 bytes long. Its additive checksum passes. The new
extractor validates wrapper/payload bounds, the zlib checksum and the inner
filesystem checksum before extracting only the four requested runtime libraries:

- `proc/boot/libc.so.3`
- `usr/lib/libm.so.2`
- `usr/lib/libz.so.2`
- `lib/libnvos.so`

All six hardware-variant boot images decode successfully, and these four files
are byte-identical across variants. Trailer bytes remain uninterpreted and their
hashes are recorded; publisher signatures are not verified by this extractor.
No executable was run and original firmware files were not modified.

## Files and validation

- `tools/extract_stage1_runtime.py`: bounded extraction and cross-variant check.
- `tools/audit_native_payload.py`: now includes recovered stage-1 libraries and
  records payload ELF flags in addition to architecture and import matching.
- `tests/test_stage1_runtime.py`: valid extraction, truncated payload, corrupt
  compressed payload, and corrupt inner image with a valid zlib checksum.
- `evidence/build/stage1-runtime.json`: source hashes, image bounds and library hashes.
- `evidence/build/native-payload-audit.json`: complete dependency-name check.

All 23 tests pass. The Java artifact and diagnostic SD ZIP are unchanged.

## Consequence for the installer

The upstream compiled binaries remain a plausible route that does not require
recompiling them with a QNX SDK. The missing-library concern is resolved. A QNX
SDK is still required for the recorded supported rebuild route if native source
changes become necessary.

Before packaging those binaries as an installable Audi tweak, remaining work is
native offset/ABI review, Audi map handover/restoration, actual installer/rollback
implementation and fault tests, followed by controlled hardware validation.
No separate firmware-capture visit is a prerequisite. Checks of installed files
belong in the eventual installer before cluster payload writes.

```sh
.venv/bin/python tools/extract_stage1_runtime.py
.venv/bin/python tools/audit_native_payload.py
.venv/bin/python -m unittest discover -s tests -v
```
