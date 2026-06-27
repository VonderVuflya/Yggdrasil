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
        self.assertEqual(self._distill(json.dumps({"lessons": []})), {"added": 0, "dup": 0, "errors": 0})


if __name__ == "__main__":
    unittest.main()
