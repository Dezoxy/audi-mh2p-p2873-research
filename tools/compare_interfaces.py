#!/usr/bin/env python3
"""Static exported-symbol and Java class-signature inventory; never load binaries."""
import io
import argparse
import json
import re
import struct
import zipfile
from pathlib import Path
from elftools.elf.elffile import ELFFile

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--include-stage2', action='store_true')
parser.add_argument('--output', type=Path, default=root / 'evidence')
args = parser.parse_args()
files = root / 'analysis/app/files'
roots = [files]
if args.include_stage2:
    roots.extend(sorted((root / 'analysis/stage2-extracted').glob('image-*/files')))
evidence = args.output
evidence.mkdir(parents=True, exist_ok=True)
exports = {}
elfs = []
for path in sorted(path for base in roots for path in base.rglob('*')):
    if not path.is_file():
        continue
    with path.open('rb') as f:
        if f.read(4) != b'\x7fELF':
            continue
        f.seek(0)
        elf = ELFFile(f)
        base = next(base for base in roots if path.is_relative_to(base))
        name = str(path.relative_to(root / 'analysis'))
        dynamic = next((s for s in elf.iter_segments() if s['p_type'] == 'PT_DYNAMIC'), None)
        try:
            needed = [t.needed for t in dynamic.iter_tags('DT_NEEDED')] if dynamic else []
        except Exception as error:
            elfs.append({'path':name, 'class':elf.elfclass, 'machine':elf['e_machine'], 'error':f'Cannot parse dynamic dependencies: {type(error).__name__}'})
            continue
        symbols = elf.get_section_by_name('.dynsym')
        if symbols is None and dynamic is not None and list(dynamic._iter_tags('DT_SYMTAB')):
            symbols = dynamic
        count = 0
        if symbols:
            try:
                symbol_list = list(symbols.iter_symbols())
            except Exception as error:
                elfs.append({'path':name, 'class':elf.elfclass, 'machine':elf['e_machine'], 'needed':needed, 'error':f'Cannot parse dynamic symbols: {type(error).__name__}: {error}'})
                continue
            for s in symbol_list:
                if s.name and s['st_shndx'] != 'SHN_UNDEF' and s['st_info']['bind'] in ('STB_GLOBAL', 'STB_WEAK') and s['st_other']['visibility'] in ('STV_DEFAULT', 'STV_PROTECTED'):
                    exports.setdefault(s.name, []).append(name)
                    count += 1
        elfs.append({'path': name, 'class':elf.elfclass,'machine':elf['e_machine'], 'flags':elf['e_flags'],'needed':needed,'export_count':count})
checks=[]
for path in (root / 'vendor/mh2p-cluster/src').glob('*.c'):
    if path.name not in ('gal_cluster.c','dio_manager_preload.c','cluster.c'):
        continue
    text=path.read_text()
    for m in re.finditer(r'dlsym\s*\(\s*[^,]+,\s*"([^"\n]+)"\s*\)', text):
        checks.append({'source':path.name, 'line':text[:m.start()].count('\n')+1,'symbol':m[1], 'providers':exports.get(m[1],[])})
(evidence/'elf-inventory.json').write_text(json.dumps(elfs,indent=2)+'\n')
(evidence/'native-symbol-checks.json').write_text(json.dumps(checks,indent=2)+'\n')

# Minimal classfile table reader: descriptors/access flags, without executing bytecode.
def class_api(data):
    f=io.BytesIO(data)
    def read(n):
        b=f.read(n)
        if len(b)!=n:raise ValueError('Truncated class')
        return b
    def u2():return struct.unpack('>H',read(2))[0]
    def u4():return struct.unpack('>I',read(4))[0]
    if read(4)!=b'\xca\xfe\xba\xbe':raise ValueError('Invalid class magic')
    minor,major=u2(),u2()
    cp=[None]*u2(); i=1
    while i<len(cp):
        tag=read(1)[0]
        if tag==1:cp[i]=read(u2()).decode('utf-8',errors='replace')
        elif tag in (3,4):read(4)
        elif tag in (5,6):read(8);i+=1
        elif tag in (7,8,16,19,20):cp[i]=u2()
        elif tag in (9,10,11,12,17,18):read(4)
        elif tag==15:read(3)
        else:raise ValueError(f'Unknown constant tag {tag}')
        i+=1
    access,this,superclass=u2(),u2(),u2()
    read(2*u2())
    def attributes():
        for _ in range(u2()):u2();read(u4())
    def members():
        out=[]
        for _ in range(u2()):
            flags,name,desc=u2(),u2(),u2()
            out.append({'name':cp[name],'descriptor':cp[desc],'access':flags})
            attributes()
        return out
    fields=members();methods=members();attributes()
    if f.read():raise ValueError('Trailing class bytes')
    return {'major':major,'minor':minor,'class':cp[cp[this]],'access':access,'fields':fields,'methods':methods}
classes=[]
jarchecks=[]
for path in sorted(path for base in roots for path in base.rglob('*.jar')):
    with zipfile.ZipFile(path) as z:
        bad=z.testzip()
        jarchecks.append({'path':str(path.relative_to(root / 'analysis')), 'entries':len(z.namelist()), 'bad_crc_entry':bad})
        if bad:raise ValueError(f'JAR CRC failed: {path}: {bad}')
        for name in z.namelist():
            if name.endswith('.class') and re.search(r'IMapClusterService|CombiBAPServiceNavi|CarPlayDSIManager\.class$|AndroidAuto2DSIManager\.class$',name):
                classes.append({'jar':str(path.relative_to(root / 'analysis')), **class_api(z.read(name))})
(evidence/'java-interfaces.json').write_text(json.dumps(classes,indent=2)+'\n')
(evidence/'jar-validation.json').write_text(json.dumps(jarchecks,indent=2)+'\n')
print('ELF parse errors:', [e['path'] for e in elfs if 'error' in e])
print('ELF files:',len(elfs),'Validated JARs:',len(jarchecks),'Java classes:',len(classes))
for source in sorted({c['source'] for c in checks}):
    rows=[c for c in checks if c['source']==source]
    print(source, 'literal lookups found:',sum(bool(c['providers']) for c in rows),'/',len(rows))
    for c in rows:
        if not c['providers']:print(' unresolved:',c['symbol'])
