"""Reasoning suppression for the distill model.

Extraction gains nothing from a <think> trace and pays for it: measured on 8 real
transcripts, qwen3-14b went 16.8s -> 6.1s per file for the same lesson count. The
off switch is NOT portable, which is the whole reason this needs code:

  * Qwen3        obeys `/no_think` in the prompt.
  * Qwen3.5/3.6  ignore it and obey only `reasoning_effort: "none"`.
  * Ollama       has its own `think: false` body field.

so all three signals go out together, and a server that rejects the unknown field
must degrade to a slower distill rather than a failed one. Offline, mocked.
"""

import io
import os
import shutil
import tempfile
import unittest
import urllib.error
from unittest import mock

from yggdrasil import ygg_seed as s


class ModelHeuristicTest(unittest.TestCase):
    def test_reasoning_families_are_recognised(self):
        for model in ("qwen3-14b", "qwen/qwen3.5-9b", "qwen3.6-35b-a3b",
                      "deepseek-r1:7b", "GLM-5.2"):
            self.assertTrue(s._is_reasoning_model(model), model)

    def test_instruct_builds_are_left_alone(self):
        """`-instruct` / `non-thinking` builds say so in the name and don't think."""
        for model in ("qwen/qwen3-4b-instruct-2507", "qwen3-8b-non-thinking",
                      "qwen2.5:3b", "gemma2:2b", "llama3.2:3b"):
            self.assertFalse(s._is_reasoning_model(model), model)


class ModeResolutionTest(unittest.TestCase):
    def _with_mode(self, mode, model):
        original = s.DISTILL_REASONING
        s.DISTILL_REASONING = mode
        try:
            return s._suppress_reasoning(model)
        finally:
            s.DISTILL_REASONING = original

    def test_auto_follows_the_model(self):
        self.assertTrue(self._with_mode("auto", "qwen3-14b"))
        self.assertFalse(self._with_mode("auto", "qwen2.5:3b"))

    def test_off_always_suppresses(self):
        self.assertTrue(self._with_mode("off", "qwen2.5:3b"))

    def test_on_never_suppresses(self):
        self.assertFalse(self._with_mode("on", "qwen3-14b"))


def _capture_request(model, *, mode="auto", url="http://host:1234"):
    """Run one distill call against a stubbed server; return the request body."""
    seen = {}

    def fake_post(u, body, timeout):  # noqa: ARG001
        seen.update(body)
        seen["_url"] = u
        return {"choices": [{"message": {"content": '{"lessons":[]}'},
                             "finish_reason": "stop"}]}

    orig_mode, orig_url, orig_cache = s.DISTILL_REASONING, s.OLLAMA_URL, dict(s._ENDPOINT_CACHE)
    s.DISTILL_REASONING, s.OLLAMA_URL = mode, url
    s._ENDPOINT_CACHE.clear()
    s._ENDPOINT_CACHE[url] = ("openai", False)  # skip dialect probing
    try:
        with mock.patch.object(s, "_post_json", fake_post), \
             mock.patch.object(s, "_stream_collect",
                               side_effect=urllib.error.HTTPError(url, 404, "no", None, None)):
            s._ollama_generate(model, "PROMPT")
    finally:
        s.DISTILL_REASONING, s.OLLAMA_URL = orig_mode, orig_url
        s._ENDPOINT_CACHE.clear()
        s._ENDPOINT_CACHE.update(orig_cache)
    return seen


class WireFormatTest(unittest.TestCase):
    def test_openai_dialect_sends_effort_and_marker(self):
        body = _capture_request("qwen3.5-9b")
        self.assertEqual(body.get("reasoning_effort"), "none")
        self.assertTrue(body["messages"][0]["content"].endswith("/no_think"))

    def test_nothing_sent_for_a_plain_model(self):
        body = _capture_request("qwen2.5:3b")
        self.assertNotIn("reasoning_effort", body)
        self.assertNotIn("/no_think", body["messages"][0]["content"])

    def test_mode_on_leaves_a_reasoning_model_alone(self):
        body = _capture_request("qwen3-14b", mode="on")
        self.assertNotIn("reasoning_effort", body)

    def test_mode_off_suppresses_a_plain_model(self):
        body = _capture_request("qwen2.5:3b", mode="off")
        self.assertEqual(body.get("reasoning_effort"), "none")


class DistillTtlTest(unittest.TestCase):
    """The distill model is the big one (4-18 GB here). `ttl` lets the runtime
    release it between runs instead of holding the GPU around the clock."""

    def _body_with_ttl(self, ttl):
        original = s.DISTILL_TTL
        s.DISTILL_TTL = ttl
        try:
            return _capture_request("qwen2.5:3b")
        finally:
            s.DISTILL_TTL = original

    def test_absent_by_default(self):
        self.assertNotIn("ttl", self._body_with_ttl(0))

    def test_sent_when_configured(self):
        self.assertEqual(self._body_with_ttl(600).get("ttl"), 600)

    def test_is_stripped_on_a_strict_server(self):
        """`ttl` is non-standard too — a 400 must cost the idle-unload, not the run."""
        self.assertIn("ttl", s._NONSTANDARD_KEYS)


class ReleaseModelTest(unittest.TestCase):
    """`distill_ttl` only starts counting after the LAST request, so a finished
    seed would still hold multi-GB of VRAM for another ttl-worth of minutes."""

    def _release_with(self, ttl, model="qwen2.5:3b"):
        seen = []
        original = s.DISTILL_TTL
        s.DISTILL_TTL = ttl
        try:
            from yggdrasil import ygg_providers as P
            with mock.patch.object(P, "unload", lambda m, **kw: seen.append(m) or True):
                s._release_model(model)
        finally:
            s.DISTILL_TTL = original
        return seen

    def test_unloads_when_a_ttl_is_configured(self):
        self.assertEqual(self._release_with(600), ["qwen2.5:3b"])

    def test_no_ttl_means_the_model_was_meant_to_stay(self):
        self.assertEqual(self._release_with(0), [])

    def test_no_model_is_a_no_op(self):
        self.assertEqual(self._release_with(600, model=""), [])

    def test_an_unload_failure_never_raises(self):
        original = s.DISTILL_TTL
        s.DISTILL_TTL = 600
        try:
            from yggdrasil import ygg_providers as P
            with mock.patch.object(P, "unload", side_effect=OSError("no lms")):
                s._release_model("qwen2.5:3b")  # must not propagate
        finally:
            s.DISTILL_TTL = original


class StrictServerFallbackTest(unittest.TestCase):
    """A server that 400s on the unknown field must still produce lessons."""

    def test_retries_without_the_reasoning_field(self):
        url = "http://strict:1234"
        bodies = []

        def fake_post(u, body, timeout):  # noqa: ARG001
            bodies.append(body)
            if "reasoning_effort" in body:
                raise urllib.error.HTTPError(u, 400, "unknown field", None,
                                             io.BytesIO(b"{}"))
            return {"choices": [{"message": {"content": '{"lessons":[]}'},
                                 "finish_reason": "stop"}]}

        orig_mode, orig_url, orig_cache = s.DISTILL_REASONING, s.OLLAMA_URL, dict(s._ENDPOINT_CACHE)
        s.DISTILL_REASONING, s.OLLAMA_URL = "off", url
        s._ENDPOINT_CACHE.clear()
        s._ENDPOINT_CACHE[url] = ("openai", False)
        try:
            with mock.patch.object(s, "_post_json", fake_post), \
                 mock.patch.object(s, "_stream_collect",
                                   side_effect=urllib.error.HTTPError(url, 404, "no", None, None)):
                out = s._ollama_generate("qwen3-14b", "PROMPT")
        finally:
            s.DISTILL_REASONING, s.OLLAMA_URL = orig_mode, orig_url
            s._ENDPOINT_CACHE.clear()
            s._ENDPOINT_CACHE.update(orig_cache)
        self.assertEqual(out, '{"lessons":[]}')
        self.assertIn("reasoning_effort", bodies[0])
        self.assertNotIn("reasoning_effort", bodies[-1])


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self._orig = os.environ.get("YGG_HOME")
        os.environ["YGG_HOME"] = self.home
        os.environ.pop("YGG_DISTILL_REASONING", None)

    def tearDown(self):
        os.environ.pop("YGG_DISTILL_REASONING", None)
        if self._orig is not None:
            os.environ["YGG_HOME"] = self._orig
        shutil.rmtree(self.home, ignore_errors=True)

    def _cfg(self):
        from yggdrasil import ygg_config
        return ygg_config

    def test_defaults_to_auto(self):
        self.assertEqual(self._cfg().distill_reasoning(), "auto")

    def test_env_overrides(self):
        os.environ["YGG_DISTILL_REASONING"] = "off"
        self.assertEqual(self._cfg().distill_reasoning(), "off")

    def test_garbage_falls_back_to_auto(self):
        os.environ["YGG_DISTILL_REASONING"] = "sometimes"
        self.assertEqual(self._cfg().distill_reasoning(), "auto")

    def test_flag_beats_everything(self):
        os.environ["YGG_DISTILL_REASONING"] = "off"
        self.assertEqual(self._cfg().distill_reasoning("on"), "on")


if __name__ == "__main__":
    unittest.main()


class WrongLanguageGuardTest(unittest.TestCase):
    """Suppressing the thinking pass makes models drop the mid-prompt language
    rule intermittently (0 of 4 runs with reasoning on, 2 of 4 with it off), so
    prompt wording alone can't be the guarantee — this is the code-level backstop."""

    RU_LOG = "Настроил конфигурацию сервиса и починил падение демона при старте. " * 3
    EN_LOG = "Configured the service and fixed the daemon crash on startup. " * 3

    def test_english_lesson_from_a_russian_log_is_rejected(self):
        lesson = "The daemon crashed on startup because the config was missing a field."
        self.assertTrue(s._wrong_language(lesson, self.RU_LOG))

    def test_russian_lesson_passes(self):
        lesson = "Демон падал при старте из-за отсутствующего поля в конфиге service.json."
        self.assertFalse(s._wrong_language(lesson, self.RU_LOG))

    def test_identifier_heavy_russian_still_passes(self):
        """A real lesson is mostly code — it must not look like a foreign language."""
        lesson = ("Фикс `docker-compose.coolify.yml`: cap_drop ALL, no-new-privileges, "
                  "healthcheck на /api/v0/models вместо TCP-порта.")
        self.assertFalse(s._wrong_language(lesson, self.RU_LOG))

    def test_english_log_never_triggers(self):
        lesson = "The daemon crashed on startup because the config was missing a field."
        self.assertFalse(s._wrong_language(lesson, self.EN_LOG))

    def test_short_fragments_are_not_judged(self):
        self.assertFalse(s._wrong_language("qwen3-14b Q5_K_M", self.RU_LOG))
