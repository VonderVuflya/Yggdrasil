# TODO — Corpus scale, model lifecycle & LM Studio integration

> Captured 2026-07-30 from a working session on a CUDA box with a **4,799-memory** store —
> ~20x the corpus BENCHMARKS.md was measured on. Several defaults that were right at 232
> memories stop being right at 4.8k, and three real bugs surfaced along the way.

## Reference: the machine that surfaced all this
- AMD **Ryzen 9 9950X3D** (16c/32t), **91 GB RAM**, **RTX 5080 16 GB** (Blackwell, sm_120).
- Runtime: **LM Studio** (llama.cpp CUDA12 `2.27.1`) serving both embeddings and distillation
  on `:1234`, OpenAI dialect. `justInTimeModelLoading: true`.
- Store: **4,799 memories** (median 146 chars, p95 252), mixed RU/EN, 12+ projects.
- Config at session start: `embed_model=paraphrase-multilingual-mpnet-base-v2`,
  `bg_model=qwen/qwen3-4b-2507` (Q8_0).

---

## 1. Default embedder is wrong at scale — ✅ measured — ✅ SHIPPED

Re-ran the embedder comparison on the **full 4,799-memory store** with 120 LLM-generated
queries (3 classes: paraphrase / crosslingual / natural), gold = source memory.

| model | recall@1 | CI95 | recall@3 | MRR@10 | docs/s |
|---|---|---|---|---|---|
| **bge-m3** (F16, 1024d) | **0.775** | 0.692–0.842 | 0.967 | 0.867 | 241 |
| qwen3-embedding-0.6b (instruct) | 0.758 | 0.683–0.833 | 0.958 | 0.856 | 127 |
| qwen3-embedding-0.6b (raw) | 0.725 | 0.650–0.800 | 0.925 | 0.827 | 127 |
| paraphrase-multilingual (default) | 0.550 | 0.467–0.642 | 0.783 | 0.671 | 384 |
| lexical baseline (FTS5/BM25) | 0.550 | 0.458–0.642 | 0.717 | 0.639 | — |

Paired: bge-m3 beats the default by **Δrecall@1 = +0.225, CI95 [+0.125…+0.325]** (46 wins,
9 losses, 65 ties). bge-m3 vs qwen3-embedding is **not** significant (Δ+0.017, CI crosses 0),
so bge-m3 wins on speed (2x) and on already being in the catalog.

**The scale effect is the real finding.** The `docs/` note from 2026-07-14 concluded "don't
change the default, paraphrase-multilingual scores 0.94" — that was on 232 memories. At 4,799
the same model drops to **0.550, exactly level with the BM25 baseline**: dense retrieval was
contributing nothing over lexical except crosslingual (0.575 vs 0.300). Weak embedders
degrade faster than strong ones as the candidate pool grows.

**Actions:**
- [x] `embed_model` switched to `text-embedding-bge-m3` on this box.
- [x] `recommend()` returns **bge-m3** once the store is past `LARGE_STORE_MEMORIES` (1,000)
      *and* the hardware can carry it (GPU tier or ≥16 GB RAM) — a big store on a weak CPU
      is not pushed toward a 1.2 GB model. Catalog blurbs now say what actually decides:
      paraphrase "fades past ~1k memories", bge-m3 "the only one that holds up on a large
      store". Tested in `tests/test_setup.py::LargeStoreEmbedderTest`.
- [x] `ygg doctor` flags a large store sitting on a weak embedder, with the three commands
      to switch (`config set` → `redeploy` → `reindex`).
- [x] BENCHMARKS.md states the corpus size next to the headline and carries the 4,799-memory
      counter-measurement, so "recall@1 = 0.94" can't be read as a constant.

### 1a. Memory length barely matters once the embedder is good
recall@1 by gold-memory length, same run:

| length | bge-m3 | paraphrase-multilingual |
|---|---|---|
| 0–150 chars | 0.857 | 0.690 |
| 150–220 | 0.721 | 0.500 |
| 220+ (n=10) | 0.800 | 0.300 |

The weak embedder loses more than half its accuracy on longer memories; bge-m3 shows no
trend. The "keep memories short so they stay findable" instinct was compensating for the
embedder, not for a property of retrieval. (n=10 in the long bucket — worth a dedicated run.)

---

## 2. `ensure_running()` spawns past the service manager — 🔴 BUG — ✅ FIXED

Switching `embed_model` and running `ygg redeploy` produced a **split brain**:

```
~/.config/systemd/user/yggdrasil.service   ExecStart ... --embed-model <OLD model>   (mtime: install day)
actually running process (from the terminal) ... --embed-model <NEW model>
systemctl --user is-active yggdrasil       activating (auto-restart)
journal: "Scheduled restart job, restart counter is at 167"
```

**Root cause (corrected after reading the code — it is not `install()`).** `_install_systemd`
does rewrite the unit and `daemon-reload`; it simply never ran, because `redeploy` was never
invoked. What actually happened: `ygg config set embed_model …` updated only `config.json`,
and then the next command that touched the engine called `ensure_running()` — which, on a
failed `health()`, **spawns the daemon directly** with the model read from config, bypassing
the manager entirely (`service.py:ensure_running` → `_spawn_detached`). The manual daemon took
the port, so systemd's own (stale) copy failed every `RestartSec=2` forever. The lazy-spawn
safety net masked the divergence by always starting the *correct* process next to the
*incorrect* unit.

**Why it is worse than a noisy loop:** the embedder is passed as an **argv flag**
(`service.py:engine_argv` → `--embed-model`), not read from config at startup. So after a
reboot systemd wins, the daemon comes up on the *old* model, and the store now holds
1024-dim bge-m3 vectors it cannot interpret. Combined with §3 this fails **without any error**.

**Actions:**
- [x] `installed_unit_argv()` / `unit_is_stale()` / `refresh_unit()` — read back what the
      manager will actually launch (systemd unit, launchd plist) and compare with the argv
      we want. Tested in `tests/test_service.py::TestStaleUnitDetection`.
- [x] `ensure_running()` now refreshes a stale unit and starts **through** the manager
      (`_start_via_manager()`), falling back to the direct spawn only if the manager hasn't
      brought the engine up within half the wait budget (masked unit, container without a
      working systemctl).
- [x] `start()` no longer duplicates the manager commands.
- [x] `ygg doctor` compares the autostart unit against what `config.json` implies and says
      "launches different flags than config.json → ygg redeploy" when they diverge.
- [ ] Consider reading `embed_model` from config **at daemon startup** instead of argv, so a
      plain restart suffices and the unit can never go stale in the first place.

---

## 3. LM Studio silently substitutes the embedding model — 🔴 BUG (upstream) — ✅ GUARDED

```
POST /v1/embeddings   {"model": "does-not-exist-12345"}   -> HTTP 200, vector from the
                                                              currently-loaded embedder,
                                                              response "model": "<other model>"
POST /v1/chat/completions {"model": "does-not-exist-12345"} -> HTTP 400  (correct)
```

Only the embeddings endpoint does this. A typo in `embed_model`, or a model that was deleted
from disk, produces **valid-looking vectors from the wrong model** — and Yggdrasil stores them
tagged with the *requested* model name, so `reindex` will later consider them current. The
store silently becomes a mix of two vector spaces.

**Actions:**
- [x] `OpenAIEmbedder._served_by_requested_model()` compares `response["model"]` with the
      requested id and refuses the vector on a mismatch, warning once. Cosmetic differences
      (publisher prefix, `.gguf` suffix, `_`/`-`) are not treated as substitution, and an
      absent `model` field stays accepted — older llama-server builds don't echo it.
      Tested in `tests/test_openai_embedder.py::ModelSubstitutionTest`.
- [ ] `ygg doctor`: probe the embeddings endpoint with the configured id and assert the echo.
- [ ] Store the **dimension** alongside `embed_model` and reject writes whose dimension
      differs from the column's existing vectors.

---

## 4. Model lifecycle: stop pinning models in VRAM — 🟡 feature — ✅ DONE (embeddings)

A user should not have to pre-load models into LM Studio and keep 10+ GB resident 24/7 just
because a background daemon might wake up. LM Studio already supports this; Yggdrasil just
doesn't use it.

Verified on this box:

```
POST /v1/embeddings {"model": "...bge-m3", "input": [...], "ttl": 300}
  -> JIT-loads the model and lms ps reports TTL "5m / 5m"; it self-unloads after idle.
```

Manually loaded models (via the GUI) carry **no TTL** and stay resident forever — that is the
actual reason a model "hangs in memory", not JIT.

**Actions:**
- [x] New `embed_ttl` config knob (default `0` = off, since `ttl` is a non-standard field and
      a strict OpenAI-compatible server could reject it). When set, `OpenAIEmbedder` sends it
      on every request; it rides to the daemon as `--embed-ttl`. Verified end-to-end on this
      box: unload the model, run `ygg search`, and LM Studio JIT-loads it with `TTL 5m / 5m`.
- [x] `distill_ttl` does the same for the bg model — the big one (4–18 GB here). A longer
      default window is the right shape: it must outlive the gaps *within* a `ygg seed`
      (a per-file reload costs more than the VRAM) while still releasing the GPU between
      runs. Verified: `qwen3-4b-2507` came back with `TTL 10m / 10m` after one distill.
- [x] `ttl` joined `_NONSTANDARD_KEYS`, so a server that 400s on it loses the idle-unload,
      not the distill.
- [x] `ygg_providers.unload()` + `_release_model()` at the end of a seed run: a `ttl` only
      starts counting down after the LAST request, so a finished run would hold multi-GB of
      VRAM for another ttl-worth of minutes. Only fires when a ttl is configured (an unset
      one means the model was meant to stay) and only for LM Studio — Ollama has its own
      `keep_alive` and llama.cpp serves one fixed model. Best-effort and silent.
- [x] `ygg doctor` reports models with no idle-unload window. The runtime's REST API doesn't
      expose per-model TTL, so it's judged from our side: an unset `embed_ttl`/`distill_ttl`
      means we never ask for a release, which is the same outcome and is actionable.
- [ ] Document that with JIT enabled the user needs **zero** manual model loading.

### 4a. `enable --now` never restarts a running service — 🔴 BUG — ✅ FIXED
Found while verifying the above: after `ygg redeploy` the unit on disk carried
`--embed-ttl 300` while the running engine had no such flag. `_install_systemd` finished with
`systemctl --user enable --now`, which only *starts a stopped* unit — an already-running
daemon keeps its old `ExecStart` until something restarts it. So every daemon-level config
change (`embed_model`, `embed_url`, `embed_ttl`) silently took effect only on the next reboot.
Now it runs an explicit `restart` after `daemon-reload` (which also starts a stopped unit).
The launchd path was already correct — it `bootout`s before `bootstrap`.
Tested in `tests/test_service.py::test_install_restarts_a_running_service`.

---

## 5. `reindex` is silent and racy — 🟡 UX + correctness — ✅ FIXED

`cli.py:_reindex()` fires one synchronous `POST /reindex` and waits with no output while the
server walks 4,799 rows in chunks of 32. It looks hung. Worse, the daemon **also** reindexes
on startup in a background thread (`ygg_memory_server.py:_warm_and_reindex`), so a manual
`ygg reindex` right after `redeploy` races it. Observed result:

```
reindex: backfilled 3615 missing embedding(s).     # not 4799 — the startup thread took the rest
```

Correct in the end (verified: 4,799/4,799 rows on the new model, 4,096-byte blobs = 1024
float32), but the number is unexplainable to a user.

**Actions:**
- [x] `GET /reindex/status` exposes `{running, done, total, remaining}`; the CLI starts a
      watcher thread that renders a bar while the blocking POST is in flight:
      `reindexing ██████░░░░░░ 41% 608/1500`. Verified on 1,500 real rows.
- [x] `_reindex_gate` (non-blocking lock) makes a second concurrent pass a no-op returning
      `-1`; the endpoint answers `already_running` with the current progress and the CLI
      prints "already running in the background (N/M done)" instead of a partial count.
- [x] The response carries `total` and `missing` as well, so the CLI can say
      "backfilled 0 embedding(s) — 4856 memories, all embedded." `healed` alone read as
      "only N of my memories are indexed" whenever the startup thread had done the rest.

---

## 6. Distillation: reasoning models burn 3–6x the time for nothing — 🟡 feature — ✅ DONE

12 configurations on 8 real transcripts (same logs, real `DISTILL_PROMPT`/parser).
Run-to-run noise measured by repeating identical runs: **±4 lessons, ±5 pp specificity** —
anything smaller is not a difference.

| model | lessons | w/ specifics | s/log | full 397-file reseed |
|---|---|---|---|---|
| qwen3-4b-2507 **Q8_0** (current) | 42–46 | 83–85% | 2.8–3.9 | **19–26 min** |
| qwen3-14b Q4 + reasoning off | 43–45 | 74–80% | 5.4–6.1 | 36–40 min |
| qwen3.6-35b-a3b (MoE) reasoning off | 37 | 89% | 10.4 | 69 min |
| qwen3-14b Q5 reasoning **on** | 43 | 86% | 16.8 | 1.9 h |
| qwen3.5-9b reasoning **on** | 39 | 92% | 29.6 | 3.3 h |
| mistral-small-3.2-24b | 40 | 72% | 30.7 | 3.4 h |
| gemma-4-26b-a4b (MoE) | 35 | 94% | 47.3 | 5.2 h |
| **qwen3.6-35b-a3b (MoE) reasoning on** | 38 | **89%**, **0 violations** | 81.3 | 8.9 h |
| qwen2.5-coder-14b | 44 | 68% | 17.7 | 2.0 h |

Turning reasoning off is the single biggest speedup available (14B: 16.8 s → 6.1 s, same
lesson count). **But how you turn it off is model-specific, and Yggdrasil can do neither:**

| method | Qwen3 | Qwen3.5 / Qwen3.6 |
|---|---|---|
| `/no_think` in the prompt | ✅ works | ❌ silently ignored |
| `reasoning_effort: "none"` in the body | ✅ works | ✅ works |
| `chat_template_kwargs.enable_thinking=false` | ❌ ignored by LM Studio | ❌ |

Also note the newer Qwen generations pay for the speed with **obedience**: with reasoning off,
qwen3.5-9b produced 11 over-length lessons and one unparseable JSON, and qwen3.6-35b wrote 9
lessons in English out of Russian logs. Qwen3-14B has no such regression.

**Actions:**
- [x] `distill_reasoning` config + `ygg seed --reasoning auto|off|on`. Default `auto`
      suppresses only for models whose names say they think (`qwen3`, `deepseek-r1`,
      `glm-5`, … minus `-instruct`/`non-thinking` builds). All three signals go out at once —
      `reasoning_effort: "none"` (OpenAI dialect), `think: false` (Ollama), and the
      `/no_think` marker — because none of them works everywhere and each is inert where
      unsupported.
- [x] A server that answers 400/422 to the unknown field gets one retry without it: an
      unrecognised knob must cost speed, never the whole distill.
- [x] Verified end-to-end on this box (qwen3.5-9b, same transcript):
      **reasoning on 64.3 s → auto 7.7 s, 6 lessons either way (×8.4)**.
- [x] Guards re-checked under suppression on 8 Russian transcripts, 4 runs. Strict JSON,
      salvage and `_looks_truncated` all held (0 failures either way). **Language did not:**
      reasoning ON drifted in 0 of 4 runs, suppressed in 2 of 4 (4 and 5 English lessons of
      ~48). Two fixes, because prompt wording alone isn't a guarantee:
      `_restate_language()` repeats the rule at the very END of a suppressed prompt
      (recency), and `_wrong_language()` is the deterministic backstop — an English lesson
      about a Cyrillic-dominant log is dropped like a truncated stub, and the file is
      retried on the next seed. Narrow by design: fires only when the source is clearly
      Russian and the lesson has *no* Cyrillic at all, so an identifier-heavy Russian
      lesson passes.
- [x] Correction to the note above: suppression is **not** free on a model that wasn't
      reasoning. `qwen/qwen3-4b-2507` is an instruct build (LM Studio's id omits
      "instruct", so the heuristic suppresses on it), gained no speed — and drifted.
- [ ] Catalog: mark models as reasoning/hybrid so `ygg install` can warn about the cost.
- [ ] Tighten `_is_reasoning_model` against ids that hide the build type (`…-2507` is an
      instruct release; the name alone can't be trusted). Probing the runtime for a
      `reasoning` capability flag would beat the substring list.

### 6a. Quantization matters more on small models
Same model, different quant, same logs:

| model | lessons | specificity |
|---|---|---|
| qwen3-4b **Q8_0** | 42 / 42 / 46 | 83–85% |
| qwen3-4b **Q4_K_M** | 30 | 97% (small-sample artifact) |
| qwen3-14b **Q5_K_M** | 38 | 79% |
| qwen3-14b **Q4_K_M** | 43 / 43 / 45 | 74–80% |

The 4B loses ~30% of its extraction at Q4 — far outside noise. The 14B does not care.
**Recommend Q8_0 for ≤4B distill models**, Q4/Q5 is fine from ~14B up.

### 6b. MoE does not pay off at 16 GB
`qwen3.6-35b-a3b` (3B active) and `gemma-4-26b-a4b` (4B active) were both **slower** than
dense 14B here: neither fits in 16 GB (16.6 / 15.0 GB of weights + KV), so layers spill to
CPU and the sparsity advantage is spent on transfers. MoE needs headroom to be worth it.

---

## 7. The 280-char lesson cap is too tight — ✅ measured — ✅ RAISED TO 500

`DISTILL_PROMPT` says `Keep each under 280 chars`. Tested 280 / 450 / 500 on the same 8 logs
with the same model:

| cap | lessons | avg len | p90 len | over cap | w/ specifics | identifiers/lesson |
|---|---|---|---|---|---|---|
| 280 | 37 | 173 | 214 | 0 | 78% | 2.11 |
| 450 | 43 | 194 | 247 | 0 | 84% | 2.58 |
| **500** | 37 | **195** | 245 | 0 | **92%** | **2.70** |

Raising the cap does **not** make the model ramble — average length moves 173 → 195 and p90
stays ~245, nowhere near the ceiling. What changes is density: specificity 78% → 92% and
identifiers per lesson +28%. Under a tight cap the model drops concrete details to fit;
given room it keeps them. Indivisible enumerations (a `.gitignore` block, a command with
flags) finally survive — the longest lesson produced was 314 chars.

**Actions:**
- [x] Cap raised to **500** in `DISTILL_PROMPT`.
- [x] Atomicity instruction added alongside it ("ONE fact per lesson; if a note covers several
      topics, split it") — the cap was doing that job implicitly and should not.
- [ ] Keep the over-cap counter as a **model obedience signal** in evals; it correlates with
      other instruction failures (language drift, malformed JSON).
- [ ] Existing memories were NOT re-distilled: only 3.1% of the 4,799 exceed 280 anyway, and a
      reseed would reset `access_count` on the 1,233 memories that carry real usage signal.
      New sessions get the higher cap; the old ones stay valid.
