import pathlib
import sys
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


if __name__ == "__main__":
    unittest.main()
