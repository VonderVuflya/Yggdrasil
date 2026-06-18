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


def tool_schema() -> list[dict[str, Any]]:
    return [
        {
            "name": "ygg_health",
            "description": "Check backend health through the Yggdrasil facade.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "ygg_bootstrap",
            "description": "Search project-scoped durable memory before non-trivial work.",
            "inputSchema": {
                "type": "object",
                "required": ["project"],
                "properties": {
                    "project": {"type": "string"},
                    "query": {"type": "string", "default": ""},
                    "limit": {"type": "integer", "default": 5},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "ygg_search",
            "description": "Search memory with mandatory project scoping by default.",
            "inputSchema": {
                "type": "object",
                "required": ["project", "query"],
                "properties": {
                    "project": {"type": "string"},
                    "query": {"type": "string"},
                    "type": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                    "json": {"type": "boolean", "default": False},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "ygg_recall",
            "description": "Search durable memory ACROSS ALL projects for prior solutions/lessons. Use before solving a non-trivial problem to find similar past work to reuse.",
            "inputSchema": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "type": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                    "json": {"type": "boolean", "default": False},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "ygg_remember",
            "description": "Save reusable project memory. Refuses common secret patterns.",
            "inputSchema": {
                "type": "object",
                "required": ["project", "type", "content"],
                "properties": {
                    "project": {"type": "string"},
                    "type": {"type": "string"},
                    "content": {"type": "string"},
                    "source": {"type": "string", "default": "ygg-mcp"},
                    "confidence": {"type": "number"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "ygg_materialize",
            "description": "Export one memory id to an Obsidian-readable Markdown note.",
            "inputSchema": {
                "type": "object",
                "required": ["id", "project"],
                "properties": {
                    "id": {"type": "string"},
                    "project": {"type": "string"},
                    "output_dir": {"type": "string", "default": "vault/04-learnings"},
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
                    "serverInfo": {"name": "yggdrasil-mvp", "version": "0.1.0"},
                },
            )
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return success(message_id, {"tools": tool_schema()})
        if method == "tools/call":
            params = message.get("params") or {}
            text = call_tool(str(params.get("name")), params.get("arguments") or {})
            return success(message_id, {"content": [{"type": "text", "text": text}], "isError": False})
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
