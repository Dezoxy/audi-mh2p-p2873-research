"""Fault tests for the journaled cluster installer, run under ksh with a PATH
limited to utilities that exist in the P2873 app image. Never touches /mnt."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
# The unit's ksh is pdksh-derived; CI runs this suite under both ksh93 and mksh.
KSH = os.environ.get('AUDI_TEST_KSH', '/bin/ksh')
spec = importlib.util.spec_from_file_location('build_cluster_installer', ROOT / 'tools/build_cluster_installer.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
# Present on the unit (stage-1/2 images or /mnt/app/armle) and used by the scripts.
UNIT_TOOLS = ['awk', 'sed', 'wc', 'dd', 'cp', 'mv', 'rm', 'mkdir', 'ls',
              'date', 'cat', 'head', 'tail', 'dirname', 'basename', 'gzip', 'df']
SHIMS = {
    'hd': '#!/bin/sh\nexec /usr/bin/hexdump -C "$@"\n',
    'slay': '#!/bin/sh\nexit 0\n',
    'sync': '#!/bin/sh\nexit 0\n',  # host-wide flush is slow on macOS and irrelevant to the fixture
    'df': '#!/bin/sh\nif [ -n "$FAKE_FREE_KB" ]; then echo "fs 1 1 $FAKE_FREE_KB 1% /x"; echo "fs 1 1 $FAKE_FREE_KB 1% /x"; exit 0; fi\nexec /bin/df "$@"\n',
    'chmod': '#!/bin/sh\nfor a in "$@"; do case "$a" in *"$FAIL_CHMOD_MATCH"*) [ -n "$FAIL_CHMOD_MATCH" ] && exit 1;; esac; done\nexec /bin/chmod "$@"\n',
    'cp': '#!/bin/sh\nfor a in "$@"; do case "$a" in *"$FAIL_CP_MATCH"*) [ -n "$FAIL_CP_MATCH" ] && exit 1;; esac; done\nexec /bin/cp "$@"\n',
}
FACTORY = {'img_ver.txt': b'IMG 1.0\n', 'eso/bin/apps/gal': b'\x7fELF gal factory ' * 500,
           'eso/bin/apps/dio_manager': b'\x7fELF dio factory ' * 300}
# gal deliberately differs from the wrapper's 755 so restored permissions are checked.
FACTORY_MODES = {'img_ver.txt': 0o644, 'eso/bin/apps/gal': 0o750, 'eso/bin/apps/dio_manager': 0o755}
NEW_TARGETS = ['eso/bin/apps/cluster/cluster', 'eso/bin/apps/cluster/gal_cluster.so',
               'eso/bin/apps/cluster/dio_cluster.so', 'eso/bin/apps/cluster/cluster_config.json',
               'eso/hmi/lsd/jars/test.jar']
OP_COUNT = 7
WRAP_STEPS = (5, 6)  # the JAR is switched last (step 7)


class InstallerFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.app = self.root / 'mnt/app'
        for rel, data in FACTORY.items():
            p = self.app / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            p.chmod(FACTORY_MODES[rel])
        (self.app / 'eso/hmi/lsd/jars').mkdir(parents=True)
        (self.root / 'mnt/ota/modkit/Mods/AudiClusterIntegration/Persist').mkdir(parents=True)
        self.set_modkit_chain(installed=True)
        self.media = self.root / 'media'
        self.media.mkdir()
        payload = self.root / 'payload'
        payload.mkdir()
        for n in ['cluster', 'gal_cluster.so', 'dio_cluster.so', 'cluster_config.json']:
            (payload / n).write_bytes(f'payload {n}\n'.encode() * 40)
        jar = self.root / 'test.jar'
        jar.write_bytes(b'PK jar bytes' * 100)
        modkit = self.root / 'modkit-files'
        modkit.mkdir()
        (modkit / 'servicemgrmibhigh.sh').write_bytes(self.CHAIN_WRAPPER)
        (modkit / 'modkit_persist.sh').write_bytes(self.CHAIN_PERSIST)
        self.modkit = modkit
        builder.build(payload, self.app, jar, self.media, modkit_dir=modkit)
        self.mod = self.media / 'Mods/AudiClusterIntegration'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for t in UNIT_TOOLS:
            (self.bin / t).symlink_to(shutil.which(t))
        for name, body in SHIMS.items():
            (self.bin / name).unlink(missing_ok=True)
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        self.state = self.app / 'eso/.audi-cluster/state'

    CHAIN_WRAPPER = b'#!/bin/sh\n\n/eso/bin/servicemgrmibhigh0 &\n\nif [[ -e /mnt/ota/modkit/modkit_persist.sh ]]; then\n    /bin/ksh /mnt/ota/modkit/modkit_persist.sh &\nfi\n'
    CHAIN_PERSIST = b'#!/bin/ksh\nfailsafe() { ksh "$1/failsafe.sh"; }\nfailsafe /fs/sdb0\n'

    def set_modkit_chain(self, installed):
        """Model ModKit's persistence chain: wrapper script + factory ELF + persist script."""
        b = self.app / 'eso/bin'
        b.mkdir(parents=True, exist_ok=True)
        persist = self.root / 'mnt/ota/modkit/modkit_persist.sh'
        if installed:
            (b / 'servicemgrmibhigh').write_bytes(self.CHAIN_WRAPPER)
            (b / 'servicemgrmibhigh0').write_bytes(b'\x7fELF factory servicemgr')
            persist.write_bytes(self.CHAIN_PERSIST)
        else:
            (b / 'servicemgrmibhigh').write_bytes(b'\x7fELF factory servicemgr')
            (b / 'servicemgrmibhigh0').unlink(missing_ok=True)
            persist.unlink(missing_ok=True)

    def failsafe(self, marker=True):
        if marker:
            (self.media / 'AudiClusterIntegration-RECOVER').write_text('recover\n')
        env = {'PATH': str(self.bin), 'AUDI_CLUSTER_FIXTURE_ROOT': str(self.root)}
        return subprocess.run([KSH, str(self.media / 'failsafe.sh')], env=env, capture_output=True, text=True)

    def run_script(self, name, release='MH2p_ER_AUG35S_P2873', **extra):
        env = {'PATH': str(self.bin), 'MOD_PATH': str(self.mod / 'Update'), 'MEDIA_PATH': str(self.media),
               'RELEASE_VERSION': release, 'AUDI_CLUSTER_FIXTURE_ROOT': str(self.root), **extra}
        return subprocess.run([KSH, str(self.mod / 'Update' / name)], env=env, capture_output=True, text=True)

    def install(self, **kw):
        return self.run_script('install.sh', **kw)

    def uninstall(self, **kw):
        return self.run_script('uninstall.sh', **kw)

    def state_text(self):
        return self.state.read_text().strip() if self.state.exists() else 'NONE'

    def assert_factory_intact(self):
        for rel, data in FACTORY.items():
            self.assertEqual((self.app / rel).read_bytes(), data, rel)
            self.assertEqual((self.app / rel).stat().st_mode & 0o777, FACTORY_MODES[rel], rel)
            self.assertFalse((self.app / (rel + '.real')).exists(), rel)
        for rel in NEW_TARGETS:
            self.assertFalse((self.app / rel).exists(), rel)
            self.assertFalse((self.app / (rel + '.staging')).exists(), rel)

    def assert_installed(self):
        self.assertEqual(self.state_text(), 'COMMITTED')
        for rel in NEW_TARGETS:
            self.assertTrue((self.app / rel).is_file(), rel)
        for name in ['gal', 'dio_manager']:
            self.assertEqual((self.app / f'eso/bin/apps/{name}.real').read_bytes(), FACTORY[f'eso/bin/apps/{name}'])
            self.assertIn(b'LD_PRELOAD', (self.app / f'eso/bin/apps/{name}').read_bytes())
            self.assertTrue(os.access(self.app / f'eso/bin/apps/{name}', os.X_OK))

    def backups(self):
        return sorted((self.media / 'AudiClusterIntegration-backup').glob('*')) if (self.media / 'AudiClusterIntegration-backup').exists() else []


class InstallAndUninstall(InstallerFixture):
    def test_install_then_uninstall_restores_baseline(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_installed()
        backup = self.backups()
        self.assertEqual(len(backup), 1)
        self.assertEqual((backup[0] / 'files/mnt/app/eso/bin/apps/gal').read_bytes(), FACTORY['eso/bin/apps/gal'])
        self.assertTrue((backup[0] / 'journal').exists())
        persist = subprocess.run([KSH, str(self.mod / 'Persist/install.sh')], capture_output=True, text=True,
                                 env={'PATH': str(self.bin), 'AUDI_CLUSTER_FIXTURE_ROOT': str(self.root)})
        self.assertIn('would start', persist.stdout)
        r = self.uninstall()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.state_text(), 'RESTORED')
        self.assert_factory_intact()
        self.assertFalse((self.root / 'mnt/ota/modkit/Mods/AudiClusterIntegration').exists())
        self.assertTrue((self.app / 'eso/.audi-cluster/journal').exists())
        self.assertEqual(len(self.backups()), 1)

    def test_repeat_install_is_a_no_op(self):
        self.assertEqual(self.install().returncode, 0)
        gal = (self.app / 'eso/bin/apps/gal').stat().st_mtime_ns
        r = self.install()
        self.assertEqual(r.returncode, 0)
        self.assertIn('already installed', r.stdout)
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual((self.app / 'eso/bin/apps/gal').stat().st_mtime_ns, gal)

    def test_uninstall_without_card_backup_uses_on_unit_originals(self):
        self.assertEqual(self.install().returncode, 0)
        shutil.rmtree(self.media / 'AudiClusterIntegration-backup')
        r = self.uninstall()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('relying on on-unit .real originals', r.stdout)
        self.assert_factory_intact()

    def test_uninstall_leaves_unrelated_file_in_cluster_dir(self):
        self.assertEqual(self.install().returncode, 0)
        stray = self.app / 'eso/bin/apps/cluster/operator-notes.txt'
        stray.write_bytes(b'not ours')
        r = self.uninstall()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(stray.read_bytes(), b'not ours')
        self.assert_factory_intact()

    def test_wrappers_load_hooks_only_when_committed(self):
        for name in ['gal', 'dio_manager']:
            text = (ROOT / f'port/installer/Update/{name}.wrapper').read_text()
            self.assertIn('== COMMITTED', text)
            self.assertIn(f'exec /mnt/app/eso/bin/apps/{name}.real', text)
            self.assertLess(text.index('COMMITTED'), text.index('LD_PRELOAD='))

    def test_refuses_altered_chain_files(self):
        (self.app / 'eso/bin/servicemgrmibhigh').write_bytes(b'#!/bin/sh\necho not modkit\n')
        r = self.install()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('pinned ModKit release', r.stderr)
        self.assert_factory_intact()
        self.assertFalse((self.app / 'eso/.audi-cluster').exists())
        self.assertEqual(self.backups(), [])

    def test_builder_refuses_foreign_output_directory(self):
        foreign = self.root / 'foreign'
        foreign.mkdir()
        (foreign / 'keep.txt').write_text('mine')
        with self.assertRaises(SystemExit):
            builder.build(self.root / 'payload', self.app, self.root / 'test.jar', foreign, modkit_dir=self.modkit)
        self.assertEqual((foreign / 'keep.txt').read_text(), 'mine')
        builder.build(self.root / 'payload', self.app, self.root / 'test.jar', self.root / 'again', modkit_dir=self.modkit)
        builder.build(self.root / 'payload', self.app, self.root / 'test.jar', self.root / 'again', modkit_dir=self.modkit)

    def test_persist_launches_the_validated_path(self):
        text = (ROOT / 'port/installer/Persist/install.sh').read_text()
        self.assertIn('"$daemon" daemon', text)
        self.assertNotIn('\n/eso/', text)

    def test_real_build_takes_factory_modes_from_inventory(self):
        if not (ROOT / 'analysis/app/filesystem-inventory.json').exists():
            self.skipTest('requires locally extracted firmware (not in the repository)')
        report = builder.build(self.root / 'payload', ROOT / 'analysis/app/files', self.root / 'test.jar',
                               self.root / 'real-build', ROOT / 'analysis/app/filesystem-inventory.json')
        self.assertEqual(report['factory']['/mnt/app/eso/bin/apps/gal']['mode'], '755')
        self.assertEqual(report['factory']['/mnt/app/img_ver.txt']['mode'], '644')

    def test_persist_entry_does_nothing_without_commit(self):
        persist = subprocess.run([KSH, str(self.mod / 'Persist/install.sh')], capture_output=True, text=True,
                                 env={'PATH': str(self.bin), 'AUDI_CLUSTER_FIXTURE_ROOT': str(self.root)})
        self.assertEqual(persist.returncode, 0)
        self.assertEqual(persist.stdout, '')


class Failsafe(InstallerFixture):
    def log(self):
        return (self.media / 'AudiClusterIntegration-failsafe.log').read_text()

    def test_marker_triggers_rollback_and_is_removed_only_on_success(self):
        self.assertEqual(self.install(AUDI_CLUSTER_FAULT='after-replace-6').returncode, 99)
        self.assertEqual(self.failsafe().returncode, 0, self.log())
        self.assert_factory_intact()
        self.assertEqual(self.state_text(), 'RESTORED')
        self.assertFalse((self.media / 'AudiClusterIntegration-RECOVER').exists())
        self.assertIn('recovery complete', self.log())

    def test_without_marker_it_does_nothing(self):
        self.assertEqual(self.install().returncode, 0)
        r = self.failsafe(marker=False)
        self.assertEqual(r.returncode, 0)
        self.assert_installed()
        self.assertFalse((self.media / 'AudiClusterIntegration-failsafe.log').exists())

    def test_marker_is_kept_when_recovery_is_incomplete(self):
        self.assertEqual(self.install().returncode, 0)
        (self.app / 'eso/bin/apps/cluster/cluster').write_bytes(b'edited after install')
        self.assertNotEqual(self.failsafe().returncode, 0)
        self.assertTrue((self.media / 'AudiClusterIntegration-RECOVER').exists())
        self.assertEqual(self.state_text(), 'ROLLBACK_INCOMPLETE')
        self.assertIn('recovery incomplete', self.log())

    def test_marker_with_nothing_installed_is_left_for_the_operator(self):
        self.assertEqual(self.failsafe().returncode, 0)
        self.assertTrue((self.media / 'AudiClusterIntegration-RECOVER').exists())
        self.assert_factory_intact()


class PreflightRefusals(InstallerFixture):
    def test_refuses_without_modkit_persistence_chain(self):
        self.set_modkit_chain(installed=False)
        r = self.install()
        self.assert_nothing_written(r)
        self.assertIn('ModKit persistence', r.stderr)
        # Wrapper present but persist script missing is also an incomplete chain.
        self.set_modkit_chain(installed=True)
        (self.root / 'mnt/ota/modkit/modkit_persist.sh').unlink()
        self.assert_nothing_written(self.install())

    def assert_nothing_written(self, result):
        self.assertNotEqual(result.returncode, 0)
        self.assert_factory_intact()
        self.assertFalse((self.app / 'eso/.audi-cluster').exists())
        self.assertEqual(self.backups(), [])

    def test_wrong_release(self):
        self.assert_nothing_written(self.install(release='MH2p_US_PO416_P2870'))
        self.assert_nothing_written(self.install(release='UNKNOWN'))

    def test_wrong_factory_hash(self):
        (self.app / 'eso/bin/apps/gal').write_bytes(b'\x7fELF other firmware' * 500)
        r = self.install()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('factory file differs', r.stderr)
        self.assertEqual(self.backups(), [])

    def test_tampered_payload(self):
        p = self.mod / 'Update/payload/cluster'
        p.write_bytes(p.read_bytes()[:-1] + b'x')
        r = self.install()
        self.assert_nothing_written(r)
        self.assertIn('payload does not match', r.stderr)

    def test_full_card_stops_before_backup(self):
        self.assert_nothing_written(self.install(FAKE_FREE_KB='10'))

    def test_missing_hash_utility_stops(self):
        (self.bin / 'gzip').unlink()
        r = self.install()
        self.assert_nothing_written(r)
        self.assertIn('self-test', r.stderr)

    def test_existing_cluster_jar_or_target_stops(self):
        (self.app / 'eso/hmi/lsd/jars/ClusterIntegration_v0034.jar').write_bytes(b'x')
        self.assertIn('existing cluster JAR', self.install().stderr)
        (self.app / 'eso/hmi/lsd/jars/ClusterIntegration_v0034.jar').unlink()
        (self.app / 'eso/bin/apps/cluster').mkdir()
        (self.app / 'eso/bin/apps/cluster/cluster').write_bytes(b'x')
        self.assertIn('already exists', self.install().stderr)


class InterruptedTransactions(InstallerFixture):
    def assert_recovers_then_installs(self, fault):
        r = self.install(AUDI_CLUSTER_FAULT=fault)
        self.assertEqual(r.returncode, 99, fault)
        self.assertNotEqual(self.state_text(), 'COMMITTED')
        r = self.install()
        self.assertNotEqual(r.returncode, 0, fault)
        self.assertIn('rolled back', r.stderr, fault)
        self.assertEqual(self.state_text(), 'RESTORED')
        self.assert_factory_intact()
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_installed()
        self.assertEqual(len(self.backups()), 2)

    def test_backup_copy_failure(self):
        r = self.install(FAIL_CP_MATCH='AudiClusterIntegration-backup')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('backup copy failed', r.stderr)
        self.assertEqual(self.state_text(), 'BACKING_UP')
        self.assert_factory_intact()
        r = self.install()  # the interrupted transaction is recovered first, then the run stops
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('rolled back', r.stderr)
        self.assertEqual(self.install().returncode, 0)  # a fresh, exclusive backup directory is used
        self.assert_installed()
        self.assertEqual(len(self.backups()), 2)

    def test_interrupted_before_and_after_staging(self):
        for fault in ('before-staging', 'after-staging'):
            with self.subTest(fault=fault):
                self.setUp()
                self.assert_recovers_then_installs(fault)

    def test_interrupted_after_each_replacement(self):
        for n in range(1, OP_COUNT + 1):
            with self.subTest(step=n):
                self.setUp()
                self.assert_recovers_then_installs(f'after-replace-{n}')

    def test_interrupted_between_the_two_renames_of_a_wrapper_swap(self):
        for n in WRAP_STEPS:
            with self.subTest(step=n):
                self.setUp()
                self.assert_recovers_then_installs(f'mid-switch-{n}')

    def test_interrupted_after_begin_record_before_any_file_moved(self):
        for n in range(1, OP_COUNT + 1):
            with self.subTest(step=n):
                self.setUp()
                self.assert_recovers_then_installs(f'before-move-original-{n}')

    def test_interrupted_after_each_restoration_before_its_done_record(self):
        # Restoration runs newest first: JAR (1), dio_manager (2), gal (3), then the four new files.
        for n in range(1, OP_COUNT + 1):
            with self.subTest(step=n):
                self.setUp()
                self.assertEqual(self.install().returncode, 0)
                self.assertEqual(self.uninstall(AUDI_CLUSTER_FAULT=f'before-restore-done-{n}').returncode, 99)
                r = self.uninstall()
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assert_factory_intact()
                if n in (2, 3):
                    self.assertIn('already-in-place', (self.app / 'eso/.audi-cluster/journal').read_text())

    def test_failed_permission_restore_is_not_reported_as_success(self):
        self.assertEqual(self.install(AUDI_CLUSTER_FAULT='before-move-original-5').returncode, 99)
        r = self.uninstall(FAIL_CHMOD_MATCH='eso/bin/apps/gal')
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.state_text(), 'ROLLBACK_INCOMPLETE')
        self.assertIn('cannot restore mode', r.stderr)
        self.assertEqual(self.uninstall().returncode, 0)
        self.assert_factory_intact()

    def persist(self):
        return subprocess.run([KSH, str(self.mod / 'Persist/install.sh')], capture_output=True, text=True,
                              env={'PATH': str(self.bin), 'AUDI_CLUSTER_FIXTURE_ROOT': str(self.root)})

    def test_boot_rolls_back_an_uncommitted_transaction_unattended(self):
        # Crash after the JAR (last file) was switched but before COMMITTED: the JAR is on the classpath.
        self.assertEqual(self.install(AUDI_CLUSTER_FAULT=f'after-replace-{OP_COUNT}').returncode, 99)
        self.assertTrue((self.app / 'eso/hmi/lsd/jars/test.jar').exists())
        shutil.rmtree(self.media / 'AudiClusterIntegration-backup')  # no card at boot
        r = self.persist()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('unattended rollback complete', r.stdout)
        self.assertEqual(self.state_text(), 'RESTORED')
        self.assert_factory_intact()
        self.assertEqual(self.persist().stdout, '')  # next boot: nothing to do

    def test_boot_rollback_needs_the_packaged_library(self):
        self.assertEqual(self.install(AUDI_CLUSTER_FAULT='after-replace-3').returncode, 99)
        (self.mod / 'Persist/common.sh').unlink()
        r = self.persist()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('cannot roll back', r.stdout)

    def test_jar_is_the_last_file_switched(self):
        ops = [l for l in (self.mod / 'Update/manifest.txt').read_text().splitlines() if l.startswith('op ')]
        self.assertTrue(ops[-1].endswith('test.jar 644'), ops[-1])
        self.assertTrue(all('.wrapper' in l for l in ops[-3:-1]), ops)


class RollbackRefusals(InstallerFixture):
    def test_rollback_refuses_subsequently_changed_file(self):
        self.assertEqual(self.install().returncode, 0)
        changed = self.app / 'eso/bin/apps/cluster/cluster'
        changed.write_bytes(b'operator edited this after install')
        r = self.uninstall()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.state_text(), 'ROLLBACK_INCOMPLETE')
        self.assertEqual(changed.read_bytes(), b'operator edited this after install')
        for name in ['gal', 'dio_manager']:
            self.assertEqual((self.app / f'eso/bin/apps/{name}').read_bytes(), FACTORY[f'eso/bin/apps/{name}'])
        self.assertFalse((self.app / 'eso/hmi/lsd/jars/test.jar').exists())
        self.assertEqual(len(self.backups()), 1)

    def test_partial_uninstall_keeps_backup_and_can_be_completed(self):
        self.assertEqual(self.install().returncode, 0)
        real = self.app / 'eso/bin/apps/gal.real'
        real.write_bytes(b'corrupted original')
        backup = self.backups()[0] / 'files/mnt/app/eso/bin/apps/gal'
        saved = backup.read_bytes()
        backup.write_bytes(b'corrupted backup')
        r = self.uninstall()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.state_text(), 'ROLLBACK_INCOMPLETE')
        self.assertEqual((self.app / 'eso/bin/apps/dio_manager').read_bytes(), FACTORY['eso/bin/apps/dio_manager'])
        self.assertTrue(backup.exists())
        backup.write_bytes(saved)
        r = self.uninstall()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_factory_intact()


if __name__ == '__main__':
    unittest.main()
