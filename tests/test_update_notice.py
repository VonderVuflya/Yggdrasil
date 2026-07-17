"""The 'newer version available' nudge — copy a user reads mid-task, so its
shape is a contract, not a detail.

Version compare, the rendered line, per-surface upgrade command, and the
fail-safes (no cache / no network / already current -> say nothing).
"""

import importlib
import json
import os
import shutil
import tempfile
import unittest

from yggdrasil import ygg_update_check as u


class NoticeRenderTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        os.environ["YGG_HOME"] = self.home
        importlib.reload(u)

    def tearDown(self):
        os.environ.pop("YGG_HOME", None)
        shutil.rmtree(self.home, ignore_errors=True)
        importlib.reload(u)

    def _cache(self, latest):
        u._CACHE.parent.mkdir(parents=True, exist_ok=True)
        u._CACHE.write_text(json.dumps({"checked_at": 0, "latest": latest}))

    def test_shows_both_versions_and_the_command(self):
        self._cache("0.12.1")
        note = u.notice("0.12.0")
        self.assertIn("v0.12.0", note)      # what you have
        self.assertIn("v0.12.1", note)      # what's out
        self.assertIn("→", note)            # the direction, at a glance
        self.assertIn("⚠️", note)
        self.assertIn("Yggdrasil", note)    # whose notice this is
        self.assertEqual(note.count("\n"), 0)   # one line, always

    def test_upgrade_command_follows_the_surface(self):
        self._cache("0.12.1")
        self.assertIn("Upgrade: ygg update", u.notice("0.12.0"))
        self.assertIn("Upgrade: /ygg-upgrade", u.notice("0.12.0", upgrade="/ygg-upgrade"))

    def test_silent_when_current(self):
        self._cache("0.12.1")
        self.assertEqual(u.notice("0.12.1"), "")

    def test_silent_when_ahead_of_pypi(self):
        """A dev running unreleased code must not be nagged."""
        self._cache("0.12.1")
        self.assertEqual(u.notice("0.13.0"), "")

    def test_silent_without_a_cache(self):
        self.assertEqual(u.notice("0.12.0"), "")

    def test_silent_on_a_corrupt_cache(self):
        u._CACHE.parent.mkdir(parents=True, exist_ok=True)
        u._CACHE.write_text("{ not json")
        self.assertEqual(u.notice("0.12.0"), "")

    def test_never_hits_the_network(self):
        """notice() is called on the hot path — it may only read the cache."""
        self._cache("0.12.1")
        real = u.urllib.request.urlopen
        u.urllib.request.urlopen = lambda *a, **k: self.fail("notice() made a request")
        try:
            u.notice("0.12.0")
        finally:
            u.urllib.request.urlopen = real


class VersionCompareTest(unittest.TestCase):
    def test_compares_numerically_not_lexically(self):
        self.assertGreater(u._vtuple("0.12.0"), u._vtuple("0.9.0"))   # not "0.12" < "0.9"
        self.assertGreater(u._vtuple("0.12.1"), u._vtuple("0.12.0"))
        self.assertGreater(u._vtuple("1.0.0"), u._vtuple("0.99.99"))

    def test_tolerates_suffixed_versions(self):
        self.assertEqual(u._vtuple("0.12.0rc1"), u._vtuple("0.12.01"))  # digits only


if __name__ == "__main__":
    unittest.main()
