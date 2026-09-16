import importlib.util
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeToolsTests(unittest.TestCase):
    def test_recipe_includes_support_sources_and_no_gles_link(self):
        module = load('build_native_port')
        jobs = module.commands('qcc', Path('/unused'))
        self.assertIn('-lz', jobs['cluster'])
        self.assertIn('-lscreen', jobs['gal_cluster.so'])
        for name in ['rgd_tlv.c', 'pps_writer.c', 'logging.c']:
            self.assertTrue(any(arg.endswith('/' + name) for arg in jobs['dio_cluster.so']))
        self.assertFalse(any('-lGLESv2' in args for args in jobs.values()))

    def test_missing_sdk_fails_without_publishing(self):
        import sys
        output = ROOT / 'build/native-experimental'
        self.assertFalse(output.exists())
        env = {k: v for k, v in os.environ.items() if k not in ('QNX_HOST', 'QNX_TARGET')}
        p = subprocess.run([sys.executable, str(ROOT / 'tools/build_native_port.py'), '--build',
                            '--qcc', '/definitely-missing/qcc'], env=env, capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('Build blocked', p.stderr)
        self.assertFalse(output.exists())

    def test_stripped_library_and_strong_weak_imports(self):
        module = load('audit_native_payload')
        path = ROOT / 'analysis/stage2-extracted/image-03/files/usr/lib/libscreen.so.1'
        if not path.exists():
            self.skipTest('requires locally extracted firmware (not in the repository)')
        result = module.inspect(path.read_bytes())
        self.assertEqual(result['machine'], 'EM_ARM')
        self.assertIn('screen_create_window', result['exports'])
        self.assertFalse(result['required'] & result['weak'])
        self.assertIn('libc.so.3', result['needed'])


if __name__ == '__main__':
    unittest.main()
