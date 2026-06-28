<!-- mcp-name: io.github.VonderVuflya/yggdrasil -->
<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>One shared, durable memory for all your AI coding agents.</b><br/>
Claude Code, Codex, and any MCP host remember your decisions, lessons, and project status — across sessions, tools, and projects.</p>

<p align="center">
  <a href="https://github.com/VonderVuflya/Yggdrasil/releases/latest"><img src="https://img.shields.io/github/v/release/VonderVuflya/Yggdrasil?label=release&color=blue" alt="Latest release"></a>
  <a href="https://pypi.org/project/yggdrasil-memory/"><img src="https://img.shields.io/pypi/v/yggdrasil-memory?label=PyPI&color=blue" alt="PyPI"></a>
  <a href="https://pypistats.org/packages/yggdrasil-memory"><img src="https://img.shields.io/pypi/dm/yggdrasil-memory?label=PyPI%20downloads&color=blue" alt="PyPI downloads"></a>
  <a href="https://www.npmjs.com/package/yggdrasil-memory"><img src="https://img.shields.io/npm/dm/yggdrasil-memory?label=npm%20downloads&color=red" alt="npm downloads"></a>
  <a href="https://github.com/VonderVuflya/Yggdrasil/stargazers"><img src="https://img.shields.io/github/stars/VonderVuflya/Yggdrasil?style=flat&color=yellow" alt="GitHub stars"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-Elastic%202.0-blue.svg" alt="Elastic License 2.0"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/deps-zero%20(stdlib)-brightgreen" alt="zero deps">
  <img src="https://img.shields.io/badge/MCP-Claude%20·%20Codex%20·%20Desktop-purple" alt="MCP">
  <img src="https://img.shields.io/badge/local--first-100%25%20private-success" alt="local-first">
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="alpha">
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> ·
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
  <a href="./i18n/README.ja.md"><img src="https://img.shields.io/badge/docs-日本語-red" alt="日本語"></a>
  <a href="./i18n/README.de.md"><img src="https://img.shields.io/badge/docs-Deutsch-yellow" alt="Deutsch"></a>
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

## 🚀 Quick Start

> **Requirements:** macOS (Linux/Windows soon), Python 3.10+ — or let `uv`/`npx` fetch Python for you. Semantic search is optional and uses a local [Ollama](https://ollama.com) model.

**Option A — install as a plugin** (one step, right inside your agent — zero-config). In **Claude Code**:

```text
/plugin marketplace add VonderVuflya/Yggdrasil
/plugin install yggdrasil
```

The engine lazy-starts on first use and generates its own local token — **no API key, no cloud, nothing to configure.** (Codex and Cursor use the same flow.)

**Option B — install the full service** (always-on daemon + auto-inject at session start + optional local models):

```bash
uvx --from yggdrasil-memory ygg install      # one-time guided setup
```

<details>
<summary>Every install channel (same engine)</summary>

| Host / tool | Command |
| --- | --- |
| **Claude Code · Codex · Cursor** (plugin) | `/plugin marketplace add VonderVuflya/Yggdrasil` → `/plugin install yggdrasil` |
| **uvx** _(recommended CLI)_ | `uvx --from yggdrasil-memory ygg install` |
| **npm / npx** | `npx yggdrasil-memory install` |
| **pipx** | `pipx install yggdrasil-memory && ygg install` |
| **pip** | `pip install yggdrasil-memory && ygg install` |
| **Homebrew** _(macOS)_ | `brew install VonderVuflya/tap/yggdrasil && ygg install` |
| **Claude Desktop** _(app)_ | drag the `.mcpb` from the [latest release](https://github.com/VonderVuflya/Yggdrasil/releases/latest) onto Settings → Extensions ([guide](./packaging/mcpb/README.md)) |
| **from source** | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` |

</details>

`ygg install` is a one-time guided setup: it detects your hardware and **recommends a local model that fits** (or pick `none` for a zero-config, lexical-only setup), generates a private auth token, installs an **always-on background service**, and **registers the tools with Claude Code and Codex**.

**Verify & use:**
```bash
ygg doctor       # engine · models · MCP registration · hook — all green?
```
Then just work. Ask your agent *"recall what we decided about this project"*, or tell it *"remember this decision"* — and in the next session it's already there.

**Already have history?** Seed memory from your existing **Claude Code + Codex** transcripts, Obsidian vaults, and `CLAUDE.md` repos in one shot — all distilled locally:

```bash
ygg seed --dry-run    # see what it'd import; drop --dry-run to distill for real
```

Just kicking the tyres? `uvx --from yggdrasil-memory ygg serve --reset --db /tmp/ygg.sqlite`.

## 🔌 More ways to connect

Beyond the plugin and `ygg install` above:

- 🖥️ **Claude Desktop (app)** — install the MCP extension: grab `yggdrasil-<version>.mcpb` from the [latest release](https://github.com/VonderVuflya/Yggdrasil/releases/latest) (or `packaging/mcpb/`), drag it onto **Settings → Extensions**, and paste your token (`ygg token`). The desktop app now shares the **same memory** as your CLI agents. → [setup guide](./packaging/mcpb/README.md)
- 🧠 **Skill (any Claude)** — the [`yggdrasil-memory` skill](./skills/) teaches the agent the workflow: recall before work, remember after. Upload `yggdrasil-memory.zip` via **Settings → Skills → Create skill → Upload a skill**.

> **MCP vs Skill:** MCP connects the *tools* (how to reach memory); the Skill teaches *when to use them*. Use both for the best behavior.

## 🧠 How it works

Yggdrasil is **memory + tools** — the *intelligence* is your LLM. It just makes sure the right memory is in front of the right agent at the right moment.

- 🛎️ **Always-on daemon** — a tiny local service (~21 MB RAM) your agents reach over MCP tools (`ygg_search`, `ygg_recall`, `ygg_remember` …).
- 🪝 **Session start** — a hook auto-injects identity, project status, and open follow-ups.
- 📌 **Ranking** — frequently-recalled and pinned memories surface higher (storage & tiers below ↓).
- 🧹 **Governance** — duplicates / conflicts are surfaced for review; changes are non-destructive (archive, never delete).
- 📓 **Obsidian** — every memory is also a Markdown note you can read and edit.

## 🎛️ Memory tiers — zero-config by default

Out of the box, Yggdrasil runs on **SQLite + FTS5 with zero dependencies** — instant keyword (lexical) search, no models, no GPU, nothing to download. Already useful: recall@1 ≈ 0.77.

Want it to match by **meaning** and across languages? If your hardware allows, `ygg install` can pull optional **local models via [Ollama](https://ollama.com)** — it detects your CPU/RAM/GPU and recommends a fit (or choose `none` to stay zero-config). Two optional, independent tiers:

```text
   your agents ─► ygg_search / ygg_recall / ygg_remember
                             │
                 ┌───────────▼───────────┐
                 │   SQLite  (storage)    │
                 │   ├─ FTS5 / BM25  ─────┼─►  keyword search   (always · zero-dep)
                 │   └─ embedding column ─┼─►  vector search    (optional)
                 └───────────▲───────────┘
                             │ vectors in
       optional · local:  Ollama models ── only COMPUTE vectors / run consolidation
```

| Tier | You add | You gain |
| --- | --- | --- |
| **0 · default** | nothing — SQLite + FTS5 | keyword search, zero deps, instant — recall@1 ≈ **0.77** |
| **1 · semantic** | an **embedding** model via Ollama (e.g. `all-minilm` 45 MB · `paraphrase-multilingual` ~560 MB) | search by **meaning** + cross-lingual — recall@1 ≈ **0.94** |
| **2 · self-learning** | a small **consolidation** LLM via Ollama (e.g. `qwen2.5:1.5b` ~1 GB) | background dedupe/merge of memory (propose-safe) |

Ollama only **computes** the vectors / runs the background model — the vectors and all memories still live in the **same SQLite**. Tiers are independent and opt-in.

<details>
<summary>Full model menu (or run <code>ygg recommend</code>)</summary>

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

</details>

Everything stays **100% local — zero API tokens, no cloud.** The installer recommends models that fit your hardware (or pick `none` to stay zero-config).

> The engine itself is swappable — any service meeting the `MemoryBackend` contract is a drop-in (point `YGG_ENGINE_URL` at it); SQLite is the zero-dep default. See [docs/backend-boundary.md](./docs/backend-boundary.md).

## 🆚 Yggdrasil vs the rest

The closest tool is **claude-mem** — also durable memory for coding agents, but a *heavier, capture-everything* system: it auto-records every session and AI-compresses it (needs Node + Bun + a vector DB). **mem0** is a memory *SDK* for apps to remember their users. context-mode and Context7 own **different layers** (your live context window; fresh library docs). Yggdrasil is **install-and-go, zero-dependency, local-first memory of _your own_ work** — curated, not a firehose, stored as plain Markdown you can edit.

| | **Yggdrasil** | [claude-mem](https://github.com/thedotmack/claude-mem) | [mem0](https://github.com/mem0ai/mem0) | [context-mode](https://github.com/mksglu/context-mode) | [Context7](https://github.com/upstash/context7) |
| --- | --- | --- | --- | --- | --- |
| Durable memory of **your own work** (decisions, lessons, status) | ✅ | ✅ | ✅ | ⚠️ in-session | ❌ |
| **Drop-in** for your agents, *no code* (install + MCP) | ✅ | ✅ | ⚠️ *SDK* | ✅ | ✅ |
| **Zero dependencies** (stdlib + SQLite; no Node/Bun/vector DB) | ✅ | ❌ | ❌ | ❌ | — |
| Works with **no LLM & no API key** (lexical default) | ✅ | ❌ *AI-compresses* | ❌ *needs an LLM* | ✅ | ❌ |
| **Curated** & editable as plain Markdown (not capture-everything) | ✅ | ❌ *auto-captures all* | ⚠️ | ❌ | — |
| **100% local & private** (no cloud by default) | ✅ | ⚠️ | ⚠️ *cloud default* | ✅ | ☁️ hosted |
| Cross-**project** recall ("solved this in project B") | ✅ | ⚠️ | ⚠️ | ❌ | — |
| One memory shared **across tools** (Claude Code · Codex · any MCP host) | ✅ | ✅ | ⚠️ *per-app* | ✅ | ✅ |
| Up-to-date public **library docs** | ❌ *(use Context7)* | ❌ | ❌ | ❌ | ✅ |

> **claude-mem vs Yggdrasil, in one line:** claude-mem auto-captures *everything* and AI-compresses it (Node + Bun + a vector DB; ~84k★, ships a crypto token) — the store grows with every session. Yggdrasil keeps the *few things that matter* — curated and **semantically de-duped** (near-identical lessons collapse, so it stays small and high-signal), zero-dependency, stored as plain rows you can grep, edit, and own — no AI required, no token. Different philosophy; you can run both.

> **mem0 vs Yggdrasil, in one line:** mem0 is a memory **SDK/platform for building apps that remember their users** (you write code; it usually calls an LLM, cloud by default). Yggdrasil is **drop-in, local-first memory of _your own_ work for the agents you already code with.** Different job — pick by who you are.

> Also pairs well with [**autoresearch**](https://github.com/karpathy/autoresearch) — an autonomous experiment loop (not a memory tool); Yggdrasil gives it long-term memory of what it already tried → [integration](./integrations/autoresearch/).

**TL;DR:** want automatic capture-everything across many IDEs and don't mind a heavier stack → **claude-mem**. Building an AI *product* that must remember its users at scale → **mem0**. Want a tiny, local, *curated* memory you own — zero deps, no AI required — for the coding agents you already use → **Yggdrasil**.

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

**Cold start — seed from your existing work**

| Command | What it does |
| --- | --- |
| `ygg seed` | Distill your **Claude Code + Codex** transcripts, Obsidian vaults, and `CLAUDE.md` repos into lessons — incremental, deduped, fully local |
| `ygg seed --dry-run` · `--force` | Discover + estimate only · re-distill everything |
| `ygg distill --source PATH` | Distill one dir/file into lessons |
| `ygg reindex` | Backfill embeddings for memories missing them (restores dense recall) |

Big sessions can be slow on a tiny model — point distillation at a beefier box on your LAN ([Configuration](#️-configuration) ↓):

```bash
ygg seed --ollama-url http://192.168.3.124:11434 --model llama3.2:3b --timeout 240
```

**Service & setup**

| Command | What it does |
| --- | --- |
| `ygg install` · `ygg setup` | Guided setup → background service + MCP registration |
| `ygg doctor` · `ygg update` | Diagnose the install (actionable fixes) · upgrade + redeploy |
| `ygg config` | Show/set persistent settings — `list` · `get` · `set` · `unset` |
| `ygg register` | (Re)register the MCP server with Claude Code / Codex |
| `ygg status` · `start` · `stop` · `restart` · `logs` | Manage the always-on daemon |
| `ygg hooks` · `unhooks` | Enable/disable the SessionStart auto-bootstrap hook |
| `ygg recommend` | Show the hardware-aware model catalog |
| `ygg token` · `uninstall` | Print the auth token · remove service + registration |

Give it a personality — edit `~/.yggdrasil/identity.json`:

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

</details>

## ⚙️ Configuration

Yggdrasil works with zero config. When you *do* want to change something, every setting resolves the same way:

> **`--flag`  >  environment variable  >  `~/.yggdrasil/config.json`  >  default**

Use a flag for one run, or `ygg config set` to make it stick:

```bash
ygg config list                       # effective values + where each one comes from
ygg config set distill_timeout 240    # persist a setting
ygg config get distill_url
ygg config unset bg_model             # back to the default
```

| Setting | Default | What it controls |
| --- | --- | --- |
| `distill_url` | local Ollama | Endpoint for `ygg seed` / consolidation — point at a beefier box |
| `distill_timeout` | `120` | Per-file distill timeout (seconds) — raise for big sessions |
| `bg_model` | `qwen2.5:1.5b` | Model used to distill & consolidate |
| `embed_model` · `embed_url` | local | Embedding model + endpoint (daemon-level; run `ygg redeploy` to apply) |
| `user_id` · `namespace` | `demo-user` · `yggdrasil-demo` | Identity / namespace for stored memories |

**Distill on another machine.** Distillation (`ygg seed`) is heavy but occasional; embeddings are light but constant. So `distill_url` is deliberately kept separate from `embed_url` — send distillation to a powerful box on your LAN while embeddings (and your data) stay local and always-on:

```bash
# on the beefy box (B): expose Ollama to the LAN + pull the model
OLLAMA_HOST=0.0.0.0:11434 ollama serve
ollama pull llama3.2:3b

# on your laptop (A): make B the default distill endpoint
ygg config set distill_url http://192.168.3.124:11434
ygg config set bg_model    llama3.2:3b
ygg seed     # distills on B; your SQLite DB + embeddings never leave A
```

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
