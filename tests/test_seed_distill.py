"""Regression tests for ygg_seed.distill_text against a loose local model.

The local distillation model (e.g. qwen2.5:1.5b) does not reliably return the
requested {"lessons":[{...}]} shape — it may return a bare list, a list of plain
strings, a single object, or malformed JSON. A real `ygg seed` run crashed on a
list-of-strings (`'str' object has no attribute 'get'`); these pin that down.
"""

import json
import unittest

from yggdrasil import ygg_seed


class DistillRobustnessTest(unittest.TestCase):
    def setUp(self):
        self._orig_write = ygg_seed._ygg.write_memory
        ygg_seed._ygg.write_memory = lambda **kw: ("added", {"id": "x"})

    def tearDown(self):
        ygg_seed._ygg.write_memory = self._orig_write

    def _distill(self, payload):
        ygg_seed._ollama_generate = lambda *a, **k: payload
        return ygg_seed.distill_text(
            "some work log", project="t", source="seed",
            model="m", user_id="u", namespace="n",
        )

    def test_list_of_strings_does_not_crash(self):
        # the exact production crash case
        self.assertEqual(self._distill(json.dumps(["lesson a", "lesson b"]))["added"], 2)

    def test_bare_single_object(self):
        self.assertEqual(self._distill(json.dumps({"type": "decision", "content": "x"}))["added"], 1)

    def test_normal_wrapped_lessons(self):
        self.assertEqual(self._distill(json.dumps({"lessons": [{"content": "x"}]}))["added"], 1)

    def test_mixed_item_types(self):
        # dict + string + non-string/dict (skipped) + {"text"} alias
        r = self._distill(json.dumps({"lessons": [{"content": "ok"}, "str", 42, {"text": "alt"}]}))
        self.assertEqual(r["added"], 3)

    def test_bad_json_is_error_not_crash(self):
        self.assertEqual(self._distill("{not valid")["errors"], 1)

    def test_empty(self):
        r = self._distill(json.dumps({"lessons": []}))
        self.assertEqual({"added": r["added"], "dup": r["dup"], "errors": r["errors"]},
                         {"added": 0, "dup": 0, "errors": 0})


class IncrementalSeedTest(unittest.TestCase):
    """Incremental seed: skip files unchanged since last distill, re-distill on change."""

    def setUp(self):
        self._orig = ygg_seed.distill_text
        ygg_seed.distill_text = lambda *a, **k: {"added": 1, "dup": 0, "errors": 0}

    def tearDown(self):
        ygg_seed.distill_text = self._orig

    def _src(self):
        import os
        import tempfile
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "memory"))
        mf = os.path.join(d, "memory", "n.md")
        open(mf, "w").write("a")
        return {"kind": "claude", "path": d, "project": "t"}, mf

    def test_skips_unchanged_and_redistills_on_change(self):
        import time
        src, mf = self._src()
        state = {}
        r1 = ygg_seed.distill_source(src, model="m", user_id="u", namespace="n", state=state)
        r2 = ygg_seed.distill_source(src, model="m", user_id="u", namespace="n", state=state)
        time.sleep(0.01)
        open(mf, "w").write("the user kept chatting; the file grew")  # changes mtime + size
        r3 = ygg_seed.distill_source(src, model="m", user_id="u", namespace="n", state=state)
        self.assertEqual((r1["added"], r1["skipped"]), (1, 0))
        self.assertEqual((r2["added"], r2["skipped"]), (0, 1))   # unchanged -> skipped
        self.assertEqual((r3["added"], r3["skipped"]), (1, 0))   # changed -> re-distilled

    def test_force_ignores_state(self):
        src, _ = self._src()
        state = {}
        ygg_seed.distill_source(src, model="m", user_id="u", namespace="n", state=state)
        r = ygg_seed.distill_source(src, model="m", user_id="u", namespace="n", state=state, force=True)
        self.assertEqual((r["added"], r["skipped"]), (1, 0))     # force re-processes


if __name__ == "__main__":
    unittest.main()
