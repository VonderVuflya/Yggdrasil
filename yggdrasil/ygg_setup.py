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
import shutil
import subprocess
import sys
from pathlib import Path

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
    ("paraphrase-multilingual", "563 MB", "Pick if your memory mixes languages.", "cpu", "EN/RU + 50 langs"),
    ("bge-m3", "1.2 GB", "Top retrieval quality, heavier.", "heavy", "multilingual"),
]
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


def recommend(h: dict) -> tuple[str, str]:
    """Default picks for the detected hardware. Multilingual-safe: the quality
    upgrade is Qwen 2.5 3B, NOT Llama 3.2 — Llama 3.2 has no Russian/Chinese and
    silently degrades non-English memory (docs/TODO §3)."""
    embed = "paraphrase-multilingual"  # safe multilingual default
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


def print_catalog(h: dict) -> None:
    rec_embed, rec_bg = recommend(h)
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


def wizard() -> int:
    h = hw()
    print("=== Yggdrasil setup ===\n")
    print_catalog(h)
    rec_embed, rec_bg = recommend(h)
    print()
    if shutil.which("ollama") is None:
        print("Note: Ollama isn't installed yet — semantic search needs it. You can still pick")
        print("models now (they'll be pulled once you install Ollama; exact commands are shown")
        print("at the end), or choose 'none' for zero-config, lexical-only mode.\n")
    embed = _ask("Embedding model (or 'none')", rec_embed)
    bg = _ask("Background model (or 'none')", rec_bg)
    feats = {
        "dense": embed != "none",
        "hooks": _ask_yes("Enable SessionStart auto-bootstrap hook?", True),
        "autosave": _ask_yes("Auto-distill finished sessions into lessons? (Stop hook, local)", False),
        "write_path": bg != "none" and _ask_yes("Enable background smart write-path?", True),
        "consolidation": bg != "none" and _ask_yes("Enable scheduled auto-consolidation?", False),
    }
    YGG_HOME.mkdir(parents=True, exist_ok=True)
    config = {"embed_model": "" if embed == "none" else embed,
              "bg_model": "" if bg == "none" else bg, "features": feats}
    (YGG_HOME / "config.json").write_text(json.dumps(config, indent=2))
    print(f"\nSaved {YGG_HOME / 'config.json'}:\n{json.dumps(config, indent=2)}")

    print("\nInstalling the background service ...")
    try:
        from . import service
    except ImportError:  # flat layout (deployed scripts dir / direct run)
        import service
    return service.install(config["embed_model"], config["bg_model"],
                           enable_hooks=feats["hooks"], enable_stop=feats["autosave"])


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "recommend"
    if cmd == "recommend":
        print_catalog(hw())
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
