#!/usr/bin/env python3
"""Yggdrasil memory CLI: a thin, safe facade over the engine's REST API."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from .ygg_core import RestMemoryBackend, YggConfig, YggError, record_is_archived
except ImportError:  # flat layout (deployed scripts dir / tests / direct run)
    from ygg_core import RestMemoryBackend, YggConfig, YggError, record_is_archived


DEFAULT_URL = "http://127.0.0.1:42069"
DEFAULT_NAMESPACE = "yggdrasil-demo"
DEFAULT_USER = "demo-user"  # unified identity — same store the MCP agent reads/writes

# Cosine >= this (when dense is on) means a near-duplicate of an existing memory —
# the write is skipped. High by default so only genuinely-redundant lessons drop.
SEMDEDUP_THRESHOLD = float(os.environ.get("YGG_SEMDEDUP_AT", "0.92"))

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"(?i)\b(api[_-]?key|token|password|secret|client_secret)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{12,}"),
]


def env_default(name: str, fallback: str) -> str:
    value = os.environ.get(name)
    return value if value else fallback


def engine_url() -> str:
    return env_default("YGG_ENGINE_URL", DEFAULT_URL).rstrip("/")


def namespace_default() -> str:
    return env_default("YGG_NAMESPACE", DEFAULT_NAMESPACE)


def user_default() -> str:
    return env_default("YGG_USER_ID", DEFAULT_USER)


_BACKEND: RestMemoryBackend | None = None


def backend() -> RestMemoryBackend:
    """Shared engine-agnostic REST client (from ygg_core), built from the env.

    The CLI no longer hand-rolls REST transport — it goes through the same
    backend contract the gates and review tools use, so swapping the engine
    (own server vs an external engine) flows through one place.
    """
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = RestMemoryBackend(YggConfig.from_env())
    return _BACKEND


def request_json(method: str, path: str, body: dict[str, Any] | None = None, query: dict[str, Any] | None = None) -> dict[str, Any]:
    return backend().request_json(method, path, body=body, query=query)


def health(_: argparse.Namespace) -> None:
    url = engine_url() + "/health"
    with urllib.request.urlopen(url, timeout=10) as response:
        print(response.read().decode("utf-8"))


def scan_for_secrets(text: str) -> list[str]:
    matches: list[str] = []
    for pattern in SECRET_PATTERNS:
        found = pattern.search(text)
        if found:
            matches.append(found.group(0)[:80])
    return matches


def require_safe_memory(content: str, metadata: dict[str, Any]) -> None:
    haystack = content + "\n" + json.dumps(metadata, sort_keys=True)
    matches = scan_for_secrets(haystack)
    if matches:
        raise YggError("Refusing to save possible secret(s): " + "; ".join(matches))


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def find_existing_hash(user_id: str, project: str, memory_type: str, digest: str, limit: int = 1000) -> dict[str, Any] | None:
    # Fast path: indexed server-side lookup — O(log n), correct at any store size.
    try:
        rec = request_json("GET", "/find_hash", query={
            "user_id": user_id, "project": project, "type": memory_type, "hash": digest,
        }).get("data")
        return rec or None
    except YggError:
        pass  # older engine without /find_hash — fall back to the bounded scan below
    try:
        result = request_json("GET", "/get_all", query={"user_id": user_id, "limit": limit})
    except YggError:
        return None
    for record in result.get("data", []):
        metadata = record.get("metadata") or {}
        if (
            not record_is_archived(record)
            and metadata.get("project") == project
            and metadata.get("type") == memory_type
            and metadata.get("content_hash") == digest
        ):
            return record
    return None


def render_value(value: Any, indent: int = 0) -> str:
    pad = " " * indent
    if isinstance(value, list):
        return "\n".join(f"{pad}- {render_value(item, indent + 2).lstrip()}" for item in value)
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            rendered = render_value(item, indent + 2)
            if "\n" in rendered:
                lines.append(f"{pad}{key}:\n{rendered}")
            else:
                lines.append(f"{pad}{key}: {rendered.strip()}")
        return "\n".join(lines)
    return str(value)


def load_content(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    metadata: dict[str, Any] = {}
    if args.json_file:
        data = json.loads(Path(args.json_file).read_text())
        if not isinstance(data, dict):
            raise YggError("--json-file must contain a JSON object.")
        metadata.update({k: data[k] for k in ("type", "confidence", "source") if k in data})
        return render_value(data), metadata
    if args.file:
        return Path(args.file).read_text(), metadata
    if args.content:
        return args.content, metadata
    raise YggError("Provide one of --content, --file, or --json-file.")


def _warn_related(args: argparse.Namespace, content: str, project: str,
                  memory_type: str, new_id: str | None) -> None:
    """After a write, surface lexically-similar existing memories (same project+type)
    so the caller can review them for supersede/merge — the in-agent conflict signal.
    Printed to stderr so stdout stays clean JSON; the MCP facade folds stderr into the
    tool output, so agents see it too."""
    payload = {
        "query": content[:300],
        "user_id": args.user_id,
        "limit": 4,
        "filters": {"project": project, "type": memory_type},
        "namespaces": [args.namespace],
    }
    try:
        data = request_json("POST", "/search", payload).get("data", [])
    except YggError:
        return
    related = [it for it in data if it.get("id") != new_id][:2]
    if not related:
        return
    print("\n⚠ similar existing memories (review for supersede/merge):", file=sys.stderr)
    for it in related:
        md = it.get("metadata") or {}
        preview = " ".join((it.get("memory") or "").split())[:120]
        print(f"  {it.get('id')}  ({md.get('type')})  {preview}", file=sys.stderr)
    print("  → replace an outdated one with:  ygg supersede --id <old-id>", file=sys.stderr)


def supersede(args: argparse.Namespace) -> None:
    """Archive an outdated memory that a newer one replaces (non-destructive)."""
    backend().archive_memory(args.id, {"superseded": True, "status": "superseded"})
    print(f"superseded (archived) {args.id}")


def delete(args: argparse.Namespace) -> None:
    """HARD delete one memory — irreversible. For 'this should never have been
    saved' (secrets, junk); prefer `ygg supersede` for merely-outdated memories."""
    request_json("POST", "/delete", {"memory_id": args.id})
    print(f"deleted {args.id} (irreversible)")


def reset(args: argparse.Namespace) -> None:
    """Bulk HARD delete by filter — the recovery path for a bad `ygg seed` or a
    model switch (previously: manual sqlite surgery). Previews the count and
    demands confirmation; always scoped to the namespace + user."""
    narrowing = {k: getattr(args, k) for k in ("project", "source", "type") if getattr(args, k)}
    if not narrowing and not args.all:
        raise YggError("Refusing to reset without a filter. Narrow with --project/--source/--type, "
                       "or pass --all to wipe the whole namespace.")
    payload: dict[str, Any] = {"user_id": args.user_id, "namespace": args.namespace,
                               "all": args.all, **narrowing}
    preview = request_json("POST", "/purge", {**payload, "dry_run": True})["data"]["deleted"]
    if preview == 0:
        print("(nothing matches — 0 memories to delete)")
        return
    scope = ", ".join(f"{k}={v}" for k, v in ({"namespace": args.namespace, **narrowing}).items())
    if not args.yes:
        if not sys.stdin.isatty():
            raise YggError(f"Would PERMANENTLY delete {preview} memories ({scope}). "
                           "Non-interactive run: pass --yes to confirm.")
        answer = input(f"About to PERMANENTLY delete {preview} memories ({scope}). "
                       f"Type 'delete' to confirm: ").strip()
        if answer != "delete":
            print("aborted — nothing deleted")
            return
    deleted = request_json("POST", "/purge", payload)["data"]["deleted"]
    print(f"deleted {deleted} memories (irreversible)")


def write_memory(
    *,
    content: str,
    project: str,
    memory_type: str,
    source: str | None,
    user_id: str,
    namespace: str,
    scope: str = "project",
    confidence: float | None = None,
    tags: list[str] | None = None,
    extract: bool = False,
    semantic_dedup: bool = True,
) -> tuple[str, dict[str, Any]]:
    """Core write path — secret-guard + content-hash dedup + add. No printing.

    Returns ``("added", record)`` or ``("duplicate", existing)``. Shared by the
    ``remember`` CLI command and by seed/distill so they all get the same
    dedup, secret refusal and provenance behavior.
    """
    metadata: dict[str, Any] = {
        "project": project,
        "scope": scope,
        "type": memory_type,
        "source": source or "ygg-cli",
        "skip_extraction": not extract,
    }
    if confidence is not None:
        metadata["confidence"] = confidence
    if tags:
        metadata["tags"] = list(dict.fromkeys(tags))  # de-dup, preserve order
    digest = content_hash(content)
    metadata["content_hash"] = digest
    require_safe_memory(content, metadata)
    existing = find_existing_hash(user_id, project, memory_type, digest)
    if existing:
        return ("duplicate", existing)
    payload = {
        "content": content,
        "user_id": user_id,
        "namespace": namespace,
        "scope": scope,
        "metadata": metadata,
    }
    if semantic_dedup:
        payload["dedupe_threshold"] = SEMDEDUP_THRESHOLD
    record = request_json("POST", "/add", payload)["data"]
    # The engine returns an existing record (not a fresh insert) on a near-dup.
    if record.get("event") == "SEMANTIC_DUPLICATE":
        return ("duplicate", record)
    return ("added", record)


def remember(args: argparse.Namespace) -> None:
    if args.scope == "project" and not args.project:
        raise YggError("--project is required for project-scoped memories.")
    content, file_metadata = load_content(args)
    project = args.project or "global"
    memory_type = args.type or file_metadata.get("type") or "memory"
    confidence = args.confidence if args.confidence is not None else file_metadata.get("confidence")
    status, record = write_memory(
        content=content,
        project=project,
        memory_type=memory_type,
        source=args.source or file_metadata.get("source"),
        user_id=args.user_id,
        namespace=args.namespace,
        scope=args.scope,
        confidence=confidence,
        tags=getattr(args, "tag", None),
        extract=args.extract,
    )
    if status == "duplicate":
        if record.get("event") == "SEMANTIC_DUPLICATE":
            print(json.dumps({"event": "YGG_SEMANTIC_DUPLICATE_SKIP", "id": record.get("id"),
                              "similarity": record.get("similarity")}, indent=2, sort_keys=True))
        else:
            print(json.dumps({"event": "YGG_DUPLICATE_SKIP", "id": record.get("id"),
                              "content_hash": content_hash(content)}, indent=2, sort_keys=True))
        return
    print(json.dumps(record, indent=2, sort_keys=True))
    _warn_related(args, content, project, memory_type, record.get("id"))


def search(args: argparse.Namespace) -> None:
    if args.scope == "project" and not args.project:
        raise YggError("--project is required for project-scoped search.")
    # Match a project across scopes, so memories saved global-but-tagged to the
    # project are found here too (use `ygg recall` for cross-project/global facts).
    filters: dict[str, Any] = {}
    if args.project:
        filters["project"] = args.project
    else:
        filters["scope"] = args.scope
    if args.type:
        filters["type"] = args.type
    if getattr(args, "tag", None):
        filters["tag"] = args.tag
    payload = {
        "query": args.query,
        "user_id": args.user_id,
        "limit": args.limit,
        "rerank": args.rerank,
        "filters": filters,
        "namespaces": [args.namespace],
        "explain": args.explain,
    }
    result = request_json("POST", "/search", payload)
    if args.json:
        print(json.dumps(result["data"], indent=2, sort_keys=True))
        return
    hits = result["data"]
    if not hits:
        if args.project:
            print(f'(no matches in project "{args.project}" — try '
                  f'`ygg recall --query "{args.query}"` to span every project + global memory)')
        else:
            print("(no matches)")
        return
    for item in hits:
        _print_hit(item)


def _print_hit(item: dict[str, Any]) -> None:
    """Render one search/recall hit with provenance (source, confidence, usage, pin)."""
    md = item.get("metadata") or {}
    pin = " 📌" if (item.get("pinned") or md.get("pinned")) else ""
    src = md.get("source") or item.get("source") or "?"
    conf = item.get("confidence")
    conf_s = f"{conf:.2f}" if isinstance(conf, (int, float)) else "?"
    used = item.get("access_count") or 0
    score = item.get("score")
    score_s = f"{score:.4f}" if isinstance(score, (int, float)) else "?"
    near = " ~nearest" if item.get("nearest") else ""
    preview = " ".join((item.get("memory") or "").split())[:160]
    tags = md.get("tags") or []
    tag_s = f"  tags={','.join(map(str, tags))}" if tags else ""
    print(f"{item.get('id')}  score={score_s}{near}{pin}  project={md.get('project')}  type={md.get('type')}")
    print(f"  src={src}  conf={conf_s}  used={used}x{tag_s}")
    print(textwrap.indent(preview, "  "))


def recall(args: argparse.Namespace) -> None:
    """Cross-project recall: search durable memory across ALL projects."""
    filters: dict[str, Any] = {}
    if args.type:
        filters["type"] = args.type
    payload = {
        "query": args.query,
        "user_id": args.user_id,
        "limit": args.limit,
        "rerank": args.rerank,
        "filters": filters,  # no project/scope filter -> spans every project
        "namespaces": [args.namespace],
        "explain": False,
    }
    result = request_json("POST", "/search", payload)
    if args.json:
        print(json.dumps(result["data"], indent=2, sort_keys=True))
        return
    for item in result["data"]:
        _print_hit(item)


def yaml_scalar(value: Any) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "memory"


def note_for_record(record: dict[str, Any]) -> str:
    metadata = record.get("metadata") or {}
    created_at = record.get("created_at") or metadata.get("created_at")
    if isinstance(created_at, (int, float)):
        created_at = dt.datetime.fromtimestamp(created_at, tz=dt.UTC).isoformat()
    elif not created_at:
        created_at = dt.datetime.now(tz=dt.UTC).isoformat()
    frontmatter = {
        "id": record.get("id"),
        "type": metadata.get("type") or record.get("memory_type") or "memory",
        "project": metadata.get("project") or "global",
        "scope": metadata.get("scope") or record.get("scope") or "project",
        "confidence": metadata.get("confidence", ""),
        "created_at": created_at,
        "source": metadata.get("source") or "yggdrasil",
    }
    yaml = "\n".join(f"{key}: {yaml_scalar(value)}" for key, value in frontmatter.items())
    title = f"{frontmatter['type']}: {frontmatter['project']}"
    return f"---\n{yaml}\n---\n\n# {title}\n\n{(record.get('memory') or '').strip()}\n"


def get_record_by_id(memory_id: str, args: argparse.Namespace) -> dict[str, Any]:
    # Fast path: direct indexed lookup — works at any store size (the old scan
    # could not materialize anything beyond the first `limit` records).
    try:
        rec = request_json("GET", "/get", query={"id": memory_id}).get("data")
        if rec:
            return rec
    except YggError:
        pass  # older engine without /get — bounded scan below
    result = request_json("GET", "/get_all", query={"user_id": args.user_id, "limit": args.limit})
    for record in result.get("data", []):
        if record.get("id") == memory_id:
            return record
    raise YggError(f"Memory not found: {memory_id}")


def materialize(args: argparse.Namespace) -> None:
    record = get_record_by_id(args.id, args)
    metadata = record.get("metadata") or {}
    if args.project and metadata.get("project") != args.project:
        raise YggError(f"Project mismatch: expected {args.project}, got {metadata.get('project')}")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = slugify(f"{metadata.get('project', 'global')}-{metadata.get('type', record.get('memory_type', 'memory'))}-{record.get('id', '')[:8]}")
    output_path = output_dir / f"{stem}.md"
    output_path.write_text(note_for_record(record))
    print(output_path)


def bootstrap(args: argparse.Namespace) -> None:
    # Query-stuffing with the CANONICAL type names (the enum agents write with),
    # so bootstrap ranks typed memories up — legacy names matched nothing.
    args.query = " ".join([args.query, "decision lesson convention fix project_status follow_up reference"]).strip()
    args.type = None
    args.limit = args.limit or 5
    args.rerank = False
    args.explain = False
    args.json = False
    search(args)


def pin(args: argparse.Namespace) -> None:
    """Pin a memory: mark it important so it reliably surfaces near the top."""
    backend().update_memory(args.id, metadata_patch={"pinned": True})
    print(f"pinned {args.id}")


def unpin(args: argparse.Namespace) -> None:
    backend().update_memory(args.id, metadata_patch={"pinned": False})
    print(f"unpinned {args.id}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Yggdrasil MVP CLI over the engine.s REST API")
    parser.set_defaults(func=None)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--namespace", default=namespace_default())
    common.add_argument("--user-id", default=user_default())

    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("health")
    p.set_defaults(func=health)

    p = sub.add_parser("remember", parents=[common])
    p.add_argument("--project")
    p.add_argument("--scope", choices=["project", "global"], default="project")
    p.add_argument("--type", default="memory")
    p.add_argument("--source")
    p.add_argument("--confidence", type=float)
    p.add_argument("--content")
    p.add_argument("--file")
    p.add_argument("--json-file")
    p.add_argument("--extract", action="store_true", help="Allow server-side extraction. Default skips extraction for deterministic agent writeback.")
    p.add_argument("--tag", action="append", help="tag(s) to attach (repeatable)")
    p.set_defaults(func=remember)

    p = sub.add_parser("search", parents=[common])
    p.add_argument("--project")
    p.add_argument("--scope", choices=["project", "global"], default="project")
    p.add_argument("--type")
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--rerank", action="store_true")
    p.add_argument("--explain", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--tag", help="only memories with this tag")
    p.set_defaults(func=search)

    p = sub.add_parser("recall", parents=[common])
    p.add_argument("--query", required=True)
    p.add_argument("--type")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--rerank", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=recall)

    p = sub.add_parser("bootstrap", parents=[common])
    p.add_argument("--project", required=True)
    p.add_argument("--scope", choices=["project"], default="project")
    p.add_argument("--query", default="")
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=bootstrap)

    p = sub.add_parser("materialize", parents=[common])
    p.add_argument("--id", required=True)
    p.add_argument("--project")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--output-dir", default="vault/04-learnings")
    p.set_defaults(func=materialize)

    p = sub.add_parser("pin", parents=[common])
    p.add_argument("--id", required=True)
    p.set_defaults(func=pin)

    p = sub.add_parser("unpin", parents=[common])
    p.add_argument("--id", required=True)
    p.set_defaults(func=unpin)

    p = sub.add_parser("supersede", parents=[common])
    p.add_argument("--id", required=True)
    p.set_defaults(func=supersede)

    p = sub.add_parser("delete", parents=[common])
    p.add_argument("--id", required=True)
    p.set_defaults(func=delete)

    p = sub.add_parser("reset", parents=[common])
    p.add_argument("--project")
    p.add_argument("--source", help="e.g. seed-claude / seed-obsidian — undo one seeding run")
    p.add_argument("--type")
    p.add_argument("--all", action="store_true", help="no narrowing filter: wipe the whole namespace")
    p.add_argument("--yes", action="store_true", help="skip the interactive confirmation")
    p.set_defaults(func=reset)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except YggError as exc:
        print(f"ygg: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
