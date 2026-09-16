import importlib.util
from pathlib import Path
import struct
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from extract_stage1_runtime import decode, TARGETS


FIRMWARE = ROOT / '4K0906961AB_MH2p_ER_AUG35_P2873/Data'

@unittest.skipUnless(FIRMWARE.exists(), 'requires the locally supplied firmware package (not in the repository)')
class Stage1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = next((ROOT / '4K0906961AB_MH2p_ER_AUG35_P2873/Data').glob('MMX2P.mifs-stage1*/**/loadimg.img'))
        cls.data = cls.path.read_bytes()

    def test_four_core_libraries_and_checksum(self):
        files, report = decode(self.data)
        self.assertEqual(set(files), TARGETS)
        self.assertEqual(report['image_checksum'], 'pass')
        self.assertTrue(all(data.startswith(b'\x7fELF') for data in files.values()))

    def test_truncated_payload_rejected(self):
        with self.assertRaises(ValueError):
            decode(self.data[:4096])

    def test_corrupt_compressed_data_rejected(self):
        bad = bytearray(self.data)
        bad[3000] ^= 0xff
        with self.assertRaises((ValueError, zlib.error)):
            decode(bytes(bad))

    def test_bad_inner_checksum_rejected_even_with_valid_zlib(self):
        raw = bytearray(zlib.decompress(self.data[2048:]))
        raw[-8] ^= 1
        compressed = zlib.compress(raw)
        header = bytearray(self.data[:2048])
        struct.pack_into('<I', header, 8, len(compressed))
        with self.assertRaisesRegex(ValueError, 'checksum'):
            decode(bytes(header) + compressed)


if __name__ == '__main__':
    unittest.main()
