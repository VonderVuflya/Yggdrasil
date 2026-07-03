#!/usr/bin/env python3
"""Cold-start onboarding for Yggdrasil: discover, estimate, distill, report.

This is the answer to the empty-memory "cold start": right after install the
store is empty and stays empty until the user figures out what to feed it. These
commands close that gap **in Yggdrasil's idiom** — curated, local-first, opt-in —
rather than the capture-everything firehose of heavier tools:

  ygg stats                 what's already in memory (project x type x scope)
  ygg seed                  find your work (Claude Code + Codex transcripts,
                            Obsidian vaults, repos), estimate cost, then distill
  ygg distill --source P    distill one dir/file into atomic lessons

Distillation uses your LOCAL Ollama background model (free) by default — raw
transcript -> a few durable lessons, deduped, with provenance. Nothing leaves
the machine.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:  # package + flat-layout (deployed scripts dir) imports
    from . import ygg as _ygg
    from . import ygg_config as _cfg
except ImportError:  # pragma: no cover
    import ygg as _ygg
    import ygg_config as _cfg

HOME = Path.home()
YGG_HOME = Path(os.environ.get("YGG_HOME", str(HOME / ".yggdrasil")))
MAX_CHARS_PER_FILE = 14000  # window we feed the local model per source file
# Distill endpoint + per-file timeout. These are the effective values; main()
# re-resolves them from flag > env > config before a seed/distill run. Big
# sessions can need a longer timeout — raise it with --timeout / `ygg config set
# distill_timeout`. Timed-out files are NOT marked done, so a re-run retries them.
OLLAMA_URL = _cfg.distill_url()
DISTILL_TIMEOUT = _cfg.distill_timeout()
DISTILL_NUM_CTX = _cfg.distill_num_ctx()


# --------------------------------------------------------------------------- #
# ygg stats — what's in memory right now
# --------------------------------------------------------------------------- #

def _scale_hint() -> str:
    """The engine's 'consider a vector backend' warning, if the store is large."""
    try:
        return _ygg.request_json("GET", "/health").get("scale_hint") or ""
    except _ygg.YggError:
        return ""


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
    try:
        from . import ygg_ui
    except ImportError:
        import ygg_ui
    p = ygg_ui.palette()
    head = (f"🌳 {p.bold('Yggdrasil memory')} — {p.bold(str(len(live)))} live "
            f"{p.dim(f'· {len(data) - len(live)} archived · db {size / 1024:.0f} KB')}")
    print(head + "\n")
    if not live:
        print("Memory is empty. Seed it from your existing work:  ygg seed")
        return 0

    def _table(title: str, counts: dict[str, int], *, typed: bool = False) -> None:
        items = sorted(counts.items(), key=lambda kv: -kv[1])
        mx = max((n for _, n in items), default=1)
        print(p.dim(title) if p.on else title)
        for k, n in items:
            label = ygg_ui.badge(k, p) if typed else k
            if p.on:
                w = max(1, round(12 * n / mx)) if n else 0
                print(f"  {n:>4}  {p.cyan('█' * w)}{' ' * (12 - w)}  {label}")
            else:
                print(f"  {n:>4}  {k}")
        print()
    _table("by project", by_project)
    _table("by type", by_type, typed=True)
    _table("by scope", by_scope)
    print("retrieve:  ygg recall --query \"…\"  (cross-project) · "
          "ygg bootstrap --project P  (one project)")
    hint = _scale_hint()
    if hint:
        print(f"\n⚠ {hint}")
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


def _codex_project(path: Path) -> str:
    """Project label for a Codex rollout-*.jsonl session, from its session_meta cwd."""
    try:
        with path.open(errors="replace") as fh:
            for _ in range(3):  # cwd lives in session_meta, among the first lines
                line = fh.readline()
                if not line:
                    break
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                p = ev.get("payload")
                if isinstance(p, dict) and p.get("cwd"):
                    return Path(p["cwd"]).name or "codex"
    except OSError:
        pass
    return "codex"


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

    # 2. Obsidian vaults (dirs containing a .obsidian/) under common roots, bounded depth.
    #    The iCloud root is where the official Obsidian iOS/macOS sync keeps vaults —
    #    for many users that's THE vault, and it was silently invisible before.
    roots = [HOME / "Documents", HOME / "Library" / "CloudStorage", HOME / "obsidian", HOME / "vaults",
             HOME / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents"]
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

    # 4. Codex CLI sessions (rollout-*.jsonl), grouped by each session's cwd project
    #    so Codex lessons merge into the same project buckets as Claude's.
    cdex = HOME / ".codex" / "sessions"
    if cdex.is_dir():
        by_project: dict[str, list[Path]] = {}
        for f in cdex.glob("**/rollout-*.jsonl"):
            by_project.setdefault(_codex_project(f), []).append(f)
        for project, files in sorted(by_project.items()):
            tbytes = 0
            for f in files:
                try:
                    tbytes += f.stat().st_size
                except OSError:
                    pass
            sources.append({
                "kind": "codex", "path": str(cdex), "project": project,
                "bytes": tbytes, "files": len(files),
                "paths": sorted(str(f) for f in files),
                "detail": f"{len(files)} Codex session(s)",
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
  derivable from the code. NEVER include secrets/tokens/keys.{LANG}
Work log follows:
---
{TEXT}
---
Return only the JSON object."""

# Small distill models (e.g. qwen2.5:3b) have a strong bias toward translating
# non-English content into Chinese. A soft "keep the source language" rule isn't
# enough; naming the target language EXPLICITLY is. Detect a Cyrillic-dominant
# log deterministically in code and inject a hard directive.
def _lang_directive(text: str) -> str:
    sample = text[:4000]
    cyr = sum(1 for c in sample if "а" <= c.lower() <= "я" or c.lower() == "ё")
    lat = sum(1 for c in sample if "a" <= c.lower() <= "z")
    if cyr > 40 and cyr >= lat:
        return ('\n- IMPORTANT: write every "content" value in RUSSIAN. Do NOT translate '
                "to English or Chinese. Keep code identifiers, commands and names verbatim.")
    return ('\n- Write each "content" in the SAME language as the work log — do NOT '
            "translate. Keep code identifiers, commands and names verbatim.")


def _salvage_lessons(raw: str) -> list:
    """Pull lesson objects out of malformed JSON. Scans for every balanced
    `{…}` at ANY nesting depth (a stack of open positions; braces inside strings
    are ignored) and parses each on its own, keeping dicts that carry content —
    so a missing comma or a truncated tail no longer discards the whole file."""
    out: list = []
    stack: list[int] = []
    in_str = esc = False
    for i, ch in enumerate(raw):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            stack.append(i)
        elif ch == "}" and stack:
            start = stack.pop()
            try:
                obj = json.loads(raw[start:i + 1])
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(obj, dict) and (obj.get("content") or obj.get("text")):
                out.append(obj)
    return out


def _lessons_from_raw(raw: str) -> list | None:
    """Parse the model's JSON into a list of lesson items, tolerantly.

    Returns a list (possibly empty = the model validly found no lessons), or
    None when the output was UNPARSEABLE (empty / malformed with nothing to
    salvage) — the caller treats None as a failure to retry, so the file is
    re-distilled next run rather than silently marked done with zero lessons."""
    raw = _strip_fences(raw)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            if isinstance(parsed.get("lessons"), list):
                return parsed["lessons"]
            if parsed.get("content") or parsed.get("text"):
                return [parsed]
            return []  # valid JSON, no lessons — done, not a failure
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        pass
    salvaged = _salvage_lessons(raw)
    return salvaged if salvaged else None


def _strip_fences(text: str) -> str:
    """Unwrap a ```json … ``` (or bare ```) markdown fence. Servers that ignore
    strict format=json (e.g. phone/on-device LLM apps) fence their JSON; plain
    Ollama output passes through untouched."""
    t = (text or "").strip()
    if not t.startswith("```"):
        return t
    first_nl = t.find("\n")
    if first_nl != -1:
        t = t[first_nl + 1:]
    t = t.rstrip()
    if t.endswith("```"):
        t = t[:-3]
    return t.strip()


def _post_json(url: str, body: dict, timeout: int) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


_TRUNCATED_MSG = ("model output truncated (ran out of output tokens) — nothing saved for this "
                  "file; raise `ygg config set distill_num_ctx` or use a larger model")

# base URL -> API dialect that worked ("generate" | "chat" | "openai"), so the
# fallback probing is paid once per endpoint, not once per file.
_ENDPOINT_CACHE: dict[str, str] = {}


# How long a STREAMING generation may go silent (no token) before we treat the
# connection as dead. A live model streams tokens continuously, so real silence
# this long means the peer vanished (phone locked, Wi-Fi dropped) — abort in
# ~this window instead of blocking the full DISTILL_TIMEOUT. Prefill of the
# capped 14k-char prompt stays well under it even on a phone.
STREAM_IDLE_TIMEOUT = int(os.environ.get("YGG_DISTILL_IDLE", "90"))


def _stream_collect(url: str, body: dict, mode: str, idle: int, total: int) -> tuple[str, str | None]:
    """POST a streaming request and assemble the text token-by-token.

    The socket timeout is the IDLE window: each read blocks at most `idle`
    seconds, so a stalled connection raises promptly rather than hanging until
    the total deadline. `total` is a belt-and-suspenders overall wall cap.
    Returns (text, finish_reason)."""
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    parts: list[str] = []
    finish: str | None = None
    start = time.monotonic()
    with urllib.request.urlopen(req, timeout=idle) as resp:  # connect + each read bounded by idle
        for raw in resp:
            if time.monotonic() - start > total:
                raise TimeoutError("exceeded total distill deadline")
            line = raw.strip()
            if not line:
                continue
            if mode == "openai":
                if not line.startswith(b"data:"):
                    continue
                payload = line[5:].strip()
                if payload == b"[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except ValueError:
                    continue
                ch = (obj.get("choices") or [{}])[0]
                parts.append((ch.get("delta") or {}).get("content") or "")
                if ch.get("finish_reason"):
                    finish = ch["finish_reason"]
            else:  # ollama generate / chat: newline-delimited JSON objects
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if mode == "ollama_generate":
                    parts.append(obj.get("response") or "")
                else:
                    parts.append((obj.get("message") or {}).get("content") or "")
                if obj.get("done"):
                    finish = obj.get("done_reason") or finish
                    break
    return "".join(parts), finish


def _ollama_generate(model: str, prompt: str, timeout: int | None = None) -> str:
    """Call the distill endpoint — speaking whichever dialect it implements,
    STREAMING so a dead connection is caught within STREAM_IDLE_TIMEOUT instead
    of hanging the full timeout.

    Tries, in order: Ollama's classic /api/generate, Ollama's /api/chat, and
    OpenAI-style /v1/chat/completions — falling through on 404 only. This makes
    `--ollama-url` work against anything on the LAN: Ollama, LM Studio,
    llama.cpp-server, exo, and phone LLM-server apps.

    num_ctx is sent EXPLICITLY on the Ollama dialects: without it Ollama applies
    its server default (often 4096), silently truncating long transcripts."""
    total = timeout or DISTILL_TIMEOUT
    idle = min(total, STREAM_IDLE_TIMEOUT)

    def base(kind: str) -> tuple[str, str, dict]:
        if kind == "generate":
            return (f"{OLLAMA_URL}/api/generate", "ollama_generate",
                    {"model": model, "prompt": prompt, "format": "json",
                     "options": {"num_ctx": DISTILL_NUM_CTX}})
        if kind == "chat":
            return (f"{OLLAMA_URL}/api/chat", "ollama_chat",
                    {"model": model, "messages": [{"role": "user", "content": prompt}],
                     "format": "json", "options": {"num_ctx": DISTILL_NUM_CTX}})
        return (f"{OLLAMA_URL}/v1/chat/completions", "openai",
                {"model": model, "messages": [{"role": "user", "content": prompt}]})

    def extract(mode: str, data: dict) -> tuple[str, str | None]:
        if mode == "ollama_generate":
            return data.get("response", ""), data.get("done_reason")
        if mode == "ollama_chat":
            return (data.get("message") or {}).get("content", ""), data.get("done_reason")
        ch = (data.get("choices") or [{}])[0]
        return (ch.get("message") or {}).get("content", "") or "", ch.get("finish_reason")

    # (dialect, streaming?) pairs. Streaming FIRST — a real Ollama/LM Studio
    # streams tokens so a dead peer is caught within `idle`, and big files can run
    # for `total`. Non-streaming SECOND for servers that don't stream (found live:
    # ai.local answers stream=True with an empty body, only works non-streamed) —
    # capped at `idle`, not `total`, so a phone that vanishes mid-request is caught
    # in ~90s instead of hanging the full timeout.
    attempts = [(k, True) for k in ("generate", "chat", "openai")] \
        + [(k, False) for k in ("generate", "chat", "openai")]
    cached = _ENDPOINT_CACHE.get(OLLAMA_URL)
    if cached in attempts:
        attempts.remove(cached)
        attempts.insert(0, cached)

    last_404: Exception | None = None
    for kind, stream in attempts:
        url, mode, body = base(kind)
        try:
            if stream:
                out, finish = _stream_collect(url, {**body, "stream": True}, mode, idle, total)
            else:
                data = _post_json(url, {**body, "stream": False}, idle)
                out, finish = extract(mode, data)
            if finish == "length":
                raise ValueError(_TRUNCATED_MSG)
            if _strip_fences(out):  # only cache a combo that actually produced text
                _ENDPOINT_CACHE[OLLAMA_URL] = (kind, stream)
                return _strip_fences(out)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:  # dialect not implemented here — try the next
                last_404 = exc
                continue
            raise
    if last_404:
        raise last_404
    return ""  # every attempt returned empty -> caller retries, then errors


def _is_timeout(exc: BaseException) -> bool:
    """True if this distill failure was a timeout (file too big for the limit),
    not a hang — so we can advise raising YGG_DISTILL_TIMEOUT and retry the file."""
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return True
    if isinstance(getattr(exc, "reason", None), (socket.timeout, TimeoutError)):
        return True
    s = str(exc).lower()
    return "timed out" in s or "errno 60" in s


# User text items Codex injects as context, not real dialogue — skipped at extract.
_CODEX_NOISE = ("# AGENTS.md", "<environment_context>", "<user_instructions>", "<INSTRUCTIONS>")


def _extract_codex_text(path: Path) -> str:
    """Pull the user/assistant dialogue out of a Codex rollout-*.jsonl session.

    Codex's shape differs from Claude's: dialogue lives in `response_item` lines
    whose `payload` is a message with a `content` list of {type, text} parts. We
    keep user+assistant turns and drop `developer` (AGENTS.md/system injections).
    """
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
            if ev.get("type") != "response_item":
                continue
            p = ev.get("payload")
            if not isinstance(p, dict) or p.get("type") != "message":
                continue
            if p.get("role") not in ("user", "assistant"):
                continue
            content = p.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    t = part["text"].strip()
                    if t and not t.startswith(_CODEX_NOISE):
                        out.append(t)
    except OSError:
        return ""
    return "\n".join(out)


def _extract_text(path: Path) -> str:
    """Pull human-readable text out of a source file (.jsonl transcript or .md)."""
    if path.suffix == ".md":
        try:
            return path.read_text(errors="replace")
        except OSError:
            return ""
    if ".codex/sessions" in str(path) or "/.codex/" in str(path):
        return _extract_codex_text(path)
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
        return {"added": 0, "dup": 0, "errors": 0, "timed_out": False}
    text = text[-MAX_CHARS_PER_FILE:]  # keep the most recent window
    prompt = DISTILL_PROMPT.replace("{LANG}", _lang_directive(text)).replace("{TEXT}", text)
    try:
        lessons = _lessons_from_raw(_ollama_generate(model, prompt))
        # Unparseable output → retry ONCE (these models are non-deterministic;
        # a re-roll usually parses clean). Salvage already recovered partial JSON.
        if lessons is None:
            lessons = _lessons_from_raw(_ollama_generate(model, prompt))
        if lessons is None:
            print(f"    distill skipped {project}: model returned malformed JSON twice "
                  "— will retry on the next `ygg seed`", file=sys.stderr)
            return {"added": 0, "dup": 0, "errors": 1, "timed_out": False}
    except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError) as exc:
        timed_out = _is_timeout(exc)
        why = ("timed out (file too big / model slow — raise --timeout)" if timed_out
               else f"model call failed ({exc}); will retry on the next `ygg seed`")
        print(f"    distill skipped {project}: {why}", file=sys.stderr)
        return {"added": 0, "dup": 0, "errors": 1, "timed_out": timed_out}
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
    return {"added": added, "dup": dup, "errors": errors, "timed_out": False}


# --------------------------------------------------------------------------- #
# incremental state — only (re)distill new or CHANGED files
# --------------------------------------------------------------------------- #

_SEED_STATE = YGG_HOME / "seed-state.json"


def _load_seed_state() -> dict:
    try:
        data = json.loads(_SEED_STATE.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_seed_state(state: dict) -> None:
    try:
        YGG_HOME.mkdir(parents=True, exist_ok=True)
        _SEED_STATE.write_text(json.dumps(state))
    except OSError:
        pass


def _source_files(src: dict[str, Any]) -> list[Path]:
    base = Path(src["path"])
    if src["kind"] == "claude":
        return sorted(base.glob("*.jsonl")) + sorted((base / "memory").glob("*.md"))
    if src["kind"] == "obsidian":
        # Bounded, but most-recent-first: the old alphabetical [:50] silently
        # dropped an arbitrary slice of larger vaults (a 151-note vault kept
        # notes A–G). Recency is the right priority for memory, and the bound
        # is generous enough for real personal vaults.
        notes = sorted(base.glob("**/*.md"),
                       key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        return notes[:500]
    if src["kind"] == "repo":
        return [base / "CLAUDE.md"]
    if src["kind"] == "codex":  # explicit per-project file list gathered in discover()
        return [Path(p) for p in src.get("paths", [])]
    return []


def _is_unchanged(f: Path, state: dict) -> bool:
    """True iff this file was already distilled at its CURRENT mtime + size — so a
    transcript the user kept chatting in (mtime/size changed) is re-distilled."""
    prev = state.get(str(f))
    if not prev:
        return False
    try:
        st = f.stat()
    except OSError:
        return False
    return prev.get("mtime") == st.st_mtime and prev.get("size") == st.st_size


# --------------------------------------------------------------------------- #
# live progress — colorful animated CLI, pure stdlib (ANSI + a spinner thread).
# Falls back to plain lines when stdout isn't a TTY (pipes/CI), or NO_COLOR set.
# --------------------------------------------------------------------------- #

class _C:
    """Minimal ANSI colorizer, gated once on tty + NO_COLOR."""
    def __init__(self, on: bool):
        self.on = on

    def __call__(self, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.on else s

    def cyan(self, s): return self("36", s)
    def green(self, s): return self("32", s)
    def red(self, s): return self("31", s)
    def yellow(self, s): return self("33", s)
    def magenta(self, s): return self("35", s)
    def dim(self, s): return self("2", s)
    def bold(self, s): return self("1", s)


def _fmt_dur(sec: float) -> str:
    sec = int(max(0, sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class _Progress:
    """A single live status line (animated spinner + bar + ETA) with scrollback
    logging above it, plus a final summary. Thread-safe; safe on non-TTY."""

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, total: int, *, db_path: str | None = None):
        self.total = max(0, total)
        self.done = 0
        self.added = self.dup = self.errors = self.timed_out = 0
        self.start = time.time()
        self.label = "starting…"
        self.db_path = db_path
        self.db_start = self._db_size()
        self.tty = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None and self.total > 0
        self.c = _C(self.tty)
        self._i = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        if self.tty:
            self._thread = threading.Thread(target=self._animate, daemon=True)
            self._thread.start()

    def _db_size(self) -> int:
        try:
            return Path(self.db_path).stat().st_size if self.db_path else 0
        except OSError:
            return 0

    def _animate(self) -> None:
        while not self._stop.wait(0.12):
            with self._lock:
                self._i = (self._i + 1) % len(self.FRAMES)
                self._draw()

    def _draw(self) -> None:
        if not self.tty:
            return
        cols = shutil.get_terminal_size((90, 20)).columns
        frac = self.done / self.total if self.total else 1.0
        width = 20
        fill = int(width * frac)
        bar = self.c.green("█" * fill) + self.c.dim("░" * (width - fill))
        el = time.time() - self.start
        eta = (el / self.done * (self.total - self.done)) if self.done else 0.0
        spin = self.c.cyan(self.FRAMES[self._i])
        label = self.label if len(self.label) <= 34 else self.label[:33] + "…"
        eta_s = f" {self.c.dim('· ~' + _fmt_dur(eta) + ' left')}" if self.done else ""
        line = (f"\r{spin} [{bar}] {self.c.bold(f'{frac * 100:3.0f}%')} "
                f"{self.done}/{self.total} {self.c.dim('·')} {self.c.cyan(label)} "
                f"{self.c.green('+' + str(self.added))} {self.c.dim('· ' + _fmt_dur(el))}{eta_s}")
        try:
            sys.stdout.write(line + "\033[K")
            sys.stdout.flush()
        except (OSError, ValueError):
            pass

    def set_label(self, label: str) -> None:
        with self._lock:
            self.label = label
            self._draw()

    def file_done(self, res: dict) -> None:
        with self._lock:
            self.done += 1
            self.added += res.get("added", 0)
            self.dup += res.get("dup", 0)
            self.errors += res.get("errors", 0)
            self.timed_out += 1 if res.get("timed_out") else 0
            self._draw()

    def log(self, msg: str) -> None:
        with self._lock:
            if self.tty:
                sys.stdout.write("\r\033[K")
            print(msg)
            if self.tty:
                self._draw()

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
            self._thread = None
        if self.tty:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

    def summary(self, *, interrupted: bool = False, up_to_date: tuple[int, int] = (0, 0)) -> None:
        self.close()
        el = time.time() - self.start
        rate = self.done / (el / 60) if el > 0 else 0.0
        head = self.c.yellow("⚠ interrupted") if interrupted else self.c.green("✓ done")
        print(f"\n🌳 {self.c.bold('Yggdrasil seed')} — {head}")
        print(f"   distilled : {self.c.bold(str(self.done))}/{self.total} files "
              f"{self.c.dim(f'({rate:.1f}/min)')}")
        print(f"   lessons   : {self.c.green('+' + str(self.added))} new "
              f"{self.c.dim(f'· {self.dup} merged · {self.errors} to retry')}")
        # One line instead of dozens of '+0 new … unchanged' project rows.
        up_proj, up_files = up_to_date
        if up_proj:
            print(f"   unchanged : {self.c.dim(f'{up_proj} projects already up to date '
                                               f'({up_files} files skipped, no re-distill)')}")
        print(f"   elapsed   : {_fmt_dur(el)}")
        if self.db_path:
            now = self._db_size()
            grew = now - self.db_start
            sign = "+" if grew >= 0 else ""
            print(f"   memory db : {now / 1_048_576:.1f} MB "
                  f"{self.c.dim(f'({sign}{grew / 1024:.0f} KB this run)')}")


def distill_source(src: dict[str, Any], *, model: str, user_id: str, namespace: str,
                   project_override: str | None = None, state: dict | None = None,
                   force: bool = False, progress: "_Progress | None" = None) -> dict[str, int]:
    project = project_override or src["project"]
    files = [f for f in _source_files(src) if f.exists()]
    agg = {"added": 0, "dup": 0, "errors": 0, "skipped": 0, "timed_out": 0}
    if state is not None and not force:
        todo = []
        for f in files:
            if _is_unchanged(f, state):
                agg["skipped"] += 1
            else:
                todo.append(f)
    else:
        todo = files
    if progress is None:
        extra = f", {agg['skipped']} unchanged" if agg["skipped"] else ""
        print(f"  distilling {project} ({len(todo)} file(s){extra}) ...")
    for f in todo:
        if progress is not None:
            progress.set_label(f"{project} · {f.name}")
        try:
            res = distill_text(_extract_text(f), project=project, source=f"seed:{src['kind']}",
                               model=model, user_id=user_id, namespace=namespace)
        except Exception as exc:  # noqa: BLE001 — one bad file must never abort the source
            (progress.log if progress else lambda m: print(m, file=sys.stderr))(f"    skipped {f.name}: {exc}")
            res = {"added": 0, "dup": 0, "errors": 1, "timed_out": _is_timeout(exc)}
        for k in ("added", "dup", "errors"):
            agg[k] += res[k]
        agg["timed_out"] += 1 if res.get("timed_out") else 0
        if progress is not None:
            progress.file_done(res)
        # Record state so the next run skips this file — UNLESS it timed out, so a
        # plain re-run (with a higher YGG_DISTILL_TIMEOUT) retries just the big ones.
        if state is not None and not res.get("timed_out"):
            try:
                st = f.stat()
                state[str(f)] = {"mtime": st.st_mtime, "size": st.st_size, "distilled_at": time.time()}
            except OSError:
                pass
    stable = (f"  {project}: +{agg['added']} new, {agg['dup']} dup-skipped, "
              f"{agg['skipped']} unchanged, {agg['errors']} error(s)")
    if progress is not None and not progress.tty:
        progress.log(stable)          # non-TTY (agents/pipes): keep the stable line
    elif progress is not None:
        # TTY: only surface a project where something actually happened — an
        # all-unchanged project stays silent (the bar already moved past it).
        if agg["added"] or agg["errors"] or agg["timed_out"]:
            c = progress.c
            bits = []
            if agg["added"]:
                bits.append(c.green(f"+{agg['added']} lessons"))
            if agg["dup"]:
                bits.append(c.dim(f"{agg['dup']} merged"))
            if agg["errors"]:
                bits.append(c.yellow(f"{agg['errors']} to retry"))
            mark = c.yellow("•") if agg["errors"] else c.green("✓")
            progress.log(f"  {mark} {c.bold(project)}  " + c.dim(" · ").join(bits))
    else:
        print(stable.strip())         # `ygg distill` path (no progress object)
    return agg


# --------------------------------------------------------------------------- #
# seed orchestrator
# --------------------------------------------------------------------------- #

def _bg_model() -> str:
    return _cfg.bg_model()


def seed(args: argparse.Namespace) -> int:
    sources = discover()
    if not sources:
        print("No seedable sources found (Claude Code + Codex transcripts, Obsidian vaults, "
              "or repos with CLAUDE.md). Nothing to do.")
        return 0
    force = getattr(args, "force", False)
    state = {} if force else _load_seed_state()

    # Per-source new/total counts (incremental: only NEW/CHANGED files cost
    # anything). We keep the per-source breakdown so the summary can show WHERE
    # the work is, not just a grand total.
    src_stats: list[dict[str, Any]] = []
    all_files: list[Path] = []
    for s in sources:
        files = [f for f in _source_files(s) if f.exists()]
        new = files if force else [f for f in files if not _is_unchanged(f, state)]
        all_files.extend(files)
        src_stats.append({"kind": s["kind"], "project": s["project"],
                          "files": len(files), "new": len(new), "new_paths": new})
    new_files = [f for st in src_stats for f in st["new_paths"]]
    total = len(all_files)
    unchanged = total - len(new_files)
    new_bytes = 0
    for f in new_files:
        try:
            new_bytes += f.stat().st_size
        except OSError:
            pass
    capped = min(new_bytes, MAX_CHARS_PER_FILE * max(1, len(new_files)))
    tokens_in = capped // 4
    minutes = max(1, round(len(new_files) * 6 / 60 + tokens_in / 9000))
    model = args.model or _bg_model()
    _local = OLLAMA_URL in ("http://127.0.0.1:11434", "http://localhost:11434")
    verbose = getattr(args, "verbose", False)

    try:
        from . import ygg_ui
    except ImportError:
        import ygg_ui
    p = ygg_ui.palette()

    if verbose:
        print("Sources to seed memory from:\n")
        for i, s in enumerate(sources):
            print(f"  [{i}] {s['kind']:8} {s['project']:<28} {_fmt_mb(s['bytes']):>9}  {s['detail']}")
            print(f"      {s['path']}")
        print()

    print(f"🌳 {p.bold('Yggdrasil seed')}\n")
    # Coverage meter — how much of the whole corpus is already distilled.
    pct = round(100 * unchanged / total) if total else 100
    cw = 26
    fill = round(cw * pct / 100)
    covbar = p.green("█" * fill) + p.dim("░" * (cw - fill))
    print(f"   {p.dim('distilled ')}  {covbar}  {p.bold(f'{pct}%')}   {p.dim(f'· {unchanged} / {total} files')}")
    where = "local" if _local else OLLAMA_URL
    print(f"   {p.dim('to distill')}  {p.bold(str(len(new_files)))} files  "
          f"{p.dim(f'· ≈{minutes} min · ~{tokens_in:,} tokens · {model} · {where}')}")

    # Busiest sources — a mini-histogram so it's obvious WHERE the time goes.
    busiest = sorted((s for s in src_stats if s["new"] > 0), key=lambda s: -s["new"])
    if busiest and not verbose:
        mxnew = busiest[0]["new"] or 1
        print(f"\n   {p.dim('busiest sources (new work)')}")
        for s in busiest[:6]:
            bw = max(1, round(18 * s["new"] / mxnew))
            bar_field = p.cyan("█" * bw) + " " * (18 - bw)  # colour bar, pad plainly
            print(f"     {s['project'][:17].ljust(17)} {bar_field}  "
                  f"{p.bold(str(s['new']).rjust(3))}   {p.dim(s['kind'])}")
        if len(busiest) > 6:
            print(f"     {p.dim(f'… and {len(busiest) - 6} more')}")

    tail = "nothing leaves your machine" if _local else "stays on your own box"
    print(f"\n  {p.dim(f'one chat → several lessons · {tail}')}")
    if not verbose:
        print(f"  {p.dim('(ygg seed --verbose to list every source + path)')}")
    print()

    if args.dry_run:
        print("(dry run — nothing written. Re-run without --dry-run to distill.)")
        return 0
    if not new_files:
        print("Everything is already distilled — nothing to do. New/edited chats are picked up next run.")
        return 0
    if sys.stdin.isatty() and not args.yes:
        try:
            if not input("Proceed with local distill now? [y/N]: ").strip().lower().startswith("y"):
                print("aborted.")
                return 0
        except EOFError:
            return 0

    progress = _Progress(len(new_files), db_path=str(YGG_HOME / "data" / "memory.sqlite"))
    interrupted = False
    up_to_date_projects = up_to_date_files = 0  # projects that had nothing new to do
    try:
        for s in sources:
            try:
                agg = distill_source(s, model=model, user_id=args.user_id, namespace=args.namespace,
                                     state=state, force=force, progress=progress)
                if not (agg["added"] or agg["errors"] or agg["timed_out"]) and agg["skipped"]:
                    up_to_date_projects += 1
                    up_to_date_files += agg["skipped"]
            except Exception as exc:  # noqa: BLE001 — one bad source must never abort the seed
                progress.log(f"  skipped {s.get('project')}: {exc}")
            _save_seed_state(state)  # persist progress after each source (crash-safe)
    except KeyboardInterrupt:  # Ctrl-C: stop cleanly and still show the summary
        interrupted = True
        _save_seed_state(state)
    progress.summary(interrupted=interrupted,
                     up_to_date=(up_to_date_projects, up_to_date_files))
    if progress.timed_out:
        n = progress.timed_out
        higher = max(180, DISTILL_TIMEOUT * 2)
        # Suggest the clean flag form (mirrors whatever endpoint/model this run used).
        flags = [f"--timeout {higher}"]
        if OLLAMA_URL not in ("http://127.0.0.1:11434", "http://localhost:11434"):
            flags.append(f"--ollama-url {OLLAMA_URL}")
        if getattr(args, "model", None):
            flags.append(f"--model {args.model}")
        print(f"\n⏱ {n} file(s) timed out at {DISTILL_TIMEOUT}s — they're large, not stuck "
              "(the local model just needs longer on big sessions).")
        print("  They were NOT marked done, so a re-run retries only them. Raise the limit:")
        print(f"    ygg seed {' '.join(flags)}")
        print(f"  Or make it permanent:  ygg config set distill_timeout {higher}")
    print("Check it:  ygg stats   ·   retrieve:  ygg recall --query \"…\"")
    hint = _scale_hint()
    if hint:
        print(f"\n⚠ {hint}")
    return 0


def distill_cmd(args: argparse.Namespace) -> int:
    path = Path(args.source).expanduser()
    if not path.exists():
        print(f"no such source: {path}", file=sys.stderr)
        return 1
    model = args.model or _bg_model()
    project = args.project or path.name
    state = _load_seed_state()  # explicit distill still records state, so `seed` skips it later
    if path.is_file():
        res = distill_text(_extract_text(path), project=project, source="distill",
                           model=model, user_id=args.user_id, namespace=args.namespace)
        try:
            st = path.stat()
            state[str(path)] = {"mtime": st.st_mtime, "size": st.st_size, "distilled_at": time.time()}
        except OSError:
            pass
    else:
        kind = "claude" if (path / "memory").is_dir() or list(path.glob("*.jsonl")) else "obsidian"
        res = distill_source({"kind": kind, "path": str(path), "project": project,
                              "bytes": 0, "files": 0}, model=model,
                             user_id=args.user_id, namespace=args.namespace,
                             project_override=project, state=state, force=True)
    _save_seed_state(state)
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
    if cmd in ("seed", "distill"):
        p.add_argument("--ollama-url", default="", dest="ollama_url",
                       help="Ollama endpoint for distillation, e.g. http://192.168.3.124:11434 "
                            "(default: config distill_url, else local)")
        p.add_argument("--timeout", default="", help="per-file distill timeout in seconds (default: config distill_timeout)")
    if cmd == "seed":
        p.add_argument("--dry-run", action="store_true", help="discover + estimate only, write nothing")
        p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
        p.add_argument("--force", action="store_true", help="re-distill everything (ignore the incremental seed state)")
        p.add_argument("--verbose", "-v", action="store_true", help="list every source with its path (default: a grouped summary)")
    if cmd == "distill":
        p.add_argument("--source", required=True, help="dir or file to distill")
        p.add_argument("--project", help="project label for the lessons (default: source name)")
    args = p.parse_args(rest)
    args.model = args.model or None
    # Apply flag > env > config > default for the distill endpoint + timeout, by
    # setting the module globals _ollama_generate reads. (stats has no such flags.)
    if cmd in ("seed", "distill"):
        global OLLAMA_URL, DISTILL_TIMEOUT
        OLLAMA_URL = _cfg.distill_url(getattr(args, "ollama_url", "") or None)
        DISTILL_TIMEOUT = _cfg.distill_timeout(getattr(args, "timeout", "") or None)
    if cmd == "stats":
        return stats(args.user_id, args.namespace)
    if cmd == "seed":
        return seed(args)
    if cmd == "distill":
        return distill_cmd(args)
    print(f"unknown seed command: {cmd}", file=sys.stderr)
    return 2
