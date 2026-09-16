#!/usr/bin/env python3
"""Inventory this firmware's QNX6 app image; extract selected regular files only.
The 16 KiB data-block alignment is specific to the inspected image. Fail closed
unless both observed superblocks agree and inode 1 is a valid root directory.
Never mount, execute firmware, materialize symlinks, or modify the source image.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from dissect.qnxfs.qnx6 import QNX6, _find_sb, _generate_dataruns
from dissect.util.stream import RunlistStream

p = argparse.ArgumentParser()
p.add_argument('image', type=Path)
p.add_argument('output', type=Path)
p.add_argument('--extract', help='Regular expression matched against image paths')
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
with a.image.open('rb') as fh:
    fs = QNX6.__new__(QNX6)
    fs.fh = fh
    offset, fs.sb, fs._c_qnx = _find_sb(fh)
    if offset != 0x2000 or fs.sb.sb_blocksize != 0x4000:
        raise ValueError('Unsupported layout; investigate before extracting')
    fh.seek(offset)
    first = fh.read(512)
    # Observed backup header is 4 KiB before the end of this image.
    backup = a.image.stat().st_size - 0x1000
    fh.seek(backup)
    if fh.read(512) != first:
        raise ValueError('Superblocks differ; snapshot selection requires investigation')
    fs.block_size = fs.sb.sb_blocksize
    fs._blocks_offset = 1
    for attr, root in [('_inodes', fs.sb.Inode), ('_long_file', fs.sb.Longfile)]:
        runs = list(_generate_dataruns(fs, root.size, root.ptr, root.levels))
        setattr(fs, attr, RunlistStream(fh, runs, root.size, fs.block_size))
    fs.root = fs.inode(1)
    if not fs.root.is_dir() or dict(fs.root.iterdir())['.'].inum != 1:
        raise ValueError('Invalid root inode')
    rows = []
    seen = set()
    def walk(node, parent=''):
        if node.inum in seen:
            raise ValueError('Directory cycle')
        seen.add(node.inum)
        for name, entry in node.iterdir():
            if name in ('.', '..'):
                continue
            if '/' in name or '\x00' in name:
                raise ValueError('Unsafe entry name')
            path = parent + '/' + name
            row = {'path': path, 'inode': entry.inum, 'size': entry.size, 'mode': oct(entry.mode),
                   'kind': 'dir' if entry.is_dir() else 'file' if entry.is_file() else 'symlink' if entry.is_symlink() else 'other'}
            if entry.is_symlink():
                row['target'] = entry.link
            if entry.is_file() and a.extract and re.search(a.extract, path, re.I):
                target = a.output / 'files' / path.lstrip('/')
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise FileExistsError(target)
                h = hashlib.sha256()
                count = 0
                stream = entry.open()
                with target.open('xb') as out:
                    while block := stream.read(1024 * 1024):
                        out.write(block)
                        h.update(block)
                        count += len(block)
                if count != entry.size:
                    raise ValueError('Extracted size mismatch')
                row['sha256'] = h.hexdigest()
            rows.append(row)
            if entry.is_dir():
                walk(entry, path)
    walk(fs.root)
    allocated = fs.sb.sb_num_inodes - fs.sb.sb_free_inodes
    reached = len({r['inode'] for r in rows} | {1})
    if reached != allocated:
        raise ValueError(f'Incomplete inventory: {reached} reachable vs {allocated} allocated inodes')
    (a.output / 'filesystem-inventory.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps({'entries':len(rows), 'extracted':sum('sha256' in r for r in rows), 'superblock_offsets':[offset,backup], 'data_offset':fs.block_size, 'block_size':fs.block_size}, indent=2))
