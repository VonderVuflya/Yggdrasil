#!/usr/bin/env python3
"""Yggdrasil setup brain: detect hardware, recommend models, run the install wizard.

`recommend` prints a hardware summary + a model catalog with descriptions and a
per-model fit verdict for THIS machine, plus recommended picks. `wizard` is the
interactive flow (model + feature choices) that writes ~/.yggdrasil/config.json
and hands off to service.install (cross-platform). The recommend logic is
pure/testable; the wizard needs a TTY.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

try:  # package context
    from . import ygg_config as _cfg
    from . import ygg_prompt as _prompt
    from . import ygg_providers as _providers
except ImportError:  # pragma: no cover — flat deploy / direct run
    import ygg_config as _cfg  # type: ignore
    import ygg_prompt as _prompt  # type: ignore
    import ygg_providers as _providers  # type: ignore

YGG_HOME = Path(os.environ.get("YGG_HOME", str(Path.home() / ".yggdrasil")))

# (name, size, description, tier, lang)  tier: cpu | mid | heavy
# `lang` = language coverage + thinking/non-thinking — the axes that actually
# decide memory quality for non-English users (docs/TODO §3). A distill model
# that silently drops the user's language (e.g. Llama 3.2 has no Russian/Chinese)
# produces poor memory no matter how fast it is.
EMBED_MODELS = [
    ("none", "0", "Lexical only (FTS5/BM25). Zero extra deps, no semantic search.", "cpu", "—"),
    ("all-minilm", "45 MB", "Tiny & fast. Pick if your memory is English-only.", "cpu", "EN only"),
    ("nomic-embed-text", "274 MB", "Better quality than all-minilm, still English.", "cpu", "EN only"),
    ("paraphrase-multilingual", "563 MB", "Multilingual and CPU-friendly, but fades past ~1k memories.", "cpu", "EN/RU + 50 langs"),
    ("bge-m3", "1.2 GB", "Best quality, and the only one that holds up on a large store.", "heavy", "multilingual"),
]
# Retrieval accuracy is a function of CORPUS SIZE, not just of the model, and the
# gap widens as the store grows: on 232 memories paraphrase-multilingual scored
# recall@1 0.94, on the same benchmark at 4,799 it fell to 0.550 — level with the
# lexical BM25 baseline, i.e. dense search stopped paying for itself. bge-m3 held
# 0.775 on that store (+0.225, CI95 [+0.125…+0.325]). Past this many memories the
# wizard recommends bge-m3 instead. (docs/TODO-scale-lifecycle-lmstudio.md §1)
LARGE_STORE_MEMORIES = 1000
BG_MODELS = [
    ("none", "0", "No background intelligence (write stays manual via ygg_remember).", "cpu", "—"),
    ("qwen2.5:0.5b", "~400 MB", "Tiny. Fast on CPU. OK for dedup/classification.", "cpu", "EN/RU/ZH · non-thinking"),
    ("qwen2.5:1.5b", "~1 GB", "Small, good balance. Best default for CPU-only.", "cpu", "EN/RU/ZH · non-thinking"),
    ("qwen2.5:3b", "~1.9 GB", "Best CPU balance, strong Russian. Recommended upgrade from 1.5b.", "mid", "EN/RU/ZH · non-thinking"),
    ("qwen3:4b-instruct-2507", "~2.6 GB", "Newer, sharper extraction. Use this instruct build — a reasoning variant burns the timeout on <think> traces.", "mid", "EN/RU/ZH · non-thinking"),
    ("gemma2:2b", "~1.6 GB", "Solid small model, a touch slower.", "mid", "EN + multi · non-thinking"),
    ("gemma3:4b", "~3.3 GB", "Strong multilingual, slower on CPU.", "heavy", "multilingual · non-thinking"),
    ("llama3.2:3b", "~2 GB", "Good extraction, but English + 7 EU languages only.", "mid", "⚠ NO Russian/Chinese"),
    ("phi3:mini", "~2.2 GB", "Capable (3.8B) but slow on CPU.", "heavy", "EN-centric"),
]
FEATURES = [
    ("dense", "Semantic search via embeddings (needs an embedding model). Finds by meaning, not just words."),
    ("hooks", "Auto-inject identity + project memory at session start (Claude Code SessionStart hook)."),
    ("autosave", "On session end, distill the transcript into durable lessons, locally (Stop hook)."),
    ("write_path", "Background model distills/dedupes/links memory autonomously (needs a background model)."),
    ("consolidation", "Scheduled background review/merge of memory (launchd cron; needs a background model)."),
]


def _ram_gb_linux() -> int:
    """Total RAM from /proc/meminfo (MemTotal is in kB)."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // (1024 ** 2)
    except (OSError, ValueError, IndexError):
        pass
    return 0


def _ram_gb_windows() -> int:
    """Total RAM via PowerShell CIM (bytes)."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"],
            capture_output=True, text=True, timeout=5).stdout.strip()
        return int(out) // (1024 ** 3) if out.isdigit() else 0
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0


def _mac_gpus() -> list[str]:
    """Best-effort GPU model names on macOS via system_profiler (JSON). Returns
    [] on any error/timeout — callers must NOT read '[]' as 'no GPU', only as
    'unknown'."""
    try:
        out = subprocess.run(["system_profiler", "SPDisplaysDataType", "-json"],
                             capture_output=True, text=True, timeout=6).stdout
        data = json.loads(out or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    names = []
    for g in data.get("SPDisplaysDataType", []) or []:
        name = g.get("sppci_model") or g.get("_name") or ""
        if name:
            names.append(name)
    return names


def _linux_has_amd_gpu() -> bool:
    """True if the amdgpu kernel driver is loaded (cheap /sys probe)."""
    try:
        return Path("/sys/module/amdgpu").exists()
    except OSError:
        return False


def hw() -> dict:
    """Detect arch / RAM / cores / CPU / accelerator — cross-platform.

    macOS uses sysctl; Linux reads /proc/meminfo + /proc/cpuinfo; Windows uses
    PowerShell CIM. RAM/CPU degrade to 0/'unknown' only if all probes fail, so
    the model recommender never silently sizes off 0 GB off-macOS.

    Also classifies the acceleration TIER honestly and, crucially, warns when a
    GPU is present but WON'T accelerate inference — the Intel-Mac + AMD case,
    where macOS is Metal-only (Apple-Silicon oriented) and ROCm doesn't exist, so
    stock inference runs on CPU regardless of the GPU (docs/TODO §1)."""
    system = platform.system()
    arch = platform.machine()
    apple_silicon = system == "Darwin" and arch == "arm64"

    def sysctl(key: str) -> str:
        try:
            return subprocess.run(["sysctl", "-n", key], capture_output=True, text=True, timeout=3).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    cpu = platform.processor() or "unknown"
    ram_gb = 0
    accel = "CPU"
    accel_tier = "cpu"      # cpu | metal | cuda | rocm/vulkan
    accel_warn = ""
    gpus: list[str] = []
    if system == "Darwin":
        try:
            ram_gb = int(sysctl("hw.memsize") or 0) // (1024 ** 3)
        except ValueError:
            ram_gb = 0
        cpu = sysctl("machdep.cpu.brand_string") or cpu
        if apple_silicon:
            accel, accel_tier = "GPU (Metal)", "metal"
        else:
            # Intel Mac: macOS GPU compute is Metal-only and Apple-Silicon
            # oriented; a discrete/eGPU AMD card is NOT usable for local LLMs
            # here (stock Metal streams weights over PCIe → slower than CPU).
            accel, accel_tier = "CPU", "cpu"
            gpus = _mac_gpus()
            discrete = [g for g in gpus if "intel" not in g.lower()]
            if discrete:
                accel_warn = (
                    f"You have a GPU ({discrete[0]}) but it will NOT accelerate inference on "
                    "macOS: GPU compute here is Metal-only (Apple-Silicon oriented) and ROCm "
                    "does not exist on macOS — stock Metal on Intel+AMD is slower than CPU. "
                    "Yggdrasil runs on CPU, which is fine for a 1.5B–4B distill model.")
            else:
                accel_warn = (
                    "Intel Mac → CPU-only inference (macOS GPU compute is Metal-only and "
                    "Apple-Silicon oriented). Fine for a small distill model.")
    elif system == "Linux":
        ram_gb = _ram_gb_linux()
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as fh:
                for line in fh:
                    if line.lower().startswith("model name"):
                        cpu = line.split(":", 1)[1].strip()
                        break
        except OSError:
            pass
        # Best-effort NVIDIA, then AMD; absence just means CPU.
        if _has("nvidia-smi"):
            try:
                if subprocess.run(["nvidia-smi"], capture_output=True, timeout=3).returncode == 0:
                    accel, accel_tier = "GPU (CUDA)", "cuda"
            except (OSError, subprocess.SubprocessError):
                pass
        if accel_tier == "cpu" and _linux_has_amd_gpu():
            # On Linux an AMD GPU CAN accelerate — but only with a ROCm/Vulkan
            # Ollama build, not the stock CPU binary. Flag the tier, don't warn.
            accel, accel_tier = "GPU (ROCm/Vulkan, needs ROCm build)", "rocm/vulkan"
    elif system == "Windows":
        ram_gb = _ram_gb_windows()

    return {
        "arch": arch,
        "os": system,
        "apple_silicon": apple_silicon,
        "ram_gb": ram_gb,
        "cores": os.cpu_count() or 0,
        "cpu": cpu or "unknown",
        "accel": accel,
        "accel_tier": accel_tier,
        "accel_warn": accel_warn,
        "gpus": gpus,
    }


def _has(binary: str) -> bool:
    from shutil import which
    return which(binary) is not None


def verdict(tier: str, h: dict) -> str:
    if h["apple_silicon"]:
        return "✓ fast (GPU)"
    return {
        "cpu": "✓ fine on CPU",
        "mid": "✓ ok (slower on CPU)",
        "heavy": "⚠ works but slow on CPU-only",
    }.get(tier, "?")


def _store_size() -> int:
    """How many live memories are already here. Read-only, 0 on any error — this
    only sharpens a recommendation and must never break `recommend`."""
    db = YGG_HOME / "data" / "memory.sqlite"
    try:
        if not db.exists():
            return 0
        import sqlite3
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1.0)
        try:
            return int(con.execute(
                "SELECT COUNT(*) FROM memories WHERE archived=0").fetchone()[0])
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        return 0


def recommend(h: dict) -> tuple[str, str]:
    """Default picks for the detected hardware. Multilingual-safe: the quality
    upgrade is Qwen 2.5 3B, NOT Llama 3.2 — Llama 3.2 has no Russian/Chinese and
    silently degrades non-English memory (docs/TODO §3)."""
    embed = "paraphrase-multilingual"  # safe multilingual default
    # A big store needs a stronger embedder: the default's recall halves between a
    # few hundred memories and a few thousand, down to the lexical baseline. Only
    # suggest the heavier model where it will actually run well.
    if _store_size() >= LARGE_STORE_MEMORIES and (
            h["accel_tier"] in ("metal", "cuda", "rocm/vulkan") or h["ram_gb"] >= 16):
        embed = "bge-m3"
    if h["ram_gb"] >= 16 and h["accel_tier"] in ("metal", "cuda", "rocm/vulkan"):
        bg = "qwen2.5:3b"  # strong multilingual, comfortable once inference is accelerated
    else:
        bg = "qwen2.5:1.5b"  # CPU-only sweet spot
    return embed, bg


def _memory_language_hint() -> str:
    """Best-effort: sample existing memory and, if it's dominantly non-English,
    steer the catalog away from English-only models. Reads the local store
    read-only; returns '' on any error or too-weak a signal (docs/TODO §3)."""
    db = YGG_HOME / "data" / "memory.sqlite"
    try:
        if not db.exists():
            return ""
        import sqlite3
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1.0)
        try:
            rows = con.execute(
                "SELECT content FROM memories WHERE archived=0 LIMIT 400").fetchall()
        finally:
            con.close()
    except Exception:  # noqa: BLE001 — a stretch hint must never break `recommend`
        return ""
    cyr = lat = cjk = 0
    for (content,) in rows:
        for ch in (content or "")[:400]:
            o = ord(ch)
            if 0x0400 <= o <= 0x04FF:
                cyr += 1
            elif "a" <= ch.lower() <= "z":
                lat += 1
            elif 0x4E00 <= o <= 0x9FFF:
                cjk += 1
    total = cyr + lat + cjk
    if total < 200:  # too little text to judge
        return ""
    if cyr >= lat and cyr >= cjk and cyr / total > 0.2:
        return "Your memory is mostly Russian → keep to Qwen/Gemma; Llama 3.2 has no Russian."
    if cjk >= lat and cjk >= cyr and cjk / total > 0.2:
        return "Your memory is mostly Chinese → keep to Qwen/Gemma; Llama 3.2 has no Chinese."
    return ""


def print_catalog(h: dict, with_hardware: bool = True) -> None:
    rec_embed, rec_bg = recommend(h)
    if with_hardware:
        print(f"Hardware: {h['cpu']} | {h['cores']} cores | {h['ram_gb']} GB RAM | {h['arch']} | inference: {h['accel']}")
        if h.get("accel_warn"):
            print(f"  ⚠ {h['accel_warn']}")
        print()
    print("Embedding models (dense/semantic search):")
    for name, size, desc, tier, lang in EMBED_MODELS:
        if name == "none":
            print(f"  - none          [lexical only] {desc}")
            continue
        star = "  ← recommended" if name == rec_embed else ""
        print(f"  - {name:<24} {size:<8} {verdict(tier, h)}  [{lang}]{star}\n      {desc}")
    print()
    print("Background models (smart write-path / consolidation):")
    for name, size, desc, tier, lang in BG_MODELS:
        if name == "none":
            print(f"  - none          {desc}")
            continue
        star = "  ← recommended" if name == rec_bg else ""
        print(f"  - {name:<24} {size:<8} {verdict(tier, h)}  [{lang}]{star}\n      {desc}")
    hint = _memory_language_hint()
    if hint:
        print(f"\n🌍 {hint}")
    print()
    print("Features (toggle in the wizard):")
    for key, desc in FEATURES:
        print(f"  - {key:<14} {desc}")


def _ask(prompt: str, default: str) -> str:
    try:
        ans = input(f"{prompt} [{default}]: ").strip()
    except EOFError:
        ans = ""
    return ans or default


def _ask_yes(prompt: str, default: bool) -> bool:
    d = "Y/n" if default else "y/N"
    ans = _ask(f"{prompt} ({d})", "Y" if default else "N").lower()
    return ans.startswith("y")


# Sentinels smuggled through a select()'s string value. `_DL` marks a catalog
# entry that still has to be downloaded, so the model step returns "what you
# picked" and the download step decides what that costs.
_DL = "\x00ygg-download:"
_CUSTOM = "\x00ygg-custom"

# Roles, so one set of helpers drives both model questions.
EMBED, LLM = "embed", "llm"


def _ollama_catalog(kind: str) -> list[tuple[str, str, str, str, str]]:
    """EMBED_MODELS / BG_MODELS in the shape the pickers want:
    (spec, label, size, description, tier). The language column is folded into
    the description — in a menu there's no second column to hang it on."""
    src = EMBED_MODELS if kind == EMBED else BG_MODELS
    return [(name, name, size, f"{desc}  [{lang}]", tier)
            for name, size, desc, tier, lang in src if name != "none"]


def _catalog_for(prov, kind: str) -> list[tuple[str, str, str, str, str]]:
    if prov.key == "ollama":
        return _ollama_catalog(kind)
    return _providers.catalog(prov.key, kind)


def _print_runtimes(provs, p) -> None:
    """What we found, before asking anything. The wizard used to open with a
    40-line model catalog and no word about whether ANY of it could run here."""
    print(f"\n{p.bold('Local LLM runtimes')}")
    for prov in provs:
        if prov.running:
            mark, detail = p.green("●"), p.green(prov.status())
        elif prov.installed:
            mark, detail = p.yellow("○"), p.yellow(prov.status())
        else:
            mark, detail = p.dim("○"), p.dim(prov.status())
        extra = ""
        if not prov.running and not prov.installed and _providers.install_hint(prov.key):
            extra = p.dim(f"   {_providers.install_hint(prov.key)}")
        print(f"  {mark} {prov.name:<12} {detail}{extra}")
    if not any(x.running or x.installed for x in provs):
        print(p.dim("  Nothing local found — you can still finish with a hosted endpoint "
                    "or lexical-only mode."))
    print()


def _offer_start(provs, p) -> None:
    """An installed-but-idle runtime is one keystroke from useful. Ask.

    This is the single most common shape of "Yggdrasil doesn't work": the models
    are on disk, the config is right, and the server just isn't listening.
    """
    for prov in provs:
        if prov.running or not prov.installed or not prov.can_start():
            continue
        if not _prompt.confirm(f"{prov.name} is installed but not running. Start it now?", True):
            print(p.dim(f"  ok — later:  {_providers.start_hint(prov)}"))
            continue
        print(f"  starting {prov.name} ...")
        if _providers.start(prov):
            print(f"  {p.green('✓')} {prov.name} is up — {prov.status()}")
        else:
            print(f"  {p.yellow('–')} couldn't start it. Run it yourself:  "
                  f"{_providers.start_hint(prov)}")


def _provider_options(provs, kind: str) -> list[_prompt.Option]:
    """The runtime picker for one role, live runtimes first."""
    ready, idle, absent = [], [], []
    for prov in provs:
        if prov.running:
            n = len(prov.of_kind(kind))
            note = f"{prov.url.split('//')[-1]} · {n} {'embedding' if kind == EMBED else 'chat'} model{'' if n == 1 else 's'}"
            ready.append(_prompt.Option(prov.key, prov.name, note, "running", "green"))
        elif prov.installed:
            idle.append(_prompt.Option(prov.key, prov.name, "installed, not running — "
                                       "we'll offer to start it", "idle", "yellow"))
        else:
            absent.append(_prompt.Option(prov.key, prov.name,
                                         _providers.install_hint(prov.key), "missing", "red"))
    opts = ready + idle + absent
    opts.append(_prompt.Option("custom", "Another machine…",
                               "Ollama / LM Studio / llama.cpp elsewhere on your LAN"))
    opts.append(_prompt.Option("openrouter", "OpenRouter",
                               "hosted · no GPU needed · memories leave your machine"))
    opts.append(_prompt.Option(
        "none", "none",
        "lexical search only, zero config" if kind == EMBED
        else "no background intelligence (write stays manual)"))
    return opts


def _model_options(prov, kind: str, h: dict) -> list[_prompt.Option]:
    """The model picker: green for what's on disk, red for what we'd download.

    Catalog order carries the recommendation, so it drives the list — but an
    entry the runtime already holds is rewritten to the id the SERVER answers to
    and floated to the top, because "which of these can I use right now" is the
    question people are actually asking at this screen."""
    have: list[_prompt.Option] = []
    want: list[_prompt.Option] = []
    seen: set[str] = set()
    for spec, label, size, desc, tier in _catalog_for(prov, kind):
        model = prov.matches(spec, kind)
        if model is not None:
            have.append(_prompt.Option(model.id, label, desc, "installed", "green"))
            seen.add(model.id)
        elif prov.can_pull():
            want.append(_prompt.Option(_DL + spec, label, f"{desc}  ·  {verdict(tier, h)}",
                                       f"↓ {size}", "red"))
    for model in prov.of_kind(kind):
        if model.id not in seen:
            note = model.note
            # A model already on disk carries no catalog blurb, so the one thing
            # that decides whether distillation takes 7s or 60s per file would be
            # invisible here. Measured on this corpus: qwen3.5-9b ran 58.3s with
            # its thinking pass and 6.9s without, for the same lessons.
            if kind == LLM and _providers.is_reasoning(model.id):
                note = f"{note} · thinking model — suppressed by default".lstrip(" ·")
            have.append(_prompt.Option(model.id, model.id, note, "installed", "green"))
    opts = have + want
    opts.append(_prompt.Option(_CUSTOM, "Something else…",
                               "type any id this endpoint serves"))
    return opts


def _recommended_value(prov, kind: str, opts, h: dict) -> str:
    """Which row the cursor opens on: the recommended model if it's there,
    otherwise the first thing already downloaded."""
    rec_embed, rec_bg = recommend(h)
    accelerated = h["accel_tier"] in ("metal", "cuda", "rocm/vulkan") and h["ram_gb"] >= 16
    if prov.key == "ollama":
        spec = rec_embed if kind == EMBED else rec_bg
    else:
        spec = _providers.defaults(prov.key, accelerated)[0 if kind == EMBED else 1]
    if spec:
        model = prov.matches(spec, kind)
        if model is not None:
            return model.id
        if any(o.value == _DL + spec for o in opts):
            return _DL + spec
    return opts[0].value if opts else ""


def _custom_endpoint(kind: str, p) -> object:
    """Point at a runtime on another machine and work out the rest ourselves.

    We probe the URL and detect the dialect, so the user never has to know that
    LM Studio needs `embed_backend openai` while Ollama doesn't."""
    url = _prompt.text("Endpoint URL (host:port, or a full /v1 base)",
                       "http://192.168.1.10:1234", allow_back=True)
    if url == _prompt.BACK:
        return _prompt.BACK
    if "://" not in url:
        url = "http://" + url
    print(f"  probing {url} ...")
    found = _providers.probe_any(url)
    if found is None:
        print(f"  {p.yellow('–')} nothing answered there. Saving the URL anyway — "
              "start the server and re-run `ygg doctor`.")
        dialect = "openai" if url.rstrip("/").endswith("/v1") else "ollama"
        return _providers.Provider("custom", "Custom endpoint", url, None, dialect=dialect)
    dialect, models = found
    prov = _providers.Provider("custom", "Custom endpoint", url, models, dialect=dialect)
    print(f"  {p.green('✓')} {dialect} endpoint · {len(prov.of_kind(kind))} "
          f"{'embedding' if kind == EMBED else 'chat'} model(s)")
    return prov


def _confirm_downloads(a: dict, p) -> bool:
    """Name every model about to be fetched, with its size, and ask once.

    The picker marks a not-yet-downloaded entry in red with its size, but picking
    one is a choice about which model to use — not yet consent to spend the disk
    and the wait. Both picks are summarised together here, right before the only
    step of the wizard that is slow and hard to undo. True when nothing needs
    downloading, so the caller has no special case."""
    pending = []
    for slot, kind in (("embed", EMBED), ("bg", LLM)):
        picked = str(a.get(slot, ""))
        if not picked.startswith(_DL):
            continue
        spec = picked[len(_DL):]
        prov = a.get(slot + "_prov")
        label, size = spec, "?"
        for cat_spec, cat_label, cat_size, _desc, _tier in _catalog_for(prov, kind):
            if cat_spec == spec:
                label, size = cat_label, cat_size
                break
        role = "embeddings" if kind == EMBED else "distillation"
        pending.append((role, label, size, getattr(prov, "name", "the runtime")))
    if not pending:
        return True
    print(f"\n  {p.bold('To download')}")
    for role, label, size, prov_name in pending:
        print(f"    {p.yellow('↓')} {label}  {p.dim(f'· {size} · for {role} · via {prov_name}')}")
    print(p.dim("    Kept on your machine; the runtime shows its own progress."))
    if _prompt.confirm("Download now?", True):
        return True
    print(p.dim("    Skipped. Yggdrasil will set up without them — "
                "re-run `ygg setup` when you want to add one."))
    return False


def _download(prov, picked: str, kind: str, p) -> str:
    """Resolve a picked catalog entry into an id the server answers to,
    downloading it if needed. Returns "" when the download failed."""
    if not picked.startswith(_DL):
        return picked
    spec = picked[len(_DL):]
    print(f"\n{p.bold('Downloading')} {spec} via {prov.name} — this can take a while.")
    resolved = _providers.pull_and_resolve(prov, spec, kind)
    if resolved:
        print(f"  {p.green('✓')} {resolved}")
        return resolved
    print(f"  {p.red('✗')} download failed. Yggdrasil will run without it; "
          "retry later and re-run `ygg setup`.")
    return ""


def _lmstudio_tips(p) -> None:
    """The two LM Studio settings that decide whether any of this works after
    the terminal is closed. Neither is discoverable from our side."""
    print(f"\n  {p.yellow('LM Studio checklist')} (Developer tab → server settings):")
    print(p.dim("    · Just-In-Time model loading ON — otherwise the first call 404s "
                "because nothing is loaded."))
    print(p.dim("    · Run the server on login ON — the Yggdrasil daemon starts at boot and "
                "will find nothing to talk to otherwise."))


def wizard() -> int:  # noqa: C901 — a linear wizard; splitting it hides the flow
    try:
        from . import ygg_ui
    except ImportError:  # pragma: no cover — flat deploy
        import ygg_ui  # type: ignore
    p = ygg_ui.palette()
    h = hw()
    _prompt.banner("Yggdrasil setup")
    print(f"Hardware: {h['cpu']} | {h['cores']} cores | {h['ram_gb']} GB RAM | "
          f"{h['arch']} | inference: {h['accel']}")
    if h.get("accel_warn"):
        print(f"  {p.yellow('⚠')} {h['accel_warn']}")
    hint = _memory_language_hint()
    if hint:
        print(f"🌍 {hint}")

    provs = _providers.detect()
    _print_runtimes(provs, p)
    _offer_start(provs, p)
    by_key = {x.key: x for x in provs}

    # A step list rather than a straight run of prompts: every answer is a
    # decision the user may want to revise once they see the next question, and
    # `ctrl-c and start over` is a miserable way to change your mind about the
    # first of six. `a` holds answers across back/forward so a revisited step
    # opens on what you already said.
    a: dict = {}
    # `key` comes after BOTH endpoint questions: either half can be the hosted
    # one, and asking before bg is answered meant an OpenRouter distill endpoint
    # never got prompted for a key.
    steps = ["embed_where", "embed_model", "bg_where", "bg_model", "key", "features"]
    i = 0
    while i < len(steps):
        step = steps[i]

        if step in ("embed_where", "bg_where"):
            kind = EMBED if step == "embed_where" else LLM
            slot = "embed" if kind == EMBED else "bg"
            title = ("Where should embeddings run?" if kind == EMBED
                     else "Where should the background model run?")
            default = a.get(slot + "_where") or (
                a.get("embed_where") if kind == LLM else "")
            if not default:
                live = [x for x in provs if x.running]
                default = live[0].key if live else "none"
            choice = _prompt.select(title, _provider_options(provs, kind), default=default,
                                    allow_back=i > 0)
            if choice == _prompt.BACK:
                i -= 1
                continue
            a[slot + "_where"] = choice
            if choice == "custom":
                prov = _custom_endpoint(kind, p)
                if prov == _prompt.BACK:
                    continue          # re-ask this same step
                a[slot + "_prov"] = prov
            elif choice in by_key:
                prov = by_key[choice]
                if not prov.running and prov.installed and prov.can_start():
                    if _prompt.confirm(f"{prov.name} isn't running. Start it now?", True):
                        _providers.start(prov)
                a[slot + "_prov"] = prov
            else:
                a.pop(slot + "_prov", None)

        elif step in ("embed_model", "bg_model"):
            kind = EMBED if step == "embed_model" else LLM
            slot = "embed" if kind == EMBED else "bg"
            where = a[slot + "_where"]
            if where == "none":
                a[slot] = ""
                i += 1
                continue
            if where == "openrouter":
                default = a.get(slot) or ("nvidia/llama-nemotron-embed-vl-1b-v2:free"
                                          if kind == EMBED else "qwen/qwen3-4b:free")
                r = _prompt.text("Model id on OpenRouter", default, allow_back=True)
                if r == _prompt.BACK:
                    i -= 1
                    continue
                a[slot] = r
                i += 1
                continue
            prov = a[slot + "_prov"]
            opts = _model_options(prov, kind, h)
            title = ("Embedding model" if kind == EMBED else "Background / distill model")
            if len(opts) == 1:      # nothing on disk and nothing we can fetch
                r = _prompt.text(f"{title} (id as {prov.name} serves it)",
                                 a.get(slot, ""), allow_back=True)
            else:
                r = _prompt.select(title, opts,
                                   default=a.get(slot) or _recommended_value(prov, kind, opts, h),
                                   allow_back=True)
                if r == _CUSTOM:
                    r = _prompt.text(f"{title} id", a.get(slot, ""), allow_back=True)
            if r == _prompt.BACK:
                i -= 1
                continue
            a[slot] = r

        elif step == "key":
            hosted = [s for s in ("embed", "bg") if a.get(s + "_where") == "openrouter"]
            if not hosted:
                a.pop("key", None)
                i += 1
                continue
            print("  A key from openrouter.ai/settings/keys — an inference key, not a")
            print("  provisioning one (those answer 401 on every embedding call).")
            r = _prompt.text("OpenRouter API key", "", secret=True, allow_back=True)
            if r == _prompt.BACK:
                i -= 1
                continue
            a["key"] = r

        elif step == "features":
            r = _prompt.confirm("Enable SessionStart auto-bootstrap hook?",
                                a.get("hooks", True), allow_back=True)
            if r == _prompt.BACK:
                i -= 1
                continue
            a["hooks"] = r
            a["autosave"] = _prompt.confirm(
                "Auto-distill finished sessions into lessons? (Stop hook, local)",
                a.get("autosave", False))
            has_bg = bool(a.get("bg"))
            a["write_path"] = has_bg and _prompt.confirm(
                "Enable background smart write-path?", a.get("write_path", True))
            a["consolidation"] = has_bg and _prompt.confirm(
                "Enable scheduled auto-consolidation?", a.get("consolidation", False))
        i += 1

    # Downloads happen HERE, not inside the picker: the resolved id (which the
    # runtime only reveals once the model is on disk) is what has to land in
    # config.json, and a 2 GB pull in the middle of a question is hostile.
    if not _confirm_downloads(a, p):
        for slot in ("embed", "bg"):
            if str(a.get(slot, "")).startswith(_DL):
                a[slot] = ""
    for slot, kind in (("embed", EMBED), ("bg", LLM)):
        if str(a.get(slot, "")).startswith(_DL):
            a[slot] = _download(a[slot + "_prov"], a[slot], kind, p)

    embed, bg = a.get("embed", ""), a.get("bg", "")
    feats = {
        "dense": bool(embed),
        "hooks": a["hooks"],
        "autosave": a["autosave"],
        "write_path": a["write_path"],
        "consolidation": a["consolidation"],
    }
    YGG_HOME.mkdir(parents=True, exist_ok=True)
    # MERGE, never overwrite. Re-running `ygg install` is routine (new model, new
    # host, a re-install), and a plain write here silently dropped every setting
    # the wizard doesn't ask about: the pinned user_id/namespace (the whole point
    # of the 0.11.0 identity migration — losing them strands existing memory),
    # embed_backend/embed_url, distill_url, sync_repo. Only touch our own keys.
    cfg_path = YGG_HOME / "config.json"
    try:
        config = json.loads(cfg_path.read_text())
        if not isinstance(config, dict):
            config = {}
    except (OSError, ValueError):
        config = {}
    config.update({"embed_model": embed, "bg_model": bg, "features": feats})
    _apply_endpoints(config, a)
    cfg_path.write_text(json.dumps(config, indent=2))
    # The key goes to its own 0600 file, never config.json — and only for the
    # half that's actually hosted. A Bearer token aimed at a local LM Studio is
    # ignored, but it still shows up in `ygg config list` as a thing you set.
    saved_keys = []
    if a.get("key"):
        if a.get("embed_where") == "openrouter":
            _cfg.set_value("embed_api_key", a["key"])
            saved_keys.append(str(_cfg.EMBED_KEY_FILE))
        if a.get("bg_where") == "openrouter":
            _cfg.set_value("distill_api_key", a["key"])
            saved_keys.append(str(_cfg.DISTILL_KEY_FILE))
    print(f"\nSaved {cfg_path}:\n{json.dumps(config, indent=2)}")
    for path in saved_keys:
        print(f"Saved the API key to {path} (0600).")
    if any(getattr(a.get(s + "_prov"), "key", "") == "lmstudio" for s in ("embed", "bg")):
        _lmstudio_tips(p)

    print("\nInstalling the background service ...")
    try:
        from . import service
    except ImportError:  # flat layout (deployed scripts dir / direct run)
        import service
    # pull=False: every model the user picked is already on disk — the wizard
    # downloaded it through whichever runtime owns it, which `ollama pull` can't.
    return service.install(embed, bg, enable_hooks=feats["hooks"],
                           enable_stop=feats["autosave"], pull=False)


def _apply_endpoints(config: dict, a: dict) -> None:
    """Write the URL/backend trio the user should never have had to work out.

    `embed_url` takes the /v1 base and `distill_url` takes the host root, so the
    same LM Studio needs two different strings — the exact trap this wizard
    exists to close. Each key is also CLEARED when the answer moves back to a
    runtime that doesn't want it, or a stale endpoint keeps aiming the daemon at
    a host the user just walked away from."""
    embed_where, bg_where = a.get("embed_where"), a.get("bg_where")
    embed_prov, bg_prov = a.get("embed_prov"), a.get("bg_prov")

    if embed_where == "openrouter":
        config["embed_backend"] = "openai"
        config["embed_url"] = "https://openrouter.ai/api/v1"
    elif embed_prov is not None:
        if embed_prov.embed_backend == "ollama" and embed_prov.url == _providers.OLLAMA_URL:
            config.pop("embed_backend", None)      # the built-in default; don't pin it
            config.pop("embed_url", None)
        else:
            config["embed_backend"] = embed_prov.embed_backend
            config["embed_url"] = embed_prov.embed_url
    else:                                          # 'none'
        config.pop("embed_backend", None)
        config.pop("embed_url", None)

    if bg_where == "openrouter":
        config["distill_url"] = "https://openrouter.ai/api/v1"
    elif bg_prov is not None:
        if bg_prov.distill_url == _providers.OLLAMA_URL:
            config.pop("distill_url", None)        # the built-in default
        else:
            config["distill_url"] = bg_prov.distill_url
    else:
        config.pop("distill_url", None)


def print_runtime_scan() -> None:
    """What's actually available to run any of this. Kept out of print_catalog so
    the catalog stays a pure function of the hardware dict (and its tests stay
    offline)."""
    try:
        from . import ygg_ui
    except ImportError:  # pragma: no cover — flat deploy
        import ygg_ui  # type: ignore
    _print_runtimes(_providers.detect(), ygg_ui.palette())
    print("`ygg install` lists the models each of these already has, marks what it would")
    print("download, and writes the endpoint settings for whichever one you pick.\n")


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "recommend"
    if cmd == "recommend":
        h = hw()
        print(f"Hardware: {h['cpu']} | {h['cores']} cores | {h['ram_gb']} GB RAM | "
              f"{h['arch']} | inference: {h['accel']}")
        if h.get("accel_warn"):
            print(f"  ⚠ {h['accel_warn']}")
        print_runtime_scan()
        print("Catalog below is named for Ollama; the wizard shows each runtime's own ids.")
        print_catalog(h, with_hardware=False)
        return 0
    if cmd == "hw":
        print(json.dumps(hw(), indent=2))
        return 0
    if cmd == "wizard":
        return wizard()
    print("usage: ygg_setup.py {recommend|hw|wizard}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
