<!-- mcp-name: io.github.VonderVuflya/yggdrasil -->
<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>Stop re-explaining your project to every new AI session.</b><br/>
One local memory for Claude Code, Codex, and every MCP agent — shared across sessions, tools, and projects. Zero dependencies. Nothing leaves your machine.</p>

<p align="center">
  <a href="https://github.com/VonderVuflya/Yggdrasil/releases/latest"><img src="https://img.shields.io/github/v/release/VonderVuflya/Yggdrasil?label=release&color=blue" alt="Latest release"></a>
  <a href="https://pypi.org/project/yggdrasil-memory/"><img src="https://img.shields.io/pypi/v/yggdrasil-memory?label=PyPI&color=blue" alt="PyPI"></a>
  <a href="https://glama.ai/mcp/servers/VonderVuflya/Yggdrasil"><img src="https://glama.ai/mcp/servers/VonderVuflya/Yggdrasil/badges/score.svg" alt="Glama quality score"></a>
  <a href="./BENCHMARKS.md"><img src="https://img.shields.io/badge/recall@1-0.94%20·%20reproducible-brightgreen" alt="Benchmarks"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-AGPL%203.0-blue.svg" alt="AGPL-3.0"></a>
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="alpha">
</p>

<p align="center">
  <a href="#-install">Install</a> ·
  <a href="#-how-it-works">How it works</a> ·
  <a href="#-the-numbers">Numbers</a> ·
  <a href="#-yggdrasil-vs-the-rest">Compare</a> ·
  <a href="#-faq">FAQ</a>
</p>

<p align="center">
  Read this in: <a href="./i18n/README.ru.md">Русский</a> · <a href="./i18n/README.zh.md">简体中文</a> · <a href="./i18n/README.es.md">Español</a> · <a href="./i18n/README.fr.md">Français</a> · <a href="./i18n/README.ja.md">日本語</a> · <a href="./i18n/README.de.md">Deutsch</a>
</p>

---

<p align="center">
  <img src="docs/demo.gif" alt="Yggdrasil — a brand-new session already knows your project, and recalls a fix from another project" width="880">
</p>

Every new chat, your AI forgets. You re-explain the project, the decisions, the gotchas — every time, in every tool. **Yggdrasil is a tiny always-on memory that any agent plugs into.** Open a new session, in any project, with any AI, and it already knows what you decided, what broke, and what's still open.

```text
$ cd ~/projects/checkout-api && claude        # a brand-new session

🌳 Yggdrasil  (injected automatically at session start)
   • [project_status] payments refactor: idempotency keys added; open: e2e tests
   • [lesson] webhook 401 → signing secret rotated; update env + redeploy

> "have I solved a flaky websocket reconnect anywhere before?"

🌳 recall → found in project `realtime-dash`:
   refresh the token *before* opening the socket, then retry with capped backoff.
```

No "let me remind you what we did yesterday." It's just there.

## 🚀 Install

Two commands, inside **Claude Code** (the plugin launches via [`uv`](https://docs.astral.sh/uv/)):

```text
/plugin marketplace add VonderVuflya/Yggdrasil
/plugin install yggdrasil
```

The engine lazy-starts on first use and generates its own local token — no API key, no cloud, nothing to configure. Codex and Cursor use the same flow.

<details>
<summary>All other channels — CLI daemon, Homebrew, npm, Claude Desktop, from source…</summary>

| Host / tool | Command |
| --- | --- |
| **uvx** _(recommended CLI)_ | `uvx --from yggdrasil-memory ygg install` |
| **npm / npx** | `npx yggdrasil-memory install` |
| **pipx** | `pipx install yggdrasil-memory && ygg install` |
| **pip** | `pip install yggdrasil-memory && ygg install` |
| **Homebrew** _(macOS)_ | `brew install VonderVuflya/tap/yggdrasil && ygg install` |
| **Claude Desktop** _(app)_ | drag the `.mcpb` from the [latest release](https://github.com/VonderVuflya/Yggdrasil/releases/latest) onto Settings → Extensions, paste your token (`ygg token`) — the desktop app then shares the same memory as your CLI agents ([guide](./packaging/mcpb/README.md)) |
| **from source** | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` |

`ygg install` is a one-time guided setup: it installs an always-on background service, registers the MCP tools with Claude Code and Codex, and — if your hardware allows — recommends optional local models (or pick `none` to stay zero-config).

There is also a [`yggdrasil-memory` skill](./skills/) for any Claude surface: MCP connects the *tools*, the skill teaches the agent *when* to use them. Use both for the best behavior.

Try it with nothing installed and a throwaway DB: `uvx --from yggdrasil-memory ygg serve --reset --db /tmp/ygg.sqlite`.

</details>

Then just work: ask your agent *"recall what we decided about this project"*, tell it *"remember this decision"* — next session it's already there. Verify the install any time with `ygg doctor`.

**Already have history?** Seed memory from your existing Claude Code + Codex transcripts, Obsidian vaults, and `CLAUDE.md` repos — distilled locally:

```bash
ygg seed --dry-run    # see what it would import; drop the flag to distill for real
```

**Leaving another memory tool?** `ygg import --from mcp-memory --path memory.json` pulls its whole store into Yggdrasil (deduped, secret-guarded) — then you can delete it.

## Why

- 🧠 **Persistent** — decisions, lessons, and project status survive across sessions.
- 🔌 **One brain, every tool** — Claude Code, Codex, and any MCP host share the same memory.
- 🌐 **Cross-project recall** — *"this looks like what you did in project B — reuse it?"*
- 🧹 **Curated, not captured** — your agent saves the few things that matter; governance dedupes and archives, never deletes.
- 🌱 **Self-maintaining** *(opt-in)* — a small local model consolidates memory in the background. Zero API tokens.
- 🪪 **One identity everywhere** — an optional name and persona every agent picks up, so Claude Code and Codex feel like the same assistant.
- 🔒 **100% local** — your memory lives on your machine. No cloud, no account, no telemetry.

## 🧠 How it works

Yggdrasil is **memory + tools** — the *intelligence* is your LLM. It just makes sure the right memory is in front of the right agent at the right moment.

- 🛎️ **Always-on daemon** — a tiny local service (~21 MB RAM) your agents reach over MCP tools (`ygg_search`, `ygg_recall`, `ygg_remember` …).
- 🪝 **Hooks** — session start auto-injects identity, project status, and open follow-ups (~300 tokens); an optional per-prompt hook auto-recalls memory relevant to *each request*.
- 📌 **Ranking** — pinned and frequently-recalled memories surface first.
- 🧹 **Governance** — duplicates and conflicts are queued for review; changes are non-destructive (archive, never delete).
- 📓 **Obsidian** — every memory doubles as a plain-Markdown note you can read, edit, and grep.

## 🎛️ Memory tiers — zero-config by default

Out of the box, Yggdrasil runs on **SQLite + FTS5 with zero dependencies** — instant keyword search, no models, nothing to download. Optional **local** models via [Ollama](https://ollama.com) add two independent tiers:

| Tier | You add | You gain |
| --- | --- | --- |
| **0 · default** | nothing — SQLite + FTS5 | keyword search, zero deps, instant — recall@1 = **0.77** |
| **1 · semantic** | an **embedding** model (`all-minilm` 45 MB · `paraphrase-multilingual` ~560 MB) | search by **meaning**, across languages — recall@1 = **0.94**, recall@3 **1.00** |
| **2 · self-maintaining** | a small **LLM** (`qwen2.5:1.5b` ~1 GB) | background dedupe/merge of memory (propose-only) |

Ollama only *computes* vectors and runs the background model — every memory and every vector stays in the same local SQLite. `ygg install` detects your hardware and recommends a fit (`ygg recommend` shows the full catalog).

<details>
<summary>Full model menu</summary>

**Embeddings (semantic search):**

| Model | Size | Good for |
| --- | --- | --- |
| `all-minilm` | 45 MB | English, tiny & fast |
| `nomic-embed-text` | 274 MB | English, better quality |
| `paraphrase-multilingual` | ~560 MB | multilingual (EN/RU + 50 langs) |
| `bge-m3` | 1.2 GB | multilingual, top quality (heavier) |

**Background consolidation (small LLM):**

| Model | Size | Good for |
| --- | --- | --- |
| `qwen2.5:0.5b` | ~400 MB | tiny, fast on CPU |
| `qwen2.5:1.5b` | ~1 GB | best CPU default |
| `llama3.2:3b` | ~2 GB | better quality, slower on CPU |

The engine itself is swappable — any service meeting the `MemoryBackend` contract is a drop-in (`YGG_ENGINE_URL`); see [docs/backend-boundary.md](./docs/backend-boundary.md).

</details>

## 📊 The numbers

Measured by [`eval/ygg_eval.py`](./eval/ygg_eval.py) — 232 memories, 110 labelled queries, ranking weights tuned on the *dev* split only, so **holdout is the unbiased number** (recall@1, with the `paraphrase-multilingual` model):

| Search view | holdout recall@1 | recall@3 | zero-dep lexical |
| --- | --- | --- | --- |
| **Within a project** (the real path, pool ~11) | **0.94** | **1.00** | 0.76 |
| **Whole store** (no filter, pool 232) | 0.72 | 0.87 | 0.69 |

**Within a project — the path you use — the right memory is #1 for 0.94 of queries and in the top 3 every time (recall@3 = 1.00).** Searching the whole store with no filter is harder (recall@1 0.72, recall@3 0.87 across all 232). Zero-dep lexical mode already solves keyword and code-identifier queries (1.00); the local model adds meaning and cross-language (crosslingual 0.25 → 0.95). The [full breakdown in BENCHMARKS.md](./BENCHMARKS.md) has 95% CIs, pool sizes, and per-class scores — rerun it in a minute: `python3 eval/ygg_eval.py --report`.

## 🆚 Yggdrasil vs the rest

Everyone else either auto-captures transcripts or sells you a cloud. Yggdrasil's bet: keep the **few things that matter**, curated and de-duped, in plain rows you own — and share them across **every** tool and project.

| | **Yggdrasil** | Built-in memory <sub>(Claude Code · Codex)</sub> | [claude-mem](https://github.com/thedotmack/claude-mem) | [mem0](https://github.com/mem0ai/mem0) / OpenMemory | [basic-memory](https://github.com/basicmachines-co/basic-memory) |
| --- | --- | --- | --- | --- | --- |
| Curated decisions / lessons / status (not transcripts) | ✅ | ⚠️ auto-notes | ❌ captures everything | ⚠️ | ⚠️ free-form notes |
| One memory **across tools** | ✅ | ❌ vendor-siloed | ✅ | ✅ | ✅ |
| **Cross-project** recall ("solved this in project B") | ✅ | ❌ repo-scoped | ⚠️ | ⚠️ | ⚠️ |
| **100% local** by default | ✅ | ✅ | ⚠️ cloud sync add-on | ❌ hosted-first | ✅ |
| **Zero dependencies** (stdlib + SQLite) | ✅ | — | ❌ Node + Bun + worker daemon | ❌ Docker + Qdrant + LLM key | ❌ |
| Works with **no LLM & no API key** | ✅ | ✅ | ❌ AI-compresses | ❌ | ✅ |
| **Semantic search, fully local** | ✅ opt-in Ollama | ❌ grep-only | ⚠️ optional Chroma | ⚠️ needs API key or Docker stack | ❌ |
| Plain **Markdown you own** (Obsidian-ready) | ✅ | ✅ | ❌ | ❌ | ✅ |

**Closest neighbor — claude-mem:** capture-everything memory that records and AI-compresses every session (Node 20+ *and* Bun, a persistent worker daemon; Chroma optional). Yggdrasil is the opposite bet: a small, high-signal store instead of a growing firehose. **mem0** is an SDK plus a hosted platform for building *apps* that remember *their users* — even self-hosted it needs an LLM API key. **Built-in memories** are genuinely useful — and structurally siloed: one vendor, one repo, one machine, literal grep. Yggdrasil is the layer above them (and `ygg seed` can bootstrap itself from those same transcripts). Different layer entirely: [context-mode](https://github.com/mksglu/context-mode) (live context window) and [Context7](https://github.com/upstash/context7) (fresh library docs) — both pair fine with Yggdrasil.

## 🧰 Commands

Agents see six MCP tools: `ygg_health`, `ygg_bootstrap`, `ygg_search`, `ygg_recall`, `ygg_remember`, `ygg_materialize` — auto-registered by the plugin or `ygg install`.

<details>
<summary>Full <code>ygg</code> CLI reference</summary>

**Memory ops**

| Command | What it does |
| --- | --- |
| `ygg recall --query "…"` | **Cross-project** search — "have I done this anywhere?" |
| `ygg search --project P --query "…"` | Project-scoped search (`--type`, `--tag`, `--limit`, `--json`) |
| `ygg remember --project P --type lesson --content "…"` | Save a durable memory (secret-guarded, deduped) |
| `ygg bootstrap --project P` | Pull a project's memory before starting work |
| `ygg pin --id ID` · `ygg unpin --id ID` | Pin a memory so it reliably surfaces |
| `ygg relate --from A --rel solves --to B` · `ygg relations --id ID` | Link memories (`solves`/`supersedes`/`contradicts`) · see why a memory exists / what replaced it |
| `ygg supersede --id OLD --by NEW` | Archive an outdated memory — `--by` records what replaced it |
| `ygg materialize --id ID --project P` | Export one memory to an Obsidian note |
| `ygg export-native --project P` | Write a curated digest into `AGENTS.md`/`MEMORY.md` — feed Claude Code & Codex's native memory |
| `ygg import --from TOOL --path P` | Migrate another memory tool's store into Yggdrasil (`mcp-memory`, `basic-memory`; `--dry-run` first) |
| `ygg review [--apply]` | Work the governance queue — consolidate duplicates, flag stale/conflicting memories (archive-only, reversible) |
| `ygg delete --id ID` · `ygg reset …` | Hard-delete one memory · bulk-undo a bad seed (confirms first) |

**Cold start**

| Command | What it does |
| --- | --- |
| `ygg seed` | Distill Claude Code + Codex transcripts, Obsidian vaults, `CLAUDE.md` repos — incremental, deduped, fully local |
| `ygg seed --dry-run` · `--force` | Discover + estimate only · re-distill everything |
| `ygg seed --schedule 03:30` | Nightly auto-distill (launchd) — memory keeps itself fresh; `off` / `status` |
| `ygg sync --repo <your-git-repo>` | Sync memory across machines through **your own** git repo — plain JSON files, no cloud in the loop |
| `ygg distill --source PATH` | Distill one dir/file into lessons |
| `ygg reindex` | Backfill missing embeddings (restores dense recall) |

**Service & setup**

| Command | What it does |
| --- | --- |
| `ygg install` · `ygg doctor` · `ygg update` | Guided setup · diagnose with actionable fixes · upgrade |
| `ygg config` | Show/set persistent settings (`list` · `get` · `set` · `unset`) |
| `ygg status` · `start` · `stop` · `restart` · `logs` | Manage the always-on daemon |
| `ygg hooks` · `unhooks` · `register` | SessionStart hook on/off · (re)register MCP |
| `ygg recommend` · `token` · `uninstall` | Model catalog · print auth token · remove everything |

Give it a personality — edit `~/.yggdrasil/identity.json`:

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

Heavy seeding, weak laptop? Point distillation at *any* box on your LAN — a desktop with Ollama, LM Studio, llama.cpp, **even an iPhone running a local-LLM server app**: `ygg config set distill_url http://<box>:11434`. Yggdrasil auto-detects the API dialect (Ollama or OpenAI-compatible); your data still never leaves your network — details in [docs/ygg-cli.md](./docs/ygg-cli.md).

</details>

## ❓ FAQ

<details>
<summary><b>Claude Code already has built-in memory — why Yggdrasil?</b></summary>

Built-in memories are per-vendor, per-repo, per-machine, and retrieved by literal text match. Yggdrasil is the layer above: the *same* memory in Claude Code, Codex, and any MCP host, recall *across* projects, optional semantic search — still 100% local. It bridges them **both ways**: `ygg seed` distills your existing native memory + transcripts into the shared brain, and `ygg export-native` writes a curated digest back into `AGENTS.md`/`MEMORY.md` — so even a fresh clone or a tool without Yggdrasil still gets your curated memory.
</details>

<details>
<summary><b>Does it send my code or memory to the cloud?</b></summary>

No. The engine, the database, and the optional models all run locally. No account, no telemetry. The only outbound call is a version check against PyPI.
</details>

<details>
<summary><b>Does it automatically remember everything?</b></summary>

No — by design. Retrieval is automatic; *writing* is deliberate (the agent calls `ygg_remember` for durable lessons). Capture-everything pollutes memory and burns tokens, so we don't. The optional background model consolidates what's already saved (propose-only).
</details>

<details>
<summary><b>Do I need a GPU or an API key?</b></summary>

No. The default is pure lexical search — zero dependencies, instant. Semantic search is opt-in and uses a *local* model via Ollama. The installer recommends one that fits your hardware.
</details>

<details>
<summary><b>How heavy is it, and what does it cost in tokens?</b></summary>

The engine idles at **~21 MB RAM** (lexical default) with ~0% CPU; disk is tens of KB per memory. Session start injects ~300 tokens; each tool call returns a small snippet. All heavy work (indexing, embeddings, consolidation) runs off-LLM on your machine.
</details>

<details>
<summary><b>Can I edit or delete memories by hand?</b></summary>

Yes. Memories materialize to Markdown notes in an Obsidian vault — read, edit, or remove them like any file. The engine never hard-deletes; it archives (reversible).
</details>

## 🚦 Status & roadmap

**Alpha.** The happy path and the governance loop are gate-tested (`scripts/run_gates.sh`); not yet hardened for multi-user or production use. macOS today; Linux/Windows service installers are built and in final on-device testing.

Next: 🛰️ cross-surface sync (one memory across CLI, web, and phone) · 🔗 relation graph (`SOLVES` / `SUPERSEDES` / `CONTRADICTS`) · 🐧 Linux/Windows GA.

## 🤝 Contributing

Issues and PRs welcome. Run `scripts/run_gates.sh` and `python3 -m unittest discover -s tests` before submitting — all gates must stay green.

## 📜 License

**GNU AGPL v3.0** — see [LICENSE](./LICENSE). Free and open source: use, modify, self-host, redistribute. If you modify it or offer it as a network service, you must release your source under the same license.
