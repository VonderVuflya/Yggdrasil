#!/usr/bin/env python3
"""Claude Code SessionStart hook: inject relevant Yggdrasil memory for the project.

Reads the hook payload on stdin, derives the project from the working directory
(git toplevel basename), queries the running Yggdrasil engine, and emits the top
matching memories as `additionalContext` so the agent starts with prior lessons
already in context — the retrieval half of the self-learning loop.

Fail-safe by design: any error (engine down, no token, no memory) prints nothing
and exits 0, so it can never break or slow a session noticeably.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path


URL = os.environ.get("YGG_ENGINE_URL", "http://127.0.0.1:42069").rstrip("/")
NAMESPACE = os.environ.get("YGG_NAMESPACE", "yggdrasil-demo")
USER_ID = os.environ.get("YGG_USER_ID", "demo-user")
LIMIT = int(os.environ.get("YGG_BOOTSTRAP_LIMIT", "5"))


def token() -> str:
    tok = os.environ.get("YGG_ENGINE_TOKEN")
    if tok:
        return tok
    try:
        return (Path.home() / ".yggdrasil" / "token").read_text().strip()
    except OSError:
        return "yggdrasil-demo-token"


# The assistant's persistent "soul": a tiny always-injected identity so any LLM,
# in any project, behaves like the same named assistant. Overridable via
# ~/.yggdrasil/identity.json ({name, persona, user_facts:[...]}).
DEFAULT_IDENTITY = {
    "name": "Yggdrasil",
    "persona": ("a concise, proactive engineering copilot with long-term memory. "
                "Lead with the answer, stay direct, flag uncertainty, and reuse prior "
                "decisions and lessons (across projects) when they are relevant."),
    "user_facts": [],
}

# Always-injected proactivity directive — the "forcing function" a passive skill
# lacks. Turns "the model might call the tools" into "recall before, remember after".
PROACTIVE_DIRECTIVE = (
    "Yggdrasil durable memory is available through the ygg_* tools — use it proactively, "
    "without waiting to be asked:\n"
    "- BEFORE non-trivial work, call ygg_recall (across projects) or ygg_bootstrap "
    "(this project) to reuse prior decisions and lessons.\n"
    "- WHEN you make a decision, learn a lesson, fix a non-obvious bug, or hit a gotcha "
    "worth keeping, call ygg_remember to save it (one durable fact, scoped to the project)."
)


def load_identity() -> dict:
    ident = dict(DEFAULT_IDENTITY)
    try:
        data = json.loads((Path.home() / ".yggdrasil" / "identity.json").read_text())
        if isinstance(data, dict):
            ident.update({k: v for k, v in data.items() if v})
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return ident


def render_identity(ident: dict) -> str:
    lines = [
        f"You are **{ident.get('name', 'Yggdrasil')}** — the user's persistent assistant "
        "across tools and projects (durable memory provided by Yggdrasil).",
        f"Behavior: {ident.get('persona', '')}".rstrip(),
    ]
    facts = ident.get("user_facts") or []
    if facts:
        lines.append("About the user:")
        lines += [f"- {f}" for f in facts]
    return "\n".join(lines)


def duplicate_invocation(payload: dict, event: str = "session-start") -> bool:
    """True when another registration of this hook already ran for this session.

    The plugin AND `ygg hooks` can both be enabled — two registrations then
    inject the whole context twice per session. An atomic O_CREAT|O_EXCL lock
    keyed by session_id makes the second invocation a silent no-op (the tmp
    dir cleans the locks up)."""
    sid = str(payload.get("session_id") or "")
    if not sid:
        return False
    import tempfile
    lock = Path(tempfile.gettempdir()) / f"ygg-{event}-{sid}.lock"
    try:
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return False
    except FileExistsError:
        return True
    except OSError:
        return False  # can't lock -> better to risk a duplicate than inject nothing


def project_for(cwd: str) -> str:
    try:
        top = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=3)
        if top.returncode == 0 and top.stdout.strip():
            return Path(top.stdout.strip()).name
    except (OSError, subprocess.SubprocessError):
        pass
    return Path(cwd).name


def fetch_status_block(project: str) -> str:
    """Surface open follow-ups and latest project status (recency-sorted) so
    'what's the status of X in project N?' is answerable immediately."""
    try:
        url = f"{URL}/get_all?user_id={USER_ID}&limit=500&namespace={NAMESPACE}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token()}"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read()).get("data", [])
    except Exception:
        return ""
    items = [r for r in data
             if not r.get("archived")
             and (r.get("metadata") or {}).get("project") == project
             and (r.get("metadata") or {}).get("type") in ("follow_up", "project_status")]
    items.sort(key=lambda r: r.get("created_at") or 0, reverse=True)
    if not items:
        return ""
    lines = ["Open follow-ups & status:"]
    for r in items[:5]:
        mtype = (r.get("metadata") or {}).get("type")
        preview = " ".join((r.get("memory") or "").split())[:180]
        lines.append(f"- [{mtype}] {preview}")
    return "\n".join(lines)


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        payload = {}
    if duplicate_invocation(payload):
        return 0
    cwd = payload.get("cwd") or os.getcwd()
    project = project_for(cwd)

    # The identity block is always present (the "soul"); project memory is added
    # when available. Memory retrieval is best-effort and never breaks a session.
    identity_block = render_identity(load_identity())

    data = []
    try:
        body = json.dumps({
            "query": f"{project} decision lesson gotcha workflow command status",
            "user_id": USER_ID,
            "limit": LIMIT,
            "rerank": False,
            "filters": {"project": project, "scope": "project"},
            "namespaces": [NAMESPACE],
        }).encode("utf-8")
        req = urllib.request.Request(URL + "/search", data=body, method="POST",
                                    headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read()).get("data", [])
    except Exception:
        data = []  # fail-safe

    memory_block = ""
    if data:
        lines = [f"Durable memory for project `{project}` (prior lessons — verify against the repo):"]
        for item in data:
            meta = item.get("metadata") or {}
            preview = " ".join((item.get("memory") or "").split())[:200]
            lines.append(f"- [{meta.get('type', 'memory')}] {preview}")
        memory_block = "\n".join(lines)

    status_block = fetch_status_block(project)
    context = "\n\n".join(b for b in (identity_block, PROACTIVE_DIRECTIVE, status_block, memory_block) if b)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
