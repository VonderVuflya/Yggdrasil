# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning is [SemVer](https://semver.org/).

## [Unreleased]

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
