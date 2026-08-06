"""Tests for ygg_providers — runtime detection and the URL shapes it derives.

The bug this module exists to kill: an LM Studio user had to know that
`embed_url` wants the /v1 base while `distill_url` wants the host root, and that
`lms get nomic-embed-text` produces a model the API calls
`text-embedding-nomic-embed-text-v1.5`. Both are asserted here.

No network: the probes are driven through a stubbed `_get`.
"""

import unittest
from unittest import mock

from yggdrasil import ygg_providers as P


OLLAMA_TAGS = {"models": [
    {"name": "qwen2.5:3b", "size": 1900000000, "details": {"family": "qwen2"}},
    {"name": "nomic-embed-text:latest", "size": 274000000, "details": {"family": "nomic-bert"}},
]}
LMS_V0 = {"data": [
    {"id": "qwen/qwen3-4b-2507", "type": "llm", "quantization": "Q8_0"},
    {"id": "text-embedding-nomic-embed-text-v1.5", "type": "embeddings"},
    {"id": "qwen/qwen3.5-9b", "type": "vlm"},
]}
OPENAI_V1 = {"data": [{"id": "bge-small-en-v1.5"}, {"id": "qwen2.5-3b-instruct"}]}


def _stub(mapping):
    """Serve canned JSON per URL suffix; anything else is 'not answering'."""
    def fake(url, timeout=1.5):
        for suffix, payload in mapping.items():
            if url.endswith(suffix):
                return payload
        return None
    return fake


class ClassifyTest(unittest.TestCase):
    def test_family_beats_the_name(self):
        self.assertEqual(P.classify("weird-name", "nomic-bert"), "embed")
        self.assertEqual(P.classify("embed-sounding", "qwen2"), "llm")

    def test_name_hints_when_the_server_says_nothing(self):
        for mid in ("nomic-embed-text", "all-minilm-l6", "bge-m3", "e5-large",
                    "paraphrase-multilingual-mpnet"):
            self.assertEqual(P.classify(mid), "embed", mid)
        for mid in ("qwen2.5-3b-instruct", "gemma-3-4b", "llama3.2"):
            self.assertEqual(P.classify(mid), "llm", mid)


class ProbeTest(unittest.TestCase):
    def test_ollama_reads_tags_and_types_them(self):
        with mock.patch.object(P, "_get", _stub({"/api/tags": OLLAMA_TAGS})):
            models = P.probe_ollama("http://127.0.0.1:11434")
        self.assertEqual([m.id for m in models], ["qwen2.5:3b", "nomic-embed-text:latest"])
        self.assertEqual([m.kind for m in models], ["llm", "embed"])

    def test_lmstudio_v0_types_every_model(self):
        with mock.patch.object(P, "_get", _stub({"/api/v0/models": LMS_V0})):
            models = P.probe_openai("http://127.0.0.1:1234")
        self.assertEqual([m.kind for m in models], ["llm", "embed", "llm"])  # vlm -> llm

    def test_openai_falls_back_to_v1_models(self):
        with mock.patch.object(P, "_get", _stub({"/v1/models": OPENAI_V1})):
            models = P.probe_openai("http://127.0.0.1:8080")
        self.assertEqual([m.kind for m in models], ["embed", "llm"])

    def test_a_v1_base_is_accepted_where_the_host_root_is_expected(self):
        """People paste whichever URL their app shows them."""
        with mock.patch.object(P, "_get", _stub({"/api/v0/models": LMS_V0})):
            self.assertIsNotNone(P.probe_openai("http://127.0.0.1:1234/v1"))

    def test_nothing_answering_is_none_not_empty(self):
        with mock.patch.object(P, "_get", _stub({})):
            self.assertIsNone(P.probe_ollama("http://127.0.0.1:11434"))
            self.assertIsNone(P.probe_openai("http://127.0.0.1:1234"))

    def test_probe_any_reports_the_dialect(self):
        with mock.patch.object(P, "_get", _stub({"/api/tags": OLLAMA_TAGS})):
            self.assertEqual(P.probe_any("http://box:11434")[0], "ollama")
        with mock.patch.object(P, "_get", _stub({"/api/v0/models": LMS_V0})):
            self.assertEqual(P.probe_any("http://box:1234")[0], "openai")
        with mock.patch.object(P, "_get", _stub({})):
            self.assertIsNone(P.probe_any("http://box:9999"))


class UrlShapeTest(unittest.TestCase):
    """embed_url takes the /v1 base, distill_url takes the host root. Getting
    this wrong by hand is the #1 way a healthy LM Studio looks dead."""

    def test_openai_dialect_splits_the_two_urls(self):
        prov = P.Provider("lmstudio", "LM Studio", "http://127.0.0.1:1234", [])
        self.assertEqual(prov.embed_url, "http://127.0.0.1:1234/v1")
        self.assertEqual(prov.distill_url, "http://127.0.0.1:1234")

    def test_a_v1_base_is_not_doubled(self):
        prov = P.Provider("custom", "c", "http://box:1234/v1", [], dialect="openai")
        self.assertEqual(prov.embed_url, "http://box:1234/v1")
        self.assertEqual(prov.distill_url, "http://box:1234")

    def test_ollama_wants_the_root_for_both(self):
        prov = P.Provider("ollama", "Ollama", "http://127.0.0.1:11434", [])
        self.assertEqual(prov.embed_backend, "ollama")
        self.assertEqual(prov.embed_url, "http://127.0.0.1:11434")
        self.assertEqual(prov.distill_url, "http://127.0.0.1:11434")


class MatchTest(unittest.TestCase):
    """A catalog spec is what you'd type to DOWNLOAD; no runtime serves it back
    under that name."""

    def _lms(self):
        return P.Provider("lmstudio", "LM Studio", "http://127.0.0.1:1234", [
            P.Model("text-embedding-nomic-embed-text-v1.5", "embed"),
            P.Model("text-embedding-paraphrase-multilingual-mpnet-base-v2.gguf", "embed"),
            P.Model("qwen/qwen3-4b-2507", "llm"),
            P.Model("google/gemma-4-e4b", "llm"),
        ])

    def test_download_spec_finds_the_served_id(self):
        prov = self._lms()
        self.assertEqual(prov.matches("nomic-embed-text", "embed").id,
                         "text-embedding-nomic-embed-text-v1.5")
        self.assertEqual(prov.matches("paraphrase-multilingual-mpnet", "embed").id,
                         "text-embedding-paraphrase-multilingual-mpnet-base-v2.gguf")
        self.assertEqual(prov.matches("qwen3-4b-2507", "llm").id, "qwen/qwen3-4b-2507")

    def test_a_different_model_is_not_a_match(self):
        # gemma-4-e4b on disk must not satisfy a request for gemma-3-4b
        self.assertIsNone(self._lms().matches("gemma-3-4b", "llm"))
        self.assertIsNone(self._lms().matches("bge-m3", "embed"))

    def test_kind_is_respected(self):
        self.assertIsNone(self._lms().matches("nomic-embed-text", "llm"))

    def test_ollama_tags_match_loosely(self):
        prov = P.Provider("ollama", "Ollama", P.OLLAMA_URL,
                          [P.Model("qwen2.5:3b", "llm")])
        self.assertTrue(prov.has("qwen2.5:3b"))
        self.assertTrue(prov.has("qwen2.5"))       # bare repo, no tag
        self.assertFalse(prov.has("qwen3:4b"))


class StatusTest(unittest.TestCase):
    def test_three_states_read_differently(self):
        up = P.Provider("lmstudio", "LM Studio", "http://127.0.0.1:1234",
                        [P.Model("a", "llm")], installed=True)
        idle = P.Provider("ollama", "Ollama", P.OLLAMA_URL, None, installed=True)
        gone = P.Provider("llamacpp", "llama.cpp", P.LLAMACPP_URL, None, installed=False)
        self.assertIn("running", up.status())
        self.assertIn("1 model", up.status())
        self.assertEqual(idle.status(), "installed, not running")
        self.assertEqual(gone.status(), "not installed")

    def test_running_is_about_answering_not_about_having_models(self):
        empty = P.Provider("lmstudio", "LM Studio", "http://127.0.0.1:1234", [])
        self.assertTrue(empty.running)          # up, just nothing downloaded
        self.assertFalse(P.Provider("lmstudio", "LM Studio", "x", None).running)


class PullResolveTest(unittest.TestCase):
    """`lms get` exits 0 even when its search finds nothing, so the id has to be
    confirmed by re-probing rather than trusted."""

    def _prov(self):
        return P.Provider("lmstudio", "LM Studio", "http://127.0.0.1:1234",
                          [P.Model("qwen/qwen3-4b-2507", "llm")])

    def test_returns_the_id_that_appeared(self):
        prov = self._prov()

        def fake_refresh(p, wait=0.0):
            p.models = list(p.models) + [P.Model("text-embedding-bge-m3", "embed")]
            return True

        with mock.patch.object(P, "pull", return_value=True), \
             mock.patch.object(P, "refresh", fake_refresh):
            self.assertEqual(P.pull_and_resolve(prov, "bge-m3", "embed"),
                             "text-embedding-bge-m3")

    def test_a_silent_no_op_download_resolves_to_nothing(self):
        prov = self._prov()
        with mock.patch.object(P, "pull", return_value=True), \
             mock.patch.object(P, "refresh", lambda p, wait=0.0: True):
            self.assertIsNone(P.pull_and_resolve(prov, "no-such-model", "embed"))

    def test_a_failed_download_never_reports_a_model(self):
        with mock.patch.object(P, "pull", return_value=False):
            self.assertIsNone(P.pull_and_resolve(self._prov(), "bge-m3", "embed"))


class CatalogTest(unittest.TestCase):
    def test_only_runtimes_we_can_drive_have_downloads(self):
        self.assertTrue(P.catalog("lmstudio", "embed"))
        self.assertTrue(P.catalog("lmstudio", "llm"))
        self.assertEqual(P.catalog("llamacpp", "embed"), [])
        self.assertEqual(P.catalog("custom", "llm"), [])

    def test_defaults_are_multilingual_safe(self):
        embed, _ = P.defaults("lmstudio", accelerated=False)
        self.assertIn("multilingual", embed)

    def test_the_distill_pick_is_never_a_reasoning_build(self):
        # A <think> trace eats the whole distill timeout and yields no lessons.
        for accel in (True, False):
            _, llm = P.defaults("lmstudio", accel)
            self.assertIn("instruct", llm)


if __name__ == "__main__":
    unittest.main()
