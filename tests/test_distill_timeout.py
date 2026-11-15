"""Distill failures: configurable timeout, error detection, and re-run contract.

Any failed distill remains pending.  A local model may emit malformed JSON in
one run and valid JSON in the next, so treating that as terminal loses chats.
"""

import argparse
import contextlib
import io
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from yggdrasil import ygg_seed as s


class TimeoutDetectionTest(unittest.TestCase):
    def test_detects_timeout_shapes(self):
        self.assertTrue(s._is_timeout(socket.timeout("timed out")))
        self.assertTrue(s._is_timeout(TimeoutError()))
        self.assertTrue(s._is_timeout(urllib.error.URLError(socket.timeout())))
        self.assertTrue(s._is_timeout(urllib.error.URLError("[Errno 60] Operation timed out")))

    def test_non_timeout_not_flagged(self):
        self.assertFalse(s._is_timeout(ValueError("bad json")))
        self.assertFalse(s._is_timeout(OSError("disk full")))


class DistillTimeoutContractTest(unittest.TestCase):
    def setUp(self):
        self._gen = s._ollama_generate
        self._extract = s._extract_text
        self._write = s._ygg.write_memory
        s._extract_text = lambda f: "a long real conversation " * 200  # non-empty
        s._ygg.write_memory = lambda **kw: ("added", {"id": "x"})

    def tearDown(self):
        s._ollama_generate = self._gen
        s._extract_text = self._extract
        s._ygg.write_memory = self._write

    def _run_once(self):
        d = Path(tempfile.mkdtemp())
        f = d / "big.jsonl"
        f.write_text('{"message":{"content":"hi"}}')
        state = {}
        agg = s.distill_source({"kind": "claude", "path": str(d), "project": "p"},
                               model="m", user_id="u", namespace="n", state=state)
        return f, state, agg

    def test_timeout_not_marked_done_so_rerun_retries(self):
        s._ollama_generate = lambda *a, **k: (_ for _ in ()).throw(socket.timeout("timed out"))
        f, state, agg = self._run_once()
        self.assertEqual(agg["timed_out"], 1)
        self.assertEqual(state, {})                       # nothing recorded
        self.assertFalse(s._is_unchanged(f, state))        # -> re-run retries it

    def test_malformed_response_is_not_marked_done(self):
        s._ollama_generate = lambda *a, **k: "not json{{{"  # parse error every time
        f, state, agg = self._run_once()
        self.assertEqual(agg["timed_out"], 0)
        self.assertEqual(state, {})                         # re-run retries it
        self.assertFalse(s._is_unchanged(f, state))

    def test_timeout_reports_elapsed_and_original_cause_without_blame_on_file_size(self):
        for error, detail in (
            (urllib.error.URLError(TimeoutError("connection timed out")), "connection timed out"),
            (socket.timeout("read timed out"), "read timed out"),
            (TimeoutError("exceeded total distill deadline"), "exceeded total distill deadline"),
        ):
            with self.subTest(error=detail):
                stderr = io.StringIO()
                with patch.object(s, "_ollama_generate", side_effect=error), \
                        patch.object(s.time, "monotonic", side_effect=[10.0, 15.0]), \
                        contextlib.redirect_stderr(stderr):
                    result = s.distill_text("text", project="p", source="s", model="m",
                                           user_id="u", namespace="n")
                self.assertTrue(result["timed_out"])
                message = stderr.getvalue()
                self.assertIn("after 5.0s", message)
                self.assertIn(detail, message)
                self.assertIn("connectivity", message)
                self.assertNotIn("file too big", message)
                self.assertNotIn("raise --timeout", message)

    def test_seed_summary_does_not_claim_network_timeout_exhausted_generation_limit(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "chat.jsonl"
            f.write_text('{"message":{"content":"hi"}}')
            src = {"kind": "claude", "path": d, "project": "p", "bytes": f.stat().st_size}
            state = {}
            stdout = io.StringIO()
            args = argparse.Namespace(model="m", user_id="u", namespace="n",
                                      yes=True, dry_run=False)
            with patch.object(s, "discover", return_value=[src]), \
                    patch.object(s, "_load_seed_state", return_value=state), \
                    patch.object(s, "_save_seed_state"), \
                    patch.object(s, "_release_model"), \
                    patch.object(s, "_scale_hint", return_value=None), \
                    patch.object(s, "_ollama_generate", side_effect=TimeoutError("timed out")), \
                    patch.object(s, "DISTILL_TIMEOUT", 300), \
                    contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(s.seed(args), 0)
            message = stdout.getvalue()
            self.assertIn("connectivity", message)
            self.assertNotIn("timed out at 300s", message)
            self.assertNotIn("they're large", message)
            self.assertNotIn("retries only them", message)
            self.assertEqual(state, {})

    def test_distill_text_reports_timed_out(self):
        s._ollama_generate = lambda *a, **k: (_ for _ in ()).throw(socket.timeout())
        r = s.distill_text("text", project="p", source="s", model="m", user_id="u", namespace="n")
        self.assertTrue(r["timed_out"])
        self.assertEqual(r["errors"], 1)


if __name__ == "__main__":
    unittest.main()
