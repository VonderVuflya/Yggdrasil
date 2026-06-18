#!/usr/bin/env python3
"""Create and record user-approved review actions for Yggdrasil memory issues."""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
from pathlib import Path
from typing import Any

try:
    from .ygg_core import BackendCapabilityError, RestMemoryBackend, record_is_archived
except ImportError:  # flat layout (deployed scripts dir / tests / direct run)
    from ygg_core import BackendCapabilityError, RestMemoryBackend, record_is_archived


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
DEFAULT_REVIEW_DIR = ROOT / "vault" / "99-review"
AUDIT_LOG = REPORTS / "review-action-audit.jsonl"


def utc_now() -> str:
    return dt.datetime.now(tz=dt.UTC).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def latest_review_report() -> Path:
    candidates = sorted(glob.glob(str(REPORTS / "review-queue-*.json")))
    if not candidates:
        raise SystemExit("No review queue reports found.")
    return Path(candidates[-1])


def latest_decisions() -> dict[str, dict[str, Any]]:
    decisions: dict[str, dict[str, Any]] = {}
    if not AUDIT_LOG.exists():
        return decisions
    for line in AUDIT_LOG.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        action_id_value = entry.get("action_id")
        if action_id_value and entry.get("decision"):
            decisions[str(action_id_value)] = entry
    return decisions


def append_audit(entry: dict[str, Any]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def load_source_user_id(bundle: dict[str, Any]) -> str | None:
    source = bundle.get("source_review_report")
    if not source:
        return None
    source_path = Path(source)
    if not source_path.is_absolute():
        source_path = ROOT / source_path
    if not source_path.exists():
        return None
    return load_json(source_path).get("user_id")


def find_memory(backend: RestMemoryBackend, memory_id: str, user_id: str | None, limit: int) -> dict[str, Any] | None:
    records = backend.get_all(user_id=user_id, limit=limit)
    for record in records:
        if record.get("id") == memory_id:
            return record
    return None


def action_id(kind: str, issue_index: int, record_id: str | None = None) -> str:
    suffix = f"-{record_id[:8]}" if record_id else ""
    return f"{kind}-{issue_index + 1}{suffix}"


def build_actions(report: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for issue_index, issue in enumerate(report.get("issues", [])):
        records = issue.get("records", [])
        if not records:
            continue
        if issue["kind"] == "exact_duplicate":
            canonical = records[0]
            actions.append(
                {
                    "id": action_id("keep", issue_index, canonical["id"]),
                    "status": "proposed",
                    "action": "keep",
                    "issue_kind": issue["kind"],
                    "project": issue.get("project"),
                    "type": issue.get("type"),
                    "memory_id": canonical["id"],
                    "reason": "Oldest record in exact duplicate group; keep as canonical unless evidence says otherwise.",
                    "requires_user_approval": True,
                }
            )
            for duplicate in records[1:]:
                actions.append(
                    {
                        "id": action_id("archive", issue_index, duplicate["id"]),
                        "status": "proposed",
                        "action": "archive",
                        "issue_kind": issue["kind"],
                        "project": issue.get("project"),
                        "type": issue.get("type"),
                        "memory_id": duplicate["id"],
                        "canonical_memory_id": canonical["id"],
                        "reason": "Exact duplicate content hash; archive after user approval.",
                        "requires_user_approval": True,
                    }
                )
        elif issue["kind"] == "near_duplicate":
            actions.append(
                {
                    "id": action_id("merge-proposal", issue_index),
                    "status": "proposed",
                    "action": "merge_proposal",
                    "issue_kind": issue["kind"],
                    "project": issue.get("project"),
                    "type": issue.get("type"),
                    "memory_ids": [record["id"] for record in records],
                    "canonical_memory_id": records[0]["id"],
                    "reason": "Near duplicate opening content; propose human-reviewed consolidation.",
                    "requires_user_approval": True,
                }
            )
        elif issue["kind"] == "stale_or_conflict_marker":
            actions.append(
                {
                    "id": action_id("verify-stale", issue_index, records[0]["id"]),
                    "status": "proposed",
                    "action": "verify_or_archive",
                    "issue_kind": issue["kind"],
                    "project": issue.get("project"),
                    "type": issue.get("type"),
                    "memory_id": records[0]["id"],
                    "reason": "Possible stale/conflicting memory; verify against repository reality before reuse.",
                    "requires_user_approval": True,
                }
            )
    return actions


def markdown_actions(bundle: dict[str, Any]) -> str:
    lines = [
        "---",
        f'created_at: "{bundle["created_at"]}"',
        f'source_review_report: "{bundle["source_review_report"]}"',
        f"action_count: {len(bundle['actions'])}",
        "---",
        "",
        "# Yggdrasil Memory Review Actions",
        "",
        "These are proposed actions only. Do not mutate durable memory without explicit user approval.",
        "",
    ]
    for action in bundle["actions"]:
        lines.extend(
            [
                f"## {action['id']}",
                "",
                f"- status: `{action['status']}`",
                f"- action: `{action['action']}`",
                f"- project: `{action.get('project')}`",
                f"- type: `{action.get('type')}`",
                f"- memory_id: `{action.get('memory_id') or ''}`",
                f"- canonical_memory_id: `{action.get('canonical_memory_id') or ''}`",
                f"- memory_ids: `{', '.join(action.get('memory_ids', []))}`",
                f"- reason: {action.get('reason')}",
                "",
            ]
        )
    return "\n".join(lines)


def write_bundle(actions: list[dict[str, Any]], review_report_path: Path, output_dir: Path) -> tuple[Path, Path]:
    created_at = utc_now()
    bundle = {
        "created_at": created_at,
        "source_review_report": str(review_report_path),
        "actions": actions,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS / f"review-actions-{int(dt.datetime.now().timestamp())}.json"
    json_path.write_text(json.dumps(bundle, indent=2, sort_keys=True))
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "memory-review-actions.md"
    md_path.write_text(markdown_actions(bundle))
    return json_path, md_path


def propose(args: argparse.Namespace) -> int:
    review_report_path = Path(args.review_report) if args.review_report else latest_review_report()
    report = load_json(review_report_path)
    actions = build_actions(report)
    json_path, md_path = write_bundle(actions, review_report_path, ROOT / args.output_dir)
    print(json_path)
    print(md_path)
    print(json.dumps({"action_count": len(actions), "source_review_report": str(review_report_path)}, indent=2))
    return 0


def record(args: argparse.Namespace) -> int:
    entry = {
        "created_at": utc_now(),
        "action_id": args.action_id,
        "decision": args.decision,
        "reason": args.reason,
        "actor": args.actor,
    }
    append_audit(entry)
    print(AUDIT_LOG)
    print(json.dumps(entry, indent=2, sort_keys=True))
    return 0


def _archive_one(
    backend: RestMemoryBackend,
    memory_id: str,
    metadata_patch: dict[str, Any],
    *,
    action_id: str,
    actor: str,
    dry_run: bool,
    user_id: str | None,
    limit: int,
) -> dict[str, Any]:
    """Non-destructively archive one memory, with dry-run + audit support."""
    mode = "dry-run" if dry_run else "execute"
    record = find_memory(backend, memory_id, user_id, limit)
    if not record:
        append_audit({"created_at": utc_now(), "event": "apply_archive", "mode": mode, "status": "missing", "action_id": action_id, "memory_id": memory_id, "actor": actor})
        return {"action_id": action_id, "memory_id": memory_id, "status": "missing"}
    if record_is_archived(record):
        append_audit({"created_at": utc_now(), "event": "apply_archive", "mode": mode, "status": "already_archived", "action_id": action_id, "memory_id": memory_id, "actor": actor})
        return {"action_id": action_id, "memory_id": memory_id, "status": "already_archived"}
    audit_entry = {"created_at": utc_now(), "event": "apply_archive", "mode": mode, "status": "planned" if dry_run else "attempted", "action_id": action_id, "memory_id": memory_id, "actor": actor, "metadata_patch": metadata_patch}
    if dry_run:
        append_audit(audit_entry)
        return {"action_id": action_id, "memory_id": memory_id, "status": "dry-run", "metadata_patch": metadata_patch}
    try:
        response = backend.archive_memory(memory_id, metadata_patch)
        audit_entry["status"] = "applied" if response.get("success") else "failed"
        audit_entry["response"] = response
    except BackendCapabilityError as exc:
        audit_entry["status"] = "failed"
        audit_entry["error"] = str(exc)
        response = {"success": False, "error": str(exc), "capability": "metadata_update"}
    except Exception as exc:
        audit_entry["status"] = "failed"
        audit_entry["error"] = repr(exc)
        response = {"success": False, "error": repr(exc)}
    append_audit(audit_entry)
    return {"action_id": action_id, "memory_id": memory_id, "status": audit_entry["status"], "response": response}


def _patch_one(
    backend: RestMemoryBackend,
    memory_id: str,
    metadata_patch: dict[str, Any],
    *,
    action_id: str,
    actor: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Non-destructive metadata patch (no archive), e.g. annotating a merge canonical."""
    mode = "dry-run" if dry_run else "execute"
    audit_entry = {"created_at": utc_now(), "event": "apply_merge_canonical", "mode": mode, "status": "planned" if dry_run else "attempted", "action_id": action_id, "memory_id": memory_id, "actor": actor, "metadata_patch": metadata_patch}
    if dry_run:
        append_audit(audit_entry)
        return {"action_id": action_id, "memory_id": memory_id, "status": "dry-run", "metadata_patch": metadata_patch}
    try:
        response = backend.update_memory(memory_id, metadata_patch=metadata_patch)
        audit_entry["status"] = "applied" if response.get("success") else "failed"
        audit_entry["response"] = response
    except BackendCapabilityError as exc:
        audit_entry["status"] = "failed"
        audit_entry["error"] = str(exc)
        response = {"success": False, "error": str(exc), "capability": "metadata_update"}
    except Exception as exc:
        audit_entry["status"] = "failed"
        audit_entry["error"] = repr(exc)
        response = {"success": False, "error": repr(exc)}
    append_audit(audit_entry)
    return {"action_id": action_id, "memory_id": memory_id, "status": audit_entry["status"], "response": response}


def apply_actions(args: argparse.Namespace) -> int:
    actions_report_path = Path(args.actions_report)
    bundle = load_json(actions_report_path)
    decisions = latest_decisions()
    user_id = args.user_id or load_source_user_id(bundle)
    dry_run = not args.execute
    results = []
    backend = RestMemoryBackend()

    for action in bundle.get("actions", []):
        decision = decisions.get(action["id"], {})
        if decision.get("decision") != "approve":
            continue
        kind = action.get("action")
        actor = args.actor

        if kind in ("archive", "verify_or_archive"):
            metadata_patch = {
                "status": "archived",
                "archived_by": "ygg_review_actions",
                "archived_at": utc_now(),
                "archive_reason": action.get("reason", "Approved review action archive."),
                "canonical_memory_id": action.get("canonical_memory_id"),
                "review_action_id": action["id"],
                "review_action": kind,
            }
            if kind == "verify_or_archive":
                metadata_patch["verified_stale"] = True
            results.append(
                _archive_one(backend, action["memory_id"], metadata_patch, action_id=action["id"], actor=actor, dry_run=dry_run, user_id=user_id, limit=args.limit)
            )

        elif kind == "merge_proposal":
            canonical = action.get("canonical_memory_id")
            members = [mid for mid in action.get("memory_ids", []) if mid != canonical]
            for member in members:
                metadata_patch = {
                    "status": "archived",
                    "archived_by": "ygg_review_actions",
                    "archived_at": utc_now(),
                    "archive_reason": action.get("reason", "Approved near-duplicate merge."),
                    "merged_into": canonical,
                    "review_action_id": action["id"],
                    "review_action": "merge_proposal",
                }
                results.append(
                    _archive_one(backend, member, metadata_patch, action_id=action["id"], actor=actor, dry_run=dry_run, user_id=user_id, limit=args.limit)
                )
            if canonical and members:
                results.append(
                    _patch_one(
                        backend,
                        canonical,
                        {"merged_from": members, "review_action_id": action["id"], "review_action": "merge_proposal_canonical"},
                        action_id=action["id"],
                        actor=actor,
                        dry_run=dry_run,
                    )
                )

        elif kind == "keep":
            results.append({"action_id": action["id"], "memory_id": action.get("memory_id"), "status": "kept"})

        else:
            results.append({"action_id": action["id"], "status": "skipped", "reason": f"unsupported action: {kind}"})

    summary = {
        "mode": "dry-run" if dry_run else "execute",
        "actions_report": str(actions_report_path),
        "approved_archive_actions_seen": len([item for item in results if item.get("status") not in {"skipped"}]),
        "results": results,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if all(result.get("status") not in {"failed", "missing"} for result in results) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("propose")
    p.add_argument("--review-report")
    p.add_argument("--output-dir", default="vault/99-review")
    p.set_defaults(func=propose)

    p = sub.add_parser("record")
    p.add_argument("--action-id", required=True)
    p.add_argument("--decision", choices=["approve", "reject", "needs-info"], required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--actor", default="user")
    p.set_defaults(func=record)

    p = sub.add_parser("apply")
    p.add_argument("--actions-report", required=True)
    p.add_argument("--user-id", help="engine user_id to scan; defaults to the source review report user_id.")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--actor", default="user")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview approved archive mutations. This is the default.")
    mode.add_argument("--execute", action="store_true", help="Actually apply approved archive mutations.")
    p.set_defaults(func=apply_actions)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
