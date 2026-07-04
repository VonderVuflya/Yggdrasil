#!/usr/bin/env python3
"""`ygg sync` — cross-machine memory sync through the user's OWN git repo.

The counter to every cloud-sync memory product, without betraying the wedge:
your memories travel as plain JSON files in a git repo YOU own (GitHub private,
self-hosted Gitea, a bare repo on a USB stick — anything git). No relay, no
account, nothing readable leaves your infrastructure.

Layout inside the repo:

    memories/<id>.json    one file per memory (sorted keys, byte-deterministic)
    relations.jsonl       one edge per line (merged with git's union driver)
    .gitattributes        relations.jsonl merge=union

Per-machine state (access counts, last-accessed, embedding vectors) is NOT
synced — vectors are recomputed locally (`ygg reindex` backfills after a pull
brings new memories).

Semantics are ADDITIVE (v1): memories propagate everywhere, edits merge by the
rules in merge_memory(); deletions do not propagate (no tombstones yet — a
hard-deleted memory returns on the next sync from a machine that still has it).

Flow (one command, converges without manual conflict resolution):
  export → commit → pull -X ours → import+merge → re-export → commit → push
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

try:  # package + flat-layout imports
    from . import ygg_config as _cfg
    from .ygg import request_json
except ImportError:  # pragma: no cover
    import ygg_config as _cfg
    from ygg import request_json


# --------------------------------------------------------------------------- #
# pure pieces (unit-tested)
# --------------------------------------------------------------------------- #

def merge_memory(local: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
    """Deterministic union of two versions of the SAME memory (same id).

    Rules, in the spirit of archive-never-delete:
      - archived: OR — an archive decision made anywhere holds everywhere
      - confidence / importance: max — trust the stronger signal
      - content: the longer text wins (edits add information); tie -> local
      - metadata_json: union of keys, local values win; `pinned` is OR'd
    """
    merged = dict(remote)
    merged["archived"] = 1 if (local.get("archived") or remote.get("archived")) else 0
    for field in ("confidence", "importance"):
        vals = [v for v in (local.get(field), remote.get(field)) if v is not None]
        merged[field] = max(vals) if vals else None
    lc, rc = local.get("content") or "", remote.get("content") or ""
    if len(lc) >= len(rc):
        merged["content"] = lc
        merged["content_hash"] = local.get("content_hash")
    try:
        lmd = json.loads(local.get("metadata_json") or "{}")
        rmd = json.loads(remote.get("metadata_json") or "{}")
        if isinstance(lmd, dict) and isinstance(rmd, dict):
            md = {**rmd, **lmd}
            if lmd.get("pinned") or rmd.get("pinned"):
                md["pinned"] = True
            merged["metadata_json"] = json.dumps(md, sort_keys=True)
    except (json.JSONDecodeError, TypeError):
        pass
    return merged


def render_memory(rec: dict[str, Any]) -> str:
    """Byte-deterministic file body for one memory."""
    return json.dumps(rec, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def render_relations(rels: list[dict[str, Any]]) -> str:
    """One edge per line, sorted+unique — git's union merge driver keeps
    concurrent additions from both machines without conflict markers."""
    lines = sorted({json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rels})
    return "\n".join(lines) + ("\n" if lines else "")


def parse_relations(text: str) -> list[dict[str, Any]]:
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("<<<") or line.startswith(">>>") or line.startswith("==="):
            continue  # tolerate stray conflict markers — union keeps content lines
        try:
            r = json.loads(line)
            if isinstance(r, dict):
                out.append(r)
        except json.JSONDecodeError:
            continue
    return out


# --------------------------------------------------------------------------- #
# git + engine glue
# --------------------------------------------------------------------------- #

def _git(repo: Path, *argv: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", "-C", str(repo), *argv], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(argv)} failed:\n{r.stderr.strip() or r.stdout.strip()}")
    return r


def _resolve_repo(flag: str) -> Path:
    """--repo beats config. A URL is cloned once to ~/.yggdrasil/sync; a local
    path is git-init'ed if needed. The choice persists in config for next time."""
    spec = flag or _cfg.resolve("sync_repo", None)
    if not spec:
        raise RuntimeError("no sync repo configured — run: ygg sync --repo <path-or-git-url>\n"
                           "  (create a PRIVATE empty repo first, e.g. on GitHub — memories are yours)")
    if "://" in spec or spec.startswith("git@"):
        local = Path(os.environ.get("YGG_HOME", str(Path.home() / ".yggdrasil"))) / "sync"
        if not (local / ".git").is_dir():
            local.parent.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(["git", "clone", spec, str(local)], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(f"git clone {spec} failed:\n{r.stderr.strip()}")
        repo = local
    else:
        repo = Path(spec).expanduser()
        repo.mkdir(parents=True, exist_ok=True)
        if not (repo / ".git").is_dir():
            _git(repo, "init", "-q")
    if flag:
        cfg = _cfg.load()
        cfg["sync_repo"] = spec
        _cfg.save(cfg)
    return repo


def _export(repo: Path, data: dict[str, Any]) -> int:
    """Write the store into the repo working tree. Returns how many memory
    files changed on disk (additive — never deletes: see module docstring)."""
    mem_dir = repo / "memories"
    mem_dir.mkdir(exist_ok=True)
    ga = repo / ".gitattributes"
    want = "relations.jsonl merge=union\n"
    if not ga.exists() or want not in ga.read_text(encoding="utf-8"):
        ga.write_text(want, encoding="utf-8")
    changed = 0
    for rec in data["memories"]:
        f = mem_dir / f"{rec['id']}.json"
        body = render_memory(rec)
        if not f.exists() or f.read_text(encoding="utf-8") != body:
            f.write_text(body, encoding="utf-8")
            changed += 1
    rel_file = repo / "relations.jsonl"
    existing = parse_relations(rel_file.read_text(encoding="utf-8")) if rel_file.exists() else []
    merged = existing + data["relations"]
    body = render_relations(merged)
    if not rel_file.exists() or rel_file.read_text(encoding="utf-8") != body:
        rel_file.write_text(body, encoding="utf-8")
    return changed


def _commit_if_dirty(repo: Path, msg: str) -> bool:
    _git(repo, "add", "-A")
    if not _git(repo, "status", "--porcelain").stdout.strip():
        return False
    _git(repo, "commit", "-q", "-m", msg)
    return True


def _has_remote(repo: Path) -> bool:
    return bool(_git(repo, "remote").stdout.strip())


def sync(args: argparse.Namespace) -> int:
    try:
        from . import ygg_ui
    except ImportError:
        import ygg_ui
    p = ygg_ui.palette()
    host = socket.gethostname().split(".")[0]
    try:
        repo = _resolve_repo(getattr(args, "repo", "") or "")
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 2

    print(f"🌳 ygg sync   {p.dim(str(repo))}")
    data = request_json("POST", "/sync_export", {})["data"]
    changed = _export(repo, data)
    _commit_if_dirty(repo, f"ygg sync: {host}: {len(data['memories'])} memories")
    print(f"  {ygg_ui.mark_ok(p)} exported   {len(data['memories'])} memories · "
          f"{len(data['relations'])} relations ({changed} changed)")

    pulled = False
    if _has_remote(repo):
        # -X ours: on a conflicting file our committed export wins for now; the
        # re-export after import writes the true merged version and commits it.
        _git(repo, "fetch", "-q", "origin")
        r = _git(repo, "pull", "-q", "--no-rebase", "-s", "recursive", "-X", "ours",
                 "--no-edit", "origin", check=False)
        pulled = r.returncode == 0
        if not pulled and "couldn't find remote ref" not in (r.stderr or "").lower():
            print(f"  {ygg_ui.mark_warn(p)} pull: {(r.stderr or r.stdout).strip().splitlines()[0] if (r.stderr or r.stdout).strip() else 'nothing to pull'}")

    # Import: every repo record that's new or different gets merged and upserted.
    local_by_id = {m["id"]: m for m in data["memories"]}
    winners: list[dict[str, Any]] = []
    for f in sorted((repo / "memories").glob("ygg_*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        mid = rec.get("id")
        if not mid:
            continue
        mine = local_by_id.get(mid)
        if mine is None:
            winners.append(rec)
        elif any(mine.get(k) != rec.get(k) for k in rec):
            winners.append(merge_memory(mine, rec))
    rel_file = repo / "relations.jsonl"
    rels = parse_relations(rel_file.read_text(encoding="utf-8")) if rel_file.exists() else []
    counts = {"added": 0, "updated": 0, "unchanged": 0, "relations_added": 0, "relations_skipped": 0}
    for i in range(0, len(winners), 500):
        got = request_json("POST", "/sync_upsert",
                           {"memories": winners[i:i + 500],
                            "relations": rels if i == 0 else []})["data"]
        for k in counts:
            counts[k] += got.get(k, 0)
    print(f"  {ygg_ui.mark_ok(p)} imported   +{counts['added']} new · {counts['updated']} merged · "
          f"+{counts['relations_added']} relations")

    # Re-export so the repo carries the merged truth, then publish.
    data2 = request_json("POST", "/sync_export", {})["data"]
    _export(repo, data2)
    _commit_if_dirty(repo, f"ygg sync: {host}: merge")
    if _has_remote(repo):
        r = _git(repo, "push", "-q", "origin", "HEAD", check=False)
        mark = ygg_ui.mark_ok(p) if r.returncode == 0 else ygg_ui.mark_fail(p)
        print(f"  {mark} push       " + ("done" if r.returncode == 0 else (r.stderr or "failed").strip().splitlines()[0]))
    else:
        print(f"  {ygg_ui.mark_warn(p)} no remote  local repo only — add one: "
              f"git -C {repo} remote add origin <your-private-repo>")
    if counts["added"]:
        print(f"  {p.dim('embeddings for new memories: run `ygg reindex`')}")
    return 0


def main(cmd: str, rest: list[str]) -> int:
    p = argparse.ArgumentParser(prog="ygg sync")
    p.add_argument("--repo", default="", help="git repo path or clone URL (persisted to config sync_repo)")
    args = p.parse_args(rest)
    return sync(args)
