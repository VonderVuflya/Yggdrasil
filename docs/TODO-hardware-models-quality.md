# TODO — Hardware-awareness, model catalog & memory quality

> Captured 2026-06-30 from a working session on a CPU-only Intel Mac.
>
> **Status (2026-07-14):** §1–§6 all ✅ done. This TODO is fully closed; the only
> optional leftover is the TensorFlow-Projector `ygg export --tsv` recipe under §6.

## Reference: the machine that surfaced all this
- Mac mini 2018 (`Macmini8,1`), Intel **i7-8700B** (6c/12t, AVX2), **32 GB RAM**.
- GPUs: **AMD Radeon RX 580 4 GB (Thunderbolt eGPU)** + Intel UHD 630.
- **macOS ⇒ CPU-only inference.** The GPU is effectively unusable for local LLMs here (see §1).
- Config after this session: `bg_model=qwen2.5:3b`, `distill_timeout=480`, `embed_model=paraphrase-multilingual`.
- `OLLAMA_CONTEXT_LENGTH=32768` is set on the Ollama.app server (by the user). **Verified via `ollama ps`:** qwen2.5:3b loads at CONTEXT **32768**, paraphrase-multilingual at **128** (its own ceiling). So distillation already runs at 32k.

---

## 1. Hardware-aware warnings (`ygg install` / `recommend` / `doctor`) — ✅ DONE
> `hw()` classifies an acceleration tier (`cpu`/`metal`/`cuda`/`rocm/vulkan`) and
> emits `accel_warn` for the Intel-Mac + AMD case; `print_catalog` surfaces it.
> (`doctor` effective-context reporting lives under §2.)
Tell the user **plainly** when their GPU will NOT be used, and why — instead of silently running on CPU.

- Detect **Intel Mac + (discrete/eGPU) AMD GPU** ⇒ warn:
  *"You have a GPU but it will NOT accelerate inference on macOS."*
- The "why" to surface:
  - macOS GPU compute = **Metal only**; **ROCm does not exist on macOS**.
  - Ollama / llama.cpp Metal backend is **Apple-Silicon-oriented**. On Intel + discrete AMD, stock Metal is **slower than CPU** (weights streamed over PCIe): measured **0.8 tok/s on a 6900 XT vs 21 tok/s on CPU** — `ggml-org/llama.cpp#15228`.
  - **Vulkan via MoltenVK on Intel Macs produces gibberish** — `ggml-org/llama.cpp#20104`.
  - The only real GPU path for an RX 580 is **Linux + Vulkan** (~25 tok/s on a 4B) — i.e. *not macOS*.
- Generalize into an **acceleration-tier classifier** shown in `ygg recommend`:
  - Apple Silicon → Metal ✓
  - Intel Mac → **CPU only**, regardless of GPU presence
  - Linux/Windows + NVIDIA → CUDA
  - Linux/Windows + AMD → ROCm/Vulkan
- Also reframe expectations: for a 1.5B–4B distill model, this CPU is *fine*; chasing the GPU here is low-ROI. Say so.

## 2. Ollama context length (`num_ctx`)
- **The real gap:** `ygg_seed.py` distill call sends `{model, prompt, stream, format}` with **no `options`** — so Yggdrasil does NOT control `num_ctx` and silently inherits the server's `OLLAMA_CONTEXT_LENGTH` (or the 4096 default if the user never set it). On this machine the user happened to set 32768, so it works — but that's **fragile/implicit**. Yggdrasil should set context explicitly.
- Ollama default `num_ctx = 4096` is **too small for distillation** — the model sees only a fragment of a session → truncated / low-quality lessons.
- **Recommend bumping the DISTILL model to 16k (sweet spot) or 32k (max for qwen2.5).** KV cache for qwen2.5:1.5b ≈ 28 KB/token ⇒ 16k ≈ 0.47 GB, 32k ≈ 0.94 GB — trivial vs 32 GB RAM. Real cost is CPU prefill time, bounded by `distill_timeout`.
- **Do NOT bump the EMBEDDING model** — `paraphrase-multilingual` caps at ~512 tokens; extra context is wasted (engine already truncates embed input to ~4000 chars).
- Implementation options:
  - New config key `distill_num_ctx`, passed as `options.num_ctx` in the Ollama distill call.
  - Or set it per-model via a generated Modelfile (`FROM <model>` + `PARAMETER num_ctx 16384`) during `ygg install`.
  - `ygg doctor`: report the **effective** loaded context (probe `ollama ps` after a load, or read `OLLAMA_CONTEXT_LENGTH`) and warn if `< ~16k` — don't assume 4096.

## 3. Model catalog updates (`ygg recommend`) — ✅ DONE
> Catalog carries language/thinking tags; qwen2.5:3b / qwen3:4b-instruct-2507 /
> gemma3:4b added; llama3.2:3b flagged `⚠ NO Russian/Chinese`; `recommend` no
> longer picks Llama; dominant-language steer implemented (`_memory_language_hint`).
- Catalog is **dated** and **language-blind**. It recommends `llama3.2:3b` as the quality upgrade, but **Llama 3.2 does NOT officially support Russian** (EN + 7 European langs only) → poor for non-English memory.
- Prefer the **Qwen family** for multilingual (RU/ZH) memory:
  - **`qwen2.5:3b`** — best CPU balance, strong Russian, ~1.9 GB. *Recommended upgrade from 1.5b.* (now in use)
  - `qwen3:4b-instruct-2507` — newer/better, slower on CPU. **Use the non-thinking `instruct` variant** — a reasoning variant burns the timeout on `<think>` traces.
  - `gemma3:4b` — strong multilingual, slower on CPU.
- Annotate each catalog entry with: **language coverage** (esp. the user's content language), **thinking vs non-thinking**, **CPU speed tier**.
- Stretch: auto-detect the dominant language of existing memory and steer the recommendation (RU/ZH → Qwen/Gemma, never Llama).

## 4. New CLI: `ygg delete` / `ygg reset` (currently MISSING)
There is **no CLI way to delete memories or reset the store** today — this session required manual `sqlite3` surgery. Make it first-class.

- `ygg delete --id <id> | --source <pat> | --project <p> | --type <t>` — selective deletion.
- `ygg reset [--keep-manual] [--yes]` — wipe the store, optionally preserving non-`seed:%` (manual/imported) sources.
- Both MUST:
  1. **auto-backup** the DB first,
  2. keep **`mem_fts` in sync** — `DELETE FROM mem_fts WHERE rowid IN (SELECT seq FROM memories WHERE …)` *then* delete from `memories` (linkage is `mem_fts.rowid == memories.seq`; no triggers exist today),
  3. **VACUUM** afterwards.
- **Why this matters:** re-distilling with a *different* `bg_model` creates **near-duplicates** (new wording → new `content_hash` → exact-dedup misses it). A clean model switch **requires deleting old `seed:%` memories first**. (Done manually this session: deleted 1070 `seed:%`, kept 57 manual, 20 MB → 1.4 MB.)

## 5. Write-path quality: truncated lessons — ✅ DONE (write-path guard)
> `_looks_truncated` drops a mid-sentence stub at write time (trailing `:` /
> dangling connector / unbalanced bracket or quote), counted as `truncated` and
> surfaced in the seed summary — length is not used as a signal. (File-level
> `finish=="length"` truncation was already raised.) A one-off backfill audit of
> pre-existing stubs is still worth doing but needs no code here.
- Found a memory **stored truncated at 132 chars** ("…выполнить следующие действия:" — the list never written). Likely a **write-path** bug (timeout / output cutoff), **not** the model.
- TODO:
  - Audit: count likely-truncated memories (end with `:` / `—` / mid-sentence; short *for their type*). NB: lessons are intentionally `<280` chars, so short ≠ truncated — needs a smarter heuristic than length alone.
  - Harden distill: detect incomplete model output (no terminal punctuation / trailing colon) → retry or discard, don't persist a stub.
- Swapping the model won't fix this — truncation can recur after re-seeding. Fix the write-path too.

## 6. Embedding-space quality tooling — ✅ DONE (`ygg quality`)
> Shipped `ygg quality` (engine `/quality` + `MemoryStore.quality_report`): type/
> project distribution, exact-duplicate pairs (content_hash), near-duplicate pairs
> (cosine ≥ threshold, default 0.95), cross-project leakage, and likely-truncated
> records (reuses the write-path `_looks_truncated`). Vectors never leave the
> engine — only derived metrics. Tests in `tests/test_quality.py`. The optional
> TensorFlow-Projector `ygg export --tsv` remains a nice-to-have (docs recipe).

## 6-orig. Embedding-space quality tooling (TensorFlow Embedding Projector)
- Ship `ygg export --tsv` (or a docs recipe) to emit `vectors.tsv` + `metadata.tsv` for **projector.tensorflow.org** (data stays client-side in the browser).
- 5 visual diagnostics: **clusters** (UMAP/t-SNE by project), **duplicates** (nearest neighbors), **outliers** (junk/truncated), **cross-project leakage**, **semantic-search sanity**.
- Or a `ygg quality` report with hard metrics from the DB: near-duplicate pairs (cosine > 0.95), truncated/short records, per-project cohesion vs leakage, type distribution.
- Local prototype exists: `scratchpad/ygg_viz.py` (read-only on `memory.sqlite`, PCA 768→3, self-contained `ygg_3d.html` with project filter, click-for-full-text, X/Y/Z axis cube).

---

## Sources
- llama.cpp [#15228](https://github.com/ggml-org/llama.cpp/issues/15228) — Metal3 on Intel+AMD: 0.8 tok/s vs 21 CPU; fix is an unmerged custom fork.
- llama.cpp [#20104](https://github.com/ggml-org/llama.cpp/issues/20104) — Vulkan on Intel Macs → gibberish.
- [LM Studio system requirements](https://lmstudio.ai/docs/app/system-requirements) — no Intel-Mac / no AMD-Metal acceleration.
- [apple/container #62](https://github.com/apple/container/discussions/62), [apple/containerization #46](https://github.com/apple/containerization/issues/46) — no GPU passthrough; Apple-Silicon only.
- Llama 3.2 supported languages (no Russian) vs Qwen2.5 (Russian among 29) — llm-stats / Meta model card.
