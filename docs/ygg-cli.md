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

Before reading transcripts or generating tokens, `ygg seed` and `ygg distill`
run these checks in order:

1. Resolve the configured server hostname (DNS) and connect to its TCP port.
   A refused connection and a timeout have separate explanations. A timeout
   alone cannot prove that the remote PC is switched off: a firewall can also
   silently drop the connection. SSH access and successful ICMP ping are not required.
2. Check the model API and obtain its model list (native Ollama `/api/tags`,
   then OpenAI-compatible `/v1/models` when the native route is unsupported).
   Requests use the configured API key; HTTP 401/403, an unsupported API and
   invalid responses are reported separately.
3. Verify the exact distillation model ID: `--model` overrides `bg_model`.
   Missing models produce an error showing the requested ID, server address and
   available IDs. A similar name is never substituted; only Ollama's standard
   bare-name / `:latest` alias is accepted.
4. If `embed_model` is configured, check it at `embed_url` using `embed_backend`
   and `embed_api_key`. A shared endpoint's inventory is reused only when its
   URL, authorization and protocol agree. Otherwise it is checked separately.
   If no embedding model is configured, that check is explicitly skipped.

The first failed check stops the command with exit code `1`, leaving files
pending. These checks never generate tokens, download models or send transcript
text. A successful model-list check means the server advertises the model; it
cannot guarantee that loading or generation will subsequently succeed. A public
model catalog may not validate credentials; authentication failures are detected
when the checked API reports them.
`--dry-run` and a seed with no new files make no model-server requests.
Embedding checks use the effective CLI settings. The running memory daemon
receives its embedding settings at startup: after changing them, redeploy it;
this preflight does not prove that an existing daemon applied the new settings.

If a local endpoint refuses connections in an interactive terminal, Yggdrasil
detects `lms` (including `~/.lmstudio/bin/lms`) and `ollama`, offers to start the
matching server, and waits up to 30 seconds for its API before checking models.
Ports 1234 and 11434 prefer LM Studio and Ollama respectively; when ambiguous,
you can choose. `--yes` does not approve launching a program: that prompt is
separate. A remote endpoint or noninteractive run stops with recovery instructions.
Authentication errors and missing models do not trigger a server restart.
If the application is installed without its CLI, start its server manually
or install the CLI. Remote processes and model settings are never changed.

When a configured model is missing and a terminal supports the wizard, preflight
shows available compatible models with green `available` badges. Use ↑/↓ and
Enter to save the highlighted choice. Cancel keeps that setting unchanged.
The chooser filters generation/embedding models using server metadata, falling
back to the setup wizard's existing name classification when metadata is absent.
It offers only models listed by that endpoint and never downloads a replacement.

Choosing a generation model saves `bg_model` through the same configuration
writer as `ygg config set` and uses it immediately, including for a command that
specified an unavailable `--model`. Choosing an embedding model saves
`embed_model` and stops before distillation with a `ygg redeploy` instruction:
the existing memory daemon must apply the change first. A model-setting
environment variable can override saved configuration; the wizard warns about it.
Noninteractive runs and `--yes` alone never approve a configuration change.
