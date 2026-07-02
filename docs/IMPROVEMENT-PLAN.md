# Yggdrasil — Improvement Plan

_Source: full technical audit on 2026-07-01 — four parallel deep-dives (core engine, periphery/packaging/DX, competitive landscape, README teardown). Version audited: 0.5.4._

Legend: **[S]** security · **[C]** correctness · **[P]** performance · **[DX]** developer experience · **[M]** marketing/positioning. Effort: ~S (<1h), ~M (<1 day), ~L (days).

---

## P0 — Fix before the next release

1. **[C] Lexical search returns nothing for non-Latin text** — `ygg_memory_server.py:93,100-101`. `_TOKEN_RE = [a-z0-9]+` is ASCII-only while FTS uses `unicode61`. Store «исправил баг в парсере», search «баг» → `[]`. The README ships in 7 languages; RU/CJK users get zero lexical recall. Fix: unicode-aware `\w+` tokenizer, keep length/stopword filters. ~S.
2. **[S] HTTP MCP facade silently runs auth-open + arbitrary-path file write** — `ygg_http_mcp.py:44-63`, `ygg.py:413-423`. No token found → `TOKEN=""` → `_auth_ok()` always true; `ygg_materialize` accepts any `output_dir` → unauthenticated remote client (this facade is built for tunnels) can write attacker-seeded `.md` into e.g. `~/.claude/commands/` = prompt-injection persistence. Fix: refuse to start without a token unless `--insecure`; normalize/whitelist `output_dir` under the vault root. ~S.
3. **[S] `install.sh` writes the auth token in plaintext into 644 launchd plists** — `install.sh:96,200`. Legacy branch, but `ygg consolidate` still executes it today (`cli.py:126-132`). Defeats the whole token-by-file design. Fix: pass token by file path; gut the legacy `install` branch. ~S.
4. **[C] No rollback on write exceptions → next commit flushes partial writes** — `ygg_memory_server.py:247-315`. A failure mid-add leaves an open transaction; the next request commits a `memories` row with no FTS row — permanently invisible to lexical search. Fix: `with self._conn:` around all write paths. ~S.
5. **[C] Malformed client input crashes HTTP routes** — `int(limit)` / `float(importance)` at `ygg_memory_server.py:233,643,690`: `limit="abc"` → traceback + dropped connection (and triggers #4). Fix: one try/except in route dispatch → JSON 400. ~S.
6. **[C] `update()` never refreshes `content_hash`** — `ygg_memory_server.py:283-304` — corrupts hash-dedup after any edit (old text wrongly rejected, new text duplicable). Fix: recompute when `data` changes. ~S.
7. **[S] Auth hygiene bundle** — token compare via `==` → `hmac.compare_digest` (`ygg_memory_server.py:586-588`); no Host-header check → DNS-rebinding risk; bare `ygg serve` falls back to the publicly-known `yggdrasil-demo-token` (`:50-54`) → generate a random token instead; MCP facade `env.setdefault(... "yggdrasil-demo-token")` (`ygg_mcp_server.py:278`) short-circuits the token-file fallback → remove; `service.py:242-294` writes the real token in plaintext into `~/.claude.json` → reference the token file. Each ≤5 lines. ~S–M total.
8. **[DX] `ygg doctor` says "All good." with zero MCP registration** — `cli.py:208-218`: `claude_reg`/`codex_reg` never folded into `ok`. The one command Quick Start tells users to trust can lie. Fix: `ok &= (claude_reg or codex_reg or plugin_detected)`. ~S.

## P1 — Quick wins (days, not weeks)

9. **[DX] Add CI.** No `.github/` at all — 759 test lines + 4 gates run on the honor system, and `release.sh --no-tests` exists. One workflow: `unittest discover` + `scripts/run_gates.sh`, matrix macOS/Linux/Windows (also validates the platform claims). ~M.
10. **[DX] `ygg delete` / `ygg reset`.** The single worst first-hour risk: a bad `ygg seed` is permanent without sqlite surgery (the author has already had to hand-delete 1070 rows). ~M.
11. **[C] `GET /get?id=` endpoint** — materialize currently linear-scans `get_all limit=1000`; memories beyond #1000 can't be materialized (`ygg.py:405-410`). ~S.
12. **[C] Seed distillation quality** — send `options.num_ctx` explicitly (quality currently depends on the user's Ollama default = truncated lessons); reject/flag incomplete model output; document `MAX_CHARS_PER_FILE=14000` truncation (`ygg_seed.py:43,349`). ~M.
13. **[DX] Hooks portability & duplication** — `hooks/hooks.json` hardcodes `python3` (Windows: silent permanent failure); plugin + `ygg hooks` double-registration injects context twice. Platform-aware launcher; dedupe by marker. ~M.
14. **[C] Dead/twin code cleanup** — delete `materialize_memory.py` (zero callers, diverged twin of `ygg.py:384-423` with a real YAML-bool bug); delete dead `ygg.py:52-56 engine_token()` (contains `YGG_ENGINE_TOKEN or YGG_ENGINE_TOKEN or YGG_ENGINE_TOKEN` copy-paste bug); fix duplicated env lookup in `ygg_quality_gate.py:22`; unify token resolution (currently re-implemented 5×). ~M.
15. **[DX] Repo hygiene** — untrack `packaging/mcpb/*.mcpb` (0.5.1–0.5.4; GitHub Releases already hosts them) + gitignore the pattern; gitignore `.cache/`, `.claude/`, `scratchpad/`; commit `docs/TODO-hardware-models-quality.md` (it's one `rm` away from lost) or convert to issues. ~S.
16. **[DX] Retire demo-heritage defaults** — all real user data lands in `namespace=yggdrasil-demo`, `user_id=demo-user`. Rename with a migration (renaming later strands memories). ~M.
17. **[DX] Stale docs/docstrings** — `cli.py:5-8` & `ygg_setup.py:7` claim install "delegates to install.sh" (false since the `service.py` rewrite); `ygg_writepath.py:13` shows a moved path; `docs/ygg-cli.md` still says "MVP CLI"; unify the platform story (README fixed already: "built, in final testing"). ~S.

## P2 — Performance & scale (unlocks growth past ~20k memories) — ✅ DONE (2026-07-02, commits 3bd78ab..e8d9786)

18. ✅ **[P] Embeddings as float32 BLOBs + cached unit-vector matrix** — dense query/add no longer JSON-parses every scoped embedding; cosine is a dot of two cached unit vectors, ~4× smaller storage. Zero-dep (stdlib `array`, no numpy). *(3bd78ab)*
19. ✅ **[P] Pushed `ORDER BY bm25 LIMIT max(k*10,50)` into SQL** — no more Python-scoring every OR-term match. *(fe11af7)*
20. ✅ **[P] In-process MCP facade** — `ygg.main()` called in-process with captured/separated streams; a lock serializes the redirect (HTTP facade is threaded); `--json` payloads stay parseable. *(e8d9786)*
21. ✅ **[P] Batched reindex** (`/api/embed`, 32/req, per-item fallback) **+ startup warmup/reindex moved off the bind path** (no lazy-spawn port race). *(97c449f)*
22. ✅ **[P] Hot-path micro-fixes** — `record_access` already batched under one transaction; added `(user_id, namespace, created_at)` index for `get_all`. *(fe11af7)* — a dedicated `/status` endpoint for the session hook is deferred (current `get_all` is now indexed; revisit if it shows up hot).
23. ✅ **[C] Embedding model versioning** — per-row `embed_model`; `missing_embeddings`/`reindex` treat a model switch as stale and re-embed. *(3bd78ab)*
24. ✅ **[C] Ranking parity** — pin/usage now cross to the vector-only path via the same lexical channel. Deliberately scoped to the user-earned signals (pin, usage), NOT importance/recency, so the eval corpus is provably unchanged (lexical recall@1 still 0.77) while real pins work on both paths. *(fe11af7)*

> **P2 dense benchmark — verified 2026-07-02 (Ollama):** the blob/cache refactor and ranking-parity change reproduce every published number exactly — lexical recall@1 **0.7714**, `all-minilm` **0.8286**, `paraphrase-multilingual` **0.9429** (recall@3 **1.0**, MRR **0.9714**, crosslingual EN→RU **0.80**). Ranking is unmoved, confirming the parity change (#24) is dense-eval-invariant as designed.
>
> **P2 speed — measured A/B, pre-P2 engine vs new (2026-07-02):** synthetic 384-dim embeddings, median of 5 interleaved rounds, dense `search()` latency per query:
>
> | memories | old (JSON parse/query) | new (blob + cached unit vectors) | speedup | storage |
> | --- | --- | --- | --- | --- |
> | 1,000 | 502 ms | 49 ms | **10×** | ~3.9× smaller |
> | 3,000 | 2,575 ms | 142 ms | **18×** | 3.9× smaller |
> | 6,000 | 8,102 ms | 282 ms | **29×** | 3.9× smaller |
>
> Speedup grows with store size (old is O(N) `json.loads` per query; new is a cached dot product) — at 6k memories, 8.1 s/query → 0.28 s/query. Storage ~3.9× smaller (float32 blob vs JSON-text floats); the recall numbers above confirm this is pure speed/size, no quality change.

## P3 — Benchmark credibility (armor for the 0.94 badge) — ✅ 25 & 27 done; 26 partial (2026-07-02, commit cbe7b14)

25. ✅ **Holdout headline + pool disclosure + full-corpus view.** `eval/ygg_eval.py --report` now leads with **holdout** recall@1 (weights tuned on dev only): **0.93** within a project (pool ~6), **0.80** full-corpus (pool 35, no filter). recall@3 = **1.00 in both views**. Per-query pool sizes (min 2 / median 6 / max 35) and 95% bootstrap CIs are printed. Re-measured on live Ollama; BENCHMARKS.md §1 + README numbers + badge (→ 0.93) + all 6 i18n rewritten to the honest two-view framing. *(cbe7b14)*
26. ◑ **Partial.** Added 95% **bootstrap confidence intervals** (stdlib) and documented the model-digest-pinning caveat. **Not done:** growing the corpus to 200+ from *real* distilled transcripts — genuinely needs the user's own `ygg seed` output; the harness reports n=35 + wide CIs honestly and flags this as a known limitation in BENCHMARKS.md §4. ~L (remaining).
27. ✅ Lexical benchmark **runs in CI** with a recall@1 ≥ 0.77 floor (the badge is now a receipt, not a claim). *(6a246e1, P1)*

## P4 — Features (differentiation-driven, in order of positioning value)

28. **Native-memory bridge** — import from Claude Code's native memory dir (`~/.claude/projects/*/memory/`) and Codex Memories; optionally materialize a curated digest *back* into `MEMORY.md`/`AGENTS.md`. Positions Yggdrasil as *the layer above the natives* instead of their competitor — the natives are structurally repo- and vendor-siloed, and that's strategic, not fixable by them. ~M.
29. **`ygg review` TUI** for the governance queue — curation is the wedge; today it's JSON reports. A 15-minute-to-build `less`-style review loop (approve merge / archive / skip) makes "curated, not captured" tangible. ~M.
30. **Git-backed vault sync** — cross-machine sync through the user's *own* git repo (encrypted optional). Directly counters cmem.ai/mem0 cloud sync without betraying local-first; no server to run. ~L.
31. **Relation graph** (`SOLVES` / `SUPERSEDES` / `CONTRADICTS`) — already on the roadmap; unlocks "why" answers, pairs with the review TUI. ~L.
32. **Linux/Windows GA** — installers exist; finish on-device testing + make `ygg_setup.hw()` read `/proc/meminfo` / `wmic` (today Linux gets model recommendations computed from 0 GB RAM). ~M.
33. **First-hour polish** — port-42069-conflict hint; non-interactive install prints "lexical-only" notice; warn that the `/tmp` tyre-kicking DB is throwaway; document the session-1 dead zone (plugin engine lazy-starts on first *tool call*, so injected memory appears from session 2). ~S each.
34. **Secret-guard hardening** — add AWS `AKIA…`, JWT, `github_pat_`, `glpat-`, connection-string patterns (`ygg.py:34-40`); move the guard engine-side so raw `/add` is covered too. ~S.

## Positioning (decided; already applied to README on 2026-07-01)

- **Wedge:** *cross-tool + cross-project recall that is provably local and provably tiny* — the one position no native feature can take (vendor silos are strategic) and no funded player will take (mem0 $24M, supermemory, cmem.ai all monetize cloud). Supporting theme: *curated decisions, not transcripts* — claude-mem and the natives structurally cannot pivot to curation.
- **Facts corrected** in the comparison: claude-mem = SQLite+FTS5 with *optional* Chroma (not "needs a vector DB"); crypto-token snark removed; mem0 phrased as "hosted-first SDK/platform"; natives added as a first-class column (Claude Code auto-memory: on by default, repo-scoped, grep-only; Codex Memories: off by default, local; Cursor removed native Memories in 2.1).
- **Do NOT build:** auto-capture of everything (contradicts the wedge), a hosted sync service (kills the only defensible moat), competitor benchmark numbers we can't reproduce (BENCHMARKS.md's refusal to fabricate is a trust asset).
- Ecosystem churn worth citing in future marketing: Zep killed its OSS server (2025-04), Cipher/ByteRover went Elastic-2.0 source-available (2026-04), Cursor removed Memories (2.1.x), mcp-memory-service fled GitHub — "boring, durable, yours" is a live nerve.

## Suggested release slicing

- **0.5.5 (patch, this week):** P0 items 1–8 + hygiene 15 + doctor fix. All ≤ a few lines each; ships "the audit release".
- **0.6.0:** CI (9), delete/reset (10), seed quality (12), hooks portability (13), dead code (14), defaults rename (16), benchmark honesty (25, 27).
- **0.7.0:** performance block (18–24), native-memory bridge (28), review TUI (29).
- **0.8.0+:** git sync (30), relation graph (31), Linux/Windows GA (32).
