"""The downloadable bundle must work without the package on Python's path."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile


class BundleTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('bash') and shutil.which('zip'), 'bundle build requires bash and zip')
    def test_bundle_contains_its_cli_dependencies_and_own_version(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            shutil.copytree(repo / 'yggdrasil', root / 'yggdrasil', ignore=shutil.ignore_patterns('__pycache__'))
            packaging = root / 'packaging/mcpb'
            packaging.mkdir(parents=True)
            for name in ('build.sh', 'manifest.json'):
                shutil.copy2(repo / 'packaging/mcpb' / name, packaging / name)
            built = subprocess.run(['bash', str(packaging / 'build.sh')], cwd=root,
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            bundle = next(packaging.glob('*.mcpb'))
            unpacked = root / 'unpacked'
            with zipfile.ZipFile(bundle) as z:
                z.extractall(unpacked)
            code = '''
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root / 'server'))
import ygg_mcp_server as mcp
assert 'usage:' in mcp.run_ygg(['health', '--help'])
assert mcp._server_version() == json.loads((root / 'manifest.json').read_text())['version']
'''
            env = dict(os.environ, YGG_HOME=str(root / 'isolated-home'))
            result = subprocess.run([sys.executable, '-I', '-S', '-c', code, str(unpacked)],
                                    cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
