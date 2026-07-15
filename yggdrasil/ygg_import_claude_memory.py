#!/usr/bin/env python3
"""Import a Claude Code auto-memory directory into Yggdrasil (real-content dogfood).

Claude Code accumulates per-project memory under
~/.claude/projects/<sanitized>/memory/*.md. Those are genuine durable lessons
(gotchas, decisions, conventions). This tool migrates them into Yggdrasil's
shared memory by driving the real agent path (`ygg.py remember`), so every
guard applies (secret refusal, content-hash dedupe), then materializes each
note into the Obsidian vault.

Usage:
  python3 scripts/ygg_import_claude_memory.py \
      --source-dir ~/.claude/projects/<sanitized-project-path>/memory \
      --project <project-name> [--materialize]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:  # package + flat-layout (deployed scripts dir) imports
    from . import ygg_config as _cfg
except ImportError:  # pragma: no cover
    import ygg_config as _cfg


ROOT = Path(__file__).resolve().parents[1]
YGG = Path(__file__).resolve().parent / "ygg.py"

# Claude auto-memory `metadata.type` -> Yggdrasil memory type.
TYPE_MAP = {
    "user": "preference",
    "feedback": "workflow",
    "project": "project_summary",
    "reference": "source_note",
}


def parse_frontmatter(text: str) -> dict[str, str]:
    """Minimal frontmatter scrape: returns {name, type} if present."""
    out: dict[str, str] = {}
    if not text.startswith("---"):
        return out
    end = text.find("\n---", 3)
    if end == -1:
        return out
    block = text[3:end]
    name = re.search(r"^name:\s*(.+)$", block, re.M)
    mtype = re.search(r"^\s*type:\s*([A-Za-z_]+)", block, re.M)
    desc = re.search(r"^description:\s*(.+)$", block, re.M)
    if name:
        out["name"] = name.group(1).strip()
    if mtype:
        out["type"] = mtype.group(1).strip()
    if desc:
        out["description"] = desc.group(1).strip().strip('"')
    return out


def strip_frontmatter(text: str) -> str:
    """Return the note body without its leading YAML frontmatter block."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


def run_ygg(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(YGG), *args], cwd=ROOT, env=env, text=True, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a Claude memory dir into Yggdrasil.")
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--namespace", default=_cfg.namespace())
    parser.add_argument("--user-id", default=_cfg.user_id())
    parser.add_argument("--materialize", action="store_true", help="Also write each memory to the Obsidian vault.")
    parser.add_argument("--output-dir", default="vault/04-learnings")
    parser.add_argument("--confidence", type=float, default=0.7, help="Confidence recorded on imported memories.")
    args = parser.parse_args()

    source = Path(args.source_dir).expanduser()
    if not source.is_dir():
        print(f"source dir not found: {source}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env.setdefault("YGG_ENGINE_URL", "http://127.0.0.1:42069")
    env.setdefault("YGG_ENGINE_TOKEN", env.get("YGG_ENGINE_TOKEN", "yggdrasil-demo-token"))
    env["YGG_NAMESPACE"] = args.namespace
    env["YGG_USER_ID"] = args.user_id

    results = []
    for path in sorted(source.glob("*.md")):
        if path.name.upper() == "MEMORY.md".upper():
            continue
        text = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        mem_type = TYPE_MAP.get(fm.get("type", ""), "debugging_lesson")

        # Clean body: drop the source frontmatter, keep a readable title/summary
        # header so the materialized note has no nested frontmatter.
        title = fm.get("name") or path.stem
        summary = fm.get("description", "")
        body = strip_frontmatter(text)
        content = (f"{title}\n{summary}\n\n{body}" if summary else f"{title}\n\n{body}").strip()

        remembered = run_ygg(
            ["remember", "--project", args.project, "--type", mem_type,
             "--source", "claude-memory-import", "--confidence", str(args.confidence),
             "--content", content],
            env,
        )
        if remembered.returncode != 0:
            results.append({"file": path.name, "status": "refused", "stderr": remembered.stderr.strip()[:200]})
            continue
        try:
            payload = json.loads(remembered.stdout)
        except json.JSONDecodeError:
            results.append({"file": path.name, "status": "unparsed", "stdout": remembered.stdout.strip()[:200]})
            continue
        memory_id = payload.get("id")
        status = "duplicate" if payload.get("event") == "YGG_DUPLICATE_SKIP" else "imported"
        entry = {"file": path.name, "type": mem_type, "status": status, "id": memory_id}

        if args.materialize and memory_id:
            mat = run_ygg(["materialize", "--id", str(memory_id), "--project", args.project, "--output-dir", args.output_dir], env)
            entry["note"] = mat.stdout.strip() if mat.returncode == 0 else None
            if mat.returncode != 0:
                entry["materialize_error"] = mat.stderr.strip()[:200]
        results.append(entry)

    print(json.dumps({"project": args.project, "namespace": args.namespace, "user_id": args.user_id, "count": len(results), "results": results}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
