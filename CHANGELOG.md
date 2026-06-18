# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning is [SemVer](https://semver.org/).

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
