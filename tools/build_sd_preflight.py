#!/usr/bin/env python3
"""Package the diagnostic addon only; no loader or proprietary payloads."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ['version_info.txt', 'img_ver.txt', 'target.properties',
           'eso/bin/apps/gal', 'eso/bin/apps/dio_manager',
           'eso/lib/libesoiap2.so', 'eso/lib/libautoreceiver.so', 'eso/hmi/lsd/lsd.jar']


def build():
    files = {}
    for name in TARGETS:
        p = ROOT / 'analysis/app/files' / name
        files['/mnt/app/' + name] = {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                                    'size': p.stat().st_size}
    manifest = {'schema': 1, 'allowed_releases': ['MH2p_ER_AUG35_P2873', 'MH2p_ER_AUG35S_P2873'],
                'vehicle_identity': 'G35S (user confirmed)', 'files': files}
    evidence = ROOT / 'evidence/build'
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'capture-reference.json').write_text(json.dumps(manifest, indent=2) + '\n')
    folder = ROOT / 'dist'
    folder.mkdir(exist_ok=True)
    output = folder / 'Audi-P2873-preflight-addon.zip'
    entries = {'README.md': (ROOT / 'port/sd/README.md').read_bytes()}
    prefix = 'Mods/AudiP2873Preflight/Update/'
    for name in ['collect.sh', 'install.sh', 'uninstall.sh', 'probe.sh']:
        entries[prefix + name] = (ROOT / 'port/sd' / name).read_bytes()
    entries[prefix + 'targets.txt'] = ('\n'.join(files) + '\n').encode()
    # The probe exercises the real installer library on the unit.
    entries[prefix + 'common.sh'] = (ROOT / 'port/installer/Update/common.sh').read_bytes()
    spec = importlib.util.spec_from_file_location('bci', ROOT / 'tools/build_cluster_installer.py')
    bci = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bci)
    selftest = bci.selftest_bytes()
    entries[prefix + 'selftest.bin'] = selftest
    img_ver = (ROOT / 'analysis/app/files/img_ver.txt').read_bytes()
    entries[prefix + 'probe-expected.txt'] = (f'selftest {len(selftest)} {zlib.crc32(selftest) & 0xffffffff:08x}\n'
                                              f'img_ver {len(img_ver)} {zlib.crc32(img_ver) & 0xffffffff:08x}\n').encode()
    entries['capture-reference.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(entries.items()):
            item = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            item.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(item, data)
    report = {'artifact': str(output.relative_to(ROOT)), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
              'entries': sorted(entries), 'capture_bytes': sum(v['size'] for v in files.values()),
              'vehicle_tested': False, 'contains_loader': False, 'contains_installable_port': False}
    (evidence / 'sd-build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    build()
