#!/usr/bin/env python3
"""Locate explicit upstream Java imports in the extracted JARs or local source.
This is a class-name check, not compilation or complete method-linkage checking.
"""
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

root=Path(__file__).resolve().parents[1]
classes=set()
jars=list((root/'analysis/app/files').rglob('*.jar'))+list((root/'analysis/stage2-extracted').rglob('*.jar'))
for path in jars:
    with zipfile.ZipFile(path) as archive:
        classes.update(name[:-6].replace('/','.') for name in archive.namelist() if name.endswith('.class'))
sources=list((root/'vendor/mh2p-cluster/lsd').rglob('*.java'))
local=set()
for path in sources:
    match=re.search(r'\bpackage\s+([\w.]+)\s*;',path.read_text())
    if match:local.add(match[1]+'.'+path.stem)
rows=[]
for path in sources:
    for name in re.findall(r'^\s*import\s+([\w.*]+)\s*;',path.read_text(),re.M):
        status='source' if name in local else 'firmware_jar' if name in classes else 'jdk_or_wildcard_not_checked' if name.startswith(('java.','javax.')) or name.endswith('.*') else 'not_found'
        rows.append({'source':str(path.relative_to(root)),'import':name,'status':status})
(root/'evidence/phase2/java-import-checks.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps({'sources':len(sources),'counts':dict(Counter(r['status'] for r in rows)), 'missing':[r for r in rows if r['status']=='not_found']},indent=2))
