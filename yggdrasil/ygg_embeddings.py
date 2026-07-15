#!/usr/bin/env python3
"""Optional embedding provider for dense/semantic retrieval.

Dense search is OPT-IN: the engine stays zero-dependency and pure-lexical by
default. Set ``YGG_EMBED_MODEL`` (e.g. ``all-minilm``) to enable embeddings via
a local Ollama server (``YGG_EMBED_URL``, default http://127.0.0.1:11434). No
Python ML dependency, no API key — the model runs locally and privately.

When enabled, the engine stores an embedding per memory and fuses lexical
(BM25) with vector (cosine) ranking, so paraphrased queries that share meaning
but not words still retrieve the right memory.
"""

from __future__ import annotations

import json
import math
import os
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


def get_embedder() -> OllamaEmbedder | None:
    """Return an embedder iff dense search is configured, else None (lexical)."""
    model = os.environ.get("YGG_EMBED_MODEL")
    if not model:
        return None
    url = os.environ.get("YGG_EMBED_URL", "http://127.0.0.1:11434")
    return OllamaEmbedder(url, model)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0
