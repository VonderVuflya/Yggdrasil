import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "yggdrasil"))

import service  # noqa: E402


class TestServiceGenerators(unittest.TestCase):
    ARGV = ["/usr/bin/python3", "/home/u/.yggdrasil/scripts/ygg_memory_server.py",
            "--db", "/home/u/.yggdrasil/data/memory.sqlite", "--port", "42069",
            "--token", "abc", "--embed-model", "all-minilm"]

    def test_launchd_plist(self):
        p = service.launchd_plist(self.ARGV)
        self.assertIn("<key>RunAtLoad</key><true/>", p)
        self.assertIn("<key>KeepAlive</key><true/>", p)
        self.assertIn(service.LABEL, p)
        for a in self.ARGV:
            self.assertIn(f"<string>{a}</string>", p)

    def test_systemd_unit(self):
        u = service.systemd_unit(self.ARGV)
        self.assertIn("[Service]", u)
        self.assertIn("Restart=always", u)
        self.assertIn("WantedBy=default.target", u)
        self.assertIn("ExecStart=/usr/bin/python3", u)
        self.assertIn("ygg_memory_server.py", u)

    def test_schtasks_create_argv(self):
        win = ["C:\\Py\\pythonw.exe", "C:\\s\\ygg_memory_server.py", "--port", "42069"]
        cmd = service.schtasks_create_argv(win)
        self.assertEqual(cmd[0], "schtasks")
        self.assertIn("/create", cmd)
        self.assertIn("onlogon", cmd)
        self.assertIn(service.TASK, cmd)
        tr = cmd[cmd.index("/tr") + 1]
        self.assertIn("pythonw.exe", tr)
        self.assertIn("42069", tr)

    def test_engine_argv_embed_optional(self):
        with_embed = service.engine_argv("sekret-tok", "all-minilm")
        self.assertIn("--embed-model", with_embed)
        self.assertIn("all-minilm", with_embed)
        without = service.engine_argv("sekret-tok", "")
        self.assertNotIn("--embed-model", without)

    def test_engine_argv_token_is_by_file_not_value(self):
        """The token must travel by file path, never as a value visible in `ps`."""
        argv = service.engine_argv("sekret-tok", "all-minilm")
        self.assertIn("--token-file", argv)
        self.assertNotIn("--token", argv)
        self.assertNotIn("sekret-tok", argv)


class TestOpenCodeRegistration(unittest.TestCase):
    """OpenCode's MCP schema differs from Claude's in four ways (mcp vs
    mcpServers, explicit type, command-as-one-array, environment vs env) — the
    generated entry must match OpenCode's, and must never eat a user's config."""

    def setUp(self):
        self.cfgdir = pathlib.Path(tempfile.mkdtemp())
        os.environ["XDG_CONFIG_HOME"] = str(self.cfgdir)

    def tearDown(self):
        os.environ.pop("XDG_CONFIG_HOME", None)
        shutil.rmtree(self.cfgdir, ignore_errors=True)

    def test_entry_uses_opencode_schema_not_claude_schema(self):
        e = service.opencode_json_entry()
        self.assertEqual(e["type"], "local")
        self.assertIsInstance(e["command"], list)      # ONE array, not command+args
        self.assertGreaterEqual(len(e["command"]), 2)
        self.assertIn("environment", e)                 # not "env"
        self.assertNotIn("args", e)
        self.assertNotIn("env", e)

    def test_entry_carries_no_token(self):
        """The token lives in the 0600 file; configs get synced and backed up."""
        self.assertNotIn("YGG_ENGINE_TOKEN", service.opencode_json_entry()["environment"])

    def test_path_honours_xdg(self):
        self.assertEqual(service.opencode_config_path(),
                         self.cfgdir / "opencode" / "opencode.json")

    def test_writes_under_mcp_key(self):
        self.assertTrue(service._register_opencode_json())
        cfg = json.loads(service.opencode_config_path().read_text())
        self.assertIn("yggdrasil", cfg["mcp"])
        self.assertNotIn("mcpServers", cfg)

    def test_merges_and_backs_up_existing_config(self):
        path = service.opencode_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "model": "openrouter/some/model",
            "mcp": {"other-server": {"type": "local", "command": ["x"]}},
        }))
        self.assertTrue(service._register_opencode_json())
        cfg = json.loads(path.read_text())
        self.assertEqual(cfg["model"], "openrouter/some/model")   # user setting survives
        self.assertIn("other-server", cfg["mcp"])                 # their server survives
        self.assertIn("yggdrasil", cfg["mcp"])
        self.assertTrue(pathlib.Path(str(path) + ".ygg.bak").exists())

    def test_refuses_to_clobber_invalid_json(self):
        path = service.opencode_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ this is not json")
        self.assertFalse(service._register_opencode_json())
        self.assertEqual(path.read_text(), "{ this is not json")  # left untouched

    def test_unregister_removes_only_our_entry(self):
        path = service.opencode_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"mcp": {"other-server": {"type": "local", "command": ["x"]}}}))
        service._register_opencode_json()
        service.unregister_mcp()
        cfg = json.loads(path.read_text())
        self.assertNotIn("yggdrasil", cfg["mcp"])
        self.assertIn("other-server", cfg["mcp"])


class TestEngineArgvEmbedBackend(unittest.TestCase):
    """embed_url/backend ride argv from config; the api key rides by file path
    only — the plist, the systemd unit and `ps` all inherit argv verbatim."""

    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp())
        self._saved_home, service.YGG_HOME = service.YGG_HOME, self.home
        self._saved_keyfile, service.EMBED_KEY_FILE = service.EMBED_KEY_FILE, self.home / "embed_api_key"
        self._saved_cfg = service._config
        self._cfg: dict = {}
        service._config = lambda: self._cfg

    def tearDown(self):
        service.YGG_HOME = self._saved_home
        service.EMBED_KEY_FILE = self._saved_keyfile
        service._config = self._saved_cfg
        shutil.rmtree(self.home, ignore_errors=True)

    def test_url_and_backend_ride_argv(self):
        self._cfg = {"embed_url": "https://openrouter.ai/api/v1", "embed_backend": "openai"}
        argv = service.engine_argv("tok", "nemotron")
        self.assertIn("--embed-url", argv)
        self.assertIn("https://openrouter.ai/api/v1", argv)
        self.assertIn("--embed-backend", argv)
        self.assertIn("openai", argv)

    def test_default_ollama_backend_not_passed(self):
        self._cfg = {"embed_backend": "ollama"}
        self.assertNotIn("--embed-backend", service.engine_argv("tok", "all-minilm"))

    def test_api_key_travels_by_file_never_by_value(self):
        service.EMBED_KEY_FILE.write_text("sk-or-v1-SUPERSECRET")
        argv = service.engine_argv("tok", "nemotron")
        self.assertIn("--embed-api-key-file", argv)
        self.assertIn(str(service.EMBED_KEY_FILE), argv)
        self.assertNotIn("--embed-api-key", argv)          # the by-value flag
        self.assertNotIn("sk-or-v1-SUPERSECRET", " ".join(argv))

    def test_no_key_file_no_flag(self):
        self.assertNotIn("--embed-api-key-file", service.engine_argv("tok", "nemotron"))


if __name__ == "__main__":
    unittest.main()
