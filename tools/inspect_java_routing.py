#!/usr/bin/env python3
"""Disassemble selected Audi routing classes without a JVM or bytecode execution."""
import io
import json
import struct
import zipfile
from pathlib import Path
from jawa.cf import ClassFile

root=Path(__file__).resolve().parents[1]
classes=[
 'org/dsi/ifc/displaymanagement/Constants',
 'de/audi/atip/hmi/view/IDisplayManager',
 'de/audi/tghu/navi/app/cluster/MapClusterService',
 'de/audi/tghu/navi/app/util/UtilFrameworkAccess',
 'de/audi/tghu/navi/app/map/AbstractMap',
]
def constant(c):
    if hasattr(c,'class_') and hasattr(c,'name_and_type'):
        return c.class_.name.value+'.'+c.name_and_type.name.value+c.name_and_type.descriptor.value
    if hasattr(c,'string'):return c.string.value
    if hasattr(c,'name'):return c.name.value
    if hasattr(c,'value'):return c.value
    return str(c)
rows=[]
with zipfile.ZipFile(root/'analysis/app/files/eso/hmi/lsd/lsd.jar') as z:
    for name in classes:
        c=ClassFile(io.BytesIO(z.read(name+'.class')))
        fields=[]
        for f in c.fields:
            # Read ConstantValue's u2 directly: Jawa 2.2.0's lazy constructor
            # passes name_index as value for this attribute and raises.
            for ni, blob in f.attributes._table:
                if c.constants[ni].value=='ConstantValue':
                    fields.append({'field':f.name.value,'value':constant(c.constants[struct.unpack('>H',blob)[0]])})
        methods=[]
        if not name.endswith(('Constants','IDisplayManager')):
            for m in c.methods:
                if not m.code:continue
                instructions=[]
                for ins in m.code.disassemble():
                    operands=[]
                    for op in ins.operands:
                        if isinstance(op,dict):operands.append(op)
                        else:operands.append(constant(c.constants[op.value]) if op.op_type.name=='CONSTANT_INDEX' else op.value)
                    instructions.append({'pc':ins.pos,'op':ins.mnemonic,'operands':operands})
                methods.append({'method':m.name.value,'descriptor':m.descriptor.value,'instructions':instructions})
        rows.append({'class':name,'fields':fields,'methods':methods})
(root/'evidence/phase2/java-routing.json').write_text(json.dumps(rows,indent=2)+'\n')
for row in rows:
    for field in row['fields']:
        if any(s in field['field'] for s in ['KOMBI_MAP','DISPLAYID_CLUSTER']):print(row['class'],field)
    for m in row['methods']:
        if m['method'] in ('isClusterMapFPKEntry','notifyViewSizeChanged'):
            print(row['class'],m)
