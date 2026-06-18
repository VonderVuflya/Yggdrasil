# yggdrasil-memory (npm launcher)

> One shared, durable memory for all your AI coding agents — MCP, local-first, zero-dependency.

This npm package is a **thin launcher**. Yggdrasil's engine is pure Python; this
package makes sure a runner is available (it prefers [`uv`](https://docs.astral.sh/uv/),
which can fetch a managed Python on its own) and then runs the Python package
[`yggdrasil-memory`](https://pypi.org/project/yggdrasil-memory/), forwarding every
argument. So this works even on a machine with no Python installed:

```bash
npx yggdrasil-memory install      # guided setup: models, background service, MCP registration
```

Everything after `install` is forwarded to the `ygg` CLI:

```bash
npx yggdrasil-memory doctor
npx yggdrasil-memory recall --query "flaky websocket reconnect"
```

Or install the launcher globally to get the `ygg` command:

```bash
npm install -g yggdrasil-memory
ygg install
```

**Prefer the native channels?** `uvx --from yggdrasil-memory ygg install`,
`pipx install yggdrasil-memory`, `pip install yggdrasil-memory`, or
`brew install VonderVuflya/tap/yggdrasil` — they all install the same engine.

Full docs, FAQ, and translations: **https://github.com/VonderVuflya/yggdrasil**

Licensed under the Elastic License 2.0 (source-available). See `LICENSE`.
