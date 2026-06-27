#!/usr/bin/env python3
"""Cold-start onboarding for Yggdrasil: discover, estimate, distill, report.

This is the answer to the empty-memory "cold start": right after install the
store is empty and stays empty until the user figures out what to feed it. These
commands close that gap **in Yggdrasil's idiom** — curated, local-first, opt-in —
rather than the capture-everything firehose of heavier tools:

  ygg stats                 what's already in memory (project x type x scope)
  ygg seed                  find your work (Claude Code transcripts, Obsidian
                            vaults, repos), estimate the cost, then distill
  ygg distill --source P    distill one dir/file into atomic lessons

Distillation uses your LOCAL Ollama background model (free) by default — raw
transcript -> a few durable lessons, deduped, with provenance. Nothing leaves
the machine.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:  # package + flat-layout (deployed scripts dir) imports
    from . import ygg as _ygg
except ImportError:  # pragma: no cover
    import ygg as _ygg

HOME = Path.home()
YGG_HOME = Path(os.environ.get("YGG_HOME", str(HOME / ".yggdrasil")))
OLLAMA_URL = os.environ.get("YGG_EMBED_URL", "http://127.0.0.1:11434")
MAX_CHARS_PER_FILE = 14000  # window we feed the local model per source file


# --------------------------------------------------------------------------- #
# ygg stats — what's in memory right now
# --------------------------------------------------------------------------- #

def stats(user_id: str, namespace: str) -> int:
    try:
        data = _ygg.request_json("GET", "/get_all", query={"user_id": user_id, "limit": 5000}).get("data", [])
    except _ygg.YggError as exc:
        print(f"could not reach the engine: {exc}", file=sys.stderr)
        return 1
    live = [r for r in data if not _ygg.record_is_archived(r)]
    by_project: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_scope: dict[str, int] = {}
    for r in live:
        md = r.get("metadata") or {}
        by_project[md.get("project") or "—"] = by_project.get(md.get("project") or "—", 0) + 1
        by_type[md.get("type") or "—"] = by_type.get(md.get("type") or "—", 0) + 1
        by_scope[md.get("scope") or "—"] = by_scope.get(md.get("scope") or "—", 0) + 1

    db = YGG_HOME / "data" / "memory.sqlite"
    size = db.stat().st_size if db.exists() else 0
    print(f"Yggdrasil memory: {len(live)} live records "
          f"({len(data) - len(live)} archived) · db {size / 1024:.0f} KB\n")
    if not live:
        print("Memory is empty. Seed it from your existing work:  ygg seed")
        return 0

    def _table(title: str, counts: dict[str, int]) -> None:
        print(title)
        for k, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>4}  {k}")
        print()
    _table("by project:", by_project)
    _table("by type:", by_type)
    _table("by scope:", by_scope)
    print("retrieve:  ygg recall --query \"…\"  (cross-project) · "
          "ygg bootstrap --project P  (one project)")
    return 0


# --------------------------------------------------------------------------- #
# discovery — find the user's existing work
# --------------------------------------------------------------------------- #

def _dir_bytes(path: Path, patterns: tuple[str, ...]) -> tuple[int, int]:
    total = files = 0
    for pat in patterns:
        for p in path.glob(pat):
            try:
                total += p.stat().st_size
                files += 1
            except OSError:
                pass
    return total, files


def _project_label(claude_dir_name: str) -> str:
    """Best-effort project name from a Claude Code project dir (path with / -> -)."""
    name = claude_dir_name.lstrip("-")
    for marker in ("Projects-", "Work-", "work-", "src-", "repos-"):
        if marker in name:
            return name.split(marker, 1)[1] or name
    return name.rsplit("-", 1)[-1] or name


def discover() -> list[dict[str, Any]]:
    """Find seedable sources. Bounded/fast — globs one or two levels, no deep walks."""
    sources: list[dict[str, Any]] = []

    # 1. Claude Code transcripts + per-project memory notes
    cproj = HOME / ".claude" / "projects"
    if cproj.is_dir():
        for d in sorted(cproj.iterdir()):
            if not d.is_dir():
                continue
            tbytes, tfiles = _dir_bytes(d, ("*.jsonl",))
            mbytes, mfiles = _dir_bytes(d / "memory", ("*.md",)) if (d / "memory").is_dir() else (0, 0)
            if tfiles or mfiles:
                sources.append({
                    "kind": "claude", "path": str(d), "project": _project_label(d.name),
                    "bytes": tbytes + mbytes, "files": tfiles + mfiles,
                    "detail": f"{tfiles} transcript(s) + {mfiles} memory note(s)",
                })

    # 2. Obsidian vaults (dirs containing a .obsidian/) under common roots, bounded depth
    roots = [HOME / "Documents", HOME / "Library" / "CloudStorage", HOME / "obsidian", HOME / "vaults"]
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for cfg in list(root.glob("*/.obsidian")) + list(root.glob("*/*/.obsidian")):
            vault = cfg.parent
            if str(vault) in seen:
                continue
            seen.add(str(vault))
            mbytes, mfiles = _dir_bytes(vault, ("**/*.md",))
            if mfiles:
                sources.append({
                    "kind": "obsidian", "path": str(vault), "project": vault.name,
                    "bytes": mbytes, "files": mfiles, "detail": f"{mfiles} note(s)",
                })

    # 3. Repos carrying a CLAUDE.md under common project roots (one level)
    for root in (HOME / "Projects", HOME / "Work", HOME / "work", HOME / "src", HOME / "code"):
        if not root.is_dir():
            continue
        for cm in root.glob("*/CLAUDE.md"):
            repo = cm.parent
            sources.append({
                "kind": "repo", "path": str(repo), "project": repo.name,
                "bytes": cm.stat().st_size, "files": 1, "detail": "CLAUDE.md",
            })
    return sources


def estimate(sources: list[dict[str, Any]]) -> dict[str, Any]:
    total_bytes = sum(s["bytes"] for s in sources)
    capped = sum(min(s["bytes"], MAX_CHARS_PER_FILE * max(1, s["files"])) for s in sources)
    tokens_in = capped // 4  # ~4 chars/token, after windowing
    minutes = max(1, round(len(sources) * 6 / 60 + tokens_in / 9000))  # rough local-model throughput
    return {"sources": len(sources), "bytes": total_bytes, "tokens_in": tokens_in, "minutes": minutes}


def _fmt_mb(n: int) -> str:
    return f"{n / 1_048_576:.1f} MB" if n >= 1_048_576 else f"{n / 1024:.0f} KB"


# --------------------------------------------------------------------------- #
# distillation — raw text -> atomic lessons via the local Ollama model
# --------------------------------------------------------------------------- #

DISTILL_PROMPT = """You extract DURABLE, reusable engineering memory from a work log.
Return STRICT JSON: {"lessons":[{"type":"...","content":"..."}]}.
- type is one of: decision, lesson, convention, fix, reference, project_status.
- content is ONE self-contained fact a future session would want: a decision and
  its rationale, a non-obvious fix, a convention, a gotcha, current status.
- Keep each under 280 chars. 0 to 6 lessons. Skip chit-chat and anything
  derivable from the code. NEVER include secrets/tokens/keys.
Work log follows:
---
{TEXT}
---
Return only the JSON object."""


def _ollama_generate(model: str, prompt: str, timeout: int = 120) -> str:
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json"}).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8")).get("response", "")


def _extract_text(path: Path) -> str:
    """Pull human-readable text out of a source file (.jsonl transcript or .md)."""
    if path.suffix == ".md":
        try:
            return path.read_text(errors="replace")
        except OSError:
            return ""
    out: list[str] = []
    try:
        for line in path.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = ev.get("message") or ev
            content = msg.get("content") if isinstance(msg, dict) else None
            if isinstance(content, str):
                out.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        out.append(part["text"])
    except OSError:
        return ""
    return "\n".join(out)


def distill_text(text: str, *, project: str, source: str, model: str,
                 user_id: str, namespace: str) -> dict[str, int]:
    text = text.strip()
    if not text:
        return {"added": 0, "dup": 0, "errors": 0}
    text = text[-MAX_CHARS_PER_FILE:]  # keep the most recent window
    try:
        raw = _ollama_generate(model, DISTILL_PROMPT.replace("{TEXT}", text))
        parsed = json.loads(raw)
        # The local model is loose: it may return {"lessons": [...]}, a bare list,
        # a bare single lesson object, or list items that are dicts OR plain strings.
        if isinstance(parsed, dict):
            if isinstance(parsed.get("lessons"), list):
                lessons = parsed["lessons"]
            elif parsed.get("content") or parsed.get("text"):
                lessons = [parsed]  # a bare single lesson object
            else:
                lessons = []
        elif isinstance(parsed, list):
            lessons = parsed
        else:
            lessons = []
    except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
        print(f"    distill failed for {project}: {exc}", file=sys.stderr)
        return {"added": 0, "dup": 0, "errors": 1}
    added = dup = errors = 0
    for item in lessons:
        if isinstance(item, str):
            content, mtype = item.strip(), "lesson"
        elif isinstance(item, dict):
            content = str(item.get("content") or item.get("text") or "").strip()
            mtype = str(item.get("type") or "lesson").strip() or "lesson"
        else:
            continue
        if not content:
            continue
        try:
            status, _ = _ygg.write_memory(
                content=content, project=project, memory_type=mtype,
                source=source, user_id=user_id, namespace=namespace,
                confidence=0.6, tags=["seed"],
            )
            added += status == "added"
            dup += status == "duplicate"
        except _ygg.YggError:
            errors += 1
    return {"added": added, "dup": dup, "errors": errors}


def distill_source(src: dict[str, Any], *, model: str, user_id: str, namespace: str,
                   project_override: str | None = None) -> dict[str, int]:
    project = project_override or src["project"]
    base = Path(src["path"])
    files: list[Path] = []
    if src["kind"] == "claude":
        files = sorted(base.glob("*.jsonl")) + sorted((base / "memory").glob("*.md"))
    elif src["kind"] == "obsidian":
        files = sorted(base.glob("**/*.md"))[:50]
    elif src["kind"] == "repo":
        files = [base / "CLAUDE.md"]
    agg = {"added": 0, "dup": 0, "errors": 0}
    print(f"  distilling {project} ({len(files)} file(s)) ...")
    for f in files:
        if not f.exists():
            continue
        try:
            res = distill_text(_extract_text(f), project=project, source=f"seed:{src['kind']}",
                               model=model, user_id=user_id, namespace=namespace)
        except Exception as exc:  # noqa: BLE001 — one bad file must never abort the source
            print(f"    skipped {f.name}: {exc}", file=sys.stderr)
            res = {"added": 0, "dup": 0, "errors": 1}
        for k in agg:
            agg[k] += res[k]
    print(f"    {project}: +{agg['added']} new, {agg['dup']} dup-skipped, {agg['errors']} error(s)")
    return agg


# --------------------------------------------------------------------------- #
# seed orchestrator
# --------------------------------------------------------------------------- #

def _bg_model() -> str:
    try:
        cfg = json.loads((YGG_HOME / "config.json").read_text())
        return cfg.get("bg_model") or "qwen2.5:1.5b"
    except (OSError, ValueError):
        return "qwen2.5:1.5b"


def seed(args: argparse.Namespace) -> int:
    sources = discover()
    if not sources:
        print("No seedable sources found (Claude Code transcripts, Obsidian vaults, "
              "or repos with CLAUDE.md). Nothing to do.")
        return 0
    print("Found sources to seed memory from:\n")
    for i, s in enumerate(sources):
        print(f"  [{i}] {s['kind']:8} {s['project']:<28} {_fmt_mb(s['bytes']):>9}  {s['detail']}")
        print(f"      {s['path']}")
    est = estimate(sources)
    print(f"\nEstimate: {est['sources']} source(s), {_fmt_mb(est['bytes'])} on disk, "
          f"~{est['tokens_in']:,} input tokens, ≈{est['minutes']} min.")
    model = args.model or _bg_model()
    print(f"Distill runs LOCALLY via Ollama model '{model}' — free, nothing leaves your machine.\n")

    if args.dry_run:
        print("(dry run — nothing written. Re-run without --dry-run to distill.)")
        return 0
    if sys.stdin.isatty() and not args.yes:
        try:
            if not input("Proceed with local distill now? [y/N]: ").strip().lower().startswith("y"):
                print("aborted.")
                return 0
        except EOFError:
            return 0

    total = {"added": 0, "dup": 0, "errors": 0}
    for s in sources:
        try:
            res = distill_source(s, model=model, user_id=args.user_id, namespace=args.namespace)
        except Exception as exc:  # noqa: BLE001 — one bad source must never abort the seed
            print(f"    skipped {s.get('project')}: {exc}", file=sys.stderr)
            res = {"added": 0, "dup": 0, "errors": 1}
        for k in total:
            total[k] += res[k]
    print(f"\nDone: +{total['added']} new memories, {total['dup']} dup-skipped, "
          f"{total['errors']} error(s).")
    print("Check it:  ygg stats   ·   retrieve:  ygg recall --query \"…\"")
    return 0


def distill_cmd(args: argparse.Namespace) -> int:
    path = Path(args.source).expanduser()
    if not path.exists():
        print(f"no such source: {path}", file=sys.stderr)
        return 1
    model = args.model or _bg_model()
    project = args.project or path.name
    if path.is_file():
        res = distill_text(_extract_text(path), project=project, source="distill",
                           model=model, user_id=args.user_id, namespace=args.namespace)
    else:
        kind = "claude" if (path / "memory").is_dir() or list(path.glob("*.jsonl")) else "obsidian"
        res = distill_source({"kind": kind, "path": str(path), "project": project,
                              "bytes": 0, "files": 0}, model=model,
                             user_id=args.user_id, namespace=args.namespace,
                             project_override=project)
    print(f"distilled: +{res['added']} new, {res['dup']} dup, {res['errors']} error(s)")
    return 0


# --------------------------------------------------------------------------- #
# entry
# --------------------------------------------------------------------------- #

def main(cmd: str, rest: list[str]) -> int:
    p = argparse.ArgumentParser(prog=f"ygg {cmd}")
    # Default to the SAME identity the MCP agent uses, so seeded memory is
    # immediately recallable by the agent (the MCP facade runs as demo-user).
    p.add_argument("--namespace", default=os.environ.get("YGG_NAMESPACE", "yggdrasil-demo"))
    p.add_argument("--user-id", default=os.environ.get("YGG_USER_ID", "demo-user"))
    p.add_argument("--model", default="", help="Ollama model for distillation (default: config bg_model)")
    if cmd == "seed":
        p.add_argument("--dry-run", action="store_true", help="discover + estimate only, write nothing")
        p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    if cmd == "distill":
        p.add_argument("--source", required=True, help="dir or file to distill")
        p.add_argument("--project", help="project label for the lessons (default: source name)")
    args = p.parse_args(rest)
    args.model = args.model or None
    if cmd == "stats":
        return stats(args.user_id, args.namespace)
    if cmd == "seed":
        return seed(args)
    if cmd == "distill":
        return distill_cmd(args)
    print(f"unknown seed command: {cmd}", file=sys.stderr)
    return 2
