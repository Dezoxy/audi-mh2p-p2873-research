#!/usr/bin/env python3
"""Audit upstream prebuilt imports within each host's declared dependency graph.
No ELF is executed; missing extracted libraries remain explicit unknowns.
"""
import hashlib
import io
import json
from pathlib import Path
import zipfile
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]


def inspect(data):
    elf = ELFFile(io.BytesIO(data))
    dynamic = next((s for s in elf.iter_segments() if s['p_type'] == 'PT_DYNAMIC'), None)
    symbols = elf.get_section_by_name('.dynsym')
    if symbols is None and dynamic is not None and list(dynamic._iter_tags('DT_SYMTAB')):
        symbols = dynamic
    exports, required, weak = set(), set(), set()
    if symbols is not None:
        for s in symbols.iter_symbols():
            if not s.name:
                continue
            if s['st_shndx'] == 'SHN_UNDEF':
                (weak if s['st_info']['bind'] == 'STB_WEAK' else required).add(s.name)
            elif s['st_info']['bind'] in ('STB_GLOBAL', 'STB_WEAK') and s['st_other']['visibility'] in ('STV_DEFAULT', 'STV_PROTECTED'):
                exports.add(s.name)
    return {'machine': elf['e_machine'], 'bits': elf.elfclass, 'little_endian': elf.little_endian, 'elf_flags': elf['e_flags'],
            'needed': [t.needed for t in dynamic.iter_tags('DT_NEEDED')] if dynamic else [],
            'sonames': [t.soname for t in dynamic.iter_tags('DT_SONAME')] if dynamic else [],
            'exports': exports, 'required': required, 'weak': weak}


def main():
    index, objects, errors = {}, {}, []
    roots = [ROOT / 'analysis/stage1-runtime/files', ROOT / 'analysis/app/files', ROOT / 'analysis/native-deps/files', ROOT / 'analysis/native-deps-nme/files', *sorted((ROOT / 'analysis/stage2-extracted').glob('image-*/files'))]
    for base in roots:
        for path in sorted(base.rglob('*')):
            if not path.is_file():
                continue
            with path.open('rb') as f:
                if f.read(4) != b'\x7fELF':
                    continue
            key = str(path.relative_to(ROOT))
            try:
                obj = inspect(path.read_bytes())
            except Exception as exc:
                errors.append({'path': key, 'error': str(exc)})
                continue
            objects[key] = obj
            for name in set([path.name, *obj['sonames']]):
                index.setdefault(name, []).append(key)
    archive = ROOT / 'vendor/mh2p-cluster/builds/ClusterIntegration_v0034_beta2_candidate_90d0b76.zip'
    rows = []
    hosts = {'cluster': None, 'gal_cluster.so': 'gal', 'dio_cluster.so': 'dio_manager'}
    with zipfile.ZipFile(archive) as z:
        for name, host in hosts.items():
            entry = next(n for n in z.namelist() if n.replace('\\', '/').endswith('/' + name))
            data = z.read(entry)
            payload = inspect(data)
            pending = list(payload['needed'])
            providers = set(payload['exports'])
            visited, missing, ambiguous = set(), set(), {}
            host_key = 'analysis/app/files/eso/bin/apps/' + host if host else None
            if host_key:
                h = objects[host_key]
                pending.extend(h['needed'])
                providers.update(h['exports'])
            while pending:
                library = pending.pop()
                if library in visited:
                    continue
                visited.add(library)
                matches = index.get(library, [])
                if not matches:
                    missing.add(library)
                    continue
                if len(matches) > 1:
                    ambiguous[library] = matches
                    # Do not union mutually exclusive providers into a false pass.
                    continue
                obj = objects[matches[0]]
                providers.update(obj['exports'])
                pending.extend(obj['needed'])
            unresolved = sorted(payload['required'] - providers)
            rows.append({'payload': name, 'host': host, 'sha256': hashlib.sha256(data).hexdigest(),
                         'machine': payload['machine'], 'bits': payload['bits'], 'little_endian': payload['little_endian'], 'elf_flags': payload['elf_flags'],
                         'direct_needed': payload['needed'], 'strong_import_count': len(payload['required']),
                         'matched_strong_import_count': len(payload['required']) - len(unresolved),
                         'unresolved_strong_imports': unresolved, 'optional_weak_imports': sorted(payload['weak']),
                         'missing_dependency_images': sorted(missing), 'ambiguous_providers': ambiguous,
                         'dependency_graph_complete': not missing and not ambiguous,
                         'reuse_approved': False})
    report = {'archive': str(archive.relative_to(ROOT)), 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
              'scope': 'DT_NEEDED graph and strong symbol names, not actual loader search order, symbol versions or ABI',
              'firmware_elf_parse_errors': errors, 'payloads': rows,
              'note': 'Missing extracted dependencies are unknowns, not proof that libraries are absent on the unit.'}
    out = ROOT / 'evidence/build/native-payload-audit.json'
    out.write_text(json.dumps(report, indent=2) + '\n')
    for row in rows:
        print(row['payload'], str(row['matched_strong_import_count']) + '/' + str(row['strong_import_count']),
              'imports matched;', 'missing images:', ', '.join(row['missing_dependency_images']),
              '; ambiguous:', ', '.join(row['ambiguous_providers']))


if __name__ == '__main__':
    main()
