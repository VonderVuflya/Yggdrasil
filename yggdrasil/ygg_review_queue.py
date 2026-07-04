#!/usr/bin/env python3
"""Build a review queue for duplicate, stale, and conflicting memories."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

try:
    from .ygg_core import RestMemoryBackend, metadata_of, record_is_archived
except ImportError:  # flat layout (deployed scripts dir / tests / direct run)
    from ygg_core import RestMemoryBackend, metadata_of, record_is_archived


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def content_of(record: dict[str, Any]) -> str:
    return str(record.get("memory") or record.get("content") or "")


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9а-яё]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def project_key(record: dict[str, Any]) -> str:
    return str(metadata_of(record).get("project") or record.get("project") or "global")


def type_key(record: dict[str, Any]) -> str:
    return str(metadata_of(record).get("type") or record.get("memory_type") or "memory")


def record_ref(record: dict[str, Any]) -> dict[str, Any]:
    content = content_of(record)
    metadata = metadata_of(record)
    return {
        "id": record.get("id"),
        "project": project_key(record),
        "type": type_key(record),
        "source": metadata.get("source"),
        "created_at": record.get("created_at"),
        "content_hash": metadata.get("content_hash") or short_hash(content),
        "preview": " ".join(content.split())[:220],
    }


def find_exact_duplicates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        metadata = metadata_of(record)
        digest = metadata.get("content_hash") or short_hash(content_of(record))
        buckets[(project_key(record), type_key(record), str(digest))].append(record)
    issues = []
    for (project, memory_type, digest), group in buckets.items():
        if len(group) > 1:
            issues.append(
                {
                    "kind": "exact_duplicate",
                    "severity": "medium",
                    "project": project,
                    "type": memory_type,
                    "content_hash": digest,
                    "recommendation": "Keep the oldest/highest-evidence memory and delete or archive exact duplicates.",
                    "records": [record_ref(record) for record in sorted(group, key=lambda item: item.get("created_at") or 0)],
                }
            )
    return issues


def find_near_duplicates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        normalized = normalize_text(content_of(record))
        words = normalized.split()
        signature = " ".join(words[:32])
        if len(signature) >= 80:
            buckets[(project_key(record), type_key(record), signature)].append(record)
    issues = []
    for (project, memory_type, signature), group in buckets.items():
        ids = {record.get("id") for record in group}
        if len(ids) > 1:
            issues.append(
                {
                    "kind": "near_duplicate",
                    "severity": "low",
                    "project": project,
                    "type": memory_type,
                    "signature": signature[:140],
                    "recommendation": "Review for possible consolidation; these records share the same opening content.",
                    "records": [record_ref(record) for record in sorted(group, key=lambda item: item.get("created_at") or 0)],
                }
            )
    return issues


def find_stale_or_conflict_markers(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues = []
    content_marker_re = re.compile(
        r"\b(memory stale|stale memory|outdated memory|superseded by|repo wins|repository wins|contradicts repo|conflicts with repo|deprecated decision)\b",
        re.I,
    )
    status_marker_re = re.compile(r"\b(stale|outdated|superseded|contradict|conflict|deprecated|repo_wins)\b", re.I)
    for record in records:
        content = content_of(record)
        metadata = metadata_of(record)
        status = str(metadata.get("status") or "")
        if content_marker_re.search(content) or status_marker_re.search(status):
            issues.append(
                {
                    "kind": "stale_or_conflict_marker",
                    "severity": "high",
                    "project": project_key(record),
                    "type": type_key(record),
                    "recommendation": "Verify against repository reality. If stale, archive/update the memory rather than trusting it.",
                    "records": [record_ref(record)],
                }
            )
    return issues


def markdown_queue(report: dict[str, Any]) -> str:
    lines = [
        "---",
        f'created_at: "{report["created_at"]}"',
        f'status: "{report["status"]}"',
        f"issue_count: {report['issue_count']}",
        "---",
        "",
        "# Yggdrasil Memory Review Queue",
        "",
        f"Generated: {report['created_at']}",
        "",
    ]
    if not report["issues"]:
        lines.append("No review issues found.")
        return "\n".join(lines) + "\n"
    for index, issue in enumerate(report["issues"], start=1):
        lines.extend(
            [
                f"## {index}. {issue['kind']} ({issue['severity']})",
                "",
                f"- project: `{issue.get('project')}`",
                f"- type: `{issue.get('type')}`",
                f"- recommendation: {issue.get('recommendation')}",
                "",
            ]
        )
        for record in issue["records"]:
            lines.extend(
                [
                    f"### {record.get('id')}",
                    "",
                    f"- source: `{record.get('source')}`",
                    f"- content_hash: `{record.get('content_hash')}`",
                    f"- preview: {record.get('preview')}",
                    "",
                ]
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", default=os.environ.get("YGG_USER_ID", "demo-user"))
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output-dir", default="vault/99-review")
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    backend = RestMemoryBackend()
    all_records = backend.get_all(user_id=args.user_id, limit=args.limit)
    data = [record for record in all_records if not record_is_archived(record)]
    issues = []
    issues.extend(find_exact_duplicates(data))
    issues.extend(find_near_duplicates(data))
    issues.extend(find_stale_or_conflict_markers(data))
    severity_order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda issue: (severity_order.get(issue["severity"], 9), issue["kind"], issue.get("project") or ""))

    created_at = dt.datetime.now(tz=dt.timezone.utc).isoformat()
    report = {
        "created_at": created_at,
        "status": "review_needed" if issues else "clean",
        "user_id": args.user_id,
        "memory_count": len(data),
        "issue_count": len(issues),
        "issues": issues,
    }

    REPORTS.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS / f"review-queue-{int(dt.datetime.now().timestamp())}.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(report_path)

    if not args.json_only:
        output_dir = ROOT / args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "memory-review-queue.md"
        md_path.write_text(markdown_queue(report))
        print(md_path)

    print(json.dumps({"status": report["status"], "memory_count": len(data), "issue_count": len(issues)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
