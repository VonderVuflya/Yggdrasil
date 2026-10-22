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
    from . import ygg_config as _cfg
except ImportError:  # flat layout (deployed scripts dir / tests / direct run)
    from ygg_core import RestMemoryBackend, metadata_of, record_is_archived
    import ygg_config as _cfg


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


# Non-interactive consolidation (`ygg review --apply --yes`) archives a semantic
# group only when its WEAKEST pair is at least this alike. 0.95 catches
# rewordings that still differ in a detail worth keeping; those wait for a human.
AUTO_ARCHIVE_SIMILARITY = 0.97


def find_semantic_duplicates(backend: Any, *, user_id: str, namespace: str | None = None,
                             project: str | None = None, threshold: float = 0.95,
                             across_types: bool = True) -> list[dict[str, Any]] | None:
    """Embedding-cosine duplicate groups from the engine (POST /near_duplicates).
    Across types by default: on a real store most rewordings were the same note
    filed as fix/lesson/decision by different sessions. None when the engine
    can't answer — dense off, an older engine without the route, or an external
    backend — so the caller keeps the text-signature finder."""
    try:
        data = backend.request_json(
            "POST", "/near_duplicates",
            body={"user_id": user_id, "namespace": namespace, "project": project,
                  "threshold": threshold, "across_types": across_types},
            timeout=300,  # whole-store scan: seconds on a laptop, never the 30 s default's business
        ).get("data") or {}
    except Exception:  # noqa: BLE001 — any failure means "no semantic signal", not a broken review
        return None
    if not data.get("dense"):
        return None
    issues = []
    for group in data.get("groups") or []:
        similarity = float(group.get("similarity") or 0.0)
        refs = []
        for record in group.get("records") or []:
            ref = record_ref(record)
            ref["similarity"] = record.get("similarity")
            refs.append(ref)
        if len(refs) < 2:
            continue
        types = sorted({ref["type"] for ref in refs})
        mixed = len(types) > 1
        issues.append(
            {
                "kind": "near_duplicate",
                "match": "semantic",
                "severity": "medium" if similarity >= AUTO_ARCHIVE_SIMILARITY and not mixed else "low",
                "project": group.get("project") or "global",
                "type": "+".join(types),
                "types": types,
                "mixed_types": mixed,
                "similarity": similarity,
                "max_similarity": group.get("max_similarity"),
                "recommendation": (
                    "Same meaning filed under different types; decide which type should hold it, then archive the rest."
                    if mixed else
                    "Same meaning by embedding cosine; keep the oldest and archive the rest unless one adds a detail worth keeping."),
                "records": refs,
            }
        )
    return issues


def merge_duplicate_issues(exact: list[dict[str, Any]], semantic: list[dict[str, Any]],
                           textual: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One listing per duplicate group. A semantic group wholly inside an exact
    group adds nothing; a text-signature group inside either is the weaker
    signal for the same records. Overlapping-but-larger groups are kept."""
    def ids(issue: dict[str, Any]) -> frozenset:
        return frozenset(r.get("id") for r in issue.get("records") or [])

    exact_sets = [ids(i) for i in exact]
    kept_semantic = [i for i in semantic if not any(ids(i) <= e for e in exact_sets)]
    stronger = exact_sets + [ids(i) for i in semantic]
    kept_textual = [i for i in textual if not any(ids(i) <= s for s in stronger)]
    return exact + kept_semantic + kept_textual


def fetch_all_records(backend: Any, *, user_id: str, namespace: str | None = None,
                      limit: int | None = None) -> list[dict[str, Any]]:
    """Every record for the user, or the first `limit` when one is given.
    /get_all has no offset, so grow the window until a reply comes back short —
    a full reply means there may be more, never that the store ends there."""
    if limit:
        return backend.get_all(user_id=user_id, limit=limit, namespace=namespace)
    window = 10_000
    while True:
        records = backend.get_all(user_id=user_id, limit=window, namespace=namespace)
        if len(records) < window:
            return records
        window *= 4


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
            ]
        )
        if issue.get("similarity") is not None:
            lines.append(f"- similarity: {issue['similarity']:.3f} (weakest pair)")
        if issue.get("mixed_types"):
            lines.append(f"- types: {', '.join(issue['types'])} (mixed — never auto-archived)")
        lines.append("")
        for record in issue["records"]:
            lines.extend(
                [
                    f"### {record.get('id')}",
                    "",
                    f"- type: `{record.get('type')}`",
                    f"- source: `{record.get('source')}`",
                    f"- content_hash: `{record.get('content_hash')}`",
                    *([f"- similarity to oldest: {record['similarity']:.3f}"] if record.get("similarity") is not None else []),
                    f"- preview: {record.get('preview')}",
                    "",
                ]
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", default=_cfg.user_id())
    parser.add_argument("--limit", type=int, default=None, help="cap on records examined (default: the whole store)")
    parser.add_argument("--threshold", type=float, default=0.95, help="semantic near-duplicate cosine")
    parser.add_argument("--output-dir", default="vault/99-review")
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    backend = RestMemoryBackend()
    all_records = fetch_all_records(backend, user_id=args.user_id, limit=args.limit)
    data = [record for record in all_records if not record_is_archived(record)]
    semantic = find_semantic_duplicates(backend, user_id=args.user_id, threshold=args.threshold) or []
    issues = merge_duplicate_issues(find_exact_duplicates(data), semantic, find_near_duplicates(data))
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
