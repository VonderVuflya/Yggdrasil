"""An unavailable model server must stop the batch without losing pending work."""

import argparse
import contextlib
import io
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from yggdrasil import ygg_seed as s


class SeedConnectionTest(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.sources = []
        for project in ("first", "second"):
            folder = root / project
            folder.mkdir()
            for i in range(2):
                (folder / f"{i}.md").write_text("A useful work log")
            self.sources.append({"kind": "obsidian", "project": project,
                                 "path": str(folder)})
        self.state = {}
        self.stack.enter_context(mock.patch.object(s._preflight, "check_connection"))
        self.stack.enter_context(mock.patch.object(s, "OLLAMA_URL", "http://studio:1234"))
        self.stack.enter_context(mock.patch.object(s, "discover", return_value=self.sources))
        self.stack.enter_context(mock.patch.object(s, "_load_seed_state", return_value=self.state))
        self.save = self.stack.enter_context(mock.patch.object(s, "_save_seed_state"))
        self.release = self.stack.enter_context(mock.patch.object(s, "_release_model"))
        self.write = self.stack.enter_context(mock.patch.object(s._ygg, "write_memory"))
        self.out, self.err = io.StringIO(), io.StringIO()
        self.stack.enter_context(contextlib.redirect_stdout(self.out))
        self.stack.enter_context(contextlib.redirect_stderr(self.err))
        self.args = argparse.Namespace(model="m", user_id="u", namespace="n",
                                       force=False, verbose=False, yes=True, dry_run=False)

    def test_seed_stops_on_connection_refusal_and_explains_recovery(self):
        with mock.patch.object(s.urllib.request, "urlopen", side_effect=
                               urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))) as request:
            code = s.seed(self.args)
        self.assertEqual(code, 1)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(self.state, {})
        self.save.assert_called()
        self.write.assert_not_called()
        self.release.assert_not_called()
        output = self.out.getvalue() + self.err.getvalue()
        for hint in ("http://studio:1234", "LM Studio", "Ollama", "ygg config get distill_url",
                     "ygg config set distill_url", "ygg doctor", "ygg seed --yes"):
            self.assertIn(hint, output)
        self.assertNotIn("✓ done", output)
        self.assertNotIn("Check it:", output)

    def test_failure_after_success_preserves_only_completed_state(self):
        with mock.patch.object(s, "_ensure_endpoint"), mock.patch.object(s, "_ollama_generate", side_effect=[
                '{"lessons":[]}', urllib.error.URLError(ConnectionRefusedError())]):
            code = s.seed(self.args)
        self.assertEqual(code, 1)
        self.assertEqual(len(self.state), 1)
        self.assertTrue(next(iter(self.state)).startswith(self.sources[0]["path"]))
        self.save.assert_called_with(self.state)

    def test_explicit_file_distill_failure_stays_pending(self):
        self.args.source = str(Path(self.sources[0]["path"]) / "0.md")
        self.args.project = None
        with mock.patch.object(s.urllib.request, "urlopen", side_effect=
                               urllib.error.URLError(ConnectionRefusedError())):
            code = s.distill_cmd(self.args)
        self.assertEqual(code, 1)
        self.assertEqual(self.state, {})
        self.assertIn("ygg config get distill_url", self.err.getvalue())

    def test_dry_run_does_not_contact_model(self):
        self.args.dry_run = True
        with mock.patch.object(s.urllib.request, "urlopen") as request:
            self.assertEqual(s.seed(self.args), 0)
        request.assert_not_called()


class EndpointStartupTest(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(s, "OLLAMA_URL", "http://localhost:1234"))
        self.stack.enter_context(mock.patch.object(s.sys.stdin, "isatty", return_value=True))
        self.stack.enter_context(mock.patch.object(s, "_endpoint_is_local", return_value=True))
        self.stack.enter_context(mock.patch.object(s, "_installed_model_servers", return_value=[
            ("LM Studio", ["lms", "server", "start"]), ("Ollama", ["ollama", "serve"])]))
        self.launch = self.stack.enter_context(mock.patch.object(s.subprocess, "Popen"))

    def test_starts_matching_server_and_waits_for_api(self):
        with mock.patch.object(s, "_ping_endpoint", side_effect=[OSError(), OSError(), None]) as ping, \
                mock.patch("builtins.input", return_value="yes") as prompt, \
                mock.patch.object(s.time, "sleep"):
            s._ensure_endpoint()
        self.assertEqual(ping.call_count, 3)
        self.assertIn("LM Studio", prompt.call_args.args[0])
        self.assertEqual(self.launch.call_args.args[0][0], "lms")

    def test_declining_does_not_launch(self):
        with mock.patch.object(s, "_ping_endpoint", side_effect=OSError()), \
                mock.patch("builtins.input", return_value="n"):
            with self.assertRaises(s._EndpointUnavailable):
                s._ensure_endpoint()
        self.launch.assert_not_called()

    def test_remote_server_does_not_prompt_or_launch(self):
        with mock.patch.object(s, "_ping_endpoint", side_effect=OSError()), \
                mock.patch.object(s, "_endpoint_is_local", return_value=False), \
                mock.patch("builtins.input") as prompt:
            with self.assertRaises(s._EndpointUnavailable):
                s._ensure_endpoint()
        prompt.assert_not_called()
        self.launch.assert_not_called()

    def test_startup_timeout_stops(self):
        with mock.patch.object(s, "_ping_endpoint", side_effect=OSError()), \
                mock.patch("builtins.input", return_value="y"), \
                mock.patch.object(s.time, "monotonic", side_effect=[0, 31]):
            with self.assertRaises(s._EndpointUnavailable):
                s._ensure_endpoint()
        self.launch.assert_called_once()

    def test_ready_server_never_prompts(self):
        with mock.patch.object(s, "_ping_endpoint"), mock.patch("builtins.input") as prompt:
            s._ensure_endpoint()
        prompt.assert_not_called()
        self.launch.assert_not_called()


class EndpointProbeTest(unittest.TestCase):
    def setUp(self):
        connection = mock.patch.object(s._preflight, "check_connection")
        connection.start()
        self.addCleanup(connection.stop)

    def test_openai_fallback_after_ollama_404(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"data": []}'
        missing = urllib.error.HTTPError("http://localhost/v1/models", 404, "missing", {}, None)
        with mock.patch.object(s, "OLLAMA_URL", "http://localhost:11434"), \
                mock.patch.object(s.urllib.request, "urlopen", side_effect=[missing, response]) as request:
            s._ping_endpoint()
        self.assertEqual(request.call_args.args[0].full_url, "http://localhost:11434/v1/models")

    def test_unrelated_http_server_is_not_ready(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"status": "ok"}'
        with mock.patch.object(s.urllib.request, "urlopen", return_value=response):
            with self.assertRaises(ValueError):
                s._ping_endpoint()
