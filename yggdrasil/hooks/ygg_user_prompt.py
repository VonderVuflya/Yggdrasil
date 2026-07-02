#!/usr/bin/env python3
"""Claude Code UserPromptSubmit hook: auto-recall relevant memory per request.

The hard problem with a memory tool is that the AGENT forgets to use it — a
passive "call ygg_recall before non-trivial work" instruction loses to the
agent's faster-feeling default (just grep / just ask). This hook removes the
decision: on EVERY user prompt it runs a cross-project recall and injects the
top matches as `additionalContext`, so relevant prior lessons are already in
front of the agent without it choosing to look. It also asks the agent to CITE
what it reused (`🌳 recalled: …`) — the visible breadcrumb that earns user trust.

Fail-safe + cheap by design: trivial prompts are skipped, only genuinely-relevant
hits (cosine gate) are injected, and any error prints nothing and exits 0.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

URL = os.environ.get("YGG_ENGINE_URL", "http://127.0.0.1:42069").rstrip("/")
NAMESPACE = os.environ.get("YGG_NAMESPACE", "yggdrasil-demo")
USER_ID = os.environ.get("YGG_USER_ID", "demo-user")
LIMIT = int(os.environ.get("YGG_RECALL_LIMIT", "3"))           # max memories injected
MIN_COSINE = float(os.environ.get("YGG_RECALL_MIN_SCORE", "0.5"))  # raw-cosine relevance gate
MIN_PROMPT_CHARS = 15                                          # skip trivial prompts


def token() -> str:
    tok = os.environ.get("YGG_ENGINE_TOKEN")
    if tok:
        return tok
    try:
        return (Path.home() / ".yggdrasil" / "token").read_text().strip()
    except OSError:
        return "yggdrasil-demo-token"


def duplicate_invocation(payload: dict) -> bool:
    """True when another registration of this hook already handled THIS prompt
    (plugin + `ygg hooks` double-registration would inject recall twice).
    Keyed by session + prompt hash with a short TTL, so the same prompt
    re-submitted later in the session still gets its recall."""
    sid = str(payload.get("session_id") or "")
    if not sid:
        return False
    import hashlib
    import tempfile
    import time
    key = hashlib.sha1((payload.get("prompt") or "").encode("utf-8", "replace")).hexdigest()[:10]
    lock = Path(tempfile.gettempdir()) / f"ygg-user-prompt-{sid}-{key}.lock"
    try:
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return False
    except FileExistsError:
        try:
            if time.time() - lock.stat().st_mtime < 15:
                return True
            lock.touch()  # stale lock from an earlier identical prompt — restamp
            return False
        except OSError:
            return False
    except OSError:
        return False  # can't lock -> better to risk a duplicate than inject nothing


def _relevant(item: dict) -> bool:
    """Absolute relevance gate so off-topic prompts inject nothing. Prefer the raw
    cosine (vector_score); fall back to the fused score for lexical-only setups."""
    vs = item.get("vector_score")
    if vs is not None:
        return float(vs) >= MIN_COSINE
    return float(item.get("score") or 0) >= 1.0  # lexical-only: require a real keyword hit


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return 0
    prompt = (payload.get("prompt") or "").strip()
    # Skip trivial / command prompts — no useful recall, not worth the latency.
    if len(prompt) < MIN_PROMPT_CHARS or prompt.startswith("/"):
        return 0
    if duplicate_invocation(payload):
        return 0

    try:
        body = json.dumps({
            "query": prompt[:500],          # cross-project recall on the actual request
            "user_id": USER_ID,
            "limit": max(LIMIT * 2, 5),     # over-fetch, then gate + cap
            "rerank": False,
            "filters": {},                  # no project filter — "have I done this anywhere?"
            "namespaces": [NAMESPACE],
        }).encode("utf-8")
        req = urllib.request.Request(URL + "/search", data=body, method="POST",
                                     headers={"Authorization": f"Bearer {token()}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read()).get("data", [])
    except Exception:
        return 0  # fail-safe: never block or slow a prompt

    hits = [it for it in data if _relevant(it)][:LIMIT]
    if not hits:
        return 0  # inject nothing rather than noise

    lines = [
        "🌳 Possibly relevant from the user's durable memory (auto-recalled for THIS request).",
        "Reuse it if it applies — and when you do, cite it inline as `🌳 recalled: <gist>` so the",
        "user can see the memory working. Verify against the actual code; memory can be stale.",
    ]
    for it in hits:
        meta = it.get("metadata") or {}
        proj = meta.get("project") or "?"
        mtype = meta.get("type") or "memory"
        text = " ".join((it.get("memory") or "").split())[:220]
        lines.append(f"- [{proj} · {mtype}] {text}")
    context = "\n".join(lines)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                             "additionalContext": context}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
