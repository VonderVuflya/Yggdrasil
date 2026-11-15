# Yggdrasil CLI

`yggdrasil/ygg.py` is a thin facade over the engine's REST API. It exists so agents do not need to remember the engine's exact payload shape.

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

## `ygg seed`: connection refused

`Connection refused` means the connection to the configured model server was
rejected, before a model could process the file. Check the server process,
listening address, port and firewall. Increasing `--timeout` will not fix a
refused connection.

1. On the model server's machine, start the server in LM Studio, or run
   `ollama serve` for Ollama. Make the configured background model available.
2. If connecting from another machine, enable listening on the LAN interface.
   A server bound only to `127.0.0.1` cannot accept requests over the LAN.
3. Check `ygg config get distill_url`. Correct a stale address with
   `ygg config set distill_url http://HOST:PORT` (LM Studio commonly uses port
   `1234`, Ollama `11434`). The URL is the server root, without `/v1`.
   Check command-line `--ollama-url` and environment variables `YGG_DISTILL_URL`
   and `YGG_EMBED_URL` too: these can override the saved configuration.
4. Run `ygg doctor`, then retry `ygg seed --yes`.

When the connection fails, seed stops at the first affected file and exits with
code `1`. Completed files remain saved; the failed and unattempted files stay
pending for the next run. `ygg distill --source PATH` uses the same protection.
Per-file generation timeouts and malformed model output still leave the file
pending and allow the batch to continue.

Before processing files, `ygg seed` and `ygg distill` probe the model API
(`/v1/models`, falling back to `/api/tags`). If a local endpoint is unavailable
in an interactive terminal, Yggdrasil detects `lms` (including
`~/.lmstudio/bin/lms`) and `ollama`, offers to start the matching server, and
waits up to 30 seconds for its API before continuing. Ports 1234 and 11434
prefer LM Studio and Ollama respectively; when ambiguous, you can choose.
`--yes` does not approve launching a program: that prompt is separate.
A remote endpoint or noninteractive run stops with recovery instructions.
If the application is installed without its CLI, start its server manually
or install the CLI. The configured model must be available on that server.
