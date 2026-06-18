#!/usr/bin/env python3
"""Dense retrieval and dedupe quality gate for Yggdrasil + Muninn."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
YGG = Path(__file__).resolve().parent / "ygg.py"
REPORTS = ROOT / "reports"
URL = os.environ.get("YGG_MUNINN_URL", "http://127.0.0.1:42069")
TOKEN = os.environ.get("YGG_MUNINN_TOKEN") or os.environ.get("MUNINN_AUTH_TOKEN") or "yggdrasil-demo-token"
NAMESPACE = os.environ.get("YGG_NAMESPACE", "yggdrasil-dense")
USER_ID = os.environ.get("YGG_USER_ID", "dense-user")


def post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        URL + path,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def health() -> dict[str, Any]:
    with urllib.request.urlopen(URL + "/health", timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def add(project: str, content: str, memory_type: str = "debugging_lesson") -> dict[str, Any]:
    payload = {
        "content": content,
        "user_id": USER_ID,
        "namespace": NAMESPACE,
        "scope": "project",
        "metadata": {
            "project": project,
            "scope": "project",
            "type": memory_type,
            "source": "dense-gate",
            "confidence": 0.8,
            "muninn_skip_extraction": True,
        },
    }
    return post("/add", payload)["data"]


def ygg_remember(project: str, content: str, memory_type: str = "debugging_lesson") -> dict[str, Any]:
    env = os.environ.copy()
    env.setdefault("YGG_MUNINN_URL", URL)
    env.setdefault("YGG_MUNINN_TOKEN", TOKEN)
    env.setdefault("YGG_NAMESPACE", NAMESPACE)
    env.setdefault("YGG_USER_ID", USER_ID)
    completed = subprocess.run(
        [
            str(YGG),
            "remember",
            "--project",
            project,
            "--type",
            memory_type,
            "--source",
            "dense-gate-ygg",
            "--content",
            content,
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=True,
    )
    return json.loads(completed.stdout)


def search(project: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
    payload = {
        "query": query,
        "user_id": USER_ID,
        "limit": limit,
        "rerank": False,
        "filters": {"project": project, "scope": "project"},
        "namespaces": [NAMESPACE],
        "explain": True,
    }
    return post("/search", payload)["data"]


def main() -> int:
    started = time.time()
    lesson = (
        "type: debugging_lesson\n"
        "project: dense-a\n"
        "problem: Mobile hero causes horizontal scrolling on narrow phones\n"
        "symptoms:\n"
        "- page width is larger than the viewport on a 390px mobile screen\n"
        "- filter chips sit outside the right edge of the screen\n"
        "failed_approaches:\n"
        "- only shrinking text\n"
        "- hiding overflow on the body\n"
        "working_solution:\n"
        "- constrain the chip row container\n"
        "- allow chips to wrap onto multiple lines\n"
        "- verify with browser viewport measurements and a screenshot\n"
        "recognition_signals:\n"
        "- document scrollWidth exceeds clientWidth\n"
        "- chip bounding rectangles extend beyond viewport\n"
        "next_time:\n"
        "- check scrollWidth/clientWidth before visual polish\n"
    )
    unrelated = (
        "type: debugging_lesson\n"
        "project: dense-b\n"
        "problem: Payment webhook verification fails\n"
        "symptoms:\n"
        "- webhook returns 401\n"
        "- signing secret is stale\n"
        "working_solution:\n"
        "- rotate webhook secret\n"
        "- update local environment configuration\n"
    )

    results: dict[str, Any] = {
        "started_at": started,
        "backend_url": URL,
        "namespace": NAMESPACE,
        "user_id": USER_ID,
        "checks": {},
    }
    failures: list[str] = []

    results["health_before"] = health()
    results["checks"]["health_ok"] = results["health_before"].get("status") == "ok"
    if not results["checks"]["health_ok"]:
        failures.append("health failed")

    first = add("dense-a", lesson)
    second = add("dense-b", unrelated)
    duplicate = add("dense-a", lesson)
    ygg_first = ygg_remember("dense-a", lesson + "\nygg_exact_dedupe_probe: true\n")
    ygg_duplicate = ygg_remember("dense-a", lesson + "\nygg_exact_dedupe_probe: true\n")
    results["add_results"] = {
        "first": first,
        "second": second,
        "backend_duplicate": duplicate,
        "ygg_first": ygg_first,
        "ygg_duplicate": ygg_duplicate,
    }

    paraphrase_query = "phone layout is wider than the screen and chips spill past the edge"
    dense_a = search("dense-a", paraphrase_query)
    dense_b = search("dense-b", paraphrase_query)
    results["search"] = {
        "query": paraphrase_query,
        "dense_a": [
            {
                "id": item.get("id"),
                "project": (item.get("metadata") or {}).get("project"),
                "score": item.get("score"),
                "source": item.get("source"),
                "preview": (item.get("memory") or "")[:180],
            }
            for item in dense_a
        ],
        "dense_b": [
            {
                "id": item.get("id"),
                "project": (item.get("metadata") or {}).get("project"),
                "score": item.get("score"),
                "source": item.get("source"),
                "preview": (item.get("memory") or "")[:180],
            }
            for item in dense_b
        ],
    }

    dense_a_text = json.dumps(dense_a)
    dense_b_text = json.dumps(dense_b)
    duplicate_event = duplicate.get("event")
    duplicate_id = duplicate.get("id")

    results["checks"]["paraphrase_finds_dense_a"] = "Mobile hero causes horizontal scrolling" in dense_a_text
    results["checks"]["dense_a_no_dense_b_leak"] = '"project": "dense-b"' not in dense_a_text and "Payment webhook" not in dense_a_text
    results["checks"]["dense_b_no_dense_a_leak"] = '"project": "dense-a"' not in dense_b_text and "Mobile hero" not in dense_b_text
    results["checks"]["backend_duplicate_not_added"] = duplicate_event != "ADD" or duplicate_id in (None, first.get("id"))
    results["checks"]["ygg_duplicate_guard"] = ygg_duplicate.get("event") == "YGG_DUPLICATE_SKIP"

    if not results["checks"]["paraphrase_finds_dense_a"]:
        failures.append("paraphrase query did not retrieve dense-a lesson")
    if not results["checks"]["dense_a_no_dense_b_leak"]:
        failures.append("dense-a search leaked dense-b memory")
    if not results["checks"]["dense_b_no_dense_a_leak"]:
        failures.append("dense-b search leaked dense-a memory")
    if not results["checks"]["ygg_duplicate_guard"]:
        failures.append(f"Ygg exact duplicate guard failed: {ygg_duplicate}")

    results["duration_seconds"] = round(time.time() - started, 3)
    results["status"] = "pass" if not failures else "fail"
    results["failures"] = failures
    results["observations"] = []
    if not results["checks"]["backend_duplicate_not_added"]:
        results["observations"].append(
            f"Muninn backend exact duplicate was added as new memory: event={duplicate_event} id={duplicate_id}; Ygg wrapper guard is required."
        )

    REPORTS.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS / f"dense-gate-{int(started)}.json"
    report_path.write_text(json.dumps(results, indent=2, sort_keys=True))
    print(report_path)
    print(json.dumps({"status": results["status"], "failures": failures, "checks": results["checks"]}, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
