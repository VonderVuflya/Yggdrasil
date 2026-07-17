#!/usr/bin/env python3
"""Cached 'a newer version is available' check — like context-mode's update nudge.

Split so nothing ever blocks on the network at call time:
- The long-lived engine periodically calls ``refresh_cache()`` (one PyPI request)
  and writes ``~/.yggdrasil/update-check.json``.
- The CLI and the MCP facade call ``notice()`` which only READS that cache and
  compares to the installed version — instant, offline-safe.

Pure stdlib; works both as a package module and as a flat-deployed script.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path

PKG = "yggdrasil-memory"
TTL = float(os.environ.get("YGG_UPDATE_CHECK_TTL", "43200"))  # 12h
_CACHE = Path(os.environ.get("YGG_HOME", str(Path.home() / ".yggdrasil"))) / "update-check.json"


def _vtuple(v: str) -> tuple:
    return tuple(int("".join(c for c in p if c.isdigit()) or 0) for p in str(v).split("."))


def installed_version() -> str | None:
    """The version of the running code — works in the package and flat-deploy."""
    try:
        from yggdrasil import __version__  # package context
        return __version__
    except ImportError:
        pass
    try:  # flat deploy: read the __init__.py sitting next to this file
        txt = (Path(__file__).resolve().parent / "__init__.py").read_text()
        m = re.search(r'__version__\s*=\s*"([^"]+)"', txt)
        return m.group(1) if m else None
    except OSError:
        return None


def _fetch_latest() -> str | None:
    # Cache-bust PyPI's CDN (it can briefly serve the previous version right after
    # a publish) with a unique query + no-cache headers.
    url = f"https://pypi.org/pypi/{PKG}/json?_={int(time.time())}"
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.load(r)["info"]["version"]
    except Exception:  # noqa: BLE001 — best effort, never raise into the engine loop
        return None


def refresh_cache() -> None:
    """Fetch the latest published version and cache it. Called by the engine."""
    latest = _fetch_latest()
    if not latest:
        return
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps({"checked_at": time.time(), "latest": latest}))
    except OSError:
        pass


def notice(installed: str | None = None, upgrade: str = "ygg update") -> str:
    """A one-line upgrade nudge if the cached latest > installed, else ''. No network.

    One line, both versions, and the exact command — nothing else. It gets read
    mid-task by someone who did not ask about versions, so it has to be skimmable
    in a glance and impossible to confuse with the answer they were waiting for.

    `upgrade` is the command for the CALLER's surface: `/ygg-upgrade` inside an
    agent that has our slash commands (it detects pipx/brew/npm/uvx on its own),
    plain `ygg update` in a terminal where a slash command means nothing.
    """
    installed = installed or installed_version()
    if not installed:
        return ""
    try:
        latest = json.loads(_CACHE.read_text()).get("latest")
    except (OSError, ValueError):
        return ""
    if latest and _vtuple(latest) > _vtuple(installed):
        return (f"⚠️ Yggdrasil v{installed} outdated → v{latest} available. "
                f"Upgrade: {upgrade}")
    return ""
