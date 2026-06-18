#!/usr/bin/env python3
"""Export a Muninn memory record to an Obsidian-readable Markdown note."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "memory"


def yaml_scalar(value: Any) -> str:
    if value is None:
        return '""'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def memory_to_markdown(record: dict[str, Any]) -> str:
    metadata = record.get("metadata") or {}
    memory_id = record.get("id") or metadata.get("id") or "unknown"
    content = record.get("memory") or record.get("content") or ""
    project = metadata.get("project") or record.get("project") or "global"
    memory_type = metadata.get("type") or record.get("memory_type") or "memory"
    scope = record.get("scope") or metadata.get("scope") or "project"
    confidence = metadata.get("confidence", "")
    source = metadata.get("source") or "muninn"
    created_at = record.get("created_at") or metadata.get("created_at")
    if isinstance(created_at, (int, float)):
        created_at = dt.datetime.fromtimestamp(created_at, tz=dt.UTC).isoformat()
    elif not created_at:
        created_at = dt.datetime.now(tz=dt.UTC).isoformat()

    frontmatter = {
        "id": memory_id,
        "type": memory_type,
        "project": project,
        "scope": scope,
        "confidence": confidence,
        "created_at": created_at,
        "source": source,
    }
    yaml = "\n".join(f"{key}: {yaml_scalar(value)}" for key, value in frontmatter.items())
    title = f"{memory_type}: {project}"
    return f"---\n{yaml}\n---\n\n# {title}\n\n{content.strip()}\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    record = json.loads(args.input_json.read_text())
    note = memory_to_markdown(record)
    metadata = record.get("metadata") or {}
    stem = slugify(f"{metadata.get('project', 'global')}-{metadata.get('type', record.get('memory_type', 'memory'))}-{record.get('id', '')[:8]}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"{stem}.md"
    output_path.write_text(note)
    print(output_path)


if __name__ == "__main__":
    main()
