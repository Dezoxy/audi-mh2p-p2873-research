#!/usr/bin/env python3
"""Assemble the AudiClusterIntegration ModKit module with a pinned manifest.

The module directory is research output. It is written under build/ and is
never marked vehicle-ready: native payload compatibility and hardware recovery
validation remain open (reports 04 and 05). A payload directory must be given
explicitly; the tool refuses to guess which binaries to ship.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
MODULE = 'AudiClusterIntegration'
RELEASES = ['MH2p_ER_AUG35_P2873', 'MH2p_ER_AUG35S_P2873']
APP = '/mnt/app'
SELFTEST_SIZE = 4096
# (payload file name, destination, mode); the JAR name is filled in at build time.
NEW_FILES = [('cluster', f'{APP}/eso/bin/apps/cluster/cluster', '755'),
             ('gal_cluster.so', f'{APP}/eso/bin/apps/cluster/gal_cluster.so', '755'),
             ('dio_cluster.so', f'{APP}/eso/bin/apps/cluster/dio_cluster.so', '755'),
             ('cluster_config.json', f'{APP}/eso/bin/apps/cluster/cluster_config.json', '644')]
WRAPPED = [('gal.wrapper', f'{APP}/eso/bin/apps/gal'), ('dio_manager.wrapper', f'{APP}/eso/bin/apps/dio_manager')]
FACTORY_CHECKS = ['img_ver.txt', 'eso/bin/apps/gal', 'eso/bin/apps/dio_manager']


def digest(data):
    return {'size': len(data), 'crc32': f'{zlib.crc32(data) & 0xffffffff:08x}',
            'sha256': hashlib.sha256(data).hexdigest()}


def selftest_bytes():
    body = bytes(range(256)) * (SELFTEST_SIZE // 256)
    return body[:-1] + b'\x00'  # last byte known to the on-unit self-test


def inventory_modes(path):
    """Map unit paths to octal modes from inspect_app's inventory; extracted copies lose their bits."""
    modes = {}

    def walk(node):
        if isinstance(node, dict):
            if 'path' in node and 'mode' in node:
                modes[node['path']] = f"{int(node['mode'], 8) & 0o777:o}"
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(json.loads(Path(path).read_text()))
    return modes


def build(payload_dir, factory_root, jar, output, inventory=None):
    payload_dir, factory_root = Path(payload_dir), Path(factory_root)
    modes = inventory_modes(inventory) if inventory else {}
    update = output / 'Mods' / MODULE / 'Update'
    if output.exists():
        shutil.rmtree(output)
    (update / 'payload').mkdir(parents=True)
    (output / 'Mods' / MODULE / 'Persist').mkdir(parents=True)
    for name in ['common.sh', 'install.sh', 'uninstall.sh']:
        shutil.copy(ROOT / 'port/installer/Update' / name, update / name)
    shutil.copy(ROOT / 'port/installer/Persist/install.sh', output / 'Mods' / MODULE / 'Persist/install.sh')
    shutil.copy(ROOT / 'port/installer/failsafe.sh', output / 'failsafe.sh')
    lines = ['# audi-cluster-manifest v1'] + [f'release {r}' for r in RELEASES]
    st = selftest_bytes()
    (update / 'selftest.bin').write_bytes(st)
    lines.append(f"selftest selftest.bin {len(st)} {digest(st)['crc32']}")
    payloads, ops = {}, []
    ops.append(('new', f'{APP}/eso/hmi/lsd/jars/{jar.name}', jar.name, '644'))
    payloads[jar.name] = jar.read_bytes()
    for name, dest, mode in NEW_FILES:
        src = payload_dir / name
        if not src.is_file():
            sys.exit(f'payload missing: {src}')
        payloads[name] = src.read_bytes()
        ops.append(('new', dest, name, mode))
    for name, dest in WRAPPED:
        payloads[name] = (ROOT / 'port/installer/Update' / name).read_bytes()
        ops.append(('wrap', dest, name, '755'))
    for name, data in payloads.items():
        (update / 'payload' / name).write_bytes(data)
        d = digest(data)
        mode = next(m for _, _, p, m in ops if p == name)
        lines.append(f"payload {name} {d['size']} {d['crc32']} {d['sha256']} {mode}")
    factory = {}
    for rel in FACTORY_CHECKS:
        src = factory_root / rel
        if not src.is_file():
            sys.exit(f'factory reference missing: {src}')
        if inventory:
            if f'/{rel}' not in modes:
                sys.exit(f'factory mode missing from inventory: /{rel}')
            mode = modes[f'/{rel}']
        else:
            mode = f'{src.stat().st_mode & 0o777:o}'
        d = digest(src.read_bytes())
        d['mode'] = mode
        factory[f'{APP}/{rel}'] = d
        lines.append(f"factory {APP}/{rel} {d['size']} {d['crc32']} {d['sha256']} {mode}")
    for op, dest, name, mode in ops:
        lines.append(f'op {op} {dest} {name} {mode}')
    (update / 'manifest.txt').write_text('\n'.join(lines) + '\n')
    for p in update.glob('*.sh'):
        p.chmod(0o755)
    (output / 'Mods' / MODULE / 'Persist/install.sh').chmod(0o755)
    (output / 'failsafe.sh').chmod(0o755)
    return {'module_dir': str(output), 'jar': jar.name, 'payloads': {k: digest(v) for k, v in payloads.items()},
            'factory': factory, 'operations': [' '.join(o) for o in ops], 'accepted_releases': RELEASES,
            'integrity_on_unit': 'size + CRC-32 (gzip trailer); not tamper-proof',
            'approved_for_vehicle': False, 'vehicle_tested': False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--payload-dir', required=True, help='directory with cluster, gal_cluster.so, dio_cluster.so, cluster_config.json')
    ap.add_argument('--jar', default=str(ROOT / 'build/java/ClusterIntegration-Audi-P2873-experimental.jar'))
    ap.add_argument('--factory-root', default=str(ROOT / 'analysis/app/files'))
    ap.add_argument('--factory-inventory', default=str(ROOT / 'analysis/app/filesystem-inventory.json'),
                    help="inspect_app inventory supplying factory modes; pass '' to use file modes (fixtures only)")
    ap.add_argument('--output', default=str(ROOT / 'build/installer'))
    ap.add_argument('--evidence', default=str(ROOT / 'evidence/build/installer-build.json'))
    a = ap.parse_args()
    report = build(a.payload_dir, a.factory_root, Path(a.jar), Path(a.output), a.factory_inventory or None)
    if a.evidence:
        Path(a.evidence).parent.mkdir(parents=True, exist_ok=True)
        Path(a.evidence).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
