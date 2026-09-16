#!/usr/bin/env python3
"""Read-only EFS traversal using pinned qnxmount structures; no FUSE mount."""
import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path, PurePosixPath
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor/qnxmount'))
from qnxmount.efs.interface import scan_partitions

p=argparse.ArgumentParser()
p.add_argument('image',type=Path)
p.add_argument('output',type=Path)
a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
rows=[]
for index, fs in enumerate(scan_partitions(a.image)):
    seen=set()
    def walk(entry, parent=''):
        for child in fs.read_dir(entry):
            name=child.name
            if not name or name in ('.','..') or '/' in name:
                raise ValueError('Unexpected directory name')
            path=parent+'/'+name
            if path in seen or len(seen)>10000:
                raise ValueError('Duplicate/cyclic EFS path')
            seen.add(path)
            mode=fs.stat(child)
            row={'partition':index,'mountpoint':fs.root.name,'path':path,'mode':oct(mode)}
            if stat.S_ISDIR(mode):
                row['kind']='dir'
                rows.append(row)
                walk(child,path)
            else:
                content=fs.read_file(child)
                row.update(size=len(content),sha256=hashlib.sha256(content).hexdigest())
                if stat.S_ISREG(mode):
                    if content.startswith(b'iwlyfmbp'):
                        raise ValueError('Compressed EFS file requires separate decompression')
                    row['kind']='file'
                    target=a.output/f'partition-{index}'/'files'/path.lstrip('/')
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(content)
                elif stat.S_ISLNK(mode):
                    row.update(kind='symlink',target=content.rstrip(b'\0').decode())
                else:
                    row['kind']='special'
                rows.append(row)
    walk(fs.root)
if not rows:raise ValueError('No EFS entries found')
(a.output/'inventory.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps({'entries':len(rows),'files':sum(r['kind']=='file' for r in rows)},indent=2))
