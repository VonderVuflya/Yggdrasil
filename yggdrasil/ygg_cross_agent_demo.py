#!/usr/bin/env python3
"""Cross-agent shared-memory proof over the real MCP facade.

Demonstrates the core promise — different agents share one memory brain — using
two INDEPENDENT MCP stdio sessions against scripts/ygg_mcp_server.py:

  Agent A ("claude")  --(ygg_remember via MCP)-->  [ shared engine ]
  Agent B ("codex")   --(ygg_bootstrap via MCP)--> finds exactly A's record

Both sessions point at the same backend (default: Yggdrasil's own engine on
:42069) and the same namespace, so B can retrieve what A persisted. The proof:
B's bootstrap output contains the exact memory id A wrote.

Requires a running engine. Start one with:
    python3 scripts/ygg_memory_server.py --reset --db /tmp/ygg-demo.sqlite
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MCP = Path(__file__).resolve().parent / "ygg_mcp_server.py"
URL = os.environ.get("YGG_MUNINN_URL", "http://127.0.0.1:42069")
TOKEN = os.environ.get("YGG_MUNINN_TOKEN") or os.environ.get("MUNINN_AUTH_TOKEN") or "yggdrasil-demo-token"
NAMESPACE = os.environ.get("YGG_NAMESPACE", "yggdrasil-crossagent")
USER_ID = os.environ.get("YGG_USER_ID", "crossagent-user")
PROJECT = "cross-agent-demo"


def mcp_session(agent_label: str, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run one MCP stdio session: initialize, then issue the given tool calls."""
    env = os.environ.copy()
    env["YGG_MUNINN_URL"] = URL
    env["YGG_MUNINN_TOKEN"] = TOKEN
    env["YGG_NAMESPACE"] = NAMESPACE
    env["YGG_USER_ID"] = USER_ID
    messages: list[dict[str, Any]] = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": agent_label, "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
    ]
    for i, call in enumerate(calls, start=2):
        messages.append({"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": call})
    stdin = "\n".join(json.dumps(m) for m in messages) + "\n"
    completed = subprocess.run([sys.executable, str(MCP)], input=stdin, cwd=ROOT, env=env, text=True, capture_output=True, timeout=60)
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def tool_text(responses: list[dict[str, Any]], message_id: int) -> str:
    for r in responses:
        if r.get("id") == message_id:
            return (r.get("result", {}).get("content") or [{}])[0].get("text", "")
    return ""


def main() -> int:
    try:
        with urllib.request.urlopen(URL + "/health", timeout=3):
            pass
    except Exception:
        print(f"engine not reachable at {URL}. Start it: python3 scripts/ygg_memory_server.py --reset --db /tmp/ygg-demo.sqlite", file=sys.stderr)
        return 2

    stamp = int(time.time())
    marker = f"CROSS_AGENT_PROOF_{stamp}"
    content = (
        f"type: debugging_lesson\nproject: {PROJECT}\nmarker: {marker}\n"
        "problem: websocket reconnect storms after auth token refresh\n"
        "working_solution: refresh the token before opening the socket and retry with capped exponential backoff\n"
    )

    print(f"[agent A: claude]  ygg_remember -> project={PROJECT}")
    a = mcp_session("claude", [{"name": "ygg_remember", "arguments": {"project": PROJECT, "type": "debugging_lesson", "content": content, "source": "agent-claude"}}])
    a_text = tool_text(a, 2)
    try:
        saved_id = json.loads(a_text).get("id")
    except json.JSONDecodeError:
        saved_id = None
    print(f"                   saved id = {saved_id}")

    print(f"[agent B: codex ]  ygg_bootstrap -> project={PROJECT} (fresh MCP session)")
    b = mcp_session("codex", [{"name": "ygg_bootstrap", "arguments": {"project": PROJECT, "query": "websocket reconnect token refresh backoff", "limit": 5}}])
    b_text = tool_text(b, 2)

    found_id = bool(saved_id) and saved_id in b_text
    found_topic = "websocket reconnect" in b_text
    ok = found_id and found_topic

    report = {
        "status": "pass" if ok else "fail",
        "namespace": NAMESPACE,
        "project": PROJECT,
        "agent_a_saved_id": saved_id,
        "agent_b_found_saved_id": found_id,
        "agent_b_found_topic": found_topic,
        "agent_b_bootstrap_excerpt": " ".join(b_text.split())[:240],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if ok:
        print("\nCROSS-AGENT MEMORY PROVEN: agent B retrieved the exact record agent A wrote, via the shared engine.")
    else:
        print("\nCROSS-AGENT PROOF FAILED.", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
