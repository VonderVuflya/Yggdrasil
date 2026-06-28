# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning is [SemVer](https://semver.org/).

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
