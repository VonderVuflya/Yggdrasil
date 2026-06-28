#!/usr/bin/env python3
"""Minimal stdio MCP facade for the Yggdrasil MVP CLI.

This intentionally delegates to scripts/ygg.py so the CLI and MCP path share
the same payload normalization and secret guardrails.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
YGG = Path(__file__).resolve().parent / "ygg.py"


def _server_version() -> str:
    """Real package version for MCP `serverInfo` — installed metadata first
    (pip/uv/Glama), then the adjacent __init__.py for flat deploys."""
    try:
        from importlib.metadata import version
        return version("yggdrasil-memory")
    except Exception:
        pass
    try:
        for line in (Path(__file__).resolve().parent / "__init__.py").read_text().splitlines():
            if line.startswith("__version__"):
                return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return "0"


def tool_schema() -> list[dict[str, Any]]:
    # Rich, self-contained tool definitions: each description says what the tool
    # does, WHEN to use it (and when to prefer a sibling), what it returns, and an
    # example; every parameter is documented with constraints and examples. This
    # is what lets a host's LLM pick the right tool unaided.
    _TYPES = "'decision', 'lesson', 'convention', 'fix', 'project_status', 'follow_up', 'reference'"
    return [
        {
            "name": "ygg_health",
            "description": (
                "Health check for the local Yggdrasil memory engine. Returns the engine "
                "status, the total number of stored memories, and whether optional "
                "dense-vector embeddings are available (semantic search). Call this first "
                "if any memory operation fails unexpectedly, to confirm the local engine "
                "is running before retrying. Takes no arguments; read-only.\n\n"
                "Returns: a JSON status object, e.g. {\"ok\": true, \"count\": 873, "
                "\"embeddings_missing\": 0}."
            ),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "ygg_bootstrap",
            "description": (
                "Load the durable memory for ONE project at the start of work on it — the "
                "project-scoped counterpart to ygg_recall. Call this before any non-trivial "
                "task in a known project to surface prior decisions, conventions, lessons, "
                "and open status, so you don't repeat past work or contradict earlier "
                "choices. Read-only.\n\n"
                "When to use: you know which project you're working in and want its context. "
                "Prefer ygg_recall when you need cross-project matches ('have I solved this "
                "anywhere?'), and ygg_search for a targeted query within one project.\n\n"
                "Returns: the top-ranked memories scoped to the project (most-used and "
                "pinned first).\n"
                "Example: ygg_bootstrap(project=\"checkout-api\", query=\"webhook signing\")."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["project"],
                "properties": {
                    "project": {
                        "type": "string",
                        "description": "Project to scope to — usually the git repository name, e.g. \"checkout-api\".",
                    },
                    "query": {
                        "type": "string",
                        "default": "",
                        "description": "Optional focus to rank within the project, e.g. \"payment retries\". Leave empty to get the project's most relevant memories overall.",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "description": "Maximum number of memories to return (default 5). Raise for a fuller picture; lower to keep context small.",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "ygg_search",
            "description": (
                "Search durable memory within a SINGLE project, with an optional type filter "
                "— the precise, project-scoped query tool. Use when you know which project a "
                "fact lives in and want targeted results (e.g. every 'decision' in "
                "'webdesk'). Read-only.\n\n"
                "When to use: a focused lookup inside one known project. Prefer ygg_recall "
                "for cross-project discovery, or ygg_bootstrap to load a project's overall "
                "context at once.\n\n"
                "Returns: ranked memories matching the query (lexical BM25, plus semantic "
                "when embeddings are enabled).\n"
                "Example: ygg_search(project=\"webdesk\", query=\"SSR hydration\", type=\"lesson\")."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["project", "query"],
                "properties": {
                    "project": {
                        "type": "string",
                        "description": "Project to search within — typically the git repo name, e.g. \"webdesk\".",
                    },
                    "query": {
                        "type": "string",
                        "description": "Free-text query describing what you're looking for, e.g. \"flaky e2e tests\".",
                    },
                    "type": {
                        "type": "string",
                        "description": f"Optional filter by memory type, one of: {_TYPES}. Omit to search all types.",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "description": "Maximum results to return (default 5).",
                    },
                    "json": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return raw JSON instead of formatted text (default false). Set true to parse fields programmatically.",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "ygg_recall",
            "description": (
                "Search durable memory ACROSS ALL projects for prior solutions, lessons, and "
                "decisions — the cross-project discovery tool. Call this BEFORE solving any "
                "non-trivial problem to find similar past work to reuse (e.g. \"have I fixed "
                "a flaky websocket reconnect before?\"). It is the single highest-value "
                "habit: it surfaces hard-won fixes from other projects you would otherwise "
                "repeat. Read-only.\n\n"
                "When to use: any time the current problem might resemble past work, "
                "regardless of project. To stay within one project, use ygg_search or "
                "ygg_bootstrap instead.\n\n"
                "Returns: the top matching memories ranked by relevance and usage, each "
                "tagged with its source project and type.\n"
                "Example: ygg_recall(query=\"rate limit retry with backoff\")."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language description of the problem or topic to find prior work for, e.g. \"token refresh before opening socket\".",
                    },
                    "type": {
                        "type": "string",
                        "description": f"Optional filter by memory type, one of: {_TYPES}. Omit to recall across all types.",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "description": "Maximum number of memories to return (default 5).",
                    },
                    "json": {
                        "type": "boolean",
                        "default": False,
                        "description": "Return raw JSON instead of formatted text (default false).",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "ygg_remember",
            "description": (
                "Save ONE durable, reusable fact to memory, scoped to a project — the write "
                "half of the loop. Call this whenever you make a decision, learn a lesson, "
                "fix a non-obvious bug, or hit a gotcha worth keeping for future sessions. "
                "Store one atomic fact per call (not a whole transcript), written to be "
                "useful out of context months later.\n\n"
                "Side effects: persists the memory locally (SQLite + Markdown). Semantic "
                "de-duplication merges near-identical memories automatically, and common "
                "secret patterns (API keys, tokens) are refused so credentials never land "
                "in memory.\n\n"
                "Returns: the saved memory id, or a notice if it merged into an existing "
                "duplicate.\n"
                "Example: ygg_remember(project=\"checkout-api\", type=\"lesson\", "
                "content=\"Webhook 401s were a rotated signing secret — update env + redeploy\")."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["project", "type", "content"],
                "properties": {
                    "project": {
                        "type": "string",
                        "description": "Project this fact belongs to — usually the git repo name, e.g. \"checkout-api\".",
                    },
                    "type": {
                        "type": "string",
                        "description": f"Memory category, one of: {_TYPES}.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The single durable fact to remember — one atomic idea, phrased so it's still useful with no surrounding context.",
                    },
                    "source": {
                        "type": "string",
                        "default": "ygg-mcp",
                        "description": "Provenance tag for where this memory came from (default \"ygg-mcp\"). Usually leave as default.",
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Optional confidence 0.0–1.0 in this fact; higher ranks it more strongly in recall. Defaults to the engine's standard for tool writes.",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "ygg_materialize",
            "description": (
                "Export one stored memory to a human-readable Markdown note "
                "(Obsidian-compatible) on disk. Use when the user wants to read, edit, or "
                "archive a specific memory as a file rather than query it. This is an "
                "export/read operation — it does not modify the stored memory.\n\n"
                "Requires the memory's id (from a prior ygg_search / ygg_recall / "
                "ygg_bootstrap result) and its project.\n\n"
                "Returns: the path of the written Markdown note.\n"
                "Example: ygg_materialize(id=\"ygg_4a5c82...\", project=\"content-factory\")."
            ),
            "inputSchema": {
                "type": "object",
                "required": ["id", "project"],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "The memory id to export, as returned by a prior search/recall/bootstrap, e.g. \"ygg_4a5c82a...\".",
                    },
                    "project": {
                        "type": "string",
                        "description": "The project the memory belongs to.",
                    },
                    "output_dir": {
                        "type": "string",
                        "default": "vault/04-learnings",
                        "description": "Directory to write the Markdown note into (default \"vault/04-learnings\").",
                    },
                },
                "additionalProperties": False,
            },
        },
    ]


def run_ygg(args: list[str]) -> str:
    env = os.environ.copy()
    env.setdefault("YGG_ENGINE_URL", "http://127.0.0.1:42069")
    env.setdefault("YGG_ENGINE_TOKEN", env.get("YGG_ENGINE_TOKEN", "yggdrasil-demo-token"))
    env.setdefault("YGG_NAMESPACE", "yggdrasil-demo")
    env.setdefault("YGG_USER_ID", "demo-user")
    completed = subprocess.run(
        [sys.executable, str(YGG), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    output = (completed.stdout + completed.stderr).strip()
    if completed.returncode != 0:
        raise RuntimeError(output or f"ygg.py exited with {completed.returncode}")
    return output


def call_tool(name: str, arguments: dict[str, Any]) -> str:
    if name == "ygg_health":
        return run_ygg(["health"])
    if name == "ygg_bootstrap":
        return run_ygg(
            [
                "bootstrap",
                "--project",
                str(arguments["project"]),
                "--query",
                str(arguments.get("query", "")),
                "--limit",
                str(arguments.get("limit", 5)),
            ]
        )
    if name == "ygg_search":
        args = [
            "search",
            "--project",
            str(arguments["project"]),
            "--query",
            str(arguments["query"]),
            "--limit",
            str(arguments.get("limit", 5)),
        ]
        if arguments.get("type"):
            args.extend(["--type", str(arguments["type"])])
        if arguments.get("json"):
            args.append("--json")
        return run_ygg(args)
    if name == "ygg_recall":
        args = ["recall", "--query", str(arguments["query"]), "--limit", str(arguments.get("limit", 5))]
        if arguments.get("type"):
            args.extend(["--type", str(arguments["type"])])
        if arguments.get("json"):
            args.append("--json")
        return run_ygg(args)
    if name == "ygg_remember":
        args = [
            "remember",
            "--project",
            str(arguments["project"]),
            "--type",
            str(arguments["type"]),
            "--source",
            str(arguments.get("source", "ygg-mcp")),
            "--content",
            str(arguments["content"]),
        ]
        if arguments.get("confidence") is not None:
            args.extend(["--confidence", str(arguments["confidence"])])
        return run_ygg(args)
    if name == "ygg_materialize":
        return run_ygg(
            [
                "materialize",
                "--id",
                str(arguments["id"]),
                "--project",
                str(arguments["project"]),
                "--output-dir",
                str(arguments.get("output_dir", "vault/04-learnings")),
            ]
        )
    raise RuntimeError(f"Unknown tool: {name}")


def success(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


_NOTICE_SHOWN = False


def _update_suffix() -> str:
    """A one-line 'newer version available' nudge, appended to the FIRST tool
    result of the session (so the agent can relay it), then never again."""
    global _NOTICE_SHOWN
    if _NOTICE_SHOWN:
        return ""
    _NOTICE_SHOWN = True
    try:
        try:
            from . import ygg_update_check
        except ImportError:
            import ygg_update_check  # type: ignore
        note = ygg_update_check.notice()
        return f"\n\n[yggdrasil] {note}" if note else ""
    except Exception:  # noqa: BLE001
        return ""


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    message_id = message.get("id")
    try:
        if method == "initialize":
            return success(
                message_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "yggdrasil", "version": _server_version()},
                },
            )
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return success(message_id, {"tools": tool_schema()})
        if method == "tools/call":
            params = message.get("params") or {}
            text = call_tool(str(params.get("name")), params.get("arguments") or {})
            return success(message_id, {"content": [{"type": "text", "text": text + _update_suffix()}], "isError": False})
        return error(message_id, -32601, f"Method not found: {method}")
    except Exception as exc:
        return success(message_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = error(None, -32700, f"Parse error: {exc}")
        else:
            response = handle(message)
        if response is not None:
            print(json.dumps(response, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
