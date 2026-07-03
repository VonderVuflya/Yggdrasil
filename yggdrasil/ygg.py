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
    from .ygg_core import RestMemoryBackend, YggConfig, YggError, metadata_of, record_is_archived
    from . import ygg_ui
except ImportError:  # flat layout (deployed scripts dir / tests / direct run)
    from ygg_core import RestMemoryBackend, YggConfig, YggError, metadata_of, record_is_archived
    import ygg_ui


DEFAULT_URL = "http://127.0.0.1:42069"
DEFAULT_NAMESPACE = "yggdrasil-demo"
DEFAULT_USER = "demo-user"  # unified identity — same store the MCP agent reads/writes

# Cosine >= this (when dense is on) means a near-duplicate of an existing memory —
# the write is skipped. High by default so only genuinely-redundant lessons drop.
SEMDEDUP_THRESHOLD = float(os.environ.get("YGG_SEMDEDUP_AT", "0.92"))

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),                       # OpenAI-style
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),                        # GitHub classic PAT
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),               # GitHub fine-grained PAT
    re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}\b"),                  # GitHub OAuth/app/refresh tokens
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),                   # GitLab PAT
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),               # Slack
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                           # AWS access key id
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),                           # AWS temporary key id
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}\b"),  # JWT
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),                      # Google API key
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s:@]+@"),  # scheme://user:PASSWORD@host
    re.compile(r"(?i)\b(api[_-]?key|token|password|passwd|secret|client_secret)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{12,}"),
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
    _print_hits(hits)


def _print_hits(hits: list[dict[str, Any]]) -> None:
    p = ygg_ui.palette()
    mx = max((h.get("score") for h in hits if isinstance(h.get("score"), (int, float))), default=0.0) or 1.0
    for i, item in enumerate(hits, 1):
        _print_hit(item, rank=i, max_score=mx, p=p)


def _print_hit(item: dict[str, Any], *, rank: int | None = None,
               max_score: float = 1.0, p: "ygg_ui.Palette | None" = None) -> None:
    """Render one search/recall hit. On a TTY: content-first, with a type badge,
    a relevance bar and relative time. Piped/agent output keeps the STABLE
    id-first provenance format (parsers + the MCP facade rely on it)."""
    md = item.get("metadata") or {}
    if p is None:
        p = ygg_ui.palette()

    if not p.on:  # ---- stable, byte-for-byte unchanged (non-TTY / agents / gates)
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
        return

    # ---- pretty (TTY): lead with what the memory IS and how relevant it is
    mtype = md.get("type") or item.get("memory_type")
    score = item.get("score") if isinstance(item.get("score"), (int, float)) else 0.0
    meta_bits = [ygg_ui.badge(mtype, p), p.cyan(md.get("project") or "global")]
    when = ygg_ui.ago(item.get("created_at"))
    if when:
        meta_bits.append(p.dim(when))
    meta_bits.append(ygg_ui.bar(score / max_score, p) + ("" if not item.get("nearest") else p.dim(" ~near")))
    used = item.get("access_count") or 0
    if used:
        meta_bits.append(p.dim(f"used {used}×"))
    if item.get("pinned") or md.get("pinned"):
        meta_bits.append("📌")
    num = p.bold(f"{rank}. ") if rank else ""
    print(num + p.dim(" · ").join(meta_bits))
    preview = " ".join((item.get("memory") or "").split())[:200]
    sid = p.dim(ygg_ui.short_id(item.get("id")))
    print("   " + preview + "  " + sid)


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
    hits = result["data"]
    if not hits:
        print("(no matches across any project)")
        return
    _print_hits(hits)


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


# Native-memory bridge: Yggdrasil is the layer ABOVE the vendors' own memory
# (Claude Code's MEMORY.md, Codex's AGENTS.md) — `ygg seed` already imports FROM
# them; this exports a curated digest BACK into the vendor-neutral AGENTS.md
# format both read, inside a managed block so a hand-edited file is never
# clobbered. Result: a fresh clone, a teammate, or a tool WITHOUT Yggdrasil still
# gets your curated memory.
_YGG_BEGIN = "<!-- ygg:begin (managed by `ygg export-native` — edits here are overwritten) -->"
_YGG_END = "<!-- ygg:end -->"
_EXPORT_ORDER = ["project_status", "follow_up", "decision", "lesson", "fix", "convention", "reference"]
_EXPORT_HEADING = {
    "project_status": "Current status", "follow_up": "Open follow-ups",
    "decision": "Decisions", "lesson": "Lessons", "fix": "Fixes",
    "convention": "Conventions", "reference": "References",
}


def _render_native_block(project: str, records: list[dict[str, Any]]) -> str:
    by_type: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        md = r.get("metadata") or {}
        by_type.setdefault(md.get("type") or r.get("memory_type") or "reference", []).append(r)
    lines = [_YGG_BEGIN, f"## 🌳 Durable memory — `{project}`",
             "_Curated by Yggdrasil. Verify against the code; memory can be stale._", ""]
    for mtype in _EXPORT_ORDER + sorted(set(by_type) - set(_EXPORT_ORDER)):
        items = by_type.get(mtype)
        if not items:
            continue
        lines.append(f"### {_EXPORT_HEADING.get(mtype, mtype.replace('_', ' ').title())}")
        for r in items:
            pin = "📌 " if (r.get("metadata") or {}).get("pinned") else ""
            text = " ".join((r.get("memory") or r.get("content") or "").split())
            lines.append(f"- {pin}{text}")
        lines.append("")
    lines.append(_YGG_END)
    return "\n".join(lines).rstrip() + "\n"


def _upsert_managed_block(path: Path, block: str) -> str:
    """Insert/replace the ygg-managed block in `path`, preserving all other
    content. Returns 'created' | 'updated' | 'unchanged'."""
    existing = path.read_text() if path.exists() else ""
    if _YGG_BEGIN in existing and _YGG_END in existing:
        pre = existing[: existing.index(_YGG_BEGIN)]
        post = existing[existing.index(_YGG_END) + len(_YGG_END):]
        new = pre.rstrip("\n") + ("\n\n" if pre.strip() else "") + block + post.lstrip("\n")
        status = "unchanged" if new == existing else "updated"
    else:
        sep = "\n\n" if existing.strip() else ""
        new = existing.rstrip("\n") + sep + block if existing.strip() else block
        status = "created" if not existing.strip() else "updated"
    if new != existing:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new)
    return status


def export_native(args: argparse.Namespace) -> None:
    """Write a project's curated memory into a native AGENTS.md/MEMORY.md block."""
    records = backend().get_all(user_id=args.user_id, limit=args.limit, namespace=args.namespace)
    live = [r for r in records
            if not record_is_archived(r)
            and (r.get("metadata") or {}).get("project") == args.project
            and (not args.type or (r.get("metadata") or {}).get("type") == args.type)]
    if not live:
        raise YggError(f"No memories to export for project '{args.project}' "
                       f"(namespace {args.namespace}).")
    # Pinned first, then by type priority, then most-recalled — the same signals
    # the engine ranks with, so the digest leads with what matters.
    def _rank(r: dict[str, Any]) -> tuple:
        md = r.get("metadata") or {}
        prio = _EXPORT_ORDER.index(md.get("type")) if md.get("type") in _EXPORT_ORDER else len(_EXPORT_ORDER)
        return (0 if md.get("pinned") else 1, prio, -(r.get("access_count") or 0))
    live.sort(key=_rank)
    block = _render_native_block(args.project, live)
    target = Path(args.out) if args.out else Path.cwd() / "AGENTS.md"
    status = _upsert_managed_block(target, block)
    print(f"{status}: {target}  ({len(live)} memories in the ygg-managed block)")


# ---- ygg review: work the governance queue (curation is the wedge) ---------
# The dup/stale/conflict FINDERS live in ygg_review_queue (also used by the
# gates); this wires them into an interactive, user-facing loop that ACTS —
# non-destructively (archive, never hard-delete), the "curated, not captured"
# promise made tangible.

def _review_issues(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        from . import ygg_review_queue as rq
    except ImportError:  # flat layout
        import ygg_review_queue as rq
    live = [r for r in records if not record_is_archived(r)]
    issues = (rq.find_exact_duplicates(live)
              + rq.find_near_duplicates(live)
              + rq.find_stale_or_conflict_markers(live))
    order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (order.get(i.get("severity"), 9), i.get("kind"), i.get("project") or ""))
    return issues


def _dup_keep_and_archive(issue: dict[str, Any]) -> tuple[str, list[str]]:
    """For a duplicate group (records sorted oldest-first): keep the oldest,
    return the ids of the rest to archive."""
    recs = issue.get("records") or []
    keep = recs[0]["id"] if recs else None
    return keep, [r["id"] for r in recs[1:]]


def _print_issue(index: int, total: int, issue: dict[str, Any]) -> None:
    print(f"\n[{index}/{total}] {issue['kind']} ({issue['severity']})  "
          f"project={issue.get('project')} type={issue.get('type')}")
    print(f"    → {issue.get('recommendation')}")
    for j, r in enumerate(issue.get("records") or []):
        tag = "keep " if (issue['kind'].endswith('duplicate') and j == 0) else "     "
        print(f"    {tag}{r.get('id')}  {r.get('preview')}")


def review(args: argparse.Namespace) -> None:
    records = backend().get_all(user_id=args.user_id, limit=args.limit, namespace=args.namespace)
    if args.project:
        records = [r for r in records if metadata_of(r).get("project") == args.project]
    issues = _review_issues(records)
    if not issues:
        print("✓ no review issues — memory is clean"
              + (f" (project {args.project})" if args.project else ""))
        return

    interactive = sys.stdin.isatty() and not args.yes
    if not args.apply and not interactive:
        for i, issue in enumerate(issues, 1):
            _print_issue(i, len(issues), issue)
        print(f"\n{len(issues)} issue(s). Act on them: `ygg review --apply` (interactive) "
              "or `ygg review --apply --yes` (auto-consolidate duplicates, flag the rest).")
        return

    archived = skipped = flagged = 0
    for i, issue in enumerate(issues, 1):
        _print_issue(i, len(issues), issue)
        kind = issue["kind"]
        if kind in ("exact_duplicate", "near_duplicate"):
            keep, dups = _dup_keep_and_archive(issue)
            if not dups:
                continue
            ans = "k" if not interactive else input(
                f"    [k]eep oldest & archive {len(dups)} dup(s) / [s]kip? ").strip().lower()
            if ans in ("", "k", "y", "keep"):
                for mid in dups:
                    backend().archive_memory(mid, {"review": "duplicate", "status": "archived"})
                    archived += 1
                print(f"    archived {len(dups)}, kept {keep}")
            else:
                skipped += 1
        else:  # stale/conflict marker — needs human verification, NEVER auto-archived
            if not interactive:
                flagged += 1
                print("    flagged for manual review (verify against the repo before archiving)")
                continue
            ans = input("    [a]rchive (verified stale) / [s]kip? ").strip().lower()
            if ans in ("a", "y", "archive"):
                backend().archive_memory(issue["records"][0]["id"], {"review": "stale", "status": "archived"})
                archived += 1
                print("    archived")
            else:
                skipped += 1
    parts = [f"archived {archived}"]
    if skipped:
        parts.append(f"skipped {skipped}")
    if flagged:
        parts.append(f"flagged {flagged} (need manual review)")
    print(f"\nreview done — {', '.join(parts)}. Archives are reversible (nothing hard-deleted).")


# ---- ygg import: one-command migration FROM another memory tool -------------
# Zero switching cost: point at another tool's local store, pull everything into
# Yggdrasil (deduped, secret-guarded), then you can delete the old tool. `ygg
# seed` already covers Claude Code / Codex / Obsidian / CLAUDE.md; this covers
# dedicated memory tools with their own stores.

def _import_mcp_memory(path: Path, project: str) -> list[tuple[str, str]]:
    """Read the reference MCP memory server's store (`@modelcontextprotocol/
    server-memory` — the most-installed memory MCP). It's newline-delimited JSON:
    {"type":"entity","name":..,"entityType":..,"observations":[..]} and
    {"type":"relation","from":..,"to":..,"relationType":..}. Returns
    (content, memory_type) pairs — one memory per entity, its relations folded in."""
    entities: dict[str, dict[str, Any]] = {}
    relations: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "entity" and obj.get("name"):
            entities[obj["name"]] = obj
        elif obj.get("type") == "relation":
            relations.append(obj)
    rel_by_from: dict[str, list[str]] = {}
    for r in relations:
        frm, to, kind = r.get("from"), r.get("to"), r.get("relationType")
        if frm and to and kind:
            rel_by_from.setdefault(frm, []).append(f"{kind} {to}")
    out: list[tuple[str, str]] = []
    for name, e in entities.items():
        obs = "; ".join(o for o in (e.get("observations") or []) if isinstance(o, str) and o.strip())
        rels = "; ".join(rel_by_from.get(name, []))
        label = name.replace("_", " ")
        etype = e.get("entityType") or "entity"
        content = f"{label} ({etype})" + (f": {obs}" if obs else "")
        if rels:
            content += f" — {rels}"
        if content.strip():
            out.append((content.strip(), "reference"))
    return out


def _import_basic_memory(path: Path, project: str) -> list[tuple[str, str]]:
    """Basic Memory keeps plain-Markdown notes (files-as-truth). Import each note
    verbatim as a reference memory — no LLM, since they're already curated."""
    base = path if path.is_dir() else path.parent
    out: list[tuple[str, str]] = []
    for md in sorted(base.rglob("*.md"))[:2000]:
        try:
            text = md.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if text:
            out.append((f"[{md.stem}] {text}"[:4000], "reference"))
    return out


_IMPORTERS = {
    "mcp-memory": (_import_mcp_memory,
                   "the reference MCP memory server (@modelcontextprotocol/server-memory) — "
                   "point --path at its memory.json"),
    "basic-memory": (_import_basic_memory,
                     "Basic Memory's Markdown notes — point --path at the vault directory"),
}


def import_cmd(args: argparse.Namespace) -> None:
    """Migrate memories FROM another tool's local store into Yggdrasil."""
    importer, _ = _IMPORTERS[args.source]
    path = Path(args.path).expanduser()
    if not path.exists():
        raise YggError(f"no such path: {path}")
    project = args.project or "imported"
    items = importer(path, project)
    if not items:
        print(f"nothing to import from {args.source} at {path}")
        return
    if args.dry_run:
        print(f"{args.source}: would import {len(items)} memories into project '{project}'. Examples:")
        for content, mtype in items[:5]:
            print(f"  [{mtype}] {' '.join(content.split())[:120]}")
        print("(dry run — nothing written. Drop --dry-run to import.)")
        return
    added = dup = errors = 0
    for content, mtype in items:
        try:
            status, _ = write_memory(
                content=content, project=project, memory_type=mtype,
                source=f"import:{args.source}", user_id=args.user_id,
                namespace=args.namespace, confidence=0.7, tags=["imported", args.source],
            )
            added += status == "added"
            dup += status == "duplicate"
        except YggError:
            errors += 1
    print(f"imported from {args.source}: +{added} new, {dup} duplicate-skipped, "
          f"{errors} error(s) → project '{project}'.")
    print("Verify:  ygg search --project " + project + " --query \"…\"   "
          "· then you can remove the old tool.")


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

    p = sub.add_parser("review", parents=[common])
    p.add_argument("--project", help="only review this project's memories")
    p.add_argument("--apply", action="store_true", help="act on the queue (interactive on a TTY)")
    p.add_argument("--yes", action="store_true", help="non-interactive: auto-consolidate duplicates, flag the rest")
    p.add_argument("--limit", type=int, default=1000)
    p.set_defaults(func=review)

    p = sub.add_parser("import", parents=[common])
    p.add_argument("--from", dest="source", required=True, choices=sorted(_IMPORTERS),
                   help="which tool to migrate FROM")
    p.add_argument("--path", required=True, help="path to that tool's store (file or dir)")
    p.add_argument("--project", help="project to file the imported memories under (default: imported)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=import_cmd)

    p = sub.add_parser("export-native", parents=[common])
    p.add_argument("--project", required=True)
    p.add_argument("--out", help="target file (default: AGENTS.md in the current dir; "
                                 "e.g. ~/.claude/projects/<p>/memory/MEMORY.md, CLAUDE.md)")
    p.add_argument("--type", help="only export one memory type")
    p.add_argument("--limit", type=int, default=1000)
    p.set_defaults(func=export_native)

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
