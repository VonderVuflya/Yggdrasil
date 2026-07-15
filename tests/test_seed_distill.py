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


class LessonsFromRawTest(unittest.TestCase):
    """The distill parser must tolerate the malformed JSON small models emit."""

    def test_clean_wrapped(self):
        out = ygg_seed._lessons_from_raw('{"lessons":[{"type":"fix","content":"a"},{"content":"b"}]}')
        self.assertEqual([l["content"] for l in out], ["a", "b"])

    def test_missing_comma_between_objects_salvaged(self):
        # the real failure: two lesson objects with no comma between them
        bad = '{"lessons":[{"type":"fix","content":"first"}{"type":"lesson","content":"second"}]}'
        with self.assertRaises(Exception):
            json.loads(bad)   # confirms it's genuinely invalid JSON
        out = ygg_seed._lessons_from_raw(bad)
        self.assertEqual({l["content"] for l in out}, {"first", "second"})

    def test_truncated_tail_keeps_complete_objects(self):
        bad = '{"lessons":[{"type":"fix","content":"kept"},{"type":"lesson","content":"cut off he'
        out = ygg_seed._lessons_from_raw(bad)
        self.assertEqual([l["content"] for l in out], ["kept"])

    def test_braces_inside_string_content_not_confused(self):
        out = ygg_seed._lessons_from_raw('{"lessons":[{"content":"use {curly} braces in code"}]}')
        self.assertEqual(out[0]["content"], "use {curly} braces in code")

    def test_valid_but_empty_is_a_list_not_a_failure(self):
        # the model correctly found nothing -> [] (done), NOT None (retry)
        self.assertEqual(ygg_seed._lessons_from_raw('{"lessons":[]}'), [])

    def test_empty_and_garbage_are_none(self):
        # unparseable -> None so the caller retries / errors (file not lost)
        self.assertIsNone(ygg_seed._lessons_from_raw(""))
        self.assertIsNone(ygg_seed._lessons_from_raw("not json at all"))


class StripFencesTest(unittest.TestCase):
    """Phone/on-device LLM servers ignore strict format=json and fence their
    JSON in markdown; plain Ollama output must pass through untouched."""

    def test_json_fence_unwrapped(self):
        fenced = '```json\n{"lessons": [{"content": "x"}]}\n```'
        self.assertEqual(json.loads(ygg_seed._strip_fences(fenced))["lessons"][0]["content"], "x")

    def test_bare_fence_unwrapped(self):
        self.assertEqual(ygg_seed._strip_fences('```\n{"a": 1}\n```'), '{"a": 1}')

    def test_plain_json_untouched(self):
        self.assertEqual(ygg_seed._strip_fences('{"a": 1}'), '{"a": 1}')

    def test_empty(self):
        self.assertEqual(ygg_seed._strip_fences(""), "")


class DistillTruncationTest(unittest.TestCase):
    """A generation cut off by the token limit must save NOTHING (a truncated
    stub persisted as a 'lesson' is worse than an error)."""

    def setUp(self):
        self._orig_write = ygg_seed._ygg.write_memory
        self._orig_gen = ygg_seed._ollama_generate
        self.writes = []
        ygg_seed._ygg.write_memory = lambda **kw: (self.writes.append(kw) or ("added", {"id": "x"}))

    def tearDown(self):
        ygg_seed._ygg.write_memory = self._orig_write
        ygg_seed._ollama_generate = self._orig_gen

    def test_truncated_generation_is_an_error_and_saves_nothing(self):
        def truncated(*a, **k):
            raise ValueError("model output truncated (done_reason=length) — nothing saved")
        ygg_seed._ollama_generate = truncated

        result = ygg_seed.distill_text(
            "a very long work log", project="t", source="seed",
            model="m", user_id="u", namespace="n",
        )

        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["added"], 0)
        self.assertEqual(self.writes, [])


class TruncatedLessonTest(unittest.TestCase):
    """A per-lesson stub that parses fine but ends mid-thought (the wild case:
    a list intro '…следующие действия:' whose items never arrived) must be
    dropped, not persisted — while valid short lessons still save."""

    def setUp(self):
        self._orig = ygg_seed._ygg.write_memory
        self.writes = []
        ygg_seed._ygg.write_memory = lambda **kw: (self.writes.append(kw) or ("added", {"id": "x"}))

    def tearDown(self):
        ygg_seed._ygg.write_memory = self._orig

    def test_looks_truncated_flags_stubs_keeps_valid(self):
        for stub in ("Сделайте следующее:", "use the flag,", "open (paren", 'say "hi', "step —"):
            self.assertTrue(ygg_seed._looks_truncated(stub), stub)
        for ok in ("x", "ok", "lesson a", "Fixed the update() bug.",
                   "Use qwen2.5:3b for RU.", 'call it "json" mode', "done…"):
            self.assertFalse(ygg_seed._looks_truncated(ok), ok)

    def test_distill_drops_stub_keeps_good_lesson(self):
        ygg_seed._ollama_generate = lambda *a, **k: json.dumps(
            {"lessons": [{"content": "Чтобы починить, сделайте следующее:"},
                         {"content": "Валидный завершённый урок."}]})
        r = ygg_seed.distill_text("log", project="t", source="seed",
                                  model="m", user_id="u", namespace="n")
        self.assertEqual((r["added"], r["truncated"]), (1, 1))
        self.assertEqual([w["content"] for w in self.writes], ["Валидный завершённый урок."])


if __name__ == "__main__":
    unittest.main()
