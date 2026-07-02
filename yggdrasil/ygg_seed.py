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
  derivable from the code. NEVER include secrets/tokens/keys.
Work log follows:
---
{TEXT}
---
Return only the JSON object."""


def _ollama_generate(model: str, prompt: str, timeout: int | None = None) -> str:
    # num_ctx is sent EXPLICITLY: without it Ollama applies its server default
    # (often 4096), silently truncating long transcripts — lesson quality then
    # depends on a setting the user never chose.
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json",
                       "options": {"num_ctx": DISTILL_NUM_CTX}}).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout or DISTILL_TIMEOUT) as r:
        data = json.loads(r.read().decode("utf-8"))
    if data.get("done_reason") == "length":
        # The model ran out of output tokens mid-JSON. Persisting a truncated
        # stub as a "lesson" is worse than persisting nothing.
        raise ValueError(
            "model output truncated (done_reason=length) — nothing saved for this file; "
            "raise `ygg config set distill_num_ctx` or use a larger model"
        )
    return data.get("response", "")


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
        timed_out = _is_timeout(exc)
        why = "timed out (file too big for the limit)" if timed_out else str(exc)
        print(f"    distill failed for {project}: {why}", file=sys.stderr)
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
        return sorted(base.glob("**/*.md"))[:50]
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

    def summary(self, *, interrupted: bool = False) -> None:
        self.close()
        el = time.time() - self.start
        rate = self.done / (el / 60) if el > 0 else 0.0
        head = self.c.yellow("⚠ interrupted") if interrupted else self.c.green("✓ done")
        print(f"\n🌳 {self.c.bold('Yggdrasil seed')} — {head}")
        print(f"   distilled : {self.c.bold(str(self.done))}/{self.total} files "
              f"{self.c.dim(f'({rate:.1f}/min)')}")
        print(f"   lessons   : {self.c.green('+' + str(self.added))} new "
              f"{self.c.dim(f'· {self.dup} dup · {self.errors} err')}")
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
    summary = (f"  {project}: +{agg['added']} new, {agg['dup']} dup-skipped, "
               f"{agg['skipped']} unchanged, {agg['errors']} error(s)")
    if progress is not None:
        progress.log(summary)
    else:
        print(f"  " + summary.strip())
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
    print("Found sources to seed memory from:\n")
    for i, s in enumerate(sources):
        print(f"  [{i}] {s['kind']:8} {s['project']:<28} {_fmt_mb(s['bytes']):>9}  {s['detail']}")
        print(f"      {s['path']}")

    # Incremental estimate — only NEW/CHANGED files cost anything.
    all_files = [f for s in sources for f in _source_files(s) if f.exists()]
    new_files = [f for f in all_files if force or not _is_unchanged(f, state)]
    unchanged = len(all_files) - len(new_files)
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
    skipped_note = f" ({unchanged} unchanged — skipped)" if unchanged else ""
    print(f"\nEstimate: {len(new_files)} new/changed file(s) to distill{skipped_note}, "
          f"~{tokens_in:,} input tokens, ≈{minutes} min.")
    _local = OLLAMA_URL in ("http://127.0.0.1:11434", "http://localhost:11434")
    _where = "LOCALLY" if _local else f"on {OLLAMA_URL}"
    _priv = "nothing leaves your machine" if _local else "stays on your own Ollama box"
    print(f"Distill runs {_where} via Ollama model '{model}' — free, {_priv}.")
    if not force:
        print("Incremental: already-distilled files are skipped (re-run picks up only new/edited "
              "chats). Use --force to redo everything.")
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
    try:
        for s in sources:
            try:
                distill_source(s, model=model, user_id=args.user_id, namespace=args.namespace,
                               state=state, force=force, progress=progress)
            except Exception as exc:  # noqa: BLE001 — one bad source must never abort the seed
                progress.log(f"  skipped {s.get('project')}: {exc}")
            _save_seed_state(state)  # persist progress after each source (crash-safe)
    except KeyboardInterrupt:  # Ctrl-C: stop cleanly and still show the summary
        interrupted = True
        _save_seed_state(state)
    progress.summary(interrupted=interrupted)
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
