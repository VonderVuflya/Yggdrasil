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

# Default identity that stored memories are written under. FIXED literals on
# purpose: `ygg sync` keys memory by (user_id, namespace) across a user's
# machines, and config.json is per-machine — so a generated-once id (or
# getpass.getuser()) would differ per box and strand synced rows. Keep stable.
DEFAULT_USER_ID = "local"
DEFAULT_NAMESPACE = "personal"

# The legacy "demo" identity. Real memory seeded before the identity migration
# lands here and is auto-rebranded once to the defaults above (see
# ygg_memory_server.migrate_identity). The demo/eval gates pin these EXPLICITLY
# via these constants so they never inherit the new user-facing defaults.
DEMO_USER_ID = "demo-user"
DEMO_NAMESPACE = "yggdrasil-demo"
DEMO_TOKEN = "yggdrasil-demo-token"

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
                  "Embeddings endpoint — keep local (daemon-level; needs `ygg redeploy`). "
                  "For the openai backend use the /v1 base, e.g. http://127.0.0.1:8080/v1 "
                  "(llama.cpp) or https://openrouter.ai/api/v1 (OpenRouter)."),
    "embed_backend": (("YGG_EMBED_BACKEND",), "ollama",
                      "Embedding wire protocol: `ollama` (/api/embeddings) or `openai` "
                      "(/v1/embeddings — llama.cpp, OpenRouter, LM Studio, vLLM)."),
    "embed_api_key": (("YGG_EMBED_API_KEY", "OPENROUTER_API_KEY"), "",
                      "Bearer key for the openai backend (e.g. OpenRouter). "
                      "Empty for a local llama-server."),
    "user_id": (("YGG_USER_ID",), DEFAULT_USER_ID, "Identity stored memories are written under."),
    "namespace": (("YGG_NAMESPACE",), DEFAULT_NAMESPACE, "Memory namespace."),
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


def user_id(flag: str | None = None) -> str:
    """The identity memories are written/read under (flag > env > config > default).
    The single source of truth — every call site resolves through here instead of
    hardcoding a literal, so the default can never diverge across the codebase."""
    return resolve("user_id", flag)


def namespace(flag: str | None = None) -> str:
    return resolve("namespace", flag)


def pin_default_identity() -> None:
    """Write the resolved default identity EXPLICITLY into config.json (only the
    fields not already set). Called once after the identity migration so an
    implicit default becomes an explicit pin — no FUTURE default change can then
    ever strand this machine's memories. No-op when the user already pinned."""
    cfg = load()
    changed = False
    if not cfg.get("user_id"):
        cfg["user_id"] = DEFAULT_USER_ID
        changed = True
    if not cfg.get("namespace"):
        cfg["namespace"] = DEFAULT_NAMESPACE
        changed = True
    if changed:
        save(cfg)
