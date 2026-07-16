"""ygg_config: precedence (flag > env > config > default), persistence, typed accessors."""

import importlib
import os
import stat
import tempfile
import unittest


class ConfigPrecedenceTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        os.environ["YGG_HOME"] = self.home
        for e in ("YGG_DISTILL_URL", "YGG_EMBED_URL", "YGG_DISTILL_TIMEOUT", "YGG_BG_MODEL"):
            os.environ.pop(e, None)
        import yggdrasil.ygg_config as C
        self.C = importlib.reload(C)  # re-evaluate YGG_HOME/CONFIG under the temp dir

    def tearDown(self):
        for e in ("YGG_DISTILL_URL", "YGG_EMBED_URL", "YGG_DISTILL_TIMEOUT", "YGG_BG_MODEL"):
            os.environ.pop(e, None)

    def test_default(self):
        self.assertEqual(self.C.distill_url(), "http://127.0.0.1:11434")
        self.assertEqual(self.C.distill_timeout(), 120)
        self.assertEqual(self.C.bg_model(), "qwen2.5:1.5b")
        self.assertEqual(self.C.source("distill_url"), "default")

    def test_config_layer(self):
        self.C.save({"distill_url": "http://box:11434", "distill_timeout": "240"})
        self.assertEqual(self.C.distill_url(), "http://box:11434")
        self.assertEqual(self.C.distill_timeout(), 240)
        self.assertEqual(self.C.source("distill_url"), "config")

    def test_env_beats_config(self):
        self.C.save({"distill_url": "http://config:11434"})
        os.environ["YGG_EMBED_URL"] = "http://env:11434"
        self.assertEqual(self.C.distill_url(), "http://env:11434")
        self.assertEqual(self.C.source("distill_url"), "env:YGG_EMBED_URL")

    def test_flag_beats_all(self):
        self.C.save({"distill_url": "http://config:11434"})
        os.environ["YGG_EMBED_URL"] = "http://env:11434"
        self.assertEqual(self.C.distill_url("http://flag:11434"), "http://flag:11434")
        self.assertEqual(self.C.source("distill_url", "http://flag:11434"), "flag")

    def test_timeout_is_int_and_robust(self):
        self.C.save({"distill_timeout": "not-a-number"})
        self.assertEqual(self.C.distill_timeout(), 120)  # falls back, never crashes
        self.assertEqual(self.C.distill_timeout("300"), 300)

    def test_url_trailing_slash_stripped(self):
        self.assertEqual(self.C.distill_url("http://box:11434/"), "http://box:11434")


class SecretSettingTest(unittest.TestCase):
    """embed_api_key is a secret: it lives in its own 0600 file, never in
    config.json (which is 0644 and ends up in backups and dotfile repos), and
    never renders in full in `ygg config list`."""

    KEY = "sk-or-v1-SECRETVALUE1234567890"

    def setUp(self):
        self.home = tempfile.mkdtemp()
        os.environ["YGG_HOME"] = self.home
        for e in ("YGG_EMBED_API_KEY", "OPENROUTER_API_KEY"):
            os.environ.pop(e, None)
        import yggdrasil.ygg_config as C
        self.C = importlib.reload(C)

    def tearDown(self):
        for e in ("YGG_HOME", "YGG_EMBED_API_KEY", "OPENROUTER_API_KEY"):
            os.environ.pop(e, None)

    def test_set_writes_keyfile_not_config_json(self):
        self.C.set_value("embed_api_key", self.KEY)
        self.assertTrue(self.C.EMBED_KEY_FILE.exists())
        self.assertNotIn("embed_api_key", self.C.load())
        if self.C.CONFIG.exists():
            self.assertNotIn("SECRETVALUE", self.C.CONFIG.read_text())

    def test_keyfile_is_0600(self):
        self.C.set_value("embed_api_key", self.KEY)
        mode = stat.S_IMODE(os.stat(self.C.EMBED_KEY_FILE).st_mode)
        self.assertEqual(mode, 0o600)

    def test_resolve_reads_keyfile(self):
        self.C.set_value("embed_api_key", self.KEY)
        self.assertEqual(self.C.resolve("embed_api_key"), self.KEY)
        self.assertEqual(self.C.source("embed_api_key"), "keyfile")

    def test_env_beats_keyfile(self):
        self.C.set_value("embed_api_key", self.KEY)
        os.environ["YGG_EMBED_API_KEY"] = "sk-or-from-env"
        self.assertEqual(self.C.resolve("embed_api_key"), "sk-or-from-env")
        self.assertEqual(self.C.source("embed_api_key"), "env:YGG_EMBED_API_KEY")

    def test_openrouter_env_fallback(self):
        os.environ["OPENROUTER_API_KEY"] = "sk-or-vendor"
        self.assertEqual(self.C.resolve("embed_api_key"), "sk-or-vendor")

    def test_display_masks_secret_but_not_plain_settings(self):
        shown = self.C.display("embed_api_key", self.KEY)
        self.assertNotIn("SECRETVALUE", shown)
        self.assertIn("…", shown)
        self.assertEqual(self.C.display("embed_backend", "openai"), "openai")

    def test_unset_removes_keyfile(self):
        self.C.set_value("embed_api_key", self.KEY)
        self.assertTrue(self.C.unset_value("embed_api_key"))
        self.assertFalse(self.C.EMBED_KEY_FILE.exists())
        self.assertEqual(self.C.resolve("embed_api_key"), "")
        self.assertFalse(self.C.unset_value("embed_api_key"))  # idempotent

    def test_stored_at_points_at_keyfile(self):
        self.assertEqual(self.C.stored_at("embed_api_key"), str(self.C.EMBED_KEY_FILE))
        self.assertEqual(self.C.stored_at("embed_backend"), str(self.C.CONFIG))


if __name__ == "__main__":
    unittest.main()
