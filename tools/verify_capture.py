#!/usr/bin/env python3
"""Compare captured live files with the private offline firmware baseline."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(capture, manifest):
    failures = []
    if not (capture / 'COMPLETE').is_file() or (capture / 'COMPLETE').read_text().strip() != 'capture-complete-v1':
        failures.append('Capture incomplete')
    release = (capture / 'release.txt').read_text().strip() if (capture / 'release.txt').is_file() else 'UNKNOWN'
    if release not in manifest['allowed_releases']:
        failures.append('Live release is unsupported or unknown: ' + release)
    checks = []
    for name, expected in manifest['files'].items():
        if not name.startswith(('/mnt/app/', '/lib/', '/usr/lib/')) or '..' in Path(name).parts:
            raise ValueError('Invalid reference target')
        p = capture / 'files' / name.lstrip('/')
        # A symlink in a capture must never redirect verification to another file.
        linked = any(q.is_symlink() for q in [p, *p.parents] if q != capture.parent)
        actual = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() and not linked else None
        match = actual == expected['sha256'] and p.stat().st_size == expected['size'] if actual else False
        checks.append({'path': name, 'match': match, 'sha256': actual})
        if not match:
            failures.append('Missing, linked or different file: ' + name)
    matched = sum(1 for c in checks if c['match'])
    return {'baseline_match': not failures, 'release': release, 'checks': checks, 'failures': failures,
            'files_matching_package': matched, 'files_total': len(checks),
            'note': 'This car may run a build different from the analysed package; per-file matches '
                    'above are the useful signal (e.g. gal/dio_manager identical, lsd.jar/version files differ).',
            'installation_approved': False,
            'remaining_checks': ['Native build/ABI', 'Active display routing and map restoration',
                                 'Existing mods and classloader precedence', 'Backup/rollback and recovery validation']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture', type=Path)
    p.add_argument('--reference', type=Path, default=ROOT / 'evidence/build/capture-reference.json')
    args = p.parse_args()
    result = verify(args.capture.absolute(), json.loads(args.reference.read_text()))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['baseline_match'] else 1)


if __name__ == '__main__':
    main()
