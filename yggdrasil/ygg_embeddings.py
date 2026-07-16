#!/usr/bin/env python3
"""Optional embedding provider for dense/semantic retrieval.

Dense search is OPT-IN: the engine stays zero-dependency and pure-lexical by
default. Set ``YGG_EMBED_MODEL`` (e.g. ``all-minilm``) to enable embeddings via
a local Ollama server (``YGG_EMBED_URL``, default http://127.0.0.1:11434). No
Python ML dependency — the model runs locally and privately.

Two wire protocols, chosen by ``YGG_EMBED_BACKEND``:
  * ``ollama`` (default) — Ollama's ``/api/embeddings`` + ``/api/embed``.
  * ``openai`` — the OpenAI-compatible ``/v1/embeddings`` served by llama.cpp's
    ``llama-server --embeddings``, OpenRouter, LM Studio, vLLM, and friends.
    Point ``YGG_EMBED_URL`` at the ``/v1`` base and set ``YGG_EMBED_API_KEY``
    (Bearer) for hosted providers; a local llama-server needs no key.

When enabled, the engine stores an embedding per memory and fuses lexical
(BM25) with vector (cosine) ranking, so paraphrased queries that share meaning
but not words still retrieve the right memory.
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request
from typing import Sequence

# urllib's default User-Agent is "Python-urllib/3.x", which the bot filters in
# front of proxied endpoints (Cloudflare on *.proxy.runpod.net, for one) reject
# with 403 — silently killing dense search against a remote box. Identify as a
# real product string instead; the same guard already lives in ygg_seed.
_HTTP_HEADERS = {"Content-Type": "application/json", "User-Agent": "yggdrasil-embed"}


class OllamaEmbedder:
    """Minimal embedding client for a local Ollama server (stdlib only)."""

    def __init__(self, url: str, model: str, timeout: int = 120):
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def embed(self, text: str) -> list[float] | None:
        """Embed one text, riding out transient proxy hiccups. A remote endpoint
        (e.g. RunPod) drops the occasional request; without a retry those become
        permanently-unembedded memories that silently degrade dense recall. Retry
        the whole attempt a few times with backoff before giving up."""
        for attempt in range(3):
            vec = self._embed_attempt(text)
            if vec is not None:
                return vec
            time.sleep(0.4 * (attempt + 1))
        return None

    def _embed_attempt(self, text: str) -> list[float] | None:
        # Embedding models have a small context window (~512 tokens). Long
        # memories overflow it (HTTP 500), so cap the input and, on overflow,
        # halve and retry — the title/summary/opening carries the retrieval
        # signal anyway.
        payload_text = (text or "").strip()[:4000]
        if not payload_text:
            return None
        # Primary: the legacy single endpoint /api/embeddings. On context overflow
        # (500) shorten and retry; on ANY other failure fall through to the newer
        # /api/embed, which some Ollama builds and hosted proxies (e.g. RunPod)
        # serve INSTEAD of the legacy one. Without this fallback, dense search
        # silently degrades to lexical against such a server.
        for _ in range(5):
            body = json.dumps({"model": self.model, "prompt": payload_text}).encode("utf-8")
            req = urllib.request.Request(
                self.url + "/api/embeddings", data=body,
                headers=dict(_HTTP_HEADERS), method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    vec = json.loads(resp.read()).get("embedding")
                if isinstance(vec, list) and vec:
                    return vec
                break  # 200 but no usable vector → try /api/embed
            except urllib.error.HTTPError as exc:
                if exc.code >= 500 and len(payload_text) > 200:
                    payload_text = payload_text[: len(payload_text) // 2]  # context overflow → shorten
                    continue
                break  # 404 (endpoint absent) / other 4xx → try /api/embed
            except (urllib.error.URLError, TimeoutError, ValueError):
                break
        batch = self.embed_batch([payload_text])  # newer /api/embed, single item
        return batch[0] if batch else None

    def embed_batch(self, texts: Sequence[str]) -> list[list[float] | None] | None:
        """Embed many texts in ONE request via Ollama's /api/embed (newer API).

        Returns a list aligned with `texts` (None for any that produced nothing),
        or None if the endpoint is unavailable/older — the caller then falls back
        to per-item embed(). Turns a cold-start reindex of N memories from N round
        trips into ceil(N/batch)."""
        items = [(t or "").strip()[:4000] for t in texts]
        if not items:
            return []
        body = json.dumps({"model": self.model, "input": items}).encode("utf-8")
        req = urllib.request.Request(
            self.url + "/api/embed", data=body,
            headers=dict(_HTTP_HEADERS), method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                embs = json.loads(resp.read()).get("embeddings")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
            return None  # older Ollama (no /api/embed) or transport error -> caller loops
        if not isinstance(embs, list) or len(embs) != len(items):
            return None
        return [e if isinstance(e, list) and e else None for e in embs]


class OpenAIEmbedder:
    """Embedding client for any OpenAI-compatible ``/v1/embeddings`` server.

    Covers llama.cpp's ``llama-server --embeddings``, OpenRouter, LM Studio,
    vLLM, and text-embeddings-inference — none of which speak Ollama's
    ``/api/embeddings``. ``url`` is the OpenAI base that already ends in ``/v1``
    (e.g. ``http://127.0.0.1:8080/v1`` for llama.cpp, ``https://openrouter.ai/api/v1``
    for OpenRouter); we POST to ``{url}/embeddings``. ``api_key`` is sent as a
    Bearer token when set (required by OpenRouter, ignored by a local llama-server).

    Same duck-typed contract as OllamaEmbedder — ``.model``, ``embed(text)`` and
    ``embed_batch(texts)`` — so MemoryStore uses either interchangeably."""

    def __init__(self, url: str, model: str, api_key: str = "", timeout: int = 120):
        base = url.rstrip("/")
        # Accept either the /v1 base or a full .../embeddings URL, so a user who
        # pastes the complete endpoint isn't punished with a 404.
        self.endpoint = base if base.endswith("/embeddings") else base + "/embeddings"
        self.model = model
        self.api_key = api_key or ""
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        h = dict(_HTTP_HEADERS)
        if self.api_key:
            h["Authorization"] = "Bearer " + self.api_key
        return h

    def _post(self, inputs: Sequence[str]) -> list[list[float] | None] | None:
        """One POST. Returns a list aligned with ``inputs`` (None per empty item),
        or None on any transport/HTTP/shape error so the caller can fall back."""
        body = json.dumps({"model": self.model, "input": list(inputs)}).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint, data=body, headers=self._headers(), method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read()).get("data")
        except urllib.error.HTTPError as exc:
            # 413/500 on a too-long input: signal overflow so embed() can shorten.
            if exc.code in (413, 500):
                raise
            return None
        except (urllib.error.URLError, TimeoutError, ValueError):
            return None
        if not isinstance(data, list) or len(data) != len(inputs):
            return None
        out: list[list[float] | None] = [None] * len(inputs)
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            idx = item.get("index", i)
            vec = item.get("embedding")
            if isinstance(vec, list) and vec and isinstance(idx, int) and 0 <= idx < len(out):
                out[idx] = vec
        return out

    def embed(self, text: str) -> list[float] | None:
        """Embed one text, riding out transient hiccups and context overflow —
        mirrors OllamaEmbedder.embed (retry with backoff; halve on 413/500)."""
        for attempt in range(3):
            payload_text = (text or "").strip()[:4000]
            if not payload_text:
                return None
            for _ in range(5):
                try:
                    batch = self._post([payload_text])
                except urllib.error.HTTPError:
                    if len(payload_text) > 200:
                        payload_text = payload_text[: len(payload_text) // 2]
                        continue
                    batch = None
                if batch is not None:
                    return batch[0]
                break
            time.sleep(0.4 * (attempt + 1))
        return None

    def embed_batch(self, texts: Sequence[str]) -> list[list[float] | None] | None:
        """Embed many texts in ONE request. Returns a list aligned with ``texts``
        (None for empties), or None if the request fails — the caller then falls
        back to per-item embed()."""
        items = [(t or "").strip()[:4000] for t in texts]
        if not items:
            return []
        try:
            return self._post(items)
        except urllib.error.HTTPError:
            return None  # overflow on a batch -> caller retries per-item


def get_embedder() -> OllamaEmbedder | OpenAIEmbedder | None:
    """Return an embedder iff dense search is configured, else None (lexical).

    ``YGG_EMBED_BACKEND`` picks the wire protocol: ``ollama`` (default,
    ``/api/embeddings``) or ``openai`` (``/v1/embeddings`` — llama.cpp, OpenRouter,
    LM Studio, vLLM, …). ``YGG_EMBED_API_KEY`` (Bearer) is used by the openai
    backend; it falls back to ``OPENROUTER_API_KEY`` for the common case."""
    model = os.environ.get("YGG_EMBED_MODEL")
    if not model:
        return None
    url = os.environ.get("YGG_EMBED_URL", "http://127.0.0.1:11434")
    backend = (os.environ.get("YGG_EMBED_BACKEND") or "ollama").strip().lower()
    if backend in ("openai", "openai-compatible", "llamacpp", "llama.cpp", "openrouter"):
        api_key = os.environ.get("YGG_EMBED_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or ""
        return OpenAIEmbedder(url, model, api_key)
    return OllamaEmbedder(url, model)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0
