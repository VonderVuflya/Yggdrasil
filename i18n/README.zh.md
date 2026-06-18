<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>为你所有的 AI 编程助手提供一份共享、持久的记忆。</b><br/>
让 Claude Code、Codex 以及任何 MCP 宿主，在不同会话、不同工具、不同项目之间都记得你的项目——记得决策、教训和进度。</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-Elastic%202.0-blue.svg" alt="Elastic License 2.0">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/deps-zero%20(stdlib)-brightgreen" alt="zero deps">
  <img src="https://img.shields.io/badge/MCP-Claude%20·%20Codex%20·%20any%20host-purple" alt="MCP">
  <img src="https://img.shields.io/badge/local--first-100%25%20private-success" alt="local-first">
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="alpha">
</p>

<p align="center">
  <a href="#-快速开始">快速开始</a> ·
  <a href="#-工作原理">工作原理</a> ·
  <a href="#%EF%B8%8F-命令">命令</a> ·
  <a href="#-常见问题">常见问题</a> ·
  <a href="#-yggdrasil-与同类方案对比">对比</a>
</p>

<p align="center">
  <a href="../README.md"><img src="https://img.shields.io/badge/README-English-blue" alt="English"></a>
  <a href="./README.ru.md"><img src="https://img.shields.io/badge/docs-Русский-darkblue" alt="Русский"></a>
  <a href="./README.zh.md"><img src="https://img.shields.io/badge/docs-简体中文-red" alt="简体中文"></a>
  <a href="./README.es.md"><img src="https://img.shields.io/badge/docs-Español-orange" alt="Español"></a>
  <a href="./README.fr.md"><img src="https://img.shields.io/badge/docs-Français-blue" alt="Français"></a>
</p>

---

每开一个新对话，你的 AI 都会忘得一干二净。于是你只能一遍又一遍地重新解释项目、决策、那些坑——每次都讲，每个工具里都讲。**Yggdrasil 是一个小巧、常驻的记忆大脑，任何助手都能接入它。** 在任何项目里、用任何 AI 开一个新会话，它都已经知道你定过什么、出过什么问题、还有什么没解决——而且它会在后台悄悄地从你的工作中学习。

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

不用再说“让我提醒你一下我们昨天做了什么”。它本来就在那儿。

## ❌ 没有 Yggdrasil 时

- 🔁 每开一个新对话，你都要把项目背景重新讲给 AI 听。
- 🧩 在一个项目里学到的教训，永远传不到下一个项目。
- 🤖 从 Claude Code 换到 Codex → 新工具对此一无所知。
- 🗑️ 来之不易的调试心得，会随着会话结束烟消云散。

## ✅ 有了 Yggdrasil 后

- 🧠 **持久记忆**——决策、教训和进度能跨越多个会话留存下来。
- 🔌 **众多助手，同一个大脑**——Claude Code、Codex 以及任何 MCP 宿主共享同一份记忆。
- 🌐 **跨项目回忆**——*“这看起来跟你在项目 B 里做过的事很像——要复用吗?”*
- 🌱 **自我学习**——一个本地模型在后台整合记忆(不消耗任何 API token)。
- 🪪 **一个灵魂**——给它起个名字、设定个性;它在每个工具里都以同样的形象出现。
- 🔒 **100% 本地且私密**——你的记忆就在你自己的机器上。无需云端,无需账号。

## 🚀 快速开始

> **环境要求:** macOS、Python 3.10+ *（或让 `uv`/`npx` 替你获取 Python）*。可选(用于语义搜索):[Ollama](https://ollama.com)。

用你已经在用的工具安装即可 —— **每个渠道安装的都是同一个引擎：**

| 工具 | 命令 |
| --- | --- |
| **uv** _(推荐)_ | `uvx --from yggdrasil-memory ygg install` |
| **npm / npx** | `npx yggdrasil-memory install` |
| **pipx** | `pipx install yggdrasil-memory && ygg install` |
| **pip** | `pip install yggdrasil-memory && ygg install` |
| **Homebrew** _(macOS)_ | `brew install VonderVuflya/tap/yggdrasil && ygg install` |
| **从源码** | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` |

> 各注册表渠道会在发布后陆续可用（参见 [RELEASING.md](../RELEASING.md)）；**从源码** 这一行现在就能用于本仓库。`npx` 和 `uvx` 可以替你获取 Python。

就这样。`ygg install` 会:
1. 🔍 检测你的 CPU/RAM/GPU,并**推荐适合你机器的模型**（或选择 `none` 进行零配置、仅词法的安装）,
2. 🔑 生成一个私有的鉴权 token(绝不硬编码),
3. 🛎️ 安装一个常驻的后台服务(登录时自动启动,崩溃后自动重启),
4. 🤝 把记忆工具注册到 **Claude Code 和 Codex**,
5. 🪝 (可选)启用一个会话启动钩子,自动注入你的项目记忆。

随时用 `ygg doctor` 检查安装；之后用 `ygg update` 升级。

只想先试试引擎本身,不安装服务?

```bash
uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg serve --reset --db /tmp/ygg.sqlite   # 运行于 :42069
```

## 🧠 工作原理

Yggdrasil 提供的是**记忆 + 工具**——*智能*来自你的 LLM。它只负责确保在恰当的时刻,把恰当的记忆送到恰当的助手面前。

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

- **引擎**——一个仅依赖标准库、运行在 SQLite + FTS5 之上的 HTTP 服务器。零依赖,约 21 MB 内存。
- **检索**——默认采用词法检索;加上一个本地嵌入模型即可实现语义检索与跨语言搜索。
- **治理**——重复、过期或相互冲突的记忆会被挑出来供你审查;所有改动都是非破坏性的(归档,绝不删除)。
- **Obsidian**——每一条记忆同时也是一份可读、可编辑的 Markdown 笔记。

## ⭐ 功能特性

- 🧠 **持久的跨会话记忆**,适用于任何兼容 MCP 的助手。
- 🌐 **跨项目回忆** + 一条主动的“你以前解决过这个”契约。
- 🔎 **混合检索**——BM25 + 可选的稠密嵌入,二者融合;支持跨语言(如 EN↔RU)。
- 🪪 **身份 / 人格**在每个会话中注入(那种“贾维斯”般的感觉)。
- 📌 **进度与待办**在会话开始时呈现——*“X 现在进展如何?”*能即刻得到答案。
- 🌱 **后台自我学习**——一个小型本地模型整合记忆(默认仅提议,安全可控)。
- 🧹 **治理闭环**——审查队列 + 非破坏性的归档/合并。
- 📓 **Obsidian 物化**——可读、可编辑、可移植。
- 🔒 **本地优先且私密**——无需云端、无需账号,你的数据原地不动。
- 🪶 **零硬性依赖**——纯 Python 标准库;可选的本地模型通过 Ollama 接入。

## 🛠️ 命令

**内存操作 —— `ygg <command>`**（面向 agent）

| 命令 | 作用 |
| --- | --- |
| `health` | 检查引擎是否在运行 |
| `bootstrap --project P` | 开始工作前拉取某个项目的记忆 |
| `search --project P --query "…"` | 项目范围内的搜索(`--type`、`--limit`、`--json`) |
| `recall --query "…"` | **跨项目**搜索——“我在哪儿做过这件事吗?” |
| `remember --project P --type debugging_lesson --content "…"` | 保存一条持久记忆(有密钥防护,会去重) |
| `materialize --id ID --project P` | 把一条记忆导出为一份 Obsidian 笔记 |

**服务与设置 —— `ygg <command>`**（生命周期）

| 命令 | 作用 |
| --- | --- |
| `install` | 引导式向导 → 后台服务 + MCP 注册 |
| `recommend` | 显示与硬件匹配的模型目录 |
| `status` · `start` · `stop` · `restart` · `logs` | 管理这个常驻守护进程 |
| `hooks` · `unhooks` | 启用/停用 SessionStart 自动 bootstrap 钩子 |
| `consolidate` · `unconsolidate` | 安排/移除后台记忆整合 |
| `token` · `uninstall` | 打印鉴权 token · 移除服务 + 注册 |

**MCP 工具**(助手所看到的):`ygg_health`、`ygg_bootstrap`、`ygg_search`、`ygg_recall`、`ygg_remember`、`ygg_materialize`。

## 🔌 搭配你的助手使用

- **Claude Code**——在 `ygg install` 之后,工具就已注册(`/mcp` 会显示 `yggdrasil`),SessionStart 钩子会自动注入记忆。打开一个项目直接干活即可。
- **Codex**——同样已注册;每个会话里批准一次 `ygg_*` 工具调用。
- **任何 MCP 宿主**——将其指向 `ygg mcp`（stdio）,并配上 `YGG_ENGINE_URL` 与 `YGG_ENGINE_TOKEN`。

给它设定个性——编辑 `~/.yggdrasil/identity.json`:

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

## 📊 占用与质量

**占用**(实测,13 条记忆):**约 21 MB 内存**、**约 0% 空闲 CPU**、**零依赖**(Python 3.10+ 标准库)。磁盘占用约为每条记忆几十 KB。稠密搜索是可选项,会额外加上一个本地 Ollama 模型(如 `all-minilm`,45 MB)。

**检索质量**(`eval/ygg_eval.py`,recall@1):

| 模式 | recall@1 | 同义改写 | 跨语言(EN→RU) |
| --- | --- | --- | --- |
| lexical(默认) | 0.63 | 0.00 | 0.00 |
| dense · `all-minilm`(45 MB,EN) | 0.75 | 0.67 | 0.00 |
| dense · `paraphrase-multilingual`(约 560 MB) | **0.94** | 0.67 | **1.00** |

`keyword` 与 `identifier` 类查询在所有模式下都是 1.0。自己跑一下:`python3 eval/ygg_eval.py`。

## ❓ 常见问题

<details>
<summary><b>它会把我的代码或记忆发到云端吗?</b></summary>

不会。引擎、数据库以及那些可选的模型全都在本地运行。没有账号,没有遥测。你的记忆永远不会离开你的机器。
</details>

<details>
<summary><b>它和 Context7 / 基于文档的 RAG 有什么不同?</b></summary>

Context7 抓取的是最新的<i>公开库文档</i>(比如最新的 React/Next.js API)。Yggdrasil 记住的是<i>你自己的工作</i>——你的决策、教训和项目进度。二者是互补的;两个一起用。参见<a href="#-yggdrasil-与同类方案对比">对比</a>。
</details>

<details>
<summary><b>它会自动记住所有东西吗?</b></summary>

不会——这是刻意的设计。检索是自动的;但<i>写入</i>是慎重的(助手会针对那些值得长期保留的教训调用 <code>ygg_remember</code>)。自动记录一切会污染记忆,所以我们不这么做。一个后台模型会整合已经保存下来的内容(默认仅提议)。
</details>

<details>
<summary><b>我需要 GPU 或 API key 吗?</b></summary>

不需要。默认是纯词法搜索——零依赖,即时可用。语义搜索是可选启用的,通过 Ollama 使用一个<i>本地</i>模型(无需 API key)。安装程序会推荐一个适合你硬件的模型。
</details>

<details>
<summary><b>它会消耗我的助手多少 token?</b></summary>

非常少。会话开始时注入约 300 token 的记忆;每次工具调用返回的也只是一小段内容。所有繁重的工作(索引、嵌入、整合)都在你机器上、LLM 之外完成。
</details>

<details>
<summary><b>我可以手动编辑或删除记忆吗?</b></summary>

可以。记忆会物化为 Obsidian 库中的 Markdown 笔记——你可以像对待任何文件一样读取、编辑或移除它们。引擎从不硬删除;它只做归档(可逆)。
</details>

<details>
<summary><b>它能用于生产环境了吗?</b></summary>

它是一个诚实的 <b>alpha</b> 版:常规流程和完整的治理闭环都有通过的门禁覆盖(<code>scripts/run_gates.sh</code>)。尚未针对多用户/生产环境做加固。
</details>

## 🆚 Yggdrasil 与同类方案对比

| | **Yggdrasil** | Context7 | 普通 LLM 记忆 |
| --- | --- | --- | --- |
| 了解**你的**决策/教训 | ✅ | ❌ | ⚠️ 仅限单个会话内 |
| 最新的公开库文档 | ❌(用 Context7) | ✅ | ❌ |
| 跨会话且跨**助手** | ✅ | ✅ | ❌ |
| 跨**项目**回忆 | ✅ | — | ❌ |
| 写入/积累你的记忆 | ✅ | ❌(只读) | ⚠️ |
| 本地且私密 | ✅ | ☁️ 托管 | 视情况而定 |
| 自我整合 | ✅ | ❌ | ❌ |

**一句话总结:** Context7 = *别人那个*库的正确 API。Yggdrasil = *你自己*工作的记忆。两个都用。

## 🗺️ 路线图

- 🔗 关系图谱(`SOLVES` / `SUPERSEDES` / `CONTRADICTS`),实现更丰富的推理。
- 🛰️ 多设备同步——真正做到从任何机器上接着干。
- 🧪 更强的可选模型,用于安全的自主整合。
- 🐧 Linux/Windows 服务安装器(目前为 macOS launchd)。

## 🤝 参与贡献

欢迎提交 Issue 和 PR。提交前请运行 `scripts/run_gates.sh` 和 `python3 -m unittest discover -s tests`——所有门禁都必须保持绿色。

## 📜 许可证

**Elastic License 2.0** —— 参见 [LICENSE](./LICENSE)。你可以自由使用、修改、自托管和分发 Yggdrasil，但**不得**将其作为产品出售，也**不得**作为托管/managed 服务提供给他人。它是 source-available，并非 OSI 认可的开源协议。

