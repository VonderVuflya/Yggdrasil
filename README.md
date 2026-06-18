<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>One shared, durable memory for all your AI coding agents.</b><br/>
Claude Code, Codex, and any MCP host remember your projects — decisions, lessons, status — across sessions, tools, and projects.</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-Elastic%202.0-blue.svg" alt="Elastic License 2.0">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/deps-zero%20(stdlib)-brightgreen" alt="zero deps">
  <img src="https://img.shields.io/badge/MCP-Claude%20·%20Codex%20·%20any%20host-purple" alt="MCP">
  <img src="https://img.shields.io/badge/local--first-100%25%20private-success" alt="local-first">
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="alpha">
</p>

<p align="center">
  <a href="#-quickstart">Quickstart</a> ·
  <a href="#-how-it-works">How it works</a> ·
  <a href="#%EF%B8%8F-commands">Commands</a> ·
  <a href="#-faq">FAQ</a> ·
  <a href="#-yggdrasil-vs-alternatives">Comparison</a>
</p>

<p align="center">
  <a href="./README.md"><img src="https://img.shields.io/badge/README-English-blue" alt="English"></a>
  <a href="./i18n/README.ru.md"><img src="https://img.shields.io/badge/docs-Русский-darkblue" alt="Русский"></a>
  <a href="./i18n/README.zh.md"><img src="https://img.shields.io/badge/docs-简体中文-red" alt="简体中文"></a>
  <a href="./i18n/README.es.md"><img src="https://img.shields.io/badge/docs-Español-orange" alt="Español"></a>
  <a href="./i18n/README.fr.md"><img src="https://img.shields.io/badge/docs-Français-blue" alt="Français"></a>
</p>

---

Every new chat, your AI forgets. You re-explain the project, the decisions, the gotchas — every time, in every tool. **Yggdrasil is a tiny always-on memory brain that any agent plugs into.** Open a new session in any project, with any AI, and it already knows what you decided, what broke, and what's still open — and it quietly learns from your work in the background.

```text
$ cd ~/projects/checkout-api && claude        # a brand-new session

🌳 Yggdrasil  (injected automatically at session start)
   You are Yggdrasil — your persistent assistant across tools and projects.
   Open follow-ups & status:
   • [project_status] payments refactor: idempotency keys added; open: e2e tests
   Durable memory for `checkout-api`:
   • [debugging_lesson] webhook 401 → signing secret rotated; update env + redeploy

> "have I solved a flaky websocket reconnect anywhere before?"

🌳 recall → found in project `realtime-dash`:
   refresh the token *before* opening the socket, then retry with capped backoff.
```

No "let me remind you what we did yesterday." It's just there.

## ❌ Without Yggdrasil

- 🔁 You re-explain project context to the AI in every new chat.
- 🧩 Lessons learned in one project never reach the next one.
- 🤖 Switch from Claude Code to Codex → the new tool knows nothing.
- 🗑️ Hard-won debugging insights vanish when the session ends.

## ✅ With Yggdrasil

- 🧠 **Persistent memory** — decisions, lessons, and status survive across sessions.
- 🔌 **Any agent, one brain** — Claude Code, Codex, any MCP host share the same memory.
- 🌐 **Cross-project recall** — *"this looks like what you did in project B — reuse it?"*
- 🌱 **Self-learning** — a local model consolidates memory in the background (zero API tokens).
- 🪪 **A soul** — give it a name and personality; it shows up the same in every tool.
- 🔒 **100% local & private** — your memory lives on your machine. No cloud, no account.

## 🚀 Quickstart

> **Requirements:** macOS, Python 3.10+ *(or let `uv`/`npx` fetch Python for you)*. Optional (for semantic search): [Ollama](https://ollama.com).

Install with whatever you already use — **every channel installs the same engine:**

| Tool | Command |
| --- | --- |
| **uv** _(recommended)_ | `uvx --from yggdrasil-memory ygg install` |
| **npm / npx** | `npx yggdrasil-memory install` |
| **pipx** | `pipx install yggdrasil-memory && ygg install` |
| **pip** | `pip install yggdrasil-memory && ygg install` |
| **Homebrew** _(macOS)_ | `brew install VonderVuflya/tap/yggdrasil && ygg install` |
| **from source** | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` |

> Registry channels go live as each is published (see [RELEASING.md](./RELEASING.md)); the **from source** line works against this repo today. `npx` and `uvx` can fetch Python for you.

That's it. `ygg install`:
1. 🔍 detects your CPU/RAM/GPU and **recommends models that fit your machine** (or choose `none` for a zero-config, lexical-only setup),
2. 🔑 generates a private auth token (never hardcoded),
3. 🛎️ installs an always-on background service (auto-starts at login, restarts on crash),
4. 🤝 registers the memory tools with **Claude Code and Codex**,
5. 🪝 (optional) enables a session-start hook that auto-injects your project memory.

Check the install any time with `ygg doctor`; upgrade later with `ygg update`.

Prefer to just try the engine first, without installing a service?

```bash
uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg serve --reset --db /tmp/ygg.sqlite   # runs on :42069
```

## 🧠 How it works

Yggdrasil is **memory + tools** — the *intelligence* is your LLM. It just makes sure the right memory is in front of the right agent at the right moment.

```text
   Claude Code / Codex / any MCP host
                 │   (MCP tools: ygg_search, ygg_recall, ygg_remember … )
                 ▼
        ┌─────────────────────┐      SessionStart hook injects
        │  Yggdrasil engine    │◀──── identity + project memory + open follow-ups
        │  (always-on daemon)  │
        │  SQLite + FTS5       │      background local model (optional)
        │  + optional vectors  │────▶ dedupes / links / consolidates memory
        └─────────────────────┘
                 │ materializes to
                 ▼
          📓 Obsidian vault (human-readable, editable)
```

- **Engine** — a stdlib-only HTTP server over SQLite + FTS5. Zero dependencies, ~21 MB RAM.
- **Retrieval** — lexical by default; add a local embedding model for semantic + cross-lingual search.
- **Governance** — duplicates / stale / conflicting memories are surfaced for review; changes are non-destructive (archive, never delete).
- **Obsidian** — every memory is also a Markdown note you can read and edit.

## ⭐ Features

- 🧠 **Durable cross-session memory** for any MCP-compatible agent.
- 🌐 **Cross-project recall** + a proactive "you solved this before" contract.
- 🔎 **Hybrid retrieval** — BM25 + optional dense embeddings, fused; cross-lingual (e.g. EN↔RU).
- 🪪 **Identity / persona** injected every session (the "Jarvis feel").
- 📌 **Status & follow-ups** surfaced at session start — *"what's the status of X?"* answers instantly.
- 🌱 **Background self-learning** — a small local model consolidates memory (propose-safe by default).
- 🧹 **Governance loop** — review queue + non-destructive archive/merge.
- 📓 **Obsidian materialization** — readable, editable, portable.
- 🔒 **Local-first & private** — no cloud, no account, your data stays put.
- 🪶 **Zero hard dependencies** — pure Python stdlib; optional local models via Ollama.

## 🛠️ Commands

**Memory ops — `ygg <command>`** (agent-facing)

| Command | What it does |
| --- | --- |
| `health` | Check the engine is alive |
| `bootstrap --project P` | Pull a project's memory before starting work |
| `search --project P --query "…"` | Project-scoped search (`--type`, `--limit`, `--json`) |
| `recall --query "…"` | **Cross-project** search — "have I done this anywhere?" |
| `remember --project P --type debugging_lesson --content "…"` | Save a durable memory (secret-guarded, deduped) |
| `materialize --id ID --project P` | Export one memory to an Obsidian note |

**Service & setup — `ygg <command>`** (lifecycle)

| Command | What it does |
| --- | --- |
| `install` | Guided wizard → background service + MCP registration |
| `recommend` | Show the hardware-aware model catalog |
| `status` · `start` · `stop` · `restart` · `logs` | Manage the always-on daemon |
| `hooks` · `unhooks` | Enable/disable the SessionStart auto-bootstrap hook |
| `consolidate` · `unconsolidate` | Schedule/remove background memory consolidation |
| `token` · `uninstall` | Print the auth token · remove service + registration |

**MCP tools** (what agents see): `ygg_health`, `ygg_bootstrap`, `ygg_search`, `ygg_recall`, `ygg_remember`, `ygg_materialize`.

## 🔌 Use it with your agent

- **Claude Code** — after `ygg install`, the tools are registered (`/mcp` shows `yggdrasil`) and the SessionStart hook auto-injects memory. Just open a project and work.
- **Codex** — registered too; approve the `ygg_*` tool call once per session.
- **Any MCP host** — point it at `ygg mcp` (stdio) with `YGG_MUNINN_URL` + `YGG_MUNINN_TOKEN`.

Give it a personality — edit `~/.yggdrasil/identity.json`:

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

## 📊 Footprint & quality

**Footprint** (measured, 13 memories): **~21 MB RAM**, **~0% idle CPU**, **zero dependencies** (Python 3.10+ stdlib). Disk ≈ tens of KB per memory. Dense search is optional and adds a local Ollama model (e.g. `all-minilm`, 45 MB).

**Retrieval quality** (`eval/ygg_eval.py`, recall@1):

| Mode | recall@1 | paraphrase | crosslingual (EN→RU) |
| --- | --- | --- | --- |
| lexical (default) | 0.63 | 0.00 | 0.00 |
| dense · `all-minilm` (45 MB, EN) | 0.75 | 0.67 | 0.00 |
| dense · `paraphrase-multilingual` (~560 MB) | **0.94** | 0.67 | **1.00** |

`keyword` and `identifier` queries are 1.0 in every mode. Run it yourself: `python3 eval/ygg_eval.py`.

## ❓ FAQ

<details>
<summary><b>Does it send my code or memory to the cloud?</b></summary>

No. The engine, the database, and the optional models all run locally. No account, no telemetry. Your memory never leaves your machine.
</details>

<details>
<summary><b>How is this different from Context7 / RAG over docs?</b></summary>

Context7 fetches up-to-date <i>public library docs</i> (the latest React/Next.js API). Yggdrasil remembers <i>your own work</i> — your decisions, lessons, and project status. They're complementary; run both. See <a href="#-yggdrasil-vs-alternatives">comparison</a>.
</details>

<details>
<summary><b>Does it automatically remember everything?</b></summary>

No — by design. Retrieval is automatic; <i>writing</i> is deliberate (the agent calls <code>ygg_remember</code> for durable lessons). Auto-capturing everything pollutes memory, so we don't. A background model consolidates what's already saved (propose-only by default).
</details>

<details>
<summary><b>Do I need a GPU or an API key?</b></summary>

No. The default is pure lexical search — zero dependencies, instant. Semantic search is opt-in and uses a <i>local</i> model via Ollama (no API key). The installer recommends a model that fits your hardware.
</details>

<details>
<summary><b>How many tokens does it cost my agent?</b></summary>

Very few. Session start injects ~300 tokens of memory; each tool call returns a small snippet. All the heavy work (indexing, embeddings, consolidation) runs off-LLM on your machine.
</details>

<details>
<summary><b>Can I edit or delete memories by hand?</b></summary>

Yes. Memories materialize to Markdown notes in an Obsidian vault — read, edit, or remove them like any file. The engine never hard-deletes; it archives (reversible).
</details>

<details>
<summary><b>Is it production-ready?</b></summary>

It's an honest <b>alpha</b>: the happy path and the full governance loop are covered by passing gates (<code>scripts/run_gates.sh</code>). Not yet hardened for multi-user/production.
</details>

## 🆚 Yggdrasil vs alternatives

| | **Yggdrasil** | Context7 | Plain LLM memory |
| --- | --- | --- | --- |
| Knows **your** decisions/lessons | ✅ | ❌ | ⚠️ within one session |
| Up-to-date public library docs | ❌ (use Context7) | ✅ | ❌ |
| Cross-session & cross-**agent** | ✅ | ✅ | ❌ |
| Cross-**project** recall | ✅ | — | ❌ |
| Writes/accumulates your memory | ✅ | ❌ (read-only) | ⚠️ |
| Local & private | ✅ | ☁️ hosted | depends |
| Self-consolidating | ✅ | ❌ | ❌ |

**TL;DR:** Context7 = correct API of *someone else's* library. Yggdrasil = memory of *your own* work. Use both.

## 🗺️ Roadmap

- 🔗 Relation graph (`SOLVES` / `SUPERSEDES` / `CONTRADICTS`) for richer reasoning.
- 🛰️ Multi-device sync — continue literally from any machine.
- 🧪 Stronger optional models for safe autonomous consolidation.
- 🐧 Linux/Windows service installers (currently macOS launchd).

## 🤝 Contributing

Issues and PRs welcome. Run `scripts/run_gates.sh` and `python3 -m unittest discover -s tests` before submitting — all gates must stay green.

## 📜 License

**Elastic License 2.0** — see [LICENSE](./LICENSE). You may freely use, modify, self-host, and redistribute Yggdrasil. You may **not** sell it as a product or offer it to others as a hosted/managed service. It is source-available — not OSI open source.

> An external **Muninn** backend (`github.com/wjohns989/Muninn`, Apache-2.0) is optional and **not bundled**; point `YGG_MUNINN_URL` at your own instance. Preserve its `NOTICE`/attribution if you redistribute it.
