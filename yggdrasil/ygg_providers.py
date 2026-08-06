#!/usr/bin/env python3
"""Find the local LLM runtimes on this machine — and drive them.

`ygg install` used to assume Ollama and then ask you to type a model name from
memory. Everyone on LM Studio had to work out three things we never told them:
that `embed_backend` has to be `openai`, that `embed_url` wants the `/v1` base
while `distill_url` wants the host root, and the exact id the server answers to
(`text-embedding-nomic-embed-text-v1.5`, not `nomic-embed-text`). This module
removes all three questions: it probes the runtimes, reads their real model
lists, starts one that's installed but idle, and downloads what you pick.

Nothing here raises. A probe that fails means "not running" — never "broken".

Wire dialects, for reference:
  * Ollama     — `/api/tags` lists models; `/api/embeddings` + `/api/generate`.
  * LM Studio  — `/api/v0/models` lists models WITH a type (llm/vlm/embeddings),
                 which is why it's preferred over `/v1/models`; serves the
                 OpenAI `/v1/embeddings` + `/v1/chat/completions`.
  * llama.cpp  — `/v1/models` (usually one model), OpenAI dialect.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from shutil import which

OLLAMA_URL = "http://127.0.0.1:11434"
LMSTUDIO_URL = "http://127.0.0.1:1234"
LLAMACPP_URL = "http://127.0.0.1:8080"

_UA = {"User-Agent": "yggdrasil-setup"}

# Name fragments that mark an EMBEDDING model when the server won't say. Only
# consulted as a fallback — Ollama exposes `details.family` and LM Studio
# exposes `type`, and both beat guessing from a string.
_EMBED_HINTS = ("embed", "minilm", "bge-", "bge_", "bge:", "gte-", "e5-",
                "paraphrase", "mxbai", "arctic-embed", "granite-embedding")


# --------------------------------------------------------------------------- #
# models
# --------------------------------------------------------------------------- #

class Model:
    """One model a runtime already has on disk. `mid` is what the API answers to."""

    __slots__ = ("id", "kind", "size", "note")

    def __init__(self, mid: str, kind: str = "unknown", size: str = "", note: str = ""):
        self.id, self.kind, self.size, self.note = mid, kind, size, note

    def __repr__(self) -> str:  # pragma: no cover — debugging aid
        return f"Model({self.id!r}, {self.kind!r})"


def classify(mid: str, family: str = "") -> str:
    """'embed' | 'llm', from the server's own hint first, the name second."""
    f = (family or "").lower()
    if f:
        if "bert" in f or "embed" in f:
            return "embed"
        return "llm"
    low = (mid or "").lower()
    return "embed" if any(x in low for x in _EMBED_HINTS) else "llm"


def _squash(s: str) -> str:
    """Alphanumerics only, lowercased — the shape names survive being renamed in."""
    return "".join(c for c in (s or "").lower() if c.isalnum())


def _human(nbytes) -> str:
    try:
        n = float(nbytes)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB", "MB") else f"{n:.1f} GB"
        n /= 1024
    return ""


# --------------------------------------------------------------------------- #
# probes
# --------------------------------------------------------------------------- #

def _get(url: str, timeout: float = 1.5):
    req = urllib.request.Request(url, headers=dict(_UA))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except Exception:  # noqa: BLE001 — a probe never fails loudly
        return None


def probe_ollama(url: str = OLLAMA_URL, timeout: float = 1.5) -> list[Model] | None:
    """Models an Ollama server has pulled, or None if it isn't answering."""
    d = _get(url.rstrip("/") + "/api/tags", timeout)
    if not isinstance(d, dict) or not isinstance(d.get("models"), list):
        return None
    out: list[Model] = []
    for m in d["models"]:
        mid = (m.get("name") or m.get("model") or "").strip()
        if mid:
            family = (m.get("details") or {}).get("family") or ""
            out.append(Model(mid, classify(mid, family), _human(m.get("size"))))
    return out


def probe_openai(url: str, timeout: float = 1.5) -> list[Model] | None:
    """Models an OpenAI-compatible server has, or None if it isn't answering.

    Tries LM Studio's `/api/v0/models` first: it's the only one of the two that
    says whether a model embeds or generates, and picking the wrong kind is the
    failure that looks like "dense search is just broken"."""
    base = url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")

    d = _get(base + "/api/v0/models", timeout)
    if isinstance(d, dict) and isinstance(d.get("data"), list):
        out: list[Model] = []
        for m in d["data"]:
            mid = (m.get("id") or "").strip()
            if not mid:
                continue
            t = (m.get("type") or "").lower()
            kind = ("embed" if t.startswith("embed")
                    else "llm" if t in ("llm", "vlm")
                    else classify(mid))
            out.append(Model(mid, kind, "", m.get("quantization") or ""))
        return out

    d = _get(base + "/v1/models", timeout)
    if isinstance(d, dict) and isinstance(d.get("data"), list):
        return [Model((m.get("id") or "").strip(), classify(m.get("id") or ""))
                for m in d["data"] if (m.get("id") or "").strip()]
    return None


def probe_any(url: str, timeout: float = 1.5) -> tuple[str, list[Model]] | None:
    """Probe an arbitrary endpoint and report which dialect it speaks.

    Returns ('ollama'|'openai', models) or None. This is what makes "LM Studio on
    the desktop down the hall" a URL the user types once, instead of a URL plus a
    backend plus a guess at whether it needs `/v1`."""
    models = probe_ollama(url, timeout)
    if models is not None:
        return "ollama", models
    models = probe_openai(url, timeout)
    if models is not None:
        return "openai", models
    return None


# --------------------------------------------------------------------------- #
# binaries / install detection
# --------------------------------------------------------------------------- #

def ollama_bin() -> str | None:
    return which("ollama")


def lms_bin() -> str | None:
    """LM Studio's CLI. It ships inside the app and is only on PATH once the user
    has run `lms bootstrap`, so check the known install roots too."""
    found = which("lms")
    if found:
        return found
    candidates = [Path.home() / ".lmstudio" / "bin" / "lms",
                  Path.home() / ".lmstudio" / "bin" / "lms.exe",
                  Path.home() / ".cache" / "lm-studio" / "bin" / "lms"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "LM-Studio" / "resources" / "app" / ".webpack" / "lms.exe")
    for c in candidates:
        try:
            if c.exists():
                return str(c)
        except OSError:
            continue
    return None


def unload(model: str, timeout: float = 15.0) -> bool:
    """Ask the local runtime to drop `model` from memory. Best-effort, never raises.

    For the tail of a long batch (`ygg seed`, `ygg reindex`): a `ttl` only starts
    counting down after the last request, so an explicit unload hands the GPU back
    now instead of minutes from now. Only LM Studio is covered — Ollama already
    unloads on its own `keep_alive`, and llama.cpp serves a single fixed model."""
    if not model:
        return False
    lms = lms_bin()
    if not lms:
        return False
    try:
        import subprocess
        return subprocess.run([lms, "unload", model], capture_output=True,
                              timeout=timeout).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def lmstudio_installed() -> bool:
    if lms_bin():
        return True
    roots = [Path("/Applications/LM Studio.app"), Path.home() / ".lmstudio"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots += [Path(local) / "LM-Studio", Path(local) / "Programs" / "lm-studio"]
    for r in roots:
        try:
            if r.exists():
                return True
        except OSError:
            continue
    return False


# --------------------------------------------------------------------------- #
# providers
# --------------------------------------------------------------------------- #

class Provider:
    """One runtime: where it lives, whether it's up, and what it holds.

    `models is None` means "not answering"; an empty list means "up, but nothing
    downloaded" — a distinction the wizard acts on differently (start it vs.
    offer downloads)."""

    def __init__(self, key: str, name: str, url: str, models: list[Model] | None = None,
                 installed: bool = False, dialect: str = ""):
        self.key, self.name, self.url = key, name, url
        self.models = models
        self.installed = installed
        self._dialect = dialect

    # -- state ------------------------------------------------------------- #
    @property
    def running(self) -> bool:
        return self.models is not None

    @property
    def dialect(self) -> str:
        return self._dialect or ("ollama" if self.key == "ollama" else "openai")

    # -- config values ------------------------------------------------------ #
    @property
    def embed_backend(self) -> str:
        return self.dialect

    @property
    def embed_url(self) -> str:
        """What `embed_url` must be set to — the /v1 base for OpenAI dialects."""
        u = self.url.rstrip("/")
        if self.dialect == "ollama":
            return u[:-3].rstrip("/") if u.endswith("/v1") else u
        return u if u.endswith("/v1") else u + "/v1"

    @property
    def distill_url(self) -> str:
        """What `distill_url` must be set to — the host ROOT, no /v1. The two
        settings wanting different shapes of the same URL is the single most
        common way a working LM Studio ends up looking dead."""
        u = self.url.rstrip("/")
        return u[:-3].rstrip("/") if u.endswith("/v1") else u

    # -- model queries ------------------------------------------------------ #
    def of_kind(self, kind: str) -> list[Model]:
        return [m for m in (self.models or []) if m.kind == kind]

    def ids(self) -> set[str]:
        return {m.id for m in (self.models or [])}

    def has(self, mid: str) -> bool:
        """Whether this runtime already holds `mid`. Ollama tags loosely (`qwen2.5:3b`
        vs a bare `qwen2.5`), so compare on the repo part too."""
        if not mid:
            return False
        want = mid.split(":")[0]
        return any(m.id == mid or m.id.split(":")[0] == want for m in (self.models or []))

    def matches(self, spec: str, kind: str = "") -> Model | None:
        """The already-downloaded model a catalog `spec` refers to, if any.

        A catalog spec is what you'd type to DOWNLOAD the thing, and no runtime
        serves it back under that name: `lms get nomic-embed-text` gives you
        `text-embedding-nomic-embed-text-v1.5`, and Ollama prefixes nothing but
        appends a tag. Compare on alphanumerics-only containment, which catches
        both without a hand-maintained alias table."""
        if not spec:
            return None
        want = _squash(spec)
        best = None
        for m in self.models or []:
            if kind and m.kind != kind:
                continue
            got = _squash(m.id)
            if got == want:
                return m
            if want and want in got and best is None:
                best = m
        return best

    def can_pull(self) -> bool:
        return bool(ollama_bin() if self.key == "ollama"
                    else lms_bin() if self.key == "lmstudio" else None)

    def can_start(self) -> bool:
        return self.can_pull()  # same binary drives both

    def status(self) -> str:
        """One line for the picker: what state is this thing in, right now."""
        if self.running:
            n = len(self.models or [])
            host = self.url.split("//")[-1]
            return f"running · {host} · {n} model{'' if n == 1 else 's'}"
        if self.installed:
            return "installed, not running"
        return "not installed"


def detect(timeout: float = 1.5) -> list[Provider]:
    """Probe the three local runtimes in parallel. ~`timeout` total, not 3×."""
    import concurrent.futures as cf

    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        f_oll = ex.submit(probe_ollama, OLLAMA_URL, timeout)
        f_lms = ex.submit(probe_openai, LMSTUDIO_URL, timeout)
        f_cpp = ex.submit(probe_openai, LLAMACPP_URL, timeout)
        oll, lms, cpp = f_oll.result(), f_lms.result(), f_cpp.result()
    return [
        Provider("lmstudio", "LM Studio", LMSTUDIO_URL, lms, lmstudio_installed()),
        Provider("ollama", "Ollama", OLLAMA_URL, oll, bool(ollama_bin())),
        Provider("llamacpp", "llama.cpp", LLAMACPP_URL, cpp, bool(which("llama-server"))),
    ]


def refresh(prov: Provider, wait: float = 0.0) -> bool:
    """Re-probe `prov` (optionally waiting up to `wait`s for it to come up)."""
    deadline = time.monotonic() + wait
    while True:
        models = (probe_ollama(prov.url) if prov.dialect == "ollama"
                  else probe_openai(prov.url))
        if models is not None:
            prov.models = models
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


def start(prov: Provider, wait: float = 25.0) -> bool:
    """Bring an installed-but-idle runtime up. True once it answers."""
    if prov.key == "ollama":
        binary = ollama_bin()
        if not binary:
            return False
        kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                        "stdin": subprocess.DEVNULL}
        if os.name != "nt":
            kwargs["start_new_session"] = True
        try:
            subprocess.Popen([binary, "serve"], **kwargs)  # noqa: S603
        except OSError:
            return False
    elif prov.key == "lmstudio":
        binary = lms_bin()
        if not binary:
            return False
        try:
            subprocess.run([binary, "server", "start"],  # noqa: S603
                           capture_output=True, timeout=90)
        except (OSError, subprocess.SubprocessError):
            return False
    else:
        return False
    return refresh(prov, wait=wait)


def pull(prov: Provider, spec: str) -> bool:
    """Download `spec`. Streams the runtime's own progress to the terminal.

    The return value is the exit code only — `lms get` exits 0 even when its
    search finds nothing, so callers MUST verify by re-probing (see
    `pull_and_resolve`)."""
    binary = ollama_bin() if prov.key == "ollama" else lms_bin()
    if not binary:
        return False
    argv = ([binary, "pull", spec] if prov.key == "ollama"
            else [binary, "get", spec, "-y"])
    try:
        return subprocess.run(argv).returncode == 0  # noqa: S603
    except (OSError, subprocess.SubprocessError):
        return False


def pull_and_resolve(prov: Provider, spec: str, kind: str) -> str | None:
    """Download `spec` and return the id the SERVER will answer to.

    They're rarely the same string: `lms get nomic-embed-text` lands a model the
    API calls `text-embedding-nomic-embed-text-v1.5`. Rather than hardcode that
    mapping (and rot the moment LM Studio renames a staff pick), diff the model
    list around the download and take what appeared."""
    before = prov.ids()
    if not pull(prov, spec):
        return None
    refresh(prov, wait=5.0)
    fresh = [m for m in (prov.models or []) if m.id not in before]
    typed = [m for m in fresh if m.kind == kind]
    if len(typed) == 1:
        return typed[0].id
    if len(fresh) == 1:
        return fresh[0].id
    if prov.has(spec):          # Ollama: the tag you asked for is the id you get
        return spec
    return None


# --------------------------------------------------------------------------- #
# download catalogs (only for runtimes we can actually drive)
# --------------------------------------------------------------------------- #
#
# (spec, label, size, description, tier)
#   spec  — argument to the download command (`ollama pull` / `lms get`)
#   tier  — cpu | mid | heavy, same scale ygg_setup.verdict() renders
#
# LM Studio specs are SEARCH TERMS, resolved by `lms get -y` against the staff
# picks. That's deliberate: pinning a Hugging Face repo path breaks silently
# whenever the publisher re-uploads, and the resulting model id is discovered by
# re-probing anyway (see pull_and_resolve).

LMSTUDIO_EMBED = [
    ("nomic-embed-text", "Nomic Embed Text v1.5", "84 MB",
     "Fast, good quality. English-only memory.", "cpu"),
    ("all-minilm", "All-MiniLM-L6-v2", "45 MB",
     "Tiny and instant. English-only memory.", "cpu"),
    ("paraphrase-multilingual-mpnet", "Paraphrase Multilingual MPNet", "563 MB",
     "Pick this if your memory mixes languages (EN/RU + 50 more).", "cpu"),
    ("embeddinggemma-300m", "EmbeddingGemma 300M", "~600 MB",
     "Google's multilingual embedder, 100+ languages.", "cpu"),
    ("bge-m3", "BGE-M3", "~1.2 GB",
     "Top multilingual retrieval quality, heavier.", "mid"),
]

LMSTUDIO_LLM = [
    ("qwen2.5-1.5b-instruct", "Qwen2.5 1.5B Instruct", "~1 GB",
     "CPU sweet spot. EN/RU/ZH, no <think> traces.", "cpu"),
    ("qwen2.5-3b-instruct", "Qwen2.5 3B Instruct", "~2 GB",
     "Best CPU balance, strong Russian.", "mid"),
    ("qwen3-4b-2507", "Qwen3 4B Instruct 2507", "~2.5 GB",
     "Sharper extraction. The INSTRUCT build — a reasoning variant burns the "
     "distill timeout on <think>.", "mid"),
    ("gemma-3-4b", "Gemma 3 4B", "~3.3 GB",
     "Strong multilingual, slower on CPU.", "heavy"),
]


# Models that think before answering unless told not to. Kept here, next to the
# catalogs, because it is a fact about model identity — the wizard labels rows
# with it and ygg_seed decides whether to suppress the thinking pass with it.
#
# Name-matching is the only option available: LM Studio's /api/v0/models reports
# `capabilities: ["tool_use"]` and says nothing about reasoning, and Ollama's tags
# don't either. It is therefore approximate in both directions — `qwen3-4b-2507`
# is an instruct build whose id omits "instruct" and matches anyway.
_REASONING_HINTS = ("qwen3", "qwen-3", "deepseek-r1", "magistral", "phi-4-reasoning",
                    "glm-4.5", "glm-5", "minimax-m", "exaone-deep")
_NON_REASONING_TAGS = ("-instruct", "instruct-", "non-thinking", "no-think")


def is_reasoning(model_id: str) -> bool:
    """Best-effort: does this model emit a <think> trace unless suppressed?"""
    name = (model_id or "").lower()
    if any(tag in name for tag in _NON_REASONING_TAGS):
        return False
    return any(hint in name for hint in _REASONING_HINTS)


def catalog(prov_key: str, kind: str) -> list[tuple[str, str, str, str, str]]:
    """Downloadable models for a runtime we can drive, else []."""
    if prov_key == "lmstudio":
        return LMSTUDIO_EMBED if kind == "embed" else LMSTUDIO_LLM
    return []


def defaults(prov_key: str, accelerated: bool) -> tuple[str, str]:
    """(embed spec, llm spec) to preselect for this runtime. Multilingual-safe."""
    if prov_key == "lmstudio":
        return ("paraphrase-multilingual-mpnet",
                "qwen2.5-3b-instruct" if accelerated else "qwen2.5-1.5b-instruct")
    return "", ""


def install_hint(prov_key: str) -> str:
    return {
        "ollama": "https://ollama.com/download",
        "lmstudio": "https://lmstudio.ai/download",
        "llamacpp": "https://github.com/ggml-org/llama.cpp",
    }.get(prov_key, "")


def start_hint(prov: Provider) -> str:
    """The command a user would run by hand — printed when we can't do it for them."""
    return {"ollama": "ollama serve",
            "lmstudio": "lms server start  (or: LM Studio → Developer → Start server)",
            "llamacpp": "llama-server -m <model.gguf> --embeddings"}.get(prov.key, "")


def main() -> int:  # pragma: no cover — `python -m yggdrasil.ygg_providers`
    out = []
    for p in detect():
        out.append({"key": p.key, "name": p.name, "url": p.url, "running": p.running,
                    "installed": p.installed, "status": p.status(),
                    "embed_backend": p.embed_backend, "embed_url": p.embed_url,
                    "distill_url": p.distill_url,
                    "models": None if p.models is None else
                              [{"id": m.id, "kind": m.kind, "size": m.size} for m in p.models]})
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
