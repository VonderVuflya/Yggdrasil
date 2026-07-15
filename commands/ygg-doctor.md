---
description: Diagnose the Yggdrasil install (engine, models, MCP, hooks)
---
Run `ygg doctor` via Bash (fall back to `uvx --from yggdrasil-memory ygg doctor` if `ygg` isn't on PATH) and present the result as a checklist. Call out anything failing — engine unreachable, no embedding model (lexical-only), MCP not registered with Claude/Codex, hooks missing, effective distill context too small — and give the exact one-line fix for each (e.g. `ygg start`, `ygg register`, `ygg install`). If everything passes, say so in one line.
