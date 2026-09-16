"""Exercise the shipped collector in an isolated fake unit; never use live paths."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify_capture', ROOT / 'tools/verify_capture.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.unit = self.root / 'unit'
        self.script = self.root / 'addon'
        self.script.mkdir()
        shutil.copy(ROOT / 'port/sd/collect.sh', self.script)
        self.target = '/mnt/app/eso/bin/apps/gal'
        (self.script / 'targets.txt').write_text(self.target + '\n')
        self.source = self.unit / self.target.lstrip('/')
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b'original unit bytes')
        self.manifest = {'allowed_releases': ['MH2p_ER_AUG35_P2873', 'MH2p_ER_AUG35S_P2873'],
                         'files': {self.target: {'sha256': hashlib.sha256(self.source.read_bytes()).hexdigest(),
                                                'size': self.source.stat().st_size}}}
        self.output = self.root / 'capture'

    def collect(self, release='MH2p_ER_AUG35_P2873'):
        return subprocess.run(['sh', str(self.script / 'collect.sh'), str(self.output), str(self.unit)],
                              env={**os.environ, 'RELEASE_VERSION': release}, capture_output=True, text=True)

    def test_capture_is_read_only_and_accepts_both_labels(self):
        before = self.source.read_bytes()
        self.assertEqual(self.collect('MH2p_ER_AUG35S_P2873').returncode, 0)
        result = verifier.verify(self.output, self.manifest)
        self.assertTrue(result['baseline_match'])
        self.assertFalse(result['installation_approved'])
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(list(self.unit.rglob('*'))[-1].read_bytes(), before)

    def test_refuses_overwrite(self):
        self.assertEqual(self.collect().returncode, 0)
        (self.output / 'sentinel').write_text('retain')
        self.assertNotEqual(self.collect().returncode, 0)
        self.assertEqual((self.output / 'sentinel').read_text(), 'retain')

    def test_missing_source_has_no_completion_marker(self):
        self.source.unlink()
        self.assertNotEqual(self.collect().returncode, 0)
        self.assertFalse((self.output / 'COMPLETE').exists())
        self.assertFalse(verifier.verify(self.output, self.manifest)['baseline_match'])

    def test_tampering_is_detected(self):
        self.assertEqual(self.collect().returncode, 0)
        (self.output / 'files' / self.target.lstrip('/')).write_bytes(b'changed')
        self.assertFalse(verifier.verify(self.output, self.manifest)['baseline_match'])

    def test_unknown_release_is_not_accepted(self):
        self.assertEqual(self.collect('UNKNOWN').returncode, 0)
        self.assertFalse(verifier.verify(self.output, self.manifest)['baseline_match'])

    def test_symlink_is_not_a_valid_backup(self):
        self.assertEqual(self.collect().returncode, 0)
        copy = self.output / 'files' / self.target.lstrip('/')
        copy.unlink()
        copy.symlink_to(self.source)
        self.assertFalse(verifier.verify(self.output, self.manifest)['baseline_match'])

    def test_adapter_rejects_wrong_release_before_writes(self):
        result = subprocess.run(['sh', str(ROOT / 'port/sd/install.sh')],
                                env={**os.environ, 'MOD_PATH': str(self.script), 'MEDIA_PATH': str(self.root),
                                     'RELEASE_VERSION': 'MH2p_US_PO416_P2870'}, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'AudiP2873-capture').exists())

    def test_live_mode_refuses_internal_destination(self):
        result = subprocess.run(['sh', str(self.script / 'collect.sh'), str(self.output)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_package_has_no_activation_payload(self):
        if not (ROOT / 'dist/Audi-P2873-preflight-addon.zip').exists():
            self.skipTest('requires the locally built addon ZIP (not in the repository)')
        with zipfile.ZipFile(ROOT / 'dist/Audi-P2873-preflight-addon.zip') as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(set(z.namelist()), {'README.md', 'capture-reference.json',
                *['Mods/AudiP2873Preflight/Update/' + n for n in ['collect.sh', 'install.sh', 'uninstall.sh', 'targets.txt']]})
            self.assertEqual(z.read('Mods/AudiP2873Preflight/Update/collect.sh'), (ROOT / 'port/sd/collect.sh').read_bytes())


if __name__ == '__main__':
    unittest.main()
