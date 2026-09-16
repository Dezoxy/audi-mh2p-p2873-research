#!/usr/bin/env python3
"""Decode the observed MH2P LZ4_ container and extract checksummed QNX images.

Uses the imagefs structures documented by OpenQNX and lclevy/dumpifs.
This handles the full app/img_restore container, not its truncated flash prefix.
Firmware is treated only as data; symlinks/devices are recorded, never created.
"""
import argparse
import hashlib
import json
import stat
import struct
from pathlib import Path, PurePosixPath

import lz4.block


def decode_container(data):
    if data[:8] != b'LZ4_\x00\x00\x20\x00':
        raise ValueError('Unsupported LZ4 container header')
    offset = 8192
    blocks, images = [], []
    current = bytearray()
    for index in range(254):  # Table ends before metadata at 0x400.
        size = struct.unpack_from('<I', data, 8 + index * 4)[0]
        if size == 0:
            break
        if size > 2097152 or offset + size > len(data):
            raise ValueError(f'Truncated/invalid block {index}')
        decoded = lz4.block.decompress(data[offset:offset + size], uncompressed_size=2097152)
        if current and len(current) == struct.unpack_from('<I', current, 8)[0]:
            images.append(bytes(current))
            current.clear()
        if not current and not decoded.startswith(b'imagefs\x04'):
            raise ValueError(f'Expected imagefs at block {index}')
        current.extend(decoded)
        if len(current) > struct.unpack_from('<I', current, 8)[0]:
            raise ValueError('Decoded data exceeds declared image size')
        blocks.append({'index': index, 'offset': offset, 'compressed': size, 'decompressed': len(decoded)})
        offset = (offset + size + 511) // 512 * 512
    else:
        raise ValueError('Unterminated block table')
    if current:
        images.append(bytes(current))
    if offset != len(data):
        raise ValueError('Unaccounted trailing container bytes')
    return images, blocks


def parse_image(data):
    if len(data) < 92 or data[:8] != b'imagefs\x04':
        raise ValueError('Unsupported imagefs header')
    size, directory_end, offset = struct.unpack_from('<III', data, 8)
    if size != len(data) or size % 4 or not 92 <= offset <= directory_end < size:
        raise ValueError('Invalid imagefs bounds')
    if sum(x[0] for x in struct.iter_unpack('<I', data)) & 0xffffffff:
        raise ValueError('Imagefs additive checksum failed')
    entries = []
    seen = set()
    while offset + 2 <= directory_end:
        length = struct.unpack_from('<H', data, offset)[0]
        if not length:
            return entries
        if length < 24 or offset + length > directory_end:
            raise ValueError('Invalid directory entry')
        _, _, inode, mode, gid, uid, mtime = struct.unpack_from('<HHIIIII', data, offset)
        kind = stat.S_IFMT(mode)
        start = offset + 24
        row = {'inode': inode, 'mode': oct(mode), 'uid': uid, 'gid': gid, 'mtime': mtime}
        if kind == stat.S_IFREG:
            file_offset, file_size = struct.unpack_from('<II', data, start)
            if file_offset < directory_end or file_offset + file_size > len(data) - 4:
                raise ValueError('File outside image data bounds')
            row.update(kind='file', offset=file_offset, size=file_size)
            start += 8
        elif kind == stat.S_IFLNK:
            link_offset, link_size = struct.unpack_from('<HH', data, start)
            start += 4
            target_start = start + link_offset
            if target_start + link_size > offset + length:
                raise ValueError('Symlink outside entry')
            row.update(kind='symlink', target=data[target_start:target_start + link_size].rstrip(b'\0').decode())
        elif kind == stat.S_IFDIR:
            row['kind'] = 'dir'
        else:
            raise ValueError(f'Unsupported special entry type {kind:o}')
        end = data.index(0, start, offset + length)
        name = data[start:end].decode()
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts :
            raise ValueError(f'Unsafe entry path: {name!r}')
        row['duplicate_path'] = name in seen
        seen.add(name)
        row['path'] = name
        entries.append(row)
        offset += length
    raise ValueError('Missing directory terminator')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('container', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    data = args.container.read_bytes()
    images, blocks = decode_container(data)
    # Validate every image before writing files.
    parsed = [parse_image(image) for image in images]
    args.output.mkdir(parents=True, exist_ok=False)
    summary = {'source': str(args.container), 'sha256': hashlib.sha256(data).hexdigest(), 'blocks': blocks, 'images': []}
    for index, (image, entries) in enumerate(zip(images, parsed)):
        destination = args.output / f'image-{index:02}' / 'files'
        for row in entries:
            if row['kind'] != 'file':
                continue
            content = image[row['offset']:row['offset'] + row['size']]
            row['sha256'] = hashlib.sha256(content).hexdigest()
            if row['path'].startswith('etc/ssh/ssh_host_'):
                row['extraction'] = 'omitted_host_key'
                continue
            relative = row['path'] if not row['duplicate_path'] else f"duplicates/{row['inode']}/{row['path']}"
            row['extracted_path'] = relative
            path = destination / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            row['sha256'] = hashlib.sha256(content).hexdigest()
        summary['images'].append({'index': index, 'size': len(image), 'sha256': hashlib.sha256(image).hexdigest(), 'checksum': 'pass', 'entries': entries})
    (args.output / 'inventory.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'blocks': len(blocks), 'images': len(images), 'entries': sum(map(len, parsed)), 'files': sum(r['kind'] == 'file' for rows in parsed for r in rows)}, indent=2))


if __name__ == '__main__':
    main()
