import json
from pathlib import Path
import re
import unittest
from yggdrasil import __version__

ROOT = Path(__file__).resolve().parents[1]

class ReleaseVersionsTests(unittest.TestCase):
    def test_product_manifests_match_the_python_package(self):
        paths = ['clients/npm/package.json','packaging/mcpb/manifest.json','server.json',
                 '.claude-plugin/plugin.json','.claude-plugin/marketplace.json',
                 '.codex-plugin/plugin.json','.cursor-plugin/plugin.json','.cursor-plugin/marketplace.json']
        for path in paths:
            content = (ROOT/path).read_text()
            json.loads(content)
            versions = re.findall(r'"version"\s*:\s*"([^"]+)"',content)
            self.assertTrue(versions,path)
            self.assertTrue(all(value == __version__ for value in versions),path)
        version = re.search(r'(?m)^version\s*=\s*"([^"]+)"',(ROOT/'pyproject.toml').read_text())[1]
        self.assertEqual(version,__version__)
        self.assertIn(f'## [{__version__}]',(ROOT/'CHANGELOG.md').read_text())

    def test_ui_version_is_independent_and_matches_displayed_minor_version(self):
        version = json.loads((ROOT/'web/package.json').read_text())['version']
        display = re.search(r'UI_VERSION = "([^"]+)"',(ROOT/'web/src/lib/features.ts').read_text())[1]
        self.assertEqual(display,'.'.join(version.split('.')[:2]))
        self.assertNotEqual(version,__version__)
