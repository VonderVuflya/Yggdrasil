#!/usr/bin/env python3
"""Yggdrasil MVP CLI: a thin, safe facade over Muninn REST."""

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

from ygg_core import MuninnBackend, YggConfig, YggError, record_is_archived


DEFAULT_URL = "http://127.0.0.1:42069"
DEFAULT_NAMESPACE = "yggdrasil-demo"
DEFAULT_USER = "global_user"

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


def muninn_url() -> str:
    return env_default("YGG_MUNINN_URL", env_default("MUNINN_SERVER_URL", DEFAULT_URL)).rstrip("/")


def muninn_token() -> str:
    token = os.environ.get("YGG_MUNINN_TOKEN") or os.environ.get("MUNINN_AUTH_TOKEN") or os.environ.get("MUNINN_SERVER_AUTH_TOKEN")
    if not token:
        raise YggError("Missing token. Set YGG_MUNINN_TOKEN or MUNINN_AUTH_TOKEN.")
    return token


def namespace_default() -> str:
    return env_default("YGG_NAMESPACE", DEFAULT_NAMESPACE)


def user_default() -> str:
    return env_default("YGG_USER_ID", DEFAULT_USER)


_BACKEND: MuninnBackend | None = None


def backend() -> MuninnBackend:
    """Shared engine-agnostic REST client (from ygg_core), built from the env.

    The CLI no longer hand-rolls REST transport — it goes through the same
    backend contract the gates and review tools use, so swapping the engine
    (own server vs external Muninn) flows through one place.
    """
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = MuninnBackend(YggConfig.from_env())
    return _BACKEND


def request_json(method: str, path: str, body: dict[str, Any] | None = None, query: dict[str, Any] | None = None) -> dict[str, Any]:
    return backend().request_json(method, path, body=body, query=query)


def health(_: argparse.Namespace) -> None:
    url = muninn_url() + "/health"
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


def remember(args: argparse.Namespace) -> None:
    if args.scope == "project" and not args.project:
        raise YggError("--project is required for project-scoped memories.")
    content, file_metadata = load_content(args)
    project = args.project or "global"
    memory_type = args.type or file_metadata.get("type") or "memory"
    metadata = {
        "project": project,
        "scope": args.scope,
        "type": memory_type,
        "source": args.source or file_metadata.get("source") or "ygg-cli",
        "muninn_skip_extraction": not args.extract,
    }
    if args.confidence is not None:
        metadata["confidence"] = args.confidence
    elif "confidence" in file_metadata:
        metadata["confidence"] = file_metadata["confidence"]
    digest = content_hash(content)
    metadata["content_hash"] = digest
    require_safe_memory(content, metadata)
    existing = find_existing_hash(args.user_id, project, memory_type, digest)
    if existing:
        print(json.dumps({"event": "YGG_DUPLICATE_SKIP", "id": existing.get("id"), "content_hash": digest}, indent=2, sort_keys=True))
        return
    payload = {
        "content": content,
        "user_id": args.user_id,
        "namespace": args.namespace,
        "scope": args.scope,
        "metadata": metadata,
    }
    result = request_json("POST", "/add", payload)
    print(json.dumps(result["data"], indent=2, sort_keys=True))


def search(args: argparse.Namespace) -> None:
    if args.scope == "project" and not args.project:
        raise YggError("--project is required for project-scoped search.")
    filters: dict[str, Any] = {"scope": args.scope}
    if args.project:
        filters["project"] = args.project
    if args.type:
        filters["type"] = args.type
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
    for item in result["data"]:
        metadata = item.get("metadata") or {}
        preview = " ".join((item.get("memory") or "").split())[:160]
        print(f"{item.get('id')}  score={item.get('score'):.4f}  project={metadata.get('project')}  type={metadata.get('type')}")
        print(textwrap.indent(preview, "  "))


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
        "source": metadata.get("source") or "muninn",
    }
    yaml = "\n".join(f"{key}: {yaml_scalar(value)}" for key, value in frontmatter.items())
    title = f"{frontmatter['type']}: {frontmatter['project']}"
    return f"---\n{yaml}\n---\n\n# {title}\n\n{(record.get('memory') or '').strip()}\n"


def get_record_by_id(memory_id: str, args: argparse.Namespace) -> dict[str, Any]:
    result = request_json("GET", "/get_all", query={"user_id": args.user_id, "limit": args.limit})
    for record in result.get("data", []):
        if record.get("id") == memory_id:
            return record
    raise YggError(f"Memory not found in first {args.limit} records: {memory_id}")


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
    args.query = " ".join([args.query, "debugging_lesson decision failed_approach workflow project instruction"]).strip()
    args.type = None
    args.limit = args.limit or 5
    args.rerank = False
    args.explain = False
    args.json = False
    search(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Yggdrasil MVP CLI over Muninn REST")
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
    p.add_argument("--extract", action="store_true", help="Allow Muninn extraction. Default skips extraction for deterministic agent writeback.")
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
    p.set_defaults(func=search)

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
