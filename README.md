<!-- mcp-name: io.github.VonderVuflya/yggdrasil -->
<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>One shared, durable memory for all your AI coding agents.</b><br/>
Claude Code, Codex, and any MCP host remember your decisions, lessons, and project status — across sessions, tools, and projects.</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-Elastic%202.0-blue.svg" alt="Elastic License 2.0">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/deps-zero%20(stdlib)-brightgreen" alt="zero deps">
  <img src="https://img.shields.io/badge/MCP-Claude%20·%20Codex%20·%20any%20host-purple" alt="MCP">
  <img src="https://img.shields.io/badge/local--first-100%25%20private-success" alt="local-first">
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="alpha">
</p>

<p align="center">
  <a href="#-install">Install</a> ·
  <a href="#-how-it-works">How it works</a> ·
  <a href="#-yggdrasil-vs-the-rest">Compare</a> ·
  <a href="#-commands">Commands</a> ·
  <a href="#-faq">FAQ</a>
</p>

<p align="center">
  <a href="./README.md"><img src="https://img.shields.io/badge/README-English-blue" alt="English"></a>
  <a href="./i18n/README.ru.md"><img src="https://img.shields.io/badge/docs-Русский-darkblue" alt="Русский"></a>
  <a href="./i18n/README.zh.md"><img src="https://img.shields.io/badge/docs-简体中文-red" alt="简体中文"></a>
  <a href="./i18n/README.es.md"><img src="https://img.shields.io/badge/docs-Español-orange" alt="Español"></a>
  <a href="./i18n/README.fr.md"><img src="https://img.shields.io/badge/docs-Français-blue" alt="Français"></a>
</p>

---

Every new chat, your AI forgets. You re-explain the project, the decisions, the gotchas — every time, in every tool. **Yggdrasil is a tiny always-on memory brain that any agent plugs into.** Open a new session, in any project, with any AI, and it already knows what you decided, what broke, and what's still open — and it keeps learning in the background.

```text
$ cd ~/projects/checkout-api && claude        # a brand-new session

🌳 Yggdrasil  (injected automatically at session start)
   Open follow-ups & status:
   • [project_status] payments refactor: idempotency keys added; open: e2e tests
   Durable memory for `checkout-api`:
   • [debugging_lesson] webhook 401 → signing secret rotated; update env + redeploy

> "have I solved a flaky websocket reconnect anywhere before?"

🌳 recall → found in project `realtime-dash`:
   refresh the token *before* opening the socket, then retry with capped backoff.
```

No "let me remind you what we did yesterday." It's just there.

## Why

**Without Yggdrasil** you re-explain context in every new chat, lessons from one project never reach the next, switching Claude Code → Codex starts from zero, and hard-won debugging insights die with the session.

**With Yggdrasil:**

- 🧠 **Persistent memory** — decisions, lessons, and status survive across sessions.
- 🔌 **Any agent, one brain** — Claude Code, Codex, any MCP host share the same memory.
- 🌐 **Cross-project recall** — *"this looks like what you did in project B — reuse it?"*
- 🌱 **Self-learning** — a local model consolidates memory in the background (zero API tokens).
- 🪪 **A soul** — give it a name and personality; it shows up the same in every tool.
- 🔒 **100% local & private** — your memory lives on your machine. No cloud, no account.

## 🚀 Install

> **Requirements:** macOS (Linux/Windows soon), Python 3.10+ — or let `uv`/`npx` fetch Python for you. Semantic search is optional and uses a local [Ollama](https://ollama.com) model.

```bash
uvx --from yggdrasil-memory ygg install      # recommended
```

<details>
<summary>Prefer npm, pipx, pip, Homebrew, or source? (same engine)</summary>

| Tool | Command |
| --- | --- |
| **npm / npx** | `npx yggdrasil-memory install` |
| **pipx** | `pipx install yggdrasil-memory && ygg install` |
| **pip** | `pip install yggdrasil-memory && ygg install` |
| **Homebrew** _(macOS)_ | `brew install VonderVuflya/tap/yggdrasil && ygg install` |
| **from source** | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` |

</details>

`ygg install` is a one-time guided setup: it detects your hardware and **recommends a local model that fits** (or pick `none` for a zero-config, lexical-only setup), generates a private auth token, installs an **always-on background service**, and **registers the tools with Claude Code and Codex**. Check it any time with `ygg doctor`; upgrade with `ygg update`.

Just want to kick the tyres without installing a service? `uvx --from yggdrasil-memory ygg serve --reset --db /tmp/ygg.sqlite`.

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
- **Retrieval** — lexical by default; add a local embedding model for semantic + cross-lingual search. Frequently-recalled and pinned memories rank higher.
- **Governance** — duplicates / conflicts are surfaced for review; changes are non-destructive (archive, never delete).
- **Obsidian** — every memory is also a Markdown note you can read and edit.

## 🆚 Yggdrasil vs the rest

These tools each own a **different layer** of the AI-context stack. The layer nobody filled — **durable, cross-session, cross-agent memory of _your own_ work** — is exactly where Yggdrasil sits. It doesn't compete with them; it's the memory they all plug into.

| Tool | What it owns | Use it *with* Yggdrasil because… |
| --- | --- | --- |
| **[context-mode](https://github.com/mksglu/context-mode)** | keeps the **live context window** lean — sandboxes tool output, "think in code", in-session continuity. Ephemeral by design ("fresh session = clean slate"). | context-mode trims *today's* session; Yggdrasil is the durable memory it deliberately throws away. Different time-horizons — run both. |
| **[Context7](https://github.com/upstash/context7)** | fresh **public library docs** (the latest React/Stripe API), read-only. | Context7 knows the *library's* API; Yggdrasil knows *your* decisions and gotchas. |
| **[autoresearch](https://github.com/karpathy/autoresearch)** | an autonomous **experiment loop** (edit → run → measure → keep/revert). | the loop wakes up cold each time; Yggdrasil gives it long-term memory of what it already tried → [integration](./integrations/autoresearch/). |
| **plain LLM "memory"** | a per-session scratchpad, one tool at a time. | Yggdrasil is durable, cross-project, cross-agent, governed, and local. |

**TL;DR:** other tools fetch docs, run experiments, or compress one session. **Yggdrasil is the durable memory of _your own_ work that they were all missing — use it alongside them and you only win.**

## 🧰 Commands

Agents see six MCP tools: `ygg_health`, `ygg_bootstrap`, `ygg_search`, `ygg_recall`, `ygg_remember`, `ygg_materialize`. After `ygg install` they're auto-registered with Claude Code and Codex — just open a project and work.

<details>
<summary>Full <code>ygg</code> CLI reference</summary>

**Memory ops**

| Command | What it does |
| --- | --- |
| `ygg recall --query "…"` | **Cross-project** search — "have I done this anywhere?" |
| `ygg search --project P --query "…"` | Project-scoped search (`--type`, `--tag`, `--limit`, `--json`) |
| `ygg remember --project P --type debugging_lesson --content "…"` | Save a durable memory (secret-guarded, deduped; `--tag` to label) |
| `ygg bootstrap --project P` | Pull a project's memory before starting work |
| `ygg pin --id ID` · `ygg unpin --id ID` | Pin a memory so it reliably surfaces |
| `ygg supersede --id ID` | Archive an outdated memory a newer one replaces |
| `ygg materialize --id ID --project P` | Export one memory to an Obsidian note |

**Service & setup**

| Command | What it does |
| --- | --- |
| `ygg install` · `ygg setup` | Guided setup → background service + MCP registration |
| `ygg doctor` · `ygg update` | Diagnose the install · redeploy the latest code |
| `ygg status` · `start` · `stop` · `restart` · `logs` | Manage the always-on daemon |
| `ygg hooks` · `unhooks` | Enable/disable the SessionStart auto-bootstrap hook |
| `ygg recommend` | Show the hardware-aware model catalog |
| `ygg token` · `uninstall` | Print the auth token · remove service + registration |

Give it a personality — edit `~/.yggdrasil/identity.json`:

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

</details>

## ❓ FAQ

<details>
<summary><b>Does it send my code or memory to the cloud?</b></summary>

No. The engine, the database, and the optional models all run locally. No account, no telemetry. Your memory never leaves your machine.
</details>

<details>
<summary><b>Does it automatically remember everything?</b></summary>

No — by design. Retrieval is automatic; *writing* is deliberate (the agent calls `ygg_remember` for durable lessons). Auto-capturing everything pollutes memory, so we don't. A background model consolidates what's already saved (propose-only by default).
</details>

<details>
<summary><b>Do I need a GPU or an API key?</b></summary>

No. The default is pure lexical search — zero dependencies, instant. Semantic search is opt-in and uses a *local* model via Ollama (no API key). The installer recommends a model that fits your hardware.
</details>

<details>
<summary><b>How heavy is it, and how many tokens does it cost?</b></summary>

Tiny. The engine is **~21 MB RAM, ~0% idle CPU, zero dependencies** (Python stdlib); disk is tens of KB per memory. Session start injects ~300 tokens of memory and each tool call returns a small snippet — all the heavy work (indexing, embeddings, consolidation) runs off-LLM on your machine.
</details>

<details>
<summary><b>How good is retrieval?</b></summary>

Measured by `eval/ygg_eval.py` (35 labelled cases, dev/holdout split), recall@1:

| Mode | recall@1 | paraphrase | crosslingual (EN→RU) |
| --- | --- | --- | --- |
| lexical (default) | 0.77 | 0.63 | 0.00 |
| dense · `all-minilm` (45 MB, EN) | 0.83 | 0.88 | 0.00 |
| dense · `paraphrase-multilingual` (~560 MB) | **0.94** | 0.88 | **0.80** |

`keyword` and `identifier` queries are 1.0 in every mode; with the multilingual model **recall@3 = 1.0** (every target in the top 3).
</details>

<details>
<summary><b>Can I edit or delete memories by hand?</b></summary>

Yes. Memories materialize to Markdown notes in an Obsidian vault — read, edit, or remove them like any file. The engine never hard-deletes; it archives (reversible).
</details>

<details>
<summary><b>Is it production-ready?</b></summary>

It's an honest **alpha**: the happy path and the full governance loop are covered by passing gates (`scripts/run_gates.sh`). Not yet hardened for multi-user/production.
</details>

## 🗺️ Roadmap

- 🛰️ **Cross-surface sync** — connect from ChatGPT / Claude on the web and mobile; one memory across CLI, browser, and phone.
- 🔗 Relation graph (`SOLVES` / `SUPERSEDES` / `CONTRADICTS`) for richer reasoning.
- 🐧 Linux/Windows service installers (implemented; final on-device testing).

## 🤝 Contributing

Issues and PRs welcome. Run `scripts/run_gates.sh` and `python3 -m unittest discover -s tests` before submitting — all gates must stay green.

## 📜 License

**Elastic License 2.0** — see [LICENSE](./LICENSE). You may freely use, modify, self-host, and redistribute Yggdrasil. You may **not** sell it as a product or offer it to others as a hosted/managed service. It is source-available — not OSI open source.
