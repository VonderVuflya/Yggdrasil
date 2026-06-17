# Yggdrasil

A thin, agent-agnostic **memory + governance layer** so coding agents (Claude
Code, Codex, and any MCP host) share one durable, inspectable project memory —
backed by its own lightweight engine and materialized into an Obsidian vault.

> Status: **alpha / working prototype.** The happy path and the full review
> governance loop are covered by passing gates (see below). Not production
> hardened. Honest about what works — every claim here is backed by a gate you
> can run.

## What's here

- **Own memory engine** — `scripts/ygg_memory_server.py`: a stdlib-only HTTP
  server over SQLite + FTS5. Zero heavy dependencies. The default backend.
- **Agent facade** — `scripts/ygg.py` (CLI) + `scripts/ygg_mcp_server.py` (MCP
  stdio). Secret-refusal guard and content-hash dedupe live here.
- **Governance loop** — `scripts/ygg_review_queue.py` →
  `scripts/ygg_review_actions.py`: surfaces duplicate / stale / conflicting
  memories and applies **non-destructive** actions (`archive`,
  `merge_proposal`, `verify_or_archive`) only after explicit approval.
- **Obsidian** — memories materialize to Markdown notes (a readable view).
- **Dense search (optional)** — set `YGG_EMBED_MODEL` to add semantic retrieval
  via a local Ollama embedding model, fused with lexical ranking via Reciprocal
  Rank Fusion. Off by default (zero-dependency lexical search).
- **Eval harness** — `eval/ygg_eval.py`: retrieval quality (recall@k, MRR) on a
  fixed corpus; the metric that gates every retrieval change.

## Quick start

```bash
# start engine, seed fixtures, run every gate, tear down — one command:
scripts/run_gates.sh

# or run the engine yourself:
python3 scripts/ygg_memory_server.py --reset --db /tmp/ygg.sqlite
```

Cross-agent shared memory over MCP (writer + reader are separate sessions):

```bash
python3 scripts/ygg_cross_agent_demo.py
```

See `docs/reproducible-demo.md` for the full flow and `docs/backend-boundary.md`
for the engine contract.

## Gates (the test suite that backs the status claims)

| Gate | Proves |
| --- | --- |
| `ygg_quality_gate.py` | health, bootstrap, project isolation, secret guard, Obsidian materialize, MCP facade |
| `ygg_dense_gate.py` | paraphrase retrieval (FTS5), isolation, wrapper dedupe guard |
| `ygg_review_apply_gate.py` | exact-duplicate detection → approved archive → follow-up queue ignores it |
| `ygg_governance_gate.py` | near-duplicate `merge_proposal` + stale `verify_or_archive`, non-destructive |

All four pass on the bundled engine (`scripts/run_gates.sh`).

## Retrieval quality

`eval/ygg_eval.py` scores recall@1/recall@3/MRR on a fixed corpus, split by
query class (keyword / identifier / paraphrase / crosslingual). Current numbers:

| Mode | recall@1 | paraphrase | crosslingual (EN→RU) |
| --- | --- | --- | --- |
| lexical (default) | 0.63 | 0.00 | 0.00 |
| dense — `all-minilm` (45 MB, English) | 0.75 | 0.67 | 0.00 |
| dense — `paraphrase-multilingual` (562 MB) | 0.94 | 0.67 | 1.00 |

`keyword` and `identifier` classes are 1.0 in every mode. Pick the embedding
model by your memory's languages: `all-minilm` is a light English-only default;
a multilingual model closes the EN↔RU gap (real bilingual memory needs it). Set
`YGG_EMBED_MODEL` accordingly.

## Footprint

Measured on a live instance (13 memories, 4 projects):

| Resource | Default (lexical) |
| --- | --- |
| RAM (engine RSS) | ~21 MB — essentially one idle Python process |
| CPU (idle) | ~0% (event-driven HTTP) |
| Disk | SQLite + FTS index, ~tens of KB per memory |
| Dependencies | none (Python 3.10+ stdlib only) |

Dense search is opt-in and adds a local Ollama embedding model — no API key,
nothing leaves the machine. Model size is your call: `all-minilm` (~45 MB,
English) or `paraphrase-multilingual` (~562 MB, EN/RU and more).

## Backend strategy

The workflow layer talks to a small REST contract (`MemoryBackend` in
`scripts/ygg_core.py`), so the engine is swappable:

- **Default:** the bundled own engine. No external service, no model downloads.
- **Optional:** an external **Muninn** instance
  (`github.com/wjohns989/Muninn`, Apache-2.0, third party — NOT bundled).
  Point `YGG_MUNINN_URL`/`YGG_MUNINN_TOKEN` at it. It needs a small
  metadata-update shim; see `docs/backend-boundary.md`. Preserve its
  `NOTICE`/attribution if you redistribute.

The "couple of genuinely useful" things an external engine adds (reranking,
temporal validity) are tracked on the roadmap as native features to build under
our own contract rather than depend on a third-party runtime.

## Migrating existing memory

Claude Code accumulates per-project memory under
`~/.claude/projects/<sanitized>/memory/`. Import it into Yggdrasil (drives the
real `ygg.py remember` path — secret guard + dedupe — then materializes notes):

```bash
python3 scripts/ygg_import_claude_memory.py \
  --source-dir ~/.claude/projects/<sanitized>/memory \
  --project <name> --materialize
```

Dogfooded on real projects: existing Claude-memory lessons import cleanly and
are retrievable by symptom (e.g. "service won't start after an image upgrade" →
the matching environment-corruption lesson ranks first).

## Known limitations

- Default retrieval is lexical (FTS5/BM25 + importance/recency boost); semantic
  paraphrase matching needs dense search enabled (`YGG_EMBED_MODEL`). See the
  Retrieval quality table.

The engine has unit tests (`tests/test_ygg_memory_server.py`, run via
`python3 -m unittest`) in addition to the integration gates.
