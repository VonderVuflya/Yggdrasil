# Memory Review Queue

`scripts/ygg_review_queue.py` scans memories and creates a human review queue.

It is intentionally conservative: it does not delete, update, or archive memories. It only reports candidates.

## Checks

- exact duplicates by `metadata.content_hash` or computed content hash;
- near duplicates by normalized opening content;
- stale/conflict markers in content or metadata status.

## Run

Start the engine first:

```bash
python3 scripts/ygg_memory_server.py --reset --db /tmp/ygg.sqlite
```

Then:

```bash
scripts/ygg_review_queue.py --user-id demo-user
```

Dense demo:

```bash
YGG_EMBED_MODEL=all-minilm python3 scripts/ygg_memory_server.py --reset --db /tmp/ygg.sqlite
YGG_USER_ID=dense-user scripts/ygg_review_queue.py --user-id dense-user
```

Outputs:

- `reports/review-queue-*.json`
- `vault/99-review/memory-review-queue.md`

## Policy

Agents may surface review queue items, but should not delete or rewrite durable memories without explicit user approval.
