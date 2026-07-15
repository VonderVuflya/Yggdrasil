---
description: Audit Yggdrasil memory quality (duplicates, leakage, truncated)
argument-hint: [optional --threshold 0.95]
---
Run `ygg quality $ARGUMENTS` via Bash (fall back to `uvx --from yggdrasil-memory ygg quality $ARGUMENTS`). Report the store's health: type/project distribution, exact + near-duplicate pairs (cosine gate), cross-project leakage, and likely-truncated records. For any problem found, recommend the concrete fix — `ygg review --apply` to consolidate duplicates, `ygg delete --id <id>` to drop a bad record, `ygg reindex` if embeddings are missing. If the store is clean, say so briefly.
