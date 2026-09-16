#!/usr/bin/env python3
"""Read-only package inventory and installer block-checksum verification."""
import argparse
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('package', type=Path)
p.add_argument('output', type=Path)
a = p.parse_args()
rows = []
checks = []
for path in sorted(a.package.rglob('*')):
    if not path.is_file() or path.name == '.DS_Store':
        continue
    h = hashlib.sha256()
    with path.open('rb') as f:
        while block := f.read(4 * 1024 * 1024):
            h.update(block)
    rows.append({'path': str(path.relative_to(a.package)), 'size': path.stat().st_size, 'sha256': h.hexdigest()})
    if not path.name.endswith('installer.txt'):
        continue
    def records(value, location='$'):
        if isinstance(value, dict):
            if isinstance(value.get('CheckSum'), list) and value.get('CheckSumSize') and value.get('Source'):
                yield location, value
            for key, child in value.items():
                yield from records(child, location + '/' + key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from records(child, location + '/' + str(index))
    for location, meta in records(json.loads(path.read_text())):
        source = (path.parent / meta['Source']).resolve()
        if not source.is_relative_to(a.package.resolve()):
            raise ValueError('Source escapes package')
        base = {'installer': str(path.relative_to(a.package)), 'record': location}
        if not source.is_file():
            checks.append({**base, 'status': 'source_missing'})
            continue
        actual = []
        with source.open('rb') as f:
            while block := f.read(meta['CheckSumSize']):
                actual.append(hashlib.sha1(block).hexdigest())
        expected = meta['CheckSum']
        checks.append({**base, 'source': str(source.relative_to(a.package.resolve())),
                       'blocks': len(actual), 'expected_blocks': len(expected),
                       'size_matches': source.stat().st_size == meta.get('FileSize', source.stat().st_size),
                       'status': 'pass' if actual == expected else 'FAIL',
                       'mismatched_blocks': [i for i, (x,y) in enumerate(zip(actual, expected)) if x != y]})
a.output.mkdir(parents=True, exist_ok=True)
(a.output / 'package-inventory.json').write_text(json.dumps(rows, indent=2) + '\n')
(a.output / 'installer-checks.json').write_text(json.dumps(checks, indent=2) + '\n')
print(json.dumps({'files': len(rows), 'bytes': sum(x['size'] for x in rows), 'checks': len(checks), 'failures': [x for x in checks if x['status'] != 'pass' or not x.get('size_matches', True)]}, indent=2))

if any(x['status'] != 'pass' or not x.get('size_matches', True) for x in checks):
    raise SystemExit(1)
