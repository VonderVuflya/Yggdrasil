"""OpenAIEmbedder: the OpenAI-compatible /v1/embeddings backend (llama.cpp,
OpenRouter, LM Studio, vLLM). Wire format, auth header, batch/index handling,
context-overflow shortening, and backend selection in get_embedder — all with a
mocked urlopen so the suite stays offline."""

import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from yggdrasil import ygg_embeddings as E


def _resp(payload: dict):
    """A urlopen() context-manager stub returning `payload` as JSON bytes."""
    body = json.dumps(payload).encode("utf-8")
    cm = mock.MagicMock()
    cm.__enter__.return_value = io.BytesIO(body)
    cm.__exit__.return_value = False
    return cm


def _openai_payload(vectors):
    return {"data": [{"index": i, "embedding": v} for i, v in enumerate(vectors)]}


class WireFormatTest(unittest.TestCase):
    def test_endpoint_and_payload_and_auth(self):
        seen = {}

        def fake_urlopen(req, timeout=None):  # noqa: ARG001
            seen["url"] = req.full_url
            seen["headers"] = {k.lower(): v for k, v in req.header_items()}
            seen["body"] = json.loads(req.data.decode("utf-8"))
            return _resp(_openai_payload([[0.1, 0.2, 0.3]]))

        emb = E.OpenAIEmbedder("http://host:8080/v1", "bge", api_key="sk-xyz")
        with mock.patch.object(E.urllib.request, "urlopen", fake_urlopen):
            vec = emb.embed("hello")

        self.assertEqual(vec, [0.1, 0.2, 0.3])
        self.assertEqual(seen["url"], "http://host:8080/v1/embeddings")
        self.assertEqual(seen["headers"].get("authorization"), "Bearer sk-xyz")
        self.assertEqual(seen["body"]["model"], "bge")
        self.assertEqual(seen["body"]["input"], ["hello"])

    def test_no_auth_header_without_key(self):
        def fake_urlopen(req, timeout=None):  # noqa: ARG001
            assert "Authorization" not in dict(req.header_items())
            return _resp(_openai_payload([[1.0]]))

        emb = E.OpenAIEmbedder("http://local/v1", "m")  # no key (local llama-server)
        with mock.patch.object(E.urllib.request, "urlopen", fake_urlopen):
            self.assertEqual(emb.embed("x"), [1.0])

    def test_url_accepts_full_embeddings_path(self):
        emb = E.OpenAIEmbedder("https://openrouter.ai/api/v1/embeddings", "m")
        self.assertEqual(emb.endpoint, "https://openrouter.ai/api/v1/embeddings")
        emb2 = E.OpenAIEmbedder("https://openrouter.ai/api/v1/", "m")
        self.assertEqual(emb2.endpoint, "https://openrouter.ai/api/v1/embeddings")


class BatchTest(unittest.TestCase):
    def test_batch_aligned_and_respects_index(self):
        # Server returns items out of order; embedder must reorder by "index".
        out_of_order = {"data": [
            {"index": 1, "embedding": [2.0]},
            {"index": 0, "embedding": [1.0]},
        ]}
        with mock.patch.object(E.urllib.request, "urlopen", lambda req, timeout=None: _resp(out_of_order)):
            emb = E.OpenAIEmbedder("http://h/v1", "m")
            self.assertEqual(emb.embed_batch(["a", "b"]), [[1.0], [2.0]])

    def test_batch_shape_mismatch_returns_none(self):
        with mock.patch.object(E.urllib.request, "urlopen",
                               lambda req, timeout=None: _resp(_openai_payload([[1.0]]))):
            emb = E.OpenAIEmbedder("http://h/v1", "m")
            self.assertIsNone(emb.embed_batch(["a", "b"]))  # asked 2, got 1

    def test_empty_batch(self):
        emb = E.OpenAIEmbedder("http://h/v1", "m")
        self.assertEqual(emb.embed_batch([]), [])


class ResilienceTest(unittest.TestCase):
    def test_500_then_shorten_and_succeed(self):
        calls = {"n": 0}

        def fake_urlopen(req, timeout=None):  # noqa: ARG001
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.HTTPError(req.full_url, 500, "overflow", {}, None)
            return _resp(_openai_payload([[9.0]]))

        emb = E.OpenAIEmbedder("http://h/v1", "m")
        with mock.patch.object(E.urllib.request, "urlopen", fake_urlopen):
            self.assertEqual(emb.embed("x" * 1000), [9.0])
        self.assertGreaterEqual(calls["n"], 2)  # retried after shortening

    def test_transport_error_returns_none(self):
        def boom(req, timeout=None):  # noqa: ARG001
            raise urllib.error.URLError("connection refused")

        emb = E.OpenAIEmbedder("http://h/v1", "m")
        with mock.patch.object(E.urllib.request, "urlopen", boom):
            self.assertIsNone(emb.embed("x"))
            self.assertIsNone(emb.embed_batch(["a"]))

    def test_4xx_returns_none_without_shorten(self):
        calls = {"n": 0}

        def fake_urlopen(req, timeout=None):  # noqa: ARG001
            calls["n"] += 1
            raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", {}, None)

        emb = E.OpenAIEmbedder("http://h/v1", "m", api_key="bad")
        with mock.patch.object(E.urllib.request, "urlopen", fake_urlopen):
            self.assertIsNone(emb.embed("x"))
        self.assertEqual(calls["n"], 3)  # 3 outer retries, no inner shorten loop


class BackendSelectionTest(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in
                       ("YGG_EMBED_MODEL", "YGG_EMBED_BACKEND", "YGG_EMBED_URL",
                        "YGG_EMBED_API_KEY", "OPENROUTER_API_KEY")}
        for k in self._saved:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_default_is_ollama(self):
        os.environ["YGG_EMBED_MODEL"] = "all-minilm"
        self.assertIsInstance(E.get_embedder(), E.OllamaEmbedder)

    def test_openai_backend_selected(self):
        os.environ["YGG_EMBED_MODEL"] = "bge"
        os.environ["YGG_EMBED_BACKEND"] = "openai"
        os.environ["YGG_EMBED_URL"] = "http://127.0.0.1:8080/v1"
        e = E.get_embedder()
        self.assertIsInstance(e, E.OpenAIEmbedder)
        self.assertEqual(e.endpoint, "http://127.0.0.1:8080/v1/embeddings")

    def test_openrouter_key_fallback(self):
        os.environ["YGG_EMBED_MODEL"] = "openai/text-embedding-3-small"
        os.environ["YGG_EMBED_BACKEND"] = "openrouter"
        os.environ["OPENROUTER_API_KEY"] = "sk-or-123"
        e = E.get_embedder()
        self.assertIsInstance(e, E.OpenAIEmbedder)
        self.assertEqual(e.api_key, "sk-or-123")

    def test_no_model_means_no_embedder(self):
        self.assertIsNone(E.get_embedder())


if __name__ == "__main__":
    unittest.main()
