#!/usr/bin/env python3
"""Check public/protected API retention for replaced top-level firmware classes.

This is a structural check; it does not establish behavioral compatibility.
"""
import io
import json
from pathlib import Path
import zipfile
from jawa.cf import ClassFile

ROOT = Path(__file__).resolve().parents[1]


def members(table):
    return {(m.name.value, m.descriptor.value, m.access_flags.acc_static,
             m.access_flags.acc_public, m.access_flags.acc_protected)
            for m in table if m.access_flags.acc_public or m.access_flags.acc_protected}


def main():
    rows = []
    with zipfile.ZipFile(ROOT / 'analysis/app/files/eso/hmi/lsd/lsd.jar') as firmware, \
            zipfile.ZipFile(ROOT / 'build/java/ClusterIntegration-Audi-P2873-experimental.jar') as port:
        names = set(firmware.namelist())
        for name in port.namelist():
            if not name.endswith('.class') or '$' in name or name not in names:
                continue
            old = ClassFile(io.BytesIO(firmware.read(name)))
            new = ClassFile(io.BytesIO(port.read(name)))
            old_interfaces = {i.name.value for i in old.interfaces}
            new_interfaces = {i.name.value for i in new.interfaces}
            rows.append({'class': name, 'firmware_method_count': len(members(old.methods)),
                         'missing_methods': sorted(members(old.methods) - members(new.methods)),
                         'missing_fields': sorted(members(old.fields) - members(new.fields)),
                         'missing_interfaces': sorted(old_interfaces - new_interfaces),
                         'superclass_unchanged': old.super_.name.value == new.super_.name.value})
    passed = len(rows) == 3 and all(not r['missing_methods'] and not r['missing_fields'] and
                                    not r['missing_interfaces'] and r['superclass_unchanged'] for r in rows)
    report = {'passed': passed, 'scope': 'Public/protected members, superclass and direct interfaces of three replaced top-level classes',
              'classes': rows, 'runtime_compatibility_proven': False}
    (ROOT / 'evidence/build/java-api-check.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
