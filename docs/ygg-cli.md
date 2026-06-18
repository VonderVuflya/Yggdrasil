# Yggdrasil MVP CLI

`yggdrasil/ygg.py` is a thin facade over the engine.s REST API. It exists so agents do not need to remember the engine.s exact payload shape.

## Environment

```bash
export YGG_ENGINE_URL="http://127.0.0.1:42069"
export YGG_ENGINE_TOKEN="..."
export YGG_NAMESPACE="yggdrasil-demo"
export YGG_USER_ID="global_user"
```

## Commands

Health:

```bash
yggdrasil/ygg.py health
```

Save a project-scoped memory:

```bash
yggdrasil/ygg.py remember \
  --project test-a \
  --type debugging_lesson \
  --json-file examples/layout-overflow-debugging-lesson.json
```

Search before non-trivial work:

```bash
yggdrasil/ygg.py bootstrap --project test-a --query "mobile layout overflow"
```

Search directly:

```bash
yggdrasil/ygg.py search --project test-a --query "scrollWidth clientWidth chips"
```

Materialize a memory to Obsidian Markdown:

```bash
yggdrasil/ygg.py materialize \
  --id MEMORY_ID \
  --project test-a \
  --output-dir vault/04-learnings
```

## Guardrails

- Project memories require `--project`.
- `project` is written into `metadata.project`.
- `scope` is always sent to the engine and mirrored into metadata.
- The CLI refuses common secret patterns before writeback.
- By default, writeback sets `skip_extraction=true` for deterministic agent-authored memories.
