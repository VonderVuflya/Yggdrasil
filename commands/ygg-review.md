---
description: Work the Yggdrasil curation queue (duplicates, stale, conflicts)
argument-hint: [--apply to act; default is report-only]
---
Run `ygg review $ARGUMENTS` via Bash (fall back to `uvx --from yggdrasil-memory ygg review $ARGUMENTS`). Default is report-only — surface duplicate clusters, stale records, and SOLVES/SUPERSEDES/CONTRADICTS conflicts. Only pass `--apply` if the user asked to act; explain that every action is an archive (reversible), never a hard delete. After an apply run, report what was consolidated vs flagged for manual review.
