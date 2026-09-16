#!/usr/bin/env python3
"""Build the experimental port against P2873, without executing firmware code."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    os.chdir(ROOT)
    java = sorted(Path('build-tools').glob('*/Contents/Home/bin/java'))
    if len(java) != 1:
        raise SystemExit('Expected one local Java runtime under build-tools')
    compiler = Path('build-tools/ecj-4.6.1.jar')
    downloaded = json.loads(Path('evidence/build/toolchain-downloads.json').read_text())
    if sha(compiler) != downloaded['ecj']['sha256']:
        raise SystemExit('Compiler differs from recorded download')
    jars = sorted(Path('analysis/app/files').rglob('*.jar')) + sorted(Path('analysis/stage2-extracted').rglob('*.jar'))
    sources = sorted(Path('port/java').rglob('*.java'))
    if len(sources) != 7:
        raise SystemExit('Unexpected source selection')
    output = Path('build/java/classes')
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    artifact = Path('build/java/ClusterIntegration-Audi-P2873-experimental.jar')
    artifact.unlink(missing_ok=True)
    command = [str(java[0]), '-jar', str(compiler), '-source', '1.4', '-target', '1.4',
               '-encoding', 'UTF-8', '-proc:none', '-warn:none', '-bootclasspath',
               'analysis/app/files/eso/hmi/lsd/lsd.jar', '-classpath', os.pathsep.join(map(str, jars)),
               '-d', str(output), *map(str, sources)]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    evidence = Path('evidence/build')
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'java-compile.log').write_text(result.stdout)
    if result.returncode:
        raise SystemExit(result.stdout)
    classes = sorted(output.rglob('*.class'))
    versions = {struct.unpack('>H', p.read_bytes()[6:8])[0] for p in classes}
    if versions != {48}:
        raise SystemExit('Wrong bytecode version: ' + repr(versions))
    # Fixed timestamps, order and permissions make this artifact reproducible.
    with zipfile.ZipFile(artifact, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        entries = [('META-INF/MANIFEST.MF', b'Manifest-Version: 1.0\r\nImplementation-Title: Audi P2873 experimental port\r\n\r\n')]
        entries += [(p.relative_to(output).as_posix(), p.read_bytes()) for p in classes]
        entries += [('LICENSE.md', Path('vendor/mh2p-cluster/LICENSE.md').read_bytes()),
                    ('NOTICE.md', Path('port/NOTICE.md').read_bytes())]
        for name, data in entries:
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    patch = []
    for p in sources:
        rel = p.relative_to('port/java')
        original = Path('vendor/mh2p-cluster/lsd') / rel
        patch.extend(difflib.unified_diff(original.read_text().splitlines(True), p.read_text().splitlines(True),
                                        fromfile='upstream/' + str(rel), tofile='port/' + str(rel)))
    (evidence / 'java-port.patch').write_text(''.join(patch))
    report = {'status': 'compiled; not approved for vehicle installation', 'source_count': len(sources),
              'class_count': len(classes), 'class_major_versions': sorted(versions),
              'artifact': str(artifact), 'sha256': sha(artifact), 'command': command,
              'inputs': {str(p): sha(p) for p in sources + jars + [compiler]},
              'excluded_upstream_classes': ['ClusterAAMirror', 'ClusterMapController', 'AndroidAutoClusterActivator'],
              'limitations': ['Reflection and native ABI are not checked by compilation.',
                              'Display routing and map restoration need vehicle validation.',
                              'No QNX native binaries are built or included.']}
    (evidence / 'java-build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['status', 'source_count', 'class_count', 'sha256']}, indent=2))


if __name__ == '__main__':
    main()
