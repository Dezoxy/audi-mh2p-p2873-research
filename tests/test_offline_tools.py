"""Regression checks for data loss, unsafe extraction, and false compatibility gaps."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from extract_stage2 import decode_container, parse_image
from elftools.elf.elffile import ELFFile

STAGE2 = ROOT/'analysis/restore/files/img_restore/main_stage2.ifs.lzo'

@unittest.skipUnless(STAGE2.exists(), 'requires locally extracted firmware (not in the repository)')
class Stage2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container=(ROOT/'analysis/restore/files/img_restore/main_stage2.ifs.lzo').read_bytes()
        cls.images,cls.blocks=decode_container(cls.container)

    def test_full_container_has_six_valid_images(self):
        self.assertEqual(len(self.blocks),86)
        self.assertEqual(len(self.images),6)
        entries=[r for image in self.images for r in parse_image(image)]
        self.assertEqual(len(entries),773)
        self.assertIn('lib/libnvmedia.so',{r['path'] for r in entries})

    def test_symlink_targets_preserve_first_character(self):
        entries=parse_image(self.images[3])
        links={r['path']:r['target'] for r in entries if r['kind']=='symlink'}
        self.assertEqual(links['usr/lib/libscreen.so'],'libscreen.so.1')
        self.assertEqual(links['lib/graphics.conf'],'/etc/graphics.conf')

    def test_flash_prefix_is_rejected_as_incomplete(self):
        with self.assertRaisesRegex(ValueError,'Truncated'):
            decode_container(self.container[:32505856])

    def test_corrupt_image_is_rejected(self):
        damaged=bytearray(self.images[0]);damaged[-8]^=1
        with self.assertRaisesRegex(ValueError,'checksum'):
            parse_image(damaged)

    def test_traversal_is_rejected_even_with_valid_checksum(self):
        damaged=bytearray(self.images[0])
        index=damaged.index(b'lib/libsbgse56.so.0')
        damaged[index:index+3]=b'../'
        struct.pack_into('<I',damaged,len(damaged)-4,0)
        checksum=(-sum(x[0] for x in struct.iter_unpack('<I',damaged)))&0xffffffff
        struct.pack_into('<I',damaged,len(damaged)-4,checksum)
        with self.assertRaisesRegex(ValueError,'Unsafe'):
            parse_image(damaged)

    def test_stripped_graphics_library_exports_are_readable(self):
        path=ROOT/'analysis/stage2-extracted/image-03/files/lib/libnvmedia.so'
        with path.open('rb') as f:
            elf=ELFFile(f)
            self.assertIsNone(elf.get_section_by_name('.dynsym'))
            segment=next(s for s in elf.iter_segments() if s['p_type']=='PT_DYNAMIC')
            defined={s.name for s in segment.iter_symbols() if s['st_shndx']!='SHN_UNDEF'}
            self.assertIn('NvMediaVideoDecoderCreateEx',defined)

class InstallerTests(unittest.TestCase):
    def test_nested_records_and_failure_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);package=base/'package';package.mkdir()
            content=b'firmware fixture';(package/'payload').write_bytes(content)
            record={'Source':'payload','CheckSumSize':512,'FileSize':len(content),'CheckSum':[hashlib.sha1(content).hexdigest()]}
            (package/'primary_installer.txt').write_text(json.dumps({'wrapper':[record]}))
            cmd=[sys.executable,str(ROOT/'tools/audit_firmware.py'),str(package),str(base/'output')]
            result=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            checks=json.loads((base/'output/installer-checks.json').read_text())
            self.assertEqual(len(checks),1);self.assertEqual(checks[0]['record'],'$/wrapper/0')
            (package/'payload').write_bytes(content+b'corrupt')
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)

if __name__=='__main__':unittest.main()
