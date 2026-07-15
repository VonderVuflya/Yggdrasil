#!/usr/bin/env python3
"""Gate for the full governance loop: merge_proposal and verify_or_archive.

The original demo only wired the `archive` action end-to-end (see
ygg_review_apply_gate.py). This gate proves the two remaining governance
actions now execute non-destructively:

- near-duplicate memories -> `merge_proposal`: archive non-canonical members,
  annotate the canonical with `merged_from`.
- stale/conflict-marked memory -> `verify_or_archive`: archive with a
  `verified_stale` tag.

Flow: seed -> review queue -> propose -> approve -> apply --execute -> verify.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from .ygg_core import RestMemoryBackend, YggConfig, metadata_of, record_is_archived
except ImportError:  # flat layout (deployed scripts dir / tests / direct run)
    from ygg_core import RestMemoryBackend, YggConfig, metadata_of, record_is_archived


ROOT = Path(__file__).resolve().parents[1]
REVIEW_QUEUE = Path(__file__).resolve().parent / "ygg_review_queue.py"
REVIEW_ACTIONS = Path(__file__).resolve().parent / "ygg_review_actions.py"
REPORTS = ROOT / "reports"
URL = os.environ.get("YGG_ENGINE_URL", "http://127.0.0.1:42069")
TOKEN = os.environ.get("YGG_ENGINE_TOKEN") or "yggdrasil-demo-token"

# >32 shared words so both near-duplicate memories share an identical 32-word
# signature (-> near_duplicate) while differing in the tail (-> not exact dup).
SHARED_PREFIX = (
    "problem: the marketing landing hero section overflows horizontally on small phones because the outer "
    "page container is wider than the device viewport and the call to action row together with the filter "
    "chip group both extend beyond the right edge of the available layout width on a very narrow phone screen "
)


def run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, env=env, text=True, capture_output=True, timeout=90, check=False)


def first_path(stdout: str) -> Path:
    for line in stdout.splitlines():
        if line.strip():
            path = Path(line.strip())
            return path if path.is_absolute() else ROOT / path
    raise RuntimeError("command did not print a report path")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def add(backend: RestMemoryBackend, project: str, mem_type: str, content: str, user_id: str, namespace: str) -> dict[str, Any]:
    payload = {
        "content": content,
        "user_id": user_id,
        "namespace": namespace,
        "scope": "project",
        "metadata": {
            "project": project,
            "scope": "project",
            "type": mem_type,
            "source": "governance-gate",
            "confidence": 0.7,
            "skip_extraction": True,
        },
    }
    return backend.add(payload)["data"]


def main() -> int:
    started = time.time()
    stamp = int(started)
    near_project = f"gov-near-{stamp}"
    stale_project = f"gov-stale-{stamp}"
    user_id = os.environ.get("YGG_GOV_GATE_USER_ID", f"gov-user-{stamp}")
    namespace = os.environ.get("YGG_GOV_GATE_NAMESPACE", "yggdrasil-governance")

    near_one = f"type: debugging_lesson\nproject: {near_project}\n{SHARED_PREFIX}\nvariant: first observed during the spring release regression sweep\n"
    near_two = f"type: debugging_lesson\nproject: {near_project}\n{SHARED_PREFIX}\nvariant: second observed during the autumn release regression sweep\n"
    stale_note = (
        f"type: decision\nproject: {stale_project}\nmarker: YGG_STALE\n"
        "note: this is stale memory and repo wins over memory; verify against the repository before reuse\n"
    )

    env = os.environ.copy()
    env.setdefault("YGG_ENGINE_URL", URL)
    env.setdefault("YGG_ENGINE_TOKEN", TOKEN)
    env["YGG_USER_ID"] = user_id
    env["YGG_NAMESPACE"] = namespace

    backend = RestMemoryBackend(YggConfig(url=URL.rstrip("/"), token=TOKEN, namespace=namespace, user_id=user_id))
    results: dict[str, Any] = {"started_at": started, "backend_url": URL, "user_id": user_id, "namespace": namespace, "checks": {}}
    failures: list[str] = []

    try:
        results["health_before"] = backend.health()
        results["checks"]["health_ok"] = results["health_before"].get("status") == "ok"
    except Exception as exc:
        results["checks"]["health_ok"] = False
        failures.append(f"health failed: {exc!r}")

    if not failures:
        one = add(backend, near_project, "debugging_lesson", near_one, user_id, namespace)
        two = add(backend, near_project, "debugging_lesson", near_two, user_id, namespace)
        stale = add(backend, stale_project, "decision", stale_note, user_id, namespace)
        near_ids = {one.get("id"), two.get("id")}
        stale_id = stale.get("id")
        results["seeded"] = {"near_ids": sorted(near_ids), "stale_id": stale_id}

        # 1) review queue detects near_duplicate + stale_or_conflict_marker
        queue = run([str(REVIEW_QUEUE), "--user-id", user_id, "--json-only"], env)
        if queue.returncode != 0:
            failures.append(f"review queue failed: {queue.stderr.strip()}")
        else:
            queue_report = load_json(first_path(queue.stdout))
            results["queue_report"] = str(first_path(queue.stdout))
            near_issue = next((i for i in queue_report.get("issues", []) if i.get("kind") == "near_duplicate" and i.get("project") == near_project), None)
            stale_issue = next((i for i in queue_report.get("issues", []) if i.get("kind") == "stale_or_conflict_marker" and i.get("project") == stale_project), None)
            results["checks"]["queue_detects_near_duplicate"] = near_issue is not None and near_ids.issubset({r.get("id") for r in (near_issue or {}).get("records", [])})
            results["checks"]["queue_detects_stale_marker"] = stale_issue is not None
            if not results["checks"]["queue_detects_near_duplicate"]:
                failures.append("review queue did not detect the near-duplicate pair")
            if not results["checks"]["queue_detects_stale_marker"]:
                failures.append("review queue did not detect the stale marker")

    if not failures:
        propose = run([str(REVIEW_ACTIONS), "propose", "--review-report", results["queue_report"]], env)
        if propose.returncode != 0:
            failures.append(f"propose failed: {propose.stderr.strip()}")
        else:
            bundle = load_json(first_path(propose.stdout))
            results["actions_report"] = str(first_path(propose.stdout))
            merge_action = next((a for a in bundle.get("actions", []) if a.get("action") == "merge_proposal" and a.get("project") == near_project), None)
            verify_action = next((a for a in bundle.get("actions", []) if a.get("action") == "verify_or_archive" and a.get("project") == stale_project), None)
            results["merge_action"] = merge_action
            results["verify_action"] = verify_action
            results["checks"]["merge_proposal_proposed"] = merge_action is not None and near_ids.issubset(set(merge_action.get("memory_ids", [])))
            results["checks"]["verify_or_archive_proposed"] = verify_action is not None and verify_action.get("memory_id") == stale_id
            if not results["checks"]["merge_proposal_proposed"]:
                failures.append("merge_proposal action was not proposed for the near-duplicate pair")
            if not results["checks"]["verify_or_archive_proposed"]:
                failures.append("verify_or_archive action was not proposed for the stale marker")

    if not failures:
        for action in (results["merge_action"], results["verify_action"]):
            rec = run([str(REVIEW_ACTIONS), "record", "--action-id", action["id"], "--decision", "approve", "--reason", "governance gate", "--actor", "governance-gate"], env)
            if rec.returncode != 0:
                failures.append(f"approval record failed for {action['id']}: {rec.stderr.strip()}")

    if not failures:
        execute = run([str(REVIEW_ACTIONS), "apply", "--actions-report", results["actions_report"], "--execute", "--user-id", user_id, "--actor", "governance-gate"], env)
        results["execute"] = {"returncode": execute.returncode, "stderr": execute.stderr.strip(), "summary": json.loads(execute.stdout) if execute.stdout.strip() else {}}
        if execute.returncode != 0:
            failures.append(f"apply --execute failed: {execute.stderr.strip()}")

    if not failures:
        records = {r.get("id"): r for r in backend.get_all(user_id=user_id, limit=200, namespace=namespace)}
        canonical_id = results["merge_action"].get("canonical_memory_id")
        member_ids = [mid for mid in results["merge_action"].get("memory_ids", []) if mid != canonical_id]
        member = records.get(member_ids[0]) if member_ids else None
        canonical = records.get(canonical_id)
        stale_rec = records.get(results["verify_action"].get("memory_id"))

        results["checks"]["merge_member_archived"] = bool(member) and record_is_archived(member) and metadata_of(member).get("merged_into") == canonical_id
        results["checks"]["merge_canonical_kept_and_annotated"] = bool(canonical) and not record_is_archived(canonical) and member_ids[0] in metadata_of(canonical).get("merged_from", [])
        results["checks"]["verify_or_archive_archived"] = bool(stale_rec) and record_is_archived(stale_rec) and metadata_of(stale_rec).get("verified_stale") is True
        for check in ("merge_member_archived", "merge_canonical_kept_and_annotated", "verify_or_archive_archived"):
            if not results["checks"][check]:
                failures.append(f"post-apply check failed: {check}")

    if not failures:
        queue_after = run([str(REVIEW_QUEUE), "--user-id", user_id, "--json-only"], env)
        if queue_after.returncode == 0:
            after = load_json(first_path(queue_after.stdout))
            after_ids = {r.get("id") for i in after.get("issues", []) for r in i.get("records", [])}
            archived_ids = {results["verify_action"].get("memory_id"), *[mid for mid in results["merge_action"].get("memory_ids", []) if mid != results["merge_action"].get("canonical_memory_id")]}
            results["checks"]["queue_ignores_archived"] = not (archived_ids & after_ids)
            if not results["checks"]["queue_ignores_archived"]:
                failures.append("follow-up queue still surfaced archived memories")

    results["duration_seconds"] = round(time.time() - started, 3)
    results["status"] = "pass" if not failures else "fail"
    results["failures"] = failures
    REPORTS.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS / f"governance-gate-{stamp}.json"
    report_path.write_text(json.dumps(results, indent=2, sort_keys=True))
    print(report_path)
    print(json.dumps({"status": results["status"], "failures": failures, "checks": results["checks"]}, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
