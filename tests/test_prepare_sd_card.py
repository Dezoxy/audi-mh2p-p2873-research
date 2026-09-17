"""Card assembly from pinned submodules; skips when submodules are not checked out."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_sd_card', ROOT / 'tools/prepare_sd_card.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
SUBMODULES_PRESENT = all((ROOT / 'third_party' / n / 'README.md').is_file()
                         for n in ['MH2p_SD_ModKit', 'MH2p_NavCompassIgnore', 'mh2p-ssh-access', 'MH2p_CarPlay_FullScreen'])


@unittest.skipUnless(SUBMODULES_PRESENT, 'requires git submodules (git submodule update --init)')
class CardAssembly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / 'card'

    def test_base_plus_mod_layout_and_manifest(self):
        m = tool.assemble(self.out, 'modkit', ['navcompass'], None, False, False)
        for rel in ['Meta/auto.mnf', 'Data/MMX2P_POSTSCRIPT.script_2021623-0210/0/modkit.sh',
                    'Mods/NavCompassIgnore/Update/install.sh', 'Mods/NavCompassIgnore/Update/NaviCompass.jar',
                    'Mods/NavCompassIgnore/LICENSE.md', 'CARD-MANIFEST.json', 'CARD-README.txt']:
            self.assertTrue((self.out / rel).is_file(), rel)
        self.assertFalse((self.out / '.git').exists())
        self.assertEqual(set(m['submodule_revisions']), {'MH2p_SD_ModKit', 'MH2p_NavCompassIgnore'})
        self.assertEqual(m['submodule_revisions']['MH2p_SD_ModKit'], '82f9452401022a4a5deadbbb4aaa86fdf7ce71fb')
        saved = json.loads((self.out / 'CARD-MANIFEST.json').read_text())
        self.assertEqual(saved['file_count'], len(saved['files']))
        self.assertFalse(saved['vehicle_tested'])

    def test_refuses_conflicts_and_missing_key(self):
        with self.assertRaises(SystemExit):
            tool.assemble(self.out, 'modkit', ['carplay-fullscreen', 'carplay-windowed'], None, False, False)
        with self.assertRaises(SystemExit):
            tool.assemble(self.out, 'modkit', ['ssh-access'], None, False, False)
        with self.assertRaises(SystemExit):
            tool.assemble(self.out, 'q3team', ['gem'], None, False, False)
        self.assertFalse((self.out / 'Mods').exists())

    def test_ssh_key_is_placed_and_validated(self):
        key = Path(self.tmp.name) / 'k.pub'
        key.write_text('not a key\n')
        with self.assertRaises(SystemExit):
            tool.assemble(self.out, 'modkit', ['ssh-access'], key, False, False)
        out2 = Path(self.tmp.name) / 'card2'
        key.write_text('ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeKeyForTests test@example\n')
        tool.assemble(out2, 'modkit', ['ssh-access'], key, False, False)
        self.assertIn('ssh-ed25519', (out2 / 'Mods/mh2p-ssh-access/Update/authorized_keys').read_text())
        self.assertTrue((out2 / 'Mods/mh2p-ssh-access/Persist/install.sh').is_file())

    def test_refuses_dirty_submodule(self):
        stray = ROOT / 'third_party/MH2p_NavCompassIgnore/UNTRACKED-test-file'
        stray.write_text('x')
        try:
            with self.assertRaises(SystemExit):
                tool.assemble(self.out, 'modkit', ['navcompass'], None, False, False)
        finally:
            stray.unlink()
        self.assertFalse((self.out / 'Mods').exists())

    def test_refuses_non_empty_output_and_unpinned_submodule(self):
        self.out.mkdir()
        (self.out / 'stale').write_text('x')
        with self.assertRaises(SystemExit):
            tool.assemble(self.out, 'modkit', [], None, False, False)
        original = tool.checked_out_revision
        tool.checked_out_revision = lambda name: 'deadbeef'
        try:
            with self.assertRaises(SystemExit):
                tool.assemble(Path(self.tmp.name) / 'card3', 'modkit', [], None, False, False)
        finally:
            tool.checked_out_revision = original


if __name__ == '__main__':
    unittest.main()
