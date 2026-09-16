#!/usr/bin/env python3
"""Extract core libraries from the observed Android-wrapped, zlib QNX stage 1.
Validates the wrapper bounds, zlib checksum and inner image checksum; records
uninterpreted trailer hashes. Does not validate publisher signatures or execute code.
"""
import hashlib
import json
from pathlib import Path
import struct
import zlib
from extract_stage2 import parse_image

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {'proc/boot/libc.so.3', 'usr/lib/libm.so.2', 'usr/lib/libz.so.2', 'lib/libnvos.so'}


def decode(data):
    if len(data) < 2048 or data[:8] != b'ANDROID!':
        raise ValueError('Unsupported boot wrapper')
    size, _, ramdisk, _, second, _, _, page = struct.unpack_from('<8I', data, 8)
    if page != 2048 or ramdisk or second or size < 1 or page + size > len(data):
        raise ValueError('Invalid boot payload bounds')
    z = zlib.decompressobj()
    decoded = z.decompress(data[page:page + size], 32 * 1024 * 1024)
    if not z.eof or z.unconsumed_tail:
        raise ValueError('Incomplete or oversized compressed payload')
    # Ignore startup strings mentioning imagefs: only the exact header qualifies.
    start = decoded.find(b'imagefs\x04')
    if start < 0 or start + 12 > len(decoded):
        raise ValueError('No bounded QNX image')
    length = struct.unpack_from('<I', decoded, start + 8)[0]
    if start + length != len(decoded):
        raise ValueError('Unexpected QNX image boundary')
    image = decoded[start:]
    rows = parse_image(image)
    files = {r['path']: image[r['offset']:r['offset'] + r['size']]
             for r in rows if r['kind'] == 'file' and r['path'] in TARGETS}
    if set(files) != TARGETS:
        raise ValueError('Missing core libraries')
    return files, {'decoded_size': len(decoded), 'image_offset': start, 'image_size': length,
                   'image_sha256': hashlib.sha256(image).hexdigest(), 'image_checksum': 'pass',
                   'entry_count': len(rows), 'compressed_payload_size': size,
                   'uninterpreted_trailer_size': len(z.unused_data),
                   'uninterpreted_trailer_sha256': hashlib.sha256(z.unused_data).hexdigest()}


def main():
    paths = sorted((ROOT / '4K0906961AB_MH2p_ER_AUG35_P2873/Data').glob('MMX2P.mifs-stage1*/**/loadimg.img'))
    if not paths:
        raise SystemExit('Stage-1 images missing')
    reports, baseline = [], None
    for path in paths:
        data = path.read_bytes()
        files, report = decode(data)
        if baseline is not None and files != baseline:
            raise SystemExit('Core libraries differ across variants; choose the hardware variant explicitly.')
        baseline = files
        reports.append({'source': str(path.relative_to(ROOT)), 'source_sha256': hashlib.sha256(data).hexdigest(), **report})
    output = ROOT / 'analysis/stage1-runtime/files'
    for name, data in baseline.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != data:
                raise SystemExit('Existing extraction differs: ' + name)
        else:
            path.write_bytes(data)
    report = {'variants': reports, 'core_libraries_identical_across_variants': True,
              'files': {n: {'sha256': hashlib.sha256(d).hexdigest(), 'size': len(d)} for n, d in baseline.items()},
              'publisher_signature_verified': False}
    (ROOT / 'evidence/build/stage1-runtime.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Validated', len(paths), 'boot variants; four core libraries are identical across them.')


if __name__ == '__main__':
    main()
