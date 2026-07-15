---
description: Upgrade Yggdrasil to the latest version and redeploy the engine
---
Upgrade the installed `yggdrasil-memory` package, then redeploy so the running engine picks up the new code.

Do this carefully — it changes an installed tool and restarts a background service, so **confirm the plan with me before running anything that mutates state**:

1. **Detect how it's installed** (read-only): check for `pipx list | grep yggdrasil`, `brew list yggdrasil 2>/dev/null`, `npm ls -g yggdrasil-memory 2>/dev/null`, and whether the plugin's MCP server uses `uvx --from yggdrasil-memory`. Report the detected channel and the current vs latest version (`ygg version`; latest via `pip index versions yggdrasil-memory` or the channel's own check).
2. **Show the exact upgrade command** for that channel and ask me to confirm:
   - pipx: `pipx upgrade yggdrasil-memory`
   - Homebrew: `brew update && brew upgrade yggdrasil`
   - npm: `npm i -g yggdrasil-memory@latest`
   - uvx (no persistent install): note that `uvx` fetches latest on next run; a pinned version may need clearing the uv cache.
3. **After upgrading**, run `ygg redeploy` (restart the engine on the new code) and then `ygg doctor`, and report the before/after version plus the doctor checklist.

If already on the latest version, say so and skip the rest. Never run an upgrade or redeploy without my go-ahead.
