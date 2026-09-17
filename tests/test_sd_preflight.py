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
import zlib

ROOT = Path(__file__).resolve().parents[1]
KSH = os.environ.get('AUDI_TEST_KSH', '/bin/ksh')


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier = load('verify_capture')
probe_verifier = load('verify_probe')
PROBE_ENTRIES = ['collect.sh', 'install.sh', 'uninstall.sh', 'targets.txt', 'probe.sh', 'common.sh',
                 'selftest.bin', 'probe-expected.txt']


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
        self.manifest = {'allowed_releases': ['MH2p_ER_AU_P2873', 'MH2p_ER_AUG35_P2873', 'MH2p_ER_AUG35S_P2873'],
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

    def test_adapter_does_not_gate_the_capture_on_release(self):
        # Card 1 showed the release gate blocked a legitimate read-only capture (the unit reported
        # MH2p_ER_AU_P2873, not AUG35). The adapter must run the collector regardless of release;
        # the collector records the release for the host verifier to judge.
        text = (ROOT / 'port/sd/install.sh').read_text()
        self.assertIn('collect.sh', text)
        # No release `case` may sit between the shebang and the collect invocation.
        before_collect = text.split('collect.sh')[0]
        self.assertNotIn('exit 2', before_collect)
        self.assertNotIn('capture skipped', text)

    def test_collector_records_an_unexpected_release(self):
        r = subprocess.run(['sh', str(self.script / 'collect.sh'), str(self.output), str(self.unit)],
                           env={**os.environ, 'RELEASE_VERSION': 'MH2p_ER_AU_P2873'}, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.output / 'release.txt').read_text().strip(), 'MH2p_ER_AU_P2873')
        self.assertEqual(self.source.read_bytes(), b'original unit bytes')  # read-only

    def test_card_scripts_call_no_tool_missing_from_the_update_mode_path(self):
        # Update mode has PATH=.:/proc/boot:/bin:/usr/bin:/usr/sbin:/sbin; dirname, basename and sed
        # exist only on the app partition. A missing command under set -e aborts the script.
        import re
        call = re.compile(r'\$\(\s*(CDPATH= )?(dirname|basename)\b|(^|[;&|(]\s*)(printf|sed|dirname|basename)\s')
        for name in ['collect.sh', 'install.sh', 'uninstall.sh', 'failsafe-heartbeat.sh', 'probe.sh']:
            code = [l for l in (ROOT / 'port/sd' / name).read_text().splitlines() if not l.lstrip().startswith('#')]
            self.assertFalse([l for l in code if call.search(l)], name)

    def test_collector_needs_only_boot_image_tools(self):
        boot = self.root / 'boot-bin'
        boot.mkdir()
        for t in ['mkdir', 'cp', 'ls', 'uname']:
            (boot / t).symlink_to(shutil.which(t))
        r = subprocess.run([KSH, str(self.script / 'collect.sh'), str(self.output), str(self.unit)],
                           env={'PATH': str(boot), 'RELEASE_VERSION': 'MH2p_ER_AUG35_P2873'}, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(verifier.verify(self.output, self.manifest)['baseline_match'])

    def test_collector_works_under_ksh(self):
        r = subprocess.run([KSH, str(self.script / 'collect.sh'), str(self.output), str(self.unit)],
                           env={**os.environ, 'RELEASE_VERSION': 'MH2p_ER_AU_P2873'}, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(verifier.verify(self.output, self.manifest)['baseline_match'])

    def test_live_mode_refuses_internal_destination(self):
        result = subprocess.run(['sh', str(self.script / 'collect.sh'), str(self.output)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_package_has_no_activation_payload(self):
        if not (ROOT / 'dist/Audi-P2873-preflight-addon.zip').exists():
            self.skipTest('requires the locally built addon ZIP (not in the repository)')
        with zipfile.ZipFile(ROOT / 'dist/Audi-P2873-preflight-addon.zip') as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(set(z.namelist()), {'README.md', 'capture-reference.json', 'failsafe.sh',
                *['Mods/AudiP2873Preflight/Update/' + n for n in PROBE_ENTRIES]})
            self.assertEqual(z.read('Mods/AudiP2873Preflight/Update/collect.sh'), (ROOT / 'port/sd/collect.sh').read_bytes())


class ProbeTests(unittest.TestCase):
    """Run the probe against a fake unit with an hd shim; the verifier must accept it."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        app = self.root / 'mnt/app'
        (app / 'eso/bin/apps').mkdir(parents=True)
        (app / 'img_ver.txt').write_bytes(b'IMG 1.0\n')
        (app / 'eso/bin/apps/gal').write_bytes(b'\x7fELF gal')
        (app / 'eso/bin/apps/dio_manager').write_bytes(b'\x7fELF dio')
        (app / 'eso/bin/servicemgrmibhigh').write_bytes(b'#!/bin/sh\n')
        (app / 'eso/bin/servicemgrmibhigh0').write_bytes(b'\x7fELF svc')
        (self.root / 'mnt/ota/modkit').mkdir(parents=True)
        (self.root / 'mnt/ota/modkit/modkit_persist.sh').write_bytes(b'#!/bin/ksh\n')
        self.mod = self.root / 'Mods/AudiP2873Preflight/Update'
        self.mod.mkdir(parents=True)
        shutil.copy(ROOT / 'port/sd/probe.sh', self.mod)
        shutil.copy(ROOT / 'port/installer/Update/common.sh', self.mod)
        selftest = load('build_cluster_installer').selftest_bytes()
        (self.mod / 'selftest.bin').write_bytes(selftest)
        img = (app / 'img_ver.txt').read_bytes()
        (self.mod / 'probe-expected.txt').write_text(
            f'selftest {len(selftest)} {zlib.crc32(selftest) & 0xffffffff:08x}\nimg_ver {len(img)} {zlib.crc32(img) & 0xffffffff:08x}\n')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        (self.bin / 'hd').write_text('#!/bin/sh\nexec hexdump -C "$@"\n')
        (self.bin / 'hd').chmod(0o755)
        self.out = self.root / 'AudiP2873-probe'

    def probe(self):
        env = {**os.environ, 'PATH': f"{self.bin}:{os.environ['PATH']}", 'AUDI_CLUSTER_FIXTURE_ROOT': str(self.root),
               'MEDIA_PATH': str(self.root), 'RELEASE_VERSION': 'MH2p_ER_AUG35S_P2873'}
        return subprocess.run([KSH, str(self.mod / 'probe.sh'), str(self.out)], env=env, capture_output=True, text=True)

    def test_probe_is_read_only_and_verifier_accepts_a_conforming_unit(self):
        before = {p: p.read_bytes() for p in (self.root / 'mnt').rglob('*') if p.is_file()}
        r = self.probe()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual({p: p.read_bytes() for p in (self.root / 'mnt').rglob('*') if p.is_file()}, before)
        v = probe_verifier.verify(self.out)
        self.assertTrue(v['complete'])
        self.assertTrue(v['hd_format_ok'], v)
        self.assertTrue(v['crc_pipeline_ok'], v)
        self.assertTrue(v['df_format_ok'], v)
        self.assertTrue(v['dir_is_empty_ok'], v)
        self.assertIn('servicemgrmibhigh=not-elf', v['modkit_chain'])
        self.assertIn('modkit_persist=present', v['modkit_chain'])
        self.assertFalse(v['installation_approved'])

    def test_verifier_rejects_wrong_hd_format_and_missing_tool(self):
        self.assertEqual(self.probe().returncode, 0)
        (self.out / 'hd-first8.txt').write_text('0000000 1f8b 0800 0000 0000\n')  # od-style 16-bit words
        v = probe_verifier.verify(self.out)
        self.assertFalse(v['hd_format_ok'])
        self.assertFalse(v['assumptions_hold'])
        (self.out / 'tools.txt').write_text('gzip MISSING\n')
        self.assertIn('gzip', probe_verifier.verify(self.out)['tools_missing'])

    def test_heartbeat_failsafe_only_appends_to_the_card(self):
        card = self.root / 'card'
        card.mkdir()
        shutil.copy(ROOT / 'port/sd/failsafe-heartbeat.sh', card / 'failsafe.sh')
        before = {p: p.read_bytes() for p in (self.root / 'mnt').rglob('*') if p.is_file()}
        env = {**os.environ, 'AUDI_HEARTBEAT_TEST_DIR': str(card.resolve())}
        elsewhere = subprocess.run([KSH, str(card / 'failsafe.sh')], capture_output=True)  # not a media root
        self.assertEqual(elsewhere.returncode, 0)
        self.assertEqual(sorted(p.name for p in card.iterdir()), ['failsafe.sh'])
        for _ in range(2):
            self.assertEqual(subprocess.run([KSH, str(card / 'failsafe.sh')], capture_output=True, env=env).returncode, 0)
        self.assertEqual(sorted(p.name for p in card.iterdir()), ['AudiP2873-failsafe-heartbeat.txt', 'failsafe.sh'])
        self.assertEqual(len((card / 'AudiP2873-failsafe-heartbeat.txt').read_text().splitlines()), 2)
        self.assertEqual({p: p.read_bytes() for p in (self.root / 'mnt').rglob('*') if p.is_file()}, before)
        probe_dir = card / 'AudiP2873-probe'
        probe_dir.mkdir()
        self.assertEqual(len(probe_verifier.verify(probe_dir)['failsafe_heartbeats']), 2)

    def test_probe_records_received_path_and_runs_from_a_bare_filename(self):
        env = {**os.environ, 'PATH': f"{self.bin}:{os.environ['PATH']}", 'AUDI_CLUSTER_FIXTURE_ROOT': str(self.root),
               'MEDIA_PATH': str(self.root), 'RELEASE_VERSION': 'MH2p_ER_AUG35S_P2873'}
        r = subprocess.run([KSH, 'probe.sh', str(self.out)], cwd=self.mod, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        received = (self.out / 'path-received.txt').read_text()
        self.assertIn(f'PATH_RECEIVED={self.bin}:', received)
        self.assertNotIn('/mnt/app/armle', received)          # recorded before the append
        self.assertIn('/mnt/app/armle/usr/bin', (self.out / 'env.txt').read_text())
        self.assertTrue((self.out / 'tools-before.txt').is_file())
        v = probe_verifier.verify(self.out)
        self.assertTrue(v['path_received'])
        self.assertIsInstance(v['unreachable_before_path_append'], list)

    BOOT_IMAGE_TOOLS = ['mkdir', 'cp', 'ls', 'uname', 'date', 'cat', 'head', 'dd', 'df', 'rm', 'mount', 'sh']

    def update_mode_path(self):
        """PATH as in software-update mode: boot-image tools only. App-partition tools sit under the fake unit."""
        boot = self.root / 'boot-bin'
        boot.mkdir()
        for t in self.BOOT_IMAGE_TOOLS:
            (boot / t).symlink_to(shutil.which(t))
        for rel, tools in [('mnt/app/armle/bin', ['gzip', 'awk', 'sed']), ('mnt/app/armle/usr/bin', ['wc'])]:
            d = self.root / rel
            d.mkdir(parents=True, exist_ok=True)
            for t in tools:
                (d / t).symlink_to(shutil.which(t))
        shutil.copy(self.bin / 'hd', self.root / 'mnt/app/armle/usr/bin/hd')
        (self.root / 'mnt/app/armle/usr/bin/hd').write_text('#!/bin/sh\nexec /usr/bin/hexdump -C "$@"\n')
        return str(boot)

    def test_probe_completes_with_the_update_mode_path(self):
        env = {'PATH': self.update_mode_path(), 'AUDI_CLUSTER_FIXTURE_ROOT': str(self.root),
               'MEDIA_PATH': str(self.root), 'RELEASE_VERSION': 'MH2p_ER_AUG35S_P2873'}
        r = subprocess.run([KSH, str(self.mod / 'probe.sh'), str(self.out)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        v = probe_verifier.verify(self.out)
        self.assertTrue(v['complete'])
        self.assertTrue(v['hd_format_ok'], v)
        self.assertTrue(v['crc_pipeline_ok'], v)
        self.assertTrue(v['free_space_ok'], v)
        for tool in ['gzip', 'hd', 'wc', 'awk', 'sed']:
            self.assertIn(tool, v['unreachable_before_path_append'])
        after = dict(l.split(' ', 1) for l in (self.out / 'tools.txt').read_text().splitlines())
        for tool in ['gzip', 'hd', 'wc', 'awk', 'sed']:
            self.assertNotEqual(after[tool], 'MISSING', tool)

    def test_probe_refuses_overwrite(self):
        self.out.mkdir()
        self.assertNotEqual(self.probe().returncode, 0)
        self.assertFalse((self.out / 'COMPLETE').exists())


if __name__ == '__main__':
    unittest.main()
