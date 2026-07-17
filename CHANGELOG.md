# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning is [SemVer](https://semver.org/).

## [Unreleased]

### Changed
- **The memory citation now reads `🌳 from memory:` instead of `🌳 recalled:`.**
  `recalled` was `ygg_recall`'s API verb leaking into a line a human reads, and
  it announced what the machine did rather than the thing the reader needs — that
  the claim came from their own memory instead of the agent guessing. It also
  broke the convention every other surface follows (`🌳 Yggdrasil doctor`, `seed`,
  `quality`): the tree carries the brand, plain words carry the meaning. The
  injected prompt copy was trimmed to match, and now has tests — it is the one
  piece of Yggdrasil copy a user reads on every single prompt.

## [0.12.1] — 2026-07-17 — fix: `ygg install` no longer eats your settings

### Fixed
- **The setup wizard overwrote `config.json` instead of merging into it**, so
  re-running `ygg install` — routine when switching models or re-installing —
  silently dropped every setting it doesn't ask about: the pinned
  `user_id`/`namespace` (the identity 0.11.0 migrated *specifically* so a
  default could never strand memory again — losing the pin re-opens that exact
  hole), plus `embed_backend`, `embed_url`, `distill_url` and `sync_repo`.
  Dense search would quietly fall back to localhost Ollama, distillation would
  drift off the box you pointed it at, and memory could end up written under a
  different identity than it was stored with.

  The bug predates 0.12.0 but that release widened the blast radius by adding
  the `embed_backend`/`embed_url` keys it destroys. The wizard now merges and
  touches only the keys it owns; a corrupt `config.json` is rebuilt rather than
  crashing the install.

## [0.12.0] — 2026-07-17 — bring your own engine: llama.cpp, OpenRouter, OpenCode

Yggdrasil stopped assuming Ollama for embeddings and Claude/Codex for agents.
Dense search now runs on anything speaking the OpenAI `/v1/embeddings` dialect
(llama.cpp, OpenRouter, LM Studio, vLLM), OpenCode is auto-registered like the
other hosts, and hosted backends are configured entirely from the CLI. Every
default is unchanged — an existing install upgrades to identical behaviour.

### Added
- **OpenAI-compatible embedding backend.** Dense search can now run against any
  `/v1/embeddings` server — llama.cpp's `llama-server --embeddings`, OpenRouter,
  LM Studio, vLLM — not just Ollama. Set `embed_backend openai` and point
  `embed_url` at the `/v1` base; `YGG_EMBED_API_KEY` (or `OPENROUTER_API_KEY`)
  carries the Bearer token for hosted providers, and a local llama-server needs
  no key. Ollama stays the default; nothing changes for existing installs.
  - Verified end-to-end against a real `llama-server` (bge-small, 384d): a
    paraphrased query with zero shared words retrieved the right memory at rank 1.
  - Verified live against OpenRouter on the 232-memory / 110-query corpus with
    the free `nvidia/llama-nemotron-embed-vl-1b-v2:free` (2048d, $0): recall@1
    **0.946** (CI95 0.900–0.982), crosslingual **1.00** — statistically level
    with the local `paraphrase-multilingual` default (0.964, CI95 0.927–0.991).
    A useful escape hatch for a box that can't run Ollama; the local default
    still wins on privacy, which is the point of the project.
  - `embed_url`/`embed_backend` propagate from `config.json` to the daemon via
    `engine_argv`, so a service install honors them without a manual env export.
- **`ygg config set embed_api_key <key>`** — the hosted backend is configured
  entirely through the CLI; no env export required. The secret is kept out of
  `config.json` (0644, and it lands in backups and dotfile repos) and written to
  `~/.yggdrasil/embed_api_key` at 0600. The daemon is handed the *path*, not the
  value — so the key stays out of `ps`, the launchd plist and the systemd unit,
  the same treatment the auth token already gets. `ygg config list` masks it;
  `ygg config get` still prints it in full for scripts, as `gh auth token` does.
  `YGG_EMBED_API_KEY` / `OPENROUTER_API_KEY` still win over the stored file.
  - Verified end to end: a daemon configured *only* via `ygg config set` embeds
    through OpenRouter (`/health` → `dense: active (…nemotron…)`), answers a
    paraphrased query with no shared words at rank 1, and shows no key in `ps`.
- **OpenCode is auto-registered.** `ygg install` detects the `opencode` binary
  and writes the MCP entry itself, merging into any existing `opencode.json`
  behind a `.ygg.bak` backup; invalid JSON is left alone, and `ygg uninstall`
  removes only our key. It always *worked* (OpenCode speaks MCP) but demanded a
  hand-written config whose schema differs from Claude's in four places at once
  — `mcp` vs `mcpServers`, mandatory `type`, `command` as one array, and
  `environment` vs `env` — so the obvious copy-paste produced four silent
  errors. Verified against a real install: `opencode mcp list` reports
  `✓ yggdrasil connected` with all 6 `ygg_*` tools exposed.

### Docs
- README (and all six translations) now cover connecting to llama.cpp,
  OpenRouter and OpenCode, including the two OpenRouter account settings that
  break embeddings for reasons the error messages actively obscure: a
  provisioning key returns `401 User not found` on inference, and a privacy
  filter hides most models behind `404 All providers have been ignored`. Also
  documented: `GET /api/v1/models` returns `200` for any key, valid or not, so
  it cannot be used to check one — `GET /api/v1/key` can.
- Recorded what the benchmark actually showed: vector size buys nothing here
  (`mxbai-embed-large` 1024d → recall@1 0.809, `nomic-embed-text` 768d → 0.818,
  `bge-small` 384d → 0.818 — all within each other's confidence intervals).
  Language coverage is what moves the number: those English-only models fall to
  0.40–0.45 on cross-language queries where the multilingual default holds 0.95.

## [0.11.0] — 2026-07-15 — identity migration + dense-search fixes (BREAKING)

Retire the demo-heritage identity so real memory no longer lives under a
throwaway "demo" name (roadmap #16), and fix dense search against remote /
proxied Ollama endpoints.

### Changed (BREAKING)
- **Default identity is now `local` / `personal`** (was `demo-user` /
  `yggdrasil-demo`). On the first engine start after upgrade, existing memory is
  **auto-migrated once** — a version-guarded (`PRAGMA user_version`) SQL relabel
  that only touches the exact legacy demo pair, so a custom identity is never
  moved. A timestamped `*.pre-identity-v1.*.bak` backup is written first, and the
  resolved identity is pinned explicitly into `config.json` so **no future
  default change can ever strand memory again**. FTS is untouched (it indexes
  content, not identity).
- **⚠ `ygg sync` users: upgrade every synced machine together.** The sync key
  format changes with the identity; a lagging demo-keyed peer is auto-adopted to
  the default on import, but mixed versions briefly diverge.

### Added
- **`ygg migrate [--dry-run]`** — preview or run the identity migration manually
  (backup-first), for when the daemon isn't the one you want to drive it.
- Identity now resolves through a single source of truth (`ygg_config.user_id()`
  / `namespace()`); ~15 hardcoded `demo-user` fallbacks were routed through it, so
  the default can no longer diverge across the codebase. The demo/eval gates pin
  the demo identity explicitly via `ygg_config.DEMO_*` constants.

### Fixed
- **Dense search silently degraded to lexical against remote / proxied Ollama.**
  Three independent causes, all fixed: the embedder only called the legacy
  `/api/embeddings` (now falls back to the newer `/api/embed` that some builds and
  hosted proxies serve instead); it sent no `User-Agent`, so the Cloudflare proxy
  in front of `*.proxy.runpod.net` 403'd every request (now identifies as a
  product string, like `ygg seed` already did); and a dropped request left a
  memory permanently unembedded (now retries transient failures with backoff).

### Benchmark
- Grew the retrieval eval corpus from 35 to **232 memories / 110 labelled queries**
  (docs/TODO #26) for statistical power — the candidate pool per query roughly
  doubles and the recall CIs tighten. `ygg_eval.py` now seeds+embeds the corpus
  once (not 6×), shows a progress heartbeat, prints per-query-class recall, and
  warns loudly if a requested embedding model produced no vectors.

### Cleanup
- Dedup the copy-pasted `YGG_ENGINE_TOKEN or YGG_ENGINE_TOKEN` env lookup in four
  gates; drop stale "MVP" wording and `engine.s`→`engine's` typos (roadmap #14/#17).

## [0.10.0] — 2026-07-15

Honest hardware, multilingual-safe models, no truncated stubs, memory-quality
report (docs/TODO §1/§3/§5/§6).

### Added
- **`ygg quality` — a store health report.** Type/project distribution, exact
  duplicate pairs (content-hash), near-duplicate pairs (cosine ≥ threshold,
  default 0.95), cross-project leakage, and likely-truncated records (reuses the
  write-path truncation heuristic). Computed server-side (`/quality`) so
  embeddings never leave the engine; `--json` for scripting. Closes docs/TODO §6.

### Added
- **Hardware-aware acceleration tier + GPU warning (`ygg recommend` / `hw`).**
  `hw()` now classifies inference as `cpu` / `metal` / `cuda` / `rocm/vulkan` and,
  crucially, warns when a GPU is present but **won't** accelerate inference — the
  Intel-Mac + AMD case, where macOS is Metal-only (Apple-Silicon oriented) and
  ROCm doesn't exist, so stock inference runs on CPU regardless of the card. The
  catalog surfaces the warning up top instead of silently running on CPU.
- **Language-aware model catalog.** Every model now carries a language/thinking
  tag (`EN/RU/ZH · non-thinking`, `⚠ NO Russian/Chinese`, …). Added the Qwen
  upgrades `qwen2.5:3b`, `qwen3:4b-instruct-2507`, and `gemma3:4b`. If the local
  store is dominantly Russian/Chinese, `recommend` prints a steer away from
  English-only models.

### Changed
- **The recommended quality upgrade is now `qwen2.5:3b`, not `llama3.2:3b`** —
  Llama 3.2 officially supports English + 7 European languages only, silently
  degrading non-English memory. Llama stays in the catalog, clearly flagged.

### Fixed
- **Truncated lessons are dropped, not persisted.** A distilled lesson whose text
  ends mid-thought (trailing `:` / dangling connector / unbalanced bracket or
  quote — e.g. a list intro whose items never arrived) is now discarded at the
  write path and counted separately, instead of being stored as a stub. Length
  is deliberately not a signal (lessons are meant to be short).

## [0.9.1] — 2026-07-04

### Fixed
- **`ygg seed` crashed at import on Python 3.10/3.11** — the 0.8.0 seed summary
  used a multi-line f-string replacement field (PEP 701, python 3.12+ only), so
  the module didn't even parse on older interpreters. 0.8.0 and 0.9.0 on PyPI
  are affected; upgrade.
- The release pipeline now syntax-checks the package on the oldest supported
  Python (3.10 via uv) before publishing, so a 3.12-only construct can't ship
  again.

## [0.9.0] — 2026-07-04

One memory across your machines, and a store that answers "why".

### Added
- **`ygg sync --repo <your-git-repo>` — cross-machine memory sync through a repo
  YOU own** (GitHub private, Gitea, even a bare repo on a USB stick). The store
  travels as one byte-deterministic JSON file per memory plus a `relations.jsonl`
  (git union-merge driver); no relay, no account, no cloud in the loop. One
  command converges both machines: export → commit → pull → import with a
  deterministic merge policy (archive-anywhere-holds-everywhere, longer content
  wins, confidence max, pinned OR) → re-export → push. Counters and vectors stay
  per-machine by design.
- **Relation graph — memories can SOLVE, SUPERSEDE, or CONTRADICT each other.**
  Typed, idempotent edges answer *why* a memory exists and what replaced it:
  `ygg remember --solves/--supersedes/--contradicts` links at write time (also
  exposed on the `ygg_remember` MCP tool, so an agent saving a fix can close the
  follow-up it resolves); `ygg supersede --by` records the replacement;
  `ygg review` dup consolidation now leaves SUPERSEDES edges instead of bare
  archives. Inspect with `ygg relations --id` (both directions, with previews).
- **`ygg seed --schedule HH:MM` — nightly auto-distill.** Installs a
  calendar-fired LaunchAgent that distills what changed since the last run and
  exits; `off` removes it, `status` reports. Incremental state + dedup keep the
  nightly run cheap; a dead Ollama just means those files retry the next night.

### Fixed
- **Python 3.10 crash in `ygg review` / reports / `materialize`** — the code used
  `datetime.UTC`, an alias that only exists on Python 3.11+. 0.8.0 on PyPI is
  affected on 3.10; upgrade.
- **Windows: explicit UTF-8 everywhere.** Text IO carrying memory content relied
  on the locale encoding (cp1252), which crashed `ygg export-native` on the 🌳 in
  the managed block; Codex session routing compared against `str(path)` and never
  matched Windows backslash paths (`as_posix()` now).
- The release pipeline itself: publishing from a detached HEAD (e.g. a checked-out
  tag) no longer fails with "not a full refname" — pushes name the target branch.

## [0.8.0] — 2026-07-03

Migrate in, and a CLI you can actually read.

### Added
- **`ygg import` — one-command migration FROM another memory tool.** Point it at
  another tool's local store and pull everything into Yggdrasil (deduped,
  secret-guarded), then delete the old tool. Adapters: `--from mcp-memory`
  (the reference MCP memory server, `@modelcontextprotocol/server-memory` — the
  most-installed memory MCP; entities become memories with their relations folded
  in) and `--from basic-memory` (Basic Memory's Markdown notes, verbatim). An
  adapter registry makes more tools drop-in; `--dry-run` previews; imports are
  tagged so a whole migration rolls back with `ygg reset --source import:<tool>`.
- **A visual CLI** (new `ygg_ui` module, zero-dependency ANSI). `ygg search` /
  `ygg recall` render content-first with colour-coded type badges, a `▰▰▰▱▱`
  relevance bar and relative time instead of a `score=… src=… conf=…` wall;
  `ygg doctor` shows green ✓ / red ✗ marks with the engine version + round-trip
  latency; `ygg stats` draws histogram bars. Colour turns on ONLY for a real TTY
  — piped / agent / MCP-facade / gate output stays byte-for-byte identical, and
  `--json` is untouched.
- **A readable `ygg seed` preamble.** The old wall of one-line-per-source (50+
  rows with full paths) is replaced by a coverage meter (`██████░░ 54% · 273 / 506
  files`) and a *busiest sources* mini-histogram, so it's obvious how much is left
  and where the work is — regardless of whether you have 5 sources or 150. The
  full per-source list with paths moves behind `ygg seed --verbose`. Also
  clarifies the input/output gap ("one chat → several lessons") that made the
  file counts confusing.

## [0.7.1] — 2026-07-03

Seeding hardening — found and fixed on a live multi-hour `ygg seed` run.

### Added
- **Distill on any LAN box or phone.** `--ollama-url` now speaks three dialects
  — Ollama `/api/generate`, Ollama `/api/chat`, and OpenAI `/v1/chat/completions`
  (auto-probed, working combo cached) — so LM Studio, llama.cpp-server, exo, and
  on-device iPhone LLM-server apps all work as distill endpoints, not just Ollama.
- **iCloud Obsidian vaults are discovered** (`~/Library/Mobile Documents/iCloud~md~obsidian/Documents`)
  — for many users that's THE vault, and it was silently invisible before. The
  per-vault note cap is now 500 most-recent (was 50 alphabetical, which dropped an
  arbitrary A–G slice of larger vaults).

### Fixed
- **Distilled lessons keep the source language.** A small model (qwen2.5:3b) would
  randomly translate Russian logs into Chinese; the target language is now named
  explicitly for Cyrillic-dominant logs. Affects every endpoint, not just phones.
- **A flaky lesson no longer loses a whole file.** Malformed model JSON (missing
  comma, truncated tail, empty) is salvaged object-by-object and retried once;
  only truly-unparseable output errors out (and is retried on the next run).
- **A dead distill peer is caught in ~90 s, not the full timeout.** Streaming with
  an idle window (`YGG_DISTILL_IDLE`, default 90 s) means a phone that locks or a
  Wi-Fi drop no longer hangs a request for the whole `distill_timeout`; servers
  that don't stream fall back to a non-streaming call capped at the idle window.
- **`ygg seed` output is readable.** Only projects where something happened are
  logged (`✓ demo +1 lessons`); all-unchanged projects collapse into one summary
  line instead of a wall of `+0 new … unchanged` rows. Non-TTY/agent output is
  unchanged (byte-stable).

## [0.7.0] — 2026-07-03

Performance, benchmark honesty, and the native-memory bridge.

### Performance
- **Embeddings stored as packed float32 blobs** (~3.9× smaller than JSON text) with an
  **in-process cache of unit-normalized vectors** — dense search/dedup no longer
  `json.loads` every scoped embedding per query; cosine is a dot of two cached unit
  vectors. Measured A/B vs the previous engine: dense `search()` **10–29× faster** and
  the speedup grows with store size (at 6k memories, 8.1 s/query → 0.28 s). Still
  zero-dependency (stdlib `array`, no numpy).
- **Lexical search pushes `ORDER BY bm25 LIMIT` into SQLite** instead of Python-scoring
  every term match.
- **Batched reindex** via Ollama `/api/embed` (32/req, per-item fallback) and **startup
  warmup/reindex moved off the bind path** (no lazy-spawn port race).
- **MCP tool calls run in-process** instead of a `python ygg.py` subprocess per call,
  with stdout/stderr separated so `--json` stays parseable.
- Index on `(user_id, namespace, created_at)` for the session-start hook's `get_all`.

### Changed
- **Embedding model is versioned per row.** Switching `YGG_EMBED_MODEL` marks old vectors
  stale and reindexes them, instead of comparing vectors across models. `ygg doctor`
  counts model-mismatched rows.
- **Benchmark reporting is credibility-first.** `eval/ygg_eval.py --report` leads with
  **holdout** recall@1 (weights tuned on dev only): 0.93 within a project, 0.80 full-corpus,
  recall@3 = 1.00 in both. Discloses candidate pool sizes (min 2 / median 6 / max 35) and
  95% bootstrap CIs. README badge → holdout 0.93; BENCHMARKS.md + all 6 translations
  rewritten to the honest two-view framing.

### Added
- **`ygg export-native --project P`** — the native-memory bridge: writes a curated,
  type-grouped digest of a project's memory into a managed block in `AGENTS.md`/`MEMORY.md`
  (idempotent; preserves hand-written content). Pairs with `ygg seed` (which imports *from*
  the native memory) so Yggdrasil is the layer above Claude Code's and Codex's own memory,
  feeding them both ways.
- **`ygg review [--apply]`** — work the governance queue from the CLI: consolidate exact/
  near duplicates (keep the oldest, archive the rest) and surface stale/conflict markers.
  Interactive on a TTY; `--apply --yes` auto-consolidates duplicates and flags stale markers
  for manual review. Everything is archived (reversible), never hard-deleted.
- **Ranking parity** — a pinned or frequently-recalled memory retrieved only by vector now
  gets its pin/usage boost, via the same channel lexical hits use.

### Security
- **Engine-side secret guard** — a raw `POST /add` bypassing the CLI now also refuses obvious
  credentials (AWS keys, JWTs, GitHub/GitLab PATs, private keys, connection-string passwords).
  High-confidence structured tokens only, so memories that merely mention "password"/"secret"
  are unaffected.

### Fixed
- **Cross-platform `hw()`** — Linux `/proc/meminfo` + `/proc/cpuinfo` (+ nvidia-smi), Windows
  PowerShell CIM; the model recommender no longer sizes off 0 GB off-macOS.
- **First-hour polish** — actionable port-conflict hint instead of a traceback; non-interactive
  install announces the lexical-only fallback.

## [0.6.0] — 2026-07-03

Robustness, DX and CI — the second slice of the audit plan.

### Added
- **CI** (GitHub Actions): unit tests on ubuntu/macos/windows (py3.10 + 3.13),
  behavioural gates on ubuntu/macos, and a benchmark job that fails the build if
  lexical recall@1 regresses below 0.77 — the badge becomes a receipt.
- **`ygg delete --id` and `ygg reset --project|--source|--type|--all`** — recover from a
  bad `ygg seed` without sqlite surgery. `reset` previews the count and demands typed
  confirmation (or `--yes`). The engine's `/delete` + `/purge` are the only destructive
  endpoints and are deliberately **not** exposed as MCP tools.
- **`GET /get?id=`** — direct indexed lookup; `ygg materialize` now works at any store
  size (the old scan couldn't reach memories past the first 1000).
- **`distill_num_ctx` setting** (default 8192) — seed distillation sends `options.num_ctx`
  explicitly instead of inheriting Ollama's default (often 4096, which silently truncated
  long transcripts); output cut off by the token limit is rejected, not persisted.

### Fixed
- **Hooks work on Windows** (`python3 … || python …` launcher) and **context is never
  injected twice** when both the plugin and `ygg hooks` are enabled (atomic per-session /
  per-prompt locks; registration dedupe by script name).
- **`ygg bootstrap` used legacy type names** absent from the canonical enum — typed
  memories got no ranking boost.
- Deleted dead code (`materialize_memory.py` twin, dead `engine_token()`, duplicated
  gate env lookup); docstrings caught up with the `service.py` rewrite.
- **Gates run on a dedicated port** (42169) instead of sharing the daemon's 42069 — the
  runner used to kill the user's daemon and race its restart (flaky `SEED FAILED`).

## [0.5.5] — 2026-07-03

The audit release — security & correctness fixes from a full technical audit,
no behaviour changes for the happy path.

### Fixed
- **Lexical search now works for non-Latin text** (Cyrillic, Greek, CJK …). The
  query tokenizer was ASCII-only while the FTS index used `unicode61`, so e.g. a
  Russian query matched nothing in lexical mode. Also splits `snake_case`.
- **Engine writes are transactional** — an exception mid-write no longer leaves an
  open transaction that the next request silently commits (which produced memories
  invisible to lexical search). Row + FTS commit or roll back together.
- **Malformed client input returns a JSON 400** instead of a traceback and a dropped
  connection (`limit="abc"`, `importance:"high"`, …).
- **Editing a memory refreshes its `content_hash`** — a stale hash corrupted dedup
  both ways.
- **`ygg doctor` no longer prints "All good." with no MCP registration** anywhere.

### Security
- **No `yggdrasil-demo-token` fallback in the engine** — a bare `ygg serve` reuses or
  generates the 0600 `~/.yggdrasil/token` instead of a publicly-known constant.
- **The Streamable-HTTP MCP facade refuses to start without a token** (`YGG_MCP_INSECURE=1`
  opts into open mode for local testing).
- **`ygg_materialize` output confined to the vault root** — a remote MCP client could
  previously write attacker-seeded `.md` anywhere the user can write.
- **Auth token no longer written in plaintext** into launchd plists, MCP registrations,
  or `~/.claude.json` — everything resolves the 0600 token file at call time.
- **Timing-safe token comparison** (`hmac.compare_digest`) + a **Host-header check** on
  loopback binds (blocks DNS-rebinding drive-bys).

### Changed
- Untracked the `.mcpb` desktop bundles (hosted on GitHub Releases); ignore
  `.cache/`, `.claude/`, `scratchpad/`.

## [0.5.4] — 2026-06-29

### Changed
- **Relicensed from Elastic-2.0 to GNU AGPL-3.0-or-later.** Elastic-2.0 is not an
  OSI/SPDX-recognized license, so GitHub (and tools that key off its detection, like
  Glama) could never identify it — it showed as "Other/NOASSERTION". AGPL-3.0 is
  OSI-approved and auto-detected, and its network copyleft keeps the original intent:
  Yggdrasil stays free to use, modify, self-host, and redistribute, but anyone who
  modifies it or offers it as a hosted/network service must release their source
  under the same license.

## [0.5.3] — 2026-06-28

> 🎉 **Yggdrasil is now listed on [glama.ai](https://glama.ai/mcp/servers/VonderVuflya/Yggdrasil)!**
> The MCP server is indexed, builds and passes introspection, and scores **tier A** on
> Glama's Tool Definition Quality Score. Most of this release is the work that got us there.

### Changed
- **MCP tool definitions tuned to the TDQS rubric** (Glama's Tool Definition Quality
  Score) — every tool now has: a tight, front-loaded description that states purpose +
  scope and **names its sibling tools** for disambiguation (recall = all projects,
  bootstrap = load one project, search = query one project); explicit when/when-not
  guidance; **MCP annotations** (`readOnlyHint`/`destructiveHint`/`idempotentHint`/
  `openWorldHint`) carrying the behavioral profile; a meaningful `title`; 100%
  per-parameter description coverage; and an **enum on `type`** (the canonical memory
  categories — also curbs type drift). Estimated per-tool TDQS ~4.3–4.5 (tier A),
  up from C.

### Fixed
- **MCP `serverInfo`** reported a stale dev identity (`yggdrasil-mvp` / hardcoded
  `0.1.0`) to every host — now reports `yggdrasil` and the real installed version
  (read from package metadata). Surfaced by Glama showing the server as `0.1.0`.

### Added
- **Dockerfile** — lets Glama and any container host build, start and introspect the
  MCP server (the stdio facade answers `initialize`/`tools/list` cold, no engine
  needed), so directory listings that gate on a Glama check pass.
- **`glama.json`** + full canonical **Elastic-2.0 LICENSE text** (was a one-line
  pointer GitHub read as `NOASSERTION`) so the license is detected and the server
  is installable from directory listings.
- **Per-prompt auto-recall hook** (`UserPromptSubmit`) — the fix for "the agent
  forgets to use the memory". On every request it runs a cross-project recall and
  injects the top genuinely-relevant matches (raw-cosine gate, so off-topic
  prompts inject nothing), and asks the agent to cite what it reused inline as
  `🌳 recalled: …` — the visible breadcrumb that makes the tool's work trustworthy.
  `ygg hooks` now installs both retrieval hooks (SessionStart bootstrap + this).

## [0.5.2] — 2026-06-28

### Added
- **Proper settings: `--flags` + `ygg config` (no more `VAR=… ygg seed`).** Every
  setting now resolves by a single rule — **flag > env var > `config.json` >
  default**. `ygg config list|get|set|unset` manages the persistent layer;
  `ygg seed`/`distill`/consolidation take `--ollama-url` and `--timeout` for
  one-off runs. The distillation endpoint (`distill_url`) is deliberately separate
  from the daemon's embedding endpoint (`embed_url`), so you can point heavy
  distillation at a beefier LAN box without dragging embeddings off-machine.
- **Distill timeout is configurable + self-explaining.** The per-file limit is now
  `YGG_DISTILL_TIMEOUT` (default 120s). When files time out, `ygg seed` explains
  they're *large, not stuck*, and prints a copy-paste re-run command with a higher
  limit (preserving the `YGG_EMBED_URL`/`--model` you used). Timed-out files are no
  longer marked done, so a plain re-run retries **only** them — while deterministic
  errors (bad model output) still get marked done so they don't loop forever.
- **`ygg seed` now also distills Codex CLI sessions** (`~/.codex/sessions/rollout-*.jsonl`),
  not just Claude Code transcripts. Sessions are grouped by their working directory
  so Codex lessons merge into the same per-project buckets as Claude's. The Codex
  rollout format (nested `response_item` → message → content list) gets its own
  extractor that keeps user+assistant turns and drops `developer` / AGENTS.md /
  environment-context boilerplate. Incremental seed + dedup apply as usual.

## [0.5.1] — 2026-06-27

### Fixed
- `ygg update` (and the update nudge) could miss a freshly-published release until
  a **second** run: PyPI's JSON API is CDN-cached and briefly serves the previous
  version right after a publish. The version check now cache-busts it (a unique
  query param + `no-cache` headers), so a new release is seen on the first try.

### Changed
- `release.sh`: the **npm** publish step is now auth-aware — it runs `npm login`
  when not authenticated instead of failing silently (mirrors the MCP step).

## [0.5.0] — 2026-06-27

### Changed
- **`ygg search --project X` now matches the project across scopes** — memories
  saved `--scope global` but tagged to a project are found here too (previously
  only `ygg recall` surfaced them). An empty project search now hints at `ygg
  recall`. This is a retrieval behavior change, hence the minor bump.

### Added
- **Recall fallbacks (no more empty-handed):** a one-word / all-stopword query no
  longer short-circuits to `[]` when dense is on, and when nothing clears the
  similarity cutoff the search returns the nearest memories by cosine (flagged
  `~nearest`). Helps paraphrase / cross-lingual / single-word lookups. The recall
  eval is unchanged (no regression; dense recall@3 = 1.0 across classes).
- **Update nudge** (like context-mode) — when a newer version is published,
  `ygg` commands and the agent's first MCP tool call show `⬆ Yggdrasil X is
  available (you have Y). Upgrade: ygg update`. The long-lived engine refreshes a
  cached check (`~/.yggdrasil/update-check.json`, TTL `YGG_UPDATE_CHECK_TTL`,
  12h); the CLI and MCP facade only READ the cache, so nothing ever blocks on the
  network.
- **Semantic dedup** — when dense (an embedding model) is on, a write that is
  near-identical (cosine ≥ `YGG_SEMDEDUP_AT`, default 0.92) to an existing memory
  in the same project+type is skipped (`YGG_SEMANTIC_DUPLICATE_SKIP`). Catches
  near-dupes that exact content-hash misses — e.g. the local model re-wording the
  same lesson across seed runs. Reuses the single add-time embedding (no extra
  cost); lexical-only setups are unaffected.
- `ygg doctor` is now **actionable**: a missing MCP registration prints
  `→ fix: ygg register`, and when no host has the tools it shows the plugin-install
  commands. New **`ygg register`** (re)registers the MCP server with Claude Code /
  Codex, or prints a ready-to-paste `~/.claude.json` entry for the binary-less
  VSCode/Cursor case.
- **`ygg reindex`** + a `ygg doctor` check: when dense is on but some memories
  have no embedding (so dense recall silently misses them), doctor flags the count
  (`→ fix: ygg reindex`) and `ygg reindex` backfills them. `/health` now reports
  `embeddings_missing`.

### Security
- The engine auth token is no longer passed as a command-line argument — it was
  visible in `ps` output and the launchd plist. The service now points the engine
  at the 0600 token file via `--token-file`; the secret never leaves the file.

## [0.4.3] — 2026-06-27

### Added
- **Colorful animated `ygg seed`** — a live progress line (spinner + bar + %, the
  current session/file, done/total, lessons added, elapsed and a live ETA), with
  completed sources scrolling above it. Ctrl-C stops cleanly and still prints the
  run summary (files distilled, lessons added, elapsed, throughput, DB size).
  Pure stdlib (ANSI); falls back to plain lines on a non-TTY or with `NO_COLOR`.

### Fixed
- `ygg update` on Homebrew ran a bare `brew upgrade yggdrasil`, which brew
  mis-resolves as a cask (`Cask 'yggdrasil' is not installed`); now tap-qualified
  (`VonderVuflya/tap/yggdrasil`).

### Changed
- `release.sh`: auto-pushes the brew formula to the tap via the GitHub API (no
  `YGG_TAP_DIR` needed) so the tap can't go stale, and `mcp-publisher publish`
  auto-runs `mcp-publisher login github` on a missing/expired token, then retries.

## [0.4.2] — 2026-06-27

### Added
- **Incremental `ygg seed`** — a per-file state (`~/.yggdrasil/seed-state.json`,
  keyed by path + mtime + size) means a re-run only distills NEW or EDITED chats;
  unchanged transcripts are skipped. A chat you kept talking in is re-distilled
  (its mtime/size changed). The estimate shows how many files are skipped, and
  `--force` redoes everything. No more re-grinding every transcript each run.
- **Scale hint** — once an embedding model is active and the store passes ~20k
  memories (`YGG_VECTOR_WARN_AT`), `/health` / `ygg doctor` / `ygg stats` /
  `ygg seed` warn that the built-in in-Python vector search will slow down and
  suggest pointing `YGG_ENGINE_URL` at a dedicated vector backend (e.g. Qdrant).
  Lexical-only setups are unaffected (FTS5 is indexed and scales).

### Changed
- **Dedup is now indexed and unbounded.** `find_existing_hash` uses a new indexed
  `GET /find_hash` (O(log n) over `(user, project, type, content_hash)`) instead
  of fetching up to 1000 rows and scanning each write — removing both the
  per-write O(store) cost and the silent dedup break past 1000 memories. Falls
  back to the old scan on older engines.

## [0.4.1] — 2026-06-27

### Added
- **Proactive memory** — the agent recalls and remembers without being asked:
  - The SessionStart hook now injects an always-on directive (recall before
    non-trivial work; remember durable decisions/lessons/gotchas after), turning
    the advisory skill into a forcing function.
  - The Claude Code / Codex / Cursor **plugin now ships that SessionStart hook**
    (`hooks/hooks.json`), so plugin-only installs also get auto-injected memory —
    not just `ygg install` users.
  - Slash commands `/ygg-recall`, `/ygg-remember`, `/ygg-health` (`commands/`) for
    explicit, discoverable control.

### Fixed
- **`ygg seed` no longer crashes** mid-run when the local distill model returns a
  loose shape. It now accepts `{"lessons":[…]}`, a bare list, a single object, or
  list items that are plain strings (the crash was `'str' object has no attribute
  'get'`). One bad item / file / source can no longer abort the whole seed.

### Changed
- Plugin manifests use the spec array form `"skills": ["./skills/yggdrasil-memory"]`.
- The uploadable skill zip is now built at release time (removed from git, gitignored).

## [0.4.0] — 2026-06-24

### Added
- **Cold-start onboarding** — `ygg seed` (autodiscovers Claude Code transcripts,
  Obsidian vaults, and repos with `CLAUDE.md`, prints a cost/time estimate, then
  distills locally), `ygg distill --source` (raw transcript → atomic, deduped
  lessons with provenance via the local Ollama model — free, nothing leaves the
  machine), and `ygg stats` (memory overview by project × type × scope).
- **Stop hook** (`ygg stophooks`, or the wizard's "autosave") — distills each
  finished session into 0-N durable lessons in a detached process, so session
  end is never delayed. The opt-in, curated alternative to capturing everything.
- **Streamable-HTTP MCP facade** (`ygg mcp-http`) — exposes the same tools over
  the MCP Streamable HTTP transport for remote/cross-surface clients (bearer
  auth). Foundation for connecting claude.ai web/mobile — see
  [docs/cross-surface.md](docs/cross-surface.md).

### Fixed
- CLI memory commands no longer fail with **401** — the token is read from
  `~/.yggdrasil/token` (and `YGG_TOKEN`) by default, like `ygg doctor` and the
  hook already did; a 401 now prints a fix hint.
- **MCP registers without a `claude`/`codex` binary** on PATH — writes the stdio
  server straight into `~/.claude.json` (merged + backed up) for Claude Code as a
  VSCode/Cursor extension; install prints ready-to-paste JSON if nothing matched
  (was a silent skip).
- Install **warns loudly** when models were selected but Ollama is missing or a
  pull fails (no more silent lexical fallback); `ygg install` ends with
  `ygg doctor`.
- `/health` now reports `storage` / `dense: active(model)|inactive` /
  `reranker: disabled (not configured)` instead of a confusing `fts5` + `inactive`.
- `config.json` no longer drops the wizard's `features` block on install.

### Changed
- **Unified memory identity** — the SessionStart hook, CLI, importer and
  write-path now share the MCP agent's `yggdrasil-demo` / `demo-user` identity
  (they had drifted into three separate silos), so hook injection, agent
  recall/remember, the CLI, and seed all read and write **one** store.
- README: **claude-mem** added to the comparison matrix (all 7 languages); a
  Claude Desktop `.mcpb` + skill connect section; dynamic release/PyPI badges.

## [0.3.0] — 2026-06-19

### Added
- **Usage-weighted ranking** — memories recalled more often rank higher. The
  HTTP `/search` route now logs access (`access_count` + `last_accessed_at`);
  ranking adds a saturating usage boost (`access/(access+scale)`, weight
  `YGG_W_USAGE`, default 0.3) alongside the existing recency boost. `search()`
  itself stays side-effect-free, so the eval harness stays deterministic —
  recall@k is unchanged on cold data (verified: lexical recall@1 = 0.625,
  keyword/identifier 1.0, matching baseline).
- **Pinned memories** — `ygg pin <id>` / `ygg unpin <id>` mark a memory as
  important; it gets a strong fixed ranking boost (`YGG_W_PIN`, default 0.5) so
  it reliably surfaces. Stored in metadata (no schema change).
- **Provenance in recall output** — `search` / `recall` now show each hit's
  source, confidence, usage count and a 📌 for pinned memories, so you can see
  where a memory came from and how trusted it is at a glance.
- **In-agent conflict review** — writing a memory now surfaces lexically-similar
  existing memories of the same project+type (to stderr, so agents see it
  through the MCP facade), so duplicates/contradictions show up in the moment;
  `ygg supersede --id <id>` non-destructively archives the outdated one.
- **Tags** — `ygg remember --tag x --tag y` attaches tags; `ygg search --tag x`
  filters to memories carrying that tag (SQLite `json_each`); tags show in the
  recall output.
- **Eval harness expanded** to 35 labelled cases (keyword / identifier /
  paraphrase / crosslingual) across a **dev/holdout split** — the foundation for
  retrieval self-tuning. Measured on the new set: lexical recall@1 0.77, dense
  `paraphrase-multilingual` recall@1 0.94 / recall@3 1.0.
- **Retrieval self-tuning** (`eval/ygg_tune.py`) — an autoresearch-style loop:
  sweep fusion weights on the eval **dev** split, validate the winner on
  **holdout**, then *propose* `YGG_FUSION_*` settings (never auto-applies;
  propose-safe). Embeddings are cached across configs. First run confirmed the
  current defaults are already optimal (dev recall@1 0.95) — no overfit.

## [0.2.1] — 2026-06-19

Maintenance release: republish so the PyPI package README carries the correctly
cased `mcp-name: io.github.VonderVuflya/yggdrasil` marker required by the MCP
Registry for PyPI ownership validation. No functional changes vs 0.2.0.

## [0.2.0] — 2026-06-19

### Changed
- **Engine env vars renamed** `YGG_MUNINN_URL` / `YGG_MUNINN_TOKEN` →
  `YGG_ENGINE_URL` / `YGG_ENGINE_TOKEN`; every third-party "Muninn" reference
  removed from code, docs and translations. Re-run `ygg install` to adopt the
  new names.

### Added
- **Cross-platform service** — one Python lifecycle (`yggdrasil/service.py`) for
  macOS (launchd), Linux (systemd --user) and Windows (Task Scheduler), plus a
  universal **lazy-spawn** fallback so the engine starts on demand even with no
  service manager. `ygg ensure` triggers it; `ygg mcp` lazy-spawns on connect.
- **autoresearch integration** (`integrations/autoresearch/`) — a memory block so
  a [karpathy/autoresearch](https://github.com/karpathy/autoresearch) agent
  recalls past experiments and remembers each result across nights/forks.
- **MCP Registry** — `server.json` (schema 2025-12-11) + `mcp-name` marker for
  publishing to registry.modelcontextprotocol.io.
- Expanded README comparison (Context7 / autoresearch / context-mode): the
  durable cross-session memory layer they all plug into.

## [0.1.0] — 2026-06-18

First public release. An alpha but honest one: the happy path and the full
governance loop are covered by passing gates (`scripts/run_gates.sh`).

### Added
- **Own memory engine** — stdlib-only HTTP server over SQLite + FTS5, zero
  dependencies (~21 MB RAM), behind a swappable `MemoryBackend` contract.
- **Agent integration** — MCP facade (`ygg_health`, `ygg_bootstrap`,
  `ygg_search`, `ygg_recall`, `ygg_remember`, `ygg_materialize`) + CLI (`ygg.py`).
- **Hybrid retrieval** — BM25 + optional local dense embeddings (via Ollama),
  cross-lingual (EN↔RU), score-normalized fusion.
- **Cross-project recall** + a proactive "you solved this before" contract.
- **Always-on service** — launchd daemon (auto-start, auto-restart) + an
  interactive installer with hardware-aware model recommendations.
- **SessionStart hook** — injects identity/persona, project memory, and open
  follow-ups/status into every session.
- **Background smart write-path** — a small local model finds semantic
  duplicates/contradictions the lexical layer misses (propose-safe by default).
- **Governance loop** — review queue + non-destructive archive / merge /
  verify-or-archive actions.
- **Obsidian materialization** + a Claude-memory importer.
- **Eval harness** (recall@k / MRR by query class) + 4 integration gates +
  engine unit tests.
- **Docs** — README in English / Русский / 简体中文 / Español / Français.
- **License** — Elastic License 2.0 (source-available: free to use, modify,
  self-host, and redistribute; no resale as a product and no offering it to
  others as a hosted/managed service).

### Notes
- The engine is swappable: any REST service satisfying the `MemoryBackend`
  contract is a drop-in (point `YGG_ENGINE_URL` at it). Yggdrasil ships its own.
- Auto-applying background consolidation is opt-in; the safe default only
  proposes (a small local model can mislabel distinct-but-similar lessons).
