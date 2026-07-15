#!/usr/bin/env python3
"""Claude Code Stop hook: distill the just-ended session into durable lessons.

This is the *write* half of the loop and the opt-in answer to "future sessions
should fill memory themselves" — without becoming a capture-everything firehose.
On session stop it reads the transcript, runs it through your LOCAL background
model (free, nothing leaves the machine), and saves 0-N atomic, deduped lessons.

Fail-safe and non-blocking: the actual distill runs in a DETACHED background
process so session end is never delayed, and any error prints nothing and exits 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]  # ~/.yggdrasil/scripts


def _project_for(cwd: str) -> str:
    try:
        top = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=3)
        if top.returncode == 0 and top.stdout.strip():
            return Path(top.stdout.strip()).name
    except (OSError, subprocess.SubprocessError):
        pass
    return Path(cwd or ".").name


def _worker(transcript: str, project: str) -> int:
    """Detached: distill the transcript locally and save lessons. Best-effort."""
    sys.path.insert(0, str(SCRIPTS))
    try:
        import ygg_seed  # type: ignore
        import ygg_config  # type: ignore  (same scripts dir; identity source of truth)
        text = ygg_seed._extract_text(Path(transcript))
        res = ygg_seed.distill_text(
            text, project=project, source="stop-hook",
            model=ygg_seed._bg_model(),
            user_id=ygg_config.user_id(),
            namespace=ygg_config.namespace(),
        )
        # leave a small breadcrumb for `ygg logs`-style debugging
        print(f"[ygg stop-hook] {project}: +{res['added']} lessons "
              f"({res['dup']} dup, {res['errors']} err)", file=sys.stderr)
    except Exception:  # noqa: BLE001 — never let the hook surface an error
        return 0
    return 0


def main() -> int:
    if len(sys.argv) >= 4 and sys.argv[1] == "--worker":
        return _worker(sys.argv[2], sys.argv[3])
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        payload = {}
    transcript = payload.get("transcript_path") or ""
    project = _project_for(payload.get("cwd") or os.getcwd())
    if transcript and Path(transcript).exists():
        # spawn detached so the session ends instantly; the distill runs after.
        try:
            subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--worker", transcript, project],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, start_new_session=True,
            )
        except OSError:
            pass
    print(json.dumps({"continue": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
