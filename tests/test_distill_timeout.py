"""Distill failures: configurable timeout, error detection, and re-run contract.

Any failed distill remains pending.  A local model may emit malformed JSON in
one run and valid JSON in the next, so treating that as terminal loses chats.
"""

import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path

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

    def test_distill_text_reports_timed_out(self):
        s._ollama_generate = lambda *a, **k: (_ for _ in ()).throw(socket.timeout())
        r = s.distill_text("text", project="p", source="s", model="m", user_id="u", namespace="n")
        self.assertTrue(r["timed_out"])
        self.assertEqual(r["errors"], 1)


if __name__ == "__main__":
    unittest.main()
