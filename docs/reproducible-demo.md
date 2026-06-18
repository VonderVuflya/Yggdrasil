# Reproducible Yggdrasil Demo

Yggdrasil is a thin workflow/governance layer over a memory engine:

- **Yggdrasil's own engine** (`yggdrasil/ygg_memory_server.py`) is the default durable backend — stdlib only (SQLite + FTS5), zero heavy dependencies.
- `yggdrasil/ygg.py` is the agent-facing facade; `yggdrasil/ygg_mcp_server.py` exposes it over MCP.
- Obsidian Markdown is a materialized view.
- An external engine is an **optional** alternative backend (see `docs/backend-boundary.md`).

## One command: start engine, seed, run every gate

```bash
scripts/run_gates.sh
```

This starts the own engine on a fresh temp DB, seeds the `test-a` / `test-b`
fixtures, runs all four gates, prints a PASS/FAIL summary, and tears the server
down. No external backend, no model downloads.

## Manual flow

Start the engine (leave it running):

```bash
python3 yggdrasil/ygg_memory_server.py --reset --db /tmp/ygg-demo.sqlite
# listening on http://127.0.0.1:42069  fts5=on
```

Seed the quality-gate fixtures:

```bash
YGG_NAMESPACE=yggdrasil-demo YGG_USER_ID=demo-user python3 yggdrasil/ygg_seed_demo.py
```

### Quality gate

```bash
yggdrasil/ygg_quality_gate.py
```

Checks `/health`, project bootstrap, project isolation, the secret guard,
Obsidian materialization, and the MCP facade handshake/tool-list/bootstrap.

### Dense / dedupe gate

```bash
yggdrasil/ygg_dense_gate.py
```

Paraphrase retrieval (FTS5 porter), project isolation, and the Ygg wrapper's
exact-duplicate guard. Note: backend-level dedupe is intentionally NOT done by
the engine (so the review loop can surface and archive duplicates); the wrapper
guard (`YGG_DUPLICATE_SKIP`) is the dedupe path.

### Review apply gate (archive action)

```bash
yggdrasil/ygg_review_apply_gate.py
```

Detects an exact duplicate, proposes actions, approves the archive action,
dry-runs, executes, and confirms the follow-up queue ignores the archived
duplicate.

### Governance gate (merge_proposal + verify_or_archive)

```bash
yggdrasil/ygg_governance_gate.py
```

Near-duplicate memories -> `merge_proposal` (archive non-canonical members,
annotate canonical with `merged_from`). Stale/conflict-marked memory ->
`verify_or_archive` (archive with `verified_stale`). Both are non-destructive.

## Cross-agent shared memory (MCP)

With an engine running:

```bash
python3 yggdrasil/ygg_cross_agent_demo.py
```

Two independent MCP sessions ("claude" writes, "codex" reads) share one engine.
The proof: the reader retrieves the exact memory id the writer persisted.

## Unit tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

Reports for every gate are written to `reports/*.json`.

## Optional: run against an external engine backend

Point Yggdrasil at any compatible REST engine instead of the bundled one:

```bash
export YGG_ENGINE_URL=http://127.0.0.1:42069   # your engine instance
export YGG_ENGINE_TOKEN=...                     # its auth token
yggdrasil/ygg_quality_gate.py
```

The client (`yggdrasil/ygg_core.py`) is engine-agnostic. See
`docs/backend-boundary.md` for the contract an engine must satisfy
(notably `PUT /update` accepting `metadata_patch` and `archived`).
