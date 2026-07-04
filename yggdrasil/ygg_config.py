#!/usr/bin/env python3
"""Persistent settings at ~/.yggdrasil/config.json + precedence resolution.

One place to resolve any setting, with a single rule:

    CLI flag  >  environment variable  >  config.json  >  built-in default

`ygg config get/set/list/unset` writes the config.json layer; `--flags` are the
per-run layer. Pure stdlib; works in both the package and a flat deploy.

Note on endpoints: `distill_url` (the heavy, occasional `ygg seed` work) is kept
SEPARATE from `embed_url` (the daemon's constant embedding work) on purpose — you
can point distillation at a beefier box without dragging embeddings off-machine.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

YGG_HOME = Path(os.environ.get("YGG_HOME", str(Path.home() / ".yggdrasil")))
CONFIG = YGG_HOME / "config.json"

# key -> (env var names in precedence order, default, one-line help)
SETTINGS: dict[str, tuple[tuple[str, ...], str, str]] = {
    "distill_url": (("YGG_DISTILL_URL", "YGG_EMBED_URL"), "http://127.0.0.1:11434",
                    "Ollama endpoint for `ygg seed` / consolidation distillation. "
                    "Point at a beefier box, e.g. http://192.168.3.124:11434."),
    "distill_timeout": (("YGG_DISTILL_TIMEOUT",), "120",
                        "Per-file distill timeout in seconds (raise for big sessions)."),
    "distill_num_ctx": (("YGG_DISTILL_NUM_CTX",), "8192",
                        "Context window (tokens) requested from the distill model. Without "
                        "this Ollama uses ITS default (often 4096) and silently truncates "
                        "long transcripts into low-quality lessons."),
    "bg_model": (("YGG_BG_MODEL",), "qwen2.5:1.5b",
                 "Local model used for distillation and consolidation."),
    "embed_model": (("YGG_EMBED_MODEL",), "",
                    "Embedding model (daemon-level; change needs `ygg redeploy`)."),
    "embed_url": (("YGG_EMBED_URL",), "http://127.0.0.1:11434",
                  "Embeddings endpoint — keep local (daemon-level; needs `ygg redeploy`)."),
    "user_id": (("YGG_USER_ID",), "demo-user", "Identity stored memories are written under."),
    "namespace": (("YGG_NAMESPACE",), "yggdrasil-demo", "Memory namespace."),
    "sync_repo": (("YGG_SYNC_REPO",), "",
                  "YOUR git repo (local path or clone URL) used by `ygg sync` — "
                  "cross-machine memory sync with no cloud in the loop."),
}


def load() -> dict:
    try:
        d = json.loads(CONFIG.read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save(cfg: dict) -> None:
    YGG_HOME.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n")


def resolve(key: str, flag: str | None = None) -> str:
    """Effective value for `key`: flag > env > config.json > default."""
    envs, default, _ = SETTINGS[key]
    if flag not in (None, ""):
        return str(flag)
    for e in envs:
        if os.environ.get(e):
            return os.environ[e]
    v = load().get(key)
    if v not in (None, ""):
        return str(v)
    return default


def source(key: str, flag: str | None = None) -> str:
    """Where the effective value comes from — for `ygg config list`."""
    envs = SETTINGS[key][0]
    if flag not in (None, ""):
        return "flag"
    for e in envs:
        if os.environ.get(e):
            return f"env:{e}"
    if load().get(key) not in (None, ""):
        return "config"
    return "default"


# typed convenience accessors used across the codebase
def distill_url(flag: str | None = None) -> str:
    return resolve("distill_url", flag).rstrip("/")


def distill_timeout(flag: str | int | None = None) -> int:
    try:
        return int(resolve("distill_timeout", str(flag) if flag not in (None, "") else None))
    except (TypeError, ValueError):
        return 120


def distill_num_ctx(flag: str | int | None = None) -> int:
    try:
        return int(resolve("distill_num_ctx", str(flag) if flag not in (None, "") else None))
    except (TypeError, ValueError):
        return 8192


def bg_model(flag: str | None = None) -> str:
    return resolve("bg_model", flag)
