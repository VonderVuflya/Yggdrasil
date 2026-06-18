#!/usr/bin/env python3
"""Yggdrasil MVP quality gate for the engine-backed demo."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
YGG = Path(__file__).resolve().parent / "ygg.py"
YGG_MCP = Path(__file__).resolve().parent / "ygg_mcp_server.py"
REPORTS = ROOT / "reports"
DEFAULT_URL = os.environ.get("YGG_ENGINE_URL", "http://127.0.0.1:42069")
DEFAULT_TOKEN = os.environ.get("YGG_ENGINE_TOKEN") or os.environ.get("YGG_ENGINE_TOKEN") or "yggdrasil-demo-token"


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("YGG_ENGINE_URL", DEFAULT_URL)
    env.setdefault("YGG_ENGINE_TOKEN", DEFAULT_TOKEN)
    env.setdefault("YGG_NAMESPACE", "yggdrasil-demo")
    env.setdefault("YGG_USER_ID", "demo-user")
    return subprocess.run(args, cwd=ROOT, env=env, text=True, capture_output=True, check=check)


def health() -> dict[str, Any]:
    with urllib.request.urlopen(DEFAULT_URL + "/health", timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        DEFAULT_URL + path,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {DEFAULT_TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def search(project: str, query: str) -> list[dict[str, Any]]:
    payload = {
        "query": query,
        "user_id": "demo-user",
        "limit": 5,
        "rerank": False,
        "filters": {"project": project, "scope": "project"},
        "namespaces": ["yggdrasil-demo"],
    }
    return post("/search", payload).get("data", [])


def mcp_smoke() -> dict[str, Any]:
    env = os.environ.copy()
    env.setdefault("YGG_ENGINE_URL", DEFAULT_URL)
    env.setdefault("YGG_ENGINE_TOKEN", DEFAULT_TOKEN)
    env.setdefault("YGG_NAMESPACE", "yggdrasil-demo")
    env.setdefault("YGG_USER_ID", "demo-user")
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "quality-gate", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "ygg_bootstrap",
                "arguments": {"project": "test-a", "query": "mobile overflow chips", "limit": 2},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "ygg_remember",
                "arguments": {
                    "project": "test-a",
                    "type": "failed_approach",
                    "content": "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456",
                },
            },
        },
    ]
    stdin = "\n".join(json.dumps(message) for message in messages) + "\n"
    completed = subprocess.run(
        [str(YGG_MCP)],
        input=stdin,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    tools: list[str] = []
    bootstrap_text = ""
    secret_blocked = False
    for response in responses:
        result = response.get("result") or {}
        if response.get("id") == 2:
            tools = [tool.get("name") for tool in result.get("tools", [])]
        if response.get("id") == 3:
            bootstrap_text = (result.get("content") or [{}])[0].get("text", "")
        if response.get("id") == 4:
            text = (result.get("content") or [{}])[0].get("text", "")
            secret_blocked = bool(result.get("isError")) and "Refusing to save" in text
    return {
        "returncode": completed.returncode,
        "stderr": completed.stderr.strip(),
        "tools": tools,
        "bootstrap_text": bootstrap_text,
        "secret_blocked": secret_blocked,
        "ok": (
            completed.returncode == 0
            and {"ygg_health", "ygg_bootstrap", "ygg_search", "ygg_remember", "ygg_materialize"}.issubset(set(tools))
            and "debugging_lesson" in bootstrap_text
            and secret_blocked
        ),
    }


def main() -> int:
    started = time.time()
    results: dict[str, Any] = {
        "started_at": started,
        "root": str(ROOT),
        "backend_url": DEFAULT_URL,
        "checks": {},
    }
    failures: list[str] = []

    try:
        results["health_before"] = health()
        results["checks"]["health_ok"] = results["health_before"].get("status") == "ok"
    except (urllib.error.URLError, TimeoutError) as exc:
        results["checks"]["health_ok"] = False
        failures.append(f"health failed: {exc}")

    if not failures:
        bootstrap = run([str(YGG), "bootstrap", "--project", "test-a", "--query", "mobile overflow chips", "--limit", "5"])
        results["bootstrap_stdout"] = bootstrap.stdout
        results["checks"]["bootstrap_finds_test_a_lesson"] = "debugging_lesson" in bootstrap.stdout and "project=test-a" in bootstrap.stdout
        if not results["checks"]["bootstrap_finds_test_a_lesson"]:
            failures.append("bootstrap did not find test-a debugging lesson")

        a_overflow = search("test-a", "scrollWidth clientWidth chips overflow")
        b_overflow = search("test-b", "scrollWidth clientWidth chips overflow")
        a_text = json.dumps(a_overflow)
        b_text = json.dumps(b_overflow)
        results["isolation_samples"] = {
            "test_a_count": len(a_overflow),
            "test_b_count": len(b_overflow),
            "test_a_ids": [item.get("id") for item in a_overflow],
            "test_b_ids": [item.get("id") for item in b_overflow],
        }
        results["checks"]["test_a_no_test_b_leak"] = '"project": "test-b"' not in a_text and "YGG_B_BETA" not in a_text
        results["checks"]["test_b_no_test_a_leak"] = '"project": "test-a"' not in b_text and "YGG_A_ALPHA" not in b_text and "debugging_lesson" not in b_text
        if not results["checks"]["test_a_no_test_b_leak"]:
            failures.append("test-a search leaked test-b memory")
        if not results["checks"]["test_b_no_test_a_leak"]:
            failures.append("test-b search leaked test-a memory")

        secret = run(
            [
                str(YGG),
                "remember",
                "--project",
                "test-a",
                "--type",
                "failed_approach",
                "--content",
                "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456",
            ],
            check=False,
        )
        results["secret_guard"] = {"returncode": secret.returncode, "stderr": secret.stderr.strip()}
        results["checks"]["secret_guard_blocks"] = secret.returncode != 0 and "Refusing to save" in secret.stderr
        if not results["checks"]["secret_guard_blocks"]:
            failures.append("secret guard did not block fake API key")

        mcp = mcp_smoke()
        results["mcp_smoke"] = mcp
        results["checks"]["mcp_facade_ok"] = bool(mcp["ok"])
        if not results["checks"]["mcp_facade_ok"]:
            failures.append("MCP facade smoke test failed")

        lesson_id = None
        for item in a_overflow:
            if (item.get("metadata") or {}).get("type") == "debugging_lesson":
                lesson_id = item.get("id")
                break
        if lesson_id:
            materialize = run(
                [
                    str(YGG),
                    "materialize",
                    "--id",
                    str(lesson_id),
                    "--project",
                    "test-a",
                    "--output-dir",
                    "vault/04-learnings",
                ]
            )
            note_path = ROOT / materialize.stdout.strip()
            results["materialized_note"] = str(note_path)
            note_text = note_path.read_text()
            results["checks"]["materialize_frontmatter"] = all(
                key in note_text.split("---", 2)[1] for key in ["id:", "type:", "project:", "scope:", "confidence:", "created_at:", "source:"]
            )
            if not results["checks"]["materialize_frontmatter"]:
                failures.append("materialized note missing required frontmatter")
        else:
            results["checks"]["materialize_frontmatter"] = False
            failures.append("no debugging_lesson id found for materialize check")

    results["duration_seconds"] = round(time.time() - started, 3)
    results["status"] = "pass" if not failures else "fail"
    results["failures"] = failures

    REPORTS.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS / f"quality-gate-{int(started)}.json"
    report_path.write_text(json.dumps(results, indent=2, sort_keys=True))
    print(report_path)
    print(json.dumps({"status": results["status"], "failures": failures, "checks": results["checks"]}, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
