#!/usr/bin/env python3
"""Plan or build experimental QNX 6.6 ARM payloads; never deploy or run them."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'vendor/mh2p-cluster/src'


def commands(qcc, output):
    framework = SRC / 'mib2q-carplay-rgi/c_hook/framework'
    route = SRC / 'mib2q-carplay-rgi/c_hook/routeguidance'
    common = [qcc, '-Vgcc_ntoarmv7le', '-O2', '-Wall', '-std=gnu99']
    shared = ['-shared', '-fPIC', '-Wl,--no-undefined']
    return {
        'cluster': common + ['-o', str(output / 'cluster'), str(SRC / 'cluster.c'), '-lscreen', '-lEGL', '-lz', '-lc'],
        'gal_cluster.so': common + shared + ['-o', str(output / 'gal_cluster.so'), str(SRC / 'gal_cluster.c'), '-lscreen', '-lc'],
        'dio_cluster.so': common + shared + ['-I' + str(framework), '-I' + str(route), '-o', str(output / 'dio_cluster.so'),
            str(SRC / 'dio_manager_preload.c'), str(route / 'rgd_tlv.c'), str(framework / 'pps_writer.c'),
            str(framework / 'logging.c'), '-lc'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true', help='Compile only with an explicitly configured QNX SDK')
    parser.add_argument('--qcc', default=shutil.which('qcc') or 'qcc')
    args = parser.parse_args()
    evidence = ROOT / 'evidence/build'
    evidence.mkdir(parents=True, exist_ok=True)
    output = ROOT / 'build/native-experimental'
    inputs = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(SRC.rglob('*')) if p.suffix in ('.c', '.h')}
    plan = {'status': 'recipe only; not compiled or validated', 'sdk_available': bool(shutil.which(args.qcc)),
            'commands': commands(args.qcc, output), 'source_sha256': inputs,
            'required_sdk': 'QNX SDP 6.6 ARMv7 little endian with Screen, EGL/GLES2 and zlib headers/libraries',
            'notes': ['No GLESv2 link: renderer resolves GL dynamically.',
                      'CarPlay needs rgd_tlv, pps_writer and logging translation units.',
                      'gal hook explicitly links Screen instead of relying on the host namespace.',
                      'SDK-linked driver SONAMEs require auditing against firmware before packaging.'],
            'installation_approved': False}
    (evidence / 'native-build-plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    if not args.build:
        print('Native build recipe recorded. SDK available: ' + str(plan['sdk_available']))
        return
    if not plan['sdk_available'] or not os.environ.get('QNX_HOST') or not os.environ.get('QNX_TARGET'):
        raise SystemExit('Build blocked: source a licensed QNX 6.6 SDK environment (QNX_HOST, QNX_TARGET, qcc).')
    if output.exists():
        raise SystemExit('Output exists; preserve it and choose a fresh workspace before rebuilding.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='native-stage-', dir=output.parent) as temp:
        stage = Path(temp)
        probe = stage / 'sdk_probe.c'
        probe.write_text('#include <sys/neutrino.h>\n#include <screen/screen.h>\n#include <EGL/egl.h>\n#include <GLES2/gl2.h>\n#include <zlib.h>\n#if !defined(__QNXNTO__) || _NTO_VERSION != 660\n#error QNX_660_required\n#endif\nint probe(void) { return 0; }\n')
        jobs = {'sdk_probe': [args.qcc, '-Vgcc_ntoarmv7le', '-c', str(probe), '-o', str(stage / 'sdk_probe.o')],
                **commands(args.qcc, stage)}
        for name, command in jobs.items():
            result = subprocess.run(command, capture_output=True, text=True)
            (evidence / (name + '.compile.log')).write_text(result.stdout + result.stderr)
            if result.returncode:
                raise SystemExit('Compilation failed at ' + name + '; no payload published.')
        built = {}
        for name in commands(args.qcc, stage):
            path = stage / name
            with path.open('rb') as f:
                elf = ELFFile(f)
                if elf['e_machine'] != 'EM_ARM' or elf.elfclass != 32 or not elf.little_endian:
                    raise SystemExit('Unexpected native ABI; no payload published.')
                dynamic = next(s for s in elf.iter_segments() if s['p_type'] == 'PT_DYNAMIC')
                needed = [t.needed for t in dynamic.iter_tags('DT_NEEDED')]
                if any(n.startswith('libGLESv2') for n in needed):
                    raise SystemExit('Unexpected GLESv2 direct dependency; no payload published.')
            built[name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'needed': needed}
        output.mkdir()
        for name in built:
            shutil.copy2(stage / name, output / name)
        (evidence / 'native-build.json').write_text(json.dumps({'payloads': built, 'installation_approved': False}, indent=2) + '\n')
        print('Experimental native build finished; runtime ABI and packaging validation remain required.')


if __name__ == '__main__':
    main()
