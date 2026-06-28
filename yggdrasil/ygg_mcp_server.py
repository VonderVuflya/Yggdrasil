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


#: Canonical memory categories (enum for `type`). The engine accepts any string,
#: but constraining the schema steers agents to the clean set — better recall
#: filtering and less type drift (e.g. "CONVENTION" / "key_decision" duplicates).
_MEMORY_TYPES = ["decision", "lesson", "convention", "fix", "project_status", "follow_up", "reference"]

#: MCP annotation presets. Declaring these lowers the disclosure burden on the
#: description (TDQS Behavioral Transparency) and tells hosts how each tool behaves.
_READ_HINTS = {"readOnlyHint": True, "idempotentHint": True, "destructiveHint": False, "openWorldHint": False}


def tool_schema() -> list[dict[str, Any]]:
    # Definitions are tuned to the six TDQS dimensions: a tight, front-loaded
    # description (purpose + scope + sibling differentiation + when/when-not),
    # MCP annotations carrying the behavioral profile, a meaningful title, and
    # all parameter meaning pushed into the schema (per-property descriptions +
    # an enum on `type`) so the prose stays concise while coverage stays 100%.
    return [
        {
            "name": "ygg_health",
            "title": "Check memory engine health",
            "description": (
                "Report the local Yggdrasil memory engine's health: running status, total "
                "stored-memory count, and whether semantic (dense-vector) search is "
                "available. Call this first when any other ygg_* tool fails unexpectedly, to "
                "confirm the engine is up before retrying. Returns a small JSON status object."
            ),
            "annotations": {"title": "Check memory engine health", **_READ_HINTS},
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "ygg_recall",
            "title": "Recall prior work across all projects",
            "description": (
                "Search durable memory ACROSS ALL projects for prior solutions, decisions, "
                "and lessons to reuse. Use BEFORE solving any non-trivial problem (\"have I "
                "handled this before?\"); for one known project use ygg_bootstrap to load its "
                "context or ygg_search for a targeted query instead. Ranks by relevance and "
                "past usage — lexical by default, semantic when embeddings are enabled."
            ),
            "annotations": {"title": "Recall prior work across all projects", **_READ_HINTS},
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
                        "enum": _MEMORY_TYPES,
                        "description": "Optional filter to one memory category. Omit to recall across all types.",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 50,
                        "description": "Maximum number of memories to return (default 5).",
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
            "name": "ygg_bootstrap",
            "title": "Load one project's memory",
            "description": (
                "Load the top durable memories for ONE project — decisions, conventions, "
                "lessons, and open status — to prime work at the start of a task. Use when "
                "you already know the project; for cross-project discovery use ygg_recall, "
                "for a targeted in-project query use ygg_search. Results are project-scoped "
                "and ranked, most-used and pinned first."
            ),
            "annotations": {"title": "Load one project's memory", **_READ_HINTS},
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
                        "description": "Optional focus to rank within the project, e.g. \"payment retries\". Leave empty for the project's most relevant memories overall.",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 50,
                        "description": "Maximum number of memories to return (default 5). Raise for a fuller picture; lower to keep context small.",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "ygg_search",
            "title": "Search one project's memory",
            "description": (
                "Search ONE project's durable memory with a free-text query and optional "
                "type filter — the precise, in-project lookup. Use when you know the project "
                "and want specific matches (e.g. every 'fix' about auth); for cross-project "
                "discovery use ygg_recall, to load a project's whole context use "
                "ygg_bootstrap. Lexical BM25 plus semantic ranking when embeddings are enabled."
            ),
            "annotations": {"title": "Search one project's memory", **_READ_HINTS},
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
                        "enum": _MEMORY_TYPES,
                        "description": "Optional filter to one memory category. Omit to search all types.",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 50,
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
            "name": "ygg_remember",
            "title": "Save a durable memory",
            "description": (
                "Persist ONE atomic, reusable fact (a decision, lesson, fix, convention, or "
                "status) to a project's durable memory for future sessions. Call right after "
                "you decide something, learn a lesson, or fix a non-obvious bug; store one "
                "idea per call, phrased to stand alone. Near-duplicates are merged "
                "automatically and obvious secrets (API keys, tokens) are refused. Returns "
                "the saved memory id."
            ),
            "annotations": {
                "title": "Save a durable memory",
                "readOnlyHint": False, "destructiveHint": False,
                "idempotentHint": False, "openWorldHint": False,
            },
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
                        "enum": _MEMORY_TYPES,
                        "description": "Memory category that best fits the fact.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The single durable fact — one atomic idea, phrased so it stays useful with no surrounding context.",
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
                        "description": "Optional confidence 0.0–1.0; higher ranks the memory more strongly in recall. Defaults to the engine's standard for tool writes.",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "ygg_materialize",
            "title": "Export a memory to Markdown",
            "description": (
                "Write ONE stored memory to a human-readable Markdown note "
                "(Obsidian-compatible) on disk; the stored memory itself is unchanged. Use "
                "when the user wants to read, edit, or archive a specific memory as a file. "
                "Needs the memory id from a prior ygg_recall / ygg_search / ygg_bootstrap "
                "result plus its project; returns the written file path."
            ),
            "annotations": {
                "title": "Export a memory to Markdown",
                "readOnlyHint": False, "destructiveHint": False,
                "idempotentHint": True, "openWorldHint": False,
            },
            "inputSchema": {
                "type": "object",
                "required": ["id", "project"],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "The memory id to export, as returned by a prior recall/search/bootstrap, e.g. \"ygg_4a5c82a...\".",
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
