"""`ygg doctor` checks each model against the runtime it's configured against.

It used to run `ollama list` for every configured model, so an LM Studio user
with a perfectly working install was told `ollama` was missing and the install
had failed. It also collapsed three different failures into one message; each
needs a different fix, so each is asserted separately here.
"""

import unittest
from unittest import mock

from yggdrasil import cli
from yggdrasil import ygg_providers as P


LMS = [P.Model("text-embedding-nomic-embed-text-v1.5", "embed"),
       P.Model("qwen2.5-3b-instruct", "llm"),
       P.Model("qwen/qwen3-4b-2507", "llm")]


class RuntimeCheckTest(unittest.TestCase):
    def setUp(self):
        self.rows = []

    def _check(self, state, label, detail="", fix=""):
        self.rows.append((state, label, detail, fix))

    def _run(self, *a, **kw):
        return cli._runtime_check(self._check, *a, **kw)

    def test_a_model_the_endpoint_serves_passes(self):
        with mock.patch.object(P, "probe_openai", lambda url, timeout=1.5: LMS):
            ok = self._run("embedding", "text-embedding-nomic-embed-text-v1.5",
                           "http://127.0.0.1:1234/v1", "openai", "embed")
        self.assertTrue(ok)
        state, _, detail, _ = self.rows[0]
        self.assertIs(state, True)
        self.assertIn("127.0.0.1:1234", detail)
        self.assertNotIn("/v1", detail)      # the host is a place, not an API path

    def test_ollama_is_never_consulted_for_an_openai_endpoint(self):
        """The actual regression: `which('ollama')` decided this verdict."""
        with mock.patch.object(P, "probe_openai", lambda url, timeout=1.5: LMS), \
             mock.patch.object(P, "probe_ollama",
                               mock.Mock(side_effect=AssertionError("wrong dialect"))):
            self.assertTrue(self._run("background", "qwen2.5-3b-instruct",
                                      "http://127.0.0.1:1234", "openai", "llm"))

    def test_a_dead_endpoint_says_start_the_runtime(self):
        with mock.patch.object(P, "probe_any", lambda url, timeout=1.5: None), \
             mock.patch.object(P, "detect", lambda timeout=1.0: []):
            ok = self._run("background", "qwen2.5-3b-instruct", "http://127.0.0.1:9999", "")
        self.assertFalse(ok)
        _, _, detail, fix = self.rows[0]
        self.assertIn("nothing answering", detail)
        self.assertIn("start", fix)

    def test_a_dead_endpoint_names_the_idle_runtime_it_found(self):
        idle = P.Provider("ollama", "Ollama", P.OLLAMA_URL, None, installed=True)
        with mock.patch.object(P, "probe_any", lambda url, timeout=1.5: None), \
             mock.patch.object(P, "detect", lambda timeout=1.0: [idle]):
            self._run("background", "qwen2.5:3b", "http://127.0.0.1:11434", "")
        self.assertIn("ollama serve", self.rows[0][3])

    def test_a_live_endpoint_missing_the_model_lists_what_it_has(self):
        with mock.patch.object(P, "probe_openai", lambda url, timeout=1.5: LMS):
            ok = self._run("embedding", "bge-m3", "http://127.0.0.1:1234/v1", "openai", "embed")
        self.assertFalse(ok)
        detail = self.rows[0][2]
        self.assertIn("is not on", detail)
        self.assertIn("text-embedding-nomic-embed-text-v1.5", detail)
        # only models of the right KIND — offering an LLM as a near-miss for an
        # embedder is worse than saying nothing
        self.assertNotIn("qwen", detail)

    def test_a_hosted_endpoint_is_not_probed(self):
        """The api-key check already covers it, and an unauthenticated probe of a
        hosted endpoint 401s — which would read as 'your model is missing'."""
        with mock.patch.object(P, "probe_openai",
                               mock.Mock(side_effect=AssertionError("must not probe"))):
            ok = self._run("embedding", "some/model", "https://openrouter.ai/api/v1",
                           "openai", "embed")
        self.assertTrue(ok)
        self.assertIsNone(self.rows[0][0])   # informational, not pass/fail

    def test_the_dialect_is_detected_when_config_does_not_say(self):
        """distill_url carries no companion backend setting."""
        with mock.patch.object(P, "probe_any", lambda url, timeout=1.5: ("openai", LMS)):
            self.assertTrue(self._run("background", "qwen/qwen3-4b-2507",
                                      "http://127.0.0.1:1234", "", "llm"))

    def test_an_ollama_tag_matches_loosely(self):
        tagged = [P.Model("qwen2.5:3b", "llm")]
        with mock.patch.object(P, "probe_ollama", lambda url, timeout=1.5: tagged):
            self.assertTrue(self._run("background", "qwen2.5:3b",
                                      "http://127.0.0.1:11434", "ollama", "llm"))


if __name__ == "__main__":
    unittest.main()
