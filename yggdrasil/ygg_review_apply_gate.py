#!/usr/bin/env python3
"""Quality gate for approved review-action archive application."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from .ygg_core import RestMemoryBackend
except ImportError:  # flat layout (deployed scripts dir / tests / direct run)
    from ygg_core import RestMemoryBackend


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
REVIEW_QUEUE = Path(__file__).resolve().parent / "ygg_review_queue.py"
REVIEW_ACTIONS = Path(__file__).resolve().parent / "ygg_review_actions.py"
URL = os.environ.get("YGG_ENGINE_URL", "http://127.0.0.1:42069")
TOKEN = os.environ.get("YGG_ENGINE_TOKEN") or os.environ.get("YGG_ENGINE_TOKEN") or "yggdrasil-demo-token"


def run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, env=env, text=True, capture_output=True, timeout=90, check=False)


def first_path(stdout: str) -> Path:
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped:
            path = Path(stripped)
            return path if path.is_absolute() else ROOT / path
    raise RuntimeError("command did not print a report path")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def add_duplicate(backend: RestMemoryBackend, project: str, user_id: str, namespace: str, content: str) -> dict[str, Any]:
    payload = {
        "content": content,
        "user_id": user_id,
        "namespace": namespace,
        "scope": "project",
        "metadata": {
            "project": project,
            "scope": "project",
            "type": "debugging_lesson",
            "source": "review-apply-gate",
            "confidence": 0.75,
            "skip_extraction": True,
        },
    }
    return backend.add(payload)["data"]


def action_results(stdout: str) -> dict[str, Any]:
    return json.loads(stdout)


def record_ids(report: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for issue in report.get("issues", []):
        for record in issue.get("records", []):
            if record.get("id"):
                ids.add(record["id"])
    return ids


def main() -> int:
    started = time.time()
    stamp = int(started)
    project = f"review-apply-{stamp}"
    user_id = os.environ.get("YGG_APPLY_GATE_USER_ID", f"review-apply-user-{stamp}")
    namespace = os.environ.get("YGG_APPLY_GATE_NAMESPACE", "yggdrasil-review-apply")
    content = (
        "type: debugging_lesson\n"
        f"project: {project}\n"
        "problem: Approved review archive flow needs a repeatable smoke test\n"
        "symptoms:\n"
        "- review queue reports exact duplicate memories\n"
        "- action proposals need one safe non-destructive mutation path\n"
        "working_solution:\n"
        "- approve one archive action\n"
        "- dry-run the metadata patch\n"
        "- execute and mark the duplicate archived without deleting it\n"
        "recognition_signals:\n"
        "- metadata.status becomes archived\n"
        "- follow-up review queue ignores the archived duplicate\n"
    )
    env = os.environ.copy()
    env.setdefault("YGG_ENGINE_URL", URL)
    env.setdefault("YGG_ENGINE_TOKEN", TOKEN)
    env["YGG_USER_ID"] = user_id
    env["YGG_NAMESPACE"] = namespace

    results: dict[str, Any] = {
        "started_at": started,
        "backend_url": URL,
        "project": project,
        "user_id": user_id,
        "namespace": namespace,
        "checks": {},
    }
    failures: list[str] = []
    backend = RestMemoryBackend()

    try:
        results["health_before"] = backend.health()
        results["checks"]["health_ok"] = results["health_before"].get("status") == "ok"
    except Exception as exc:
        results["checks"]["health_ok"] = False
        failures.append(f"health failed: {exc!r}")

    if not failures:
        first = add_duplicate(backend, project, user_id, namespace, content)
        duplicate = add_duplicate(backend, project, user_id, namespace, content)
        results["added"] = {"canonical_candidate": first, "duplicate_candidate": duplicate}
        duplicate_id = duplicate.get("id")

        queue_before = run([str(REVIEW_QUEUE), "--user-id", user_id, "--json-only"], env)
        results["queue_before"] = {"returncode": queue_before.returncode, "stderr": queue_before.stderr.strip()}
        if queue_before.returncode != 0:
            failures.append(f"review queue before failed: {queue_before.stderr.strip()}")
        else:
            queue_before_path = first_path(queue_before.stdout)
            queue_before_report = load_json(queue_before_path)
            results["queue_before"]["report"] = str(queue_before_path)
            exact_issue = next(
                (
                    issue
                    for issue in queue_before_report.get("issues", [])
                    if issue.get("kind") == "exact_duplicate"
                    and issue.get("project") == project
                    and duplicate_id in {record.get("id") for record in issue.get("records", [])}
                ),
                None,
            )
            results["checks"]["queue_detects_exact_duplicate"] = exact_issue is not None
            if not exact_issue:
                failures.append("review queue did not find the gate duplicate")

        if not failures:
            propose = run([str(REVIEW_ACTIONS), "propose", "--review-report", results["queue_before"]["report"]], env)
            results["propose"] = {"returncode": propose.returncode, "stderr": propose.stderr.strip()}
            if propose.returncode != 0:
                failures.append(f"action proposal failed: {propose.stderr.strip()}")
            else:
                actions_path = first_path(propose.stdout)
                bundle = load_json(actions_path)
                results["propose"]["report"] = str(actions_path)
                archive_action = next(
                    (
                        action
                        for action in bundle.get("actions", [])
                        if action.get("action") == "archive"
                        and action.get("project") == project
                        and action.get("memory_id") == duplicate_id
                    ),
                    None,
                )
                results["archive_action"] = archive_action
                results["checks"]["archive_action_proposed"] = archive_action is not None
                if not archive_action:
                    failures.append("archive action was not proposed for the duplicate")

        if not failures:
            action_id = results["archive_action"]["id"]
            record = run(
                [
                    str(REVIEW_ACTIONS),
                    "record",
                    "--action-id",
                    action_id,
                    "--decision",
                    "approve",
                    "--reason",
                    "Review apply gate exact duplicate archive.",
                    "--actor",
                    "review-apply-gate",
                ],
                env,
            )
            results["record_approval"] = {"returncode": record.returncode, "stderr": record.stderr.strip()}
            if record.returncode != 0:
                failures.append(f"approval record failed: {record.stderr.strip()}")

        if not failures:
            dry_run = run(
                [
                    str(REVIEW_ACTIONS),
                    "apply",
                    "--actions-report",
                    results["propose"]["report"],
                    "--dry-run",
                    "--user-id",
                    user_id,
                    "--actor",
                    "review-apply-gate",
                ],
                env,
            )
            results["dry_run"] = {"returncode": dry_run.returncode, "stderr": dry_run.stderr.strip(), "stdout": dry_run.stdout}
            if dry_run.returncode != 0:
                failures.append(f"apply dry-run failed: {dry_run.stderr.strip()}")
            else:
                dry_summary = action_results(dry_run.stdout)
                results["dry_run"]["summary"] = dry_summary
                results["checks"]["dry_run_plans_archive"] = any(item.get("memory_id") == duplicate_id and item.get("status") == "dry-run" for item in dry_summary.get("results", []))
                if not results["checks"]["dry_run_plans_archive"]:
                    failures.append("dry-run did not plan the approved archive")

        if not failures:
            execute = run(
                [
                    str(REVIEW_ACTIONS),
                    "apply",
                    "--actions-report",
                    results["propose"]["report"],
                    "--execute",
                    "--user-id",
                    user_id,
                    "--actor",
                    "review-apply-gate",
                ],
                env,
            )
            results["execute"] = {"returncode": execute.returncode, "stderr": execute.stderr.strip(), "stdout": execute.stdout}
            if execute.returncode != 0:
                failures.append(f"apply execute failed: {execute.stderr.strip()}")
            else:
                execute_summary = action_results(execute.stdout)
                results["execute"]["summary"] = execute_summary
                results["checks"]["execute_applies_archive"] = any(item.get("memory_id") == duplicate_id and item.get("status") == "applied" for item in execute_summary.get("results", []))
                if not results["checks"]["execute_applies_archive"]:
                    failures.append("execute did not apply the approved archive")

        if not failures:
            records = backend.get_all(user_id=user_id, limit=50)
            archived_record = next((record for record in records if record.get("id") == duplicate_id), None)
            metadata = (archived_record or {}).get("metadata") or {}
            results["archived_record"] = {
                "id": (archived_record or {}).get("id"),
                "archived": (archived_record or {}).get("archived"),
                "metadata_status": metadata.get("status"),
                "canonical_memory_id": metadata.get("canonical_memory_id"),
                "review_action_id": metadata.get("review_action_id"),
            }
            results["checks"]["metadata_status_archived"] = metadata.get("status") == "archived"
            results["checks"]["top_level_archived"] = (archived_record or {}).get("archived") is True
            if not results["checks"]["metadata_status_archived"]:
                failures.append("archived memory metadata.status was not archived")
            if not results["checks"]["top_level_archived"]:
                failures.append("archived memory top-level archived flag was not true")

        if not failures:
            queue_after = run([str(REVIEW_QUEUE), "--user-id", user_id, "--json-only"], env)
            results["queue_after"] = {"returncode": queue_after.returncode, "stderr": queue_after.stderr.strip()}
            if queue_after.returncode != 0:
                failures.append(f"review queue after failed: {queue_after.stderr.strip()}")
            else:
                queue_after_path = first_path(queue_after.stdout)
                queue_after_report = load_json(queue_after_path)
                results["queue_after"]["report"] = str(queue_after_path)
                results["queue_after"]["status"] = queue_after_report.get("status")
                results["queue_after"]["memory_count"] = queue_after_report.get("memory_count")
                results["queue_after"]["issue_count"] = queue_after_report.get("issue_count")
                ids_after = record_ids(queue_after_report)
                results["checks"]["queue_ignores_archived_duplicate"] = duplicate_id not in ids_after
                if not results["checks"]["queue_ignores_archived_duplicate"]:
                    failures.append("follow-up review queue still included archived duplicate")

    results["duration_seconds"] = round(time.time() - started, 3)
    results["status"] = "pass" if not failures else "fail"
    results["failures"] = failures

    REPORTS.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS / f"review-apply-gate-{int(started)}.json"
    report_path.write_text(json.dumps(results, indent=2, sort_keys=True))
    print(report_path)
    print(json.dumps({"status": results["status"], "failures": failures, "checks": results["checks"]}, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
