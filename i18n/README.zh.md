<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>为你所有的 AI 编程助手提供一份共享、持久的记忆。</b><br/>
让 Claude Code、Codex 以及任何 MCP 宿主，跨越会话、工具和项目，都记得你的决策、教训和项目进度。</p>

<p align="center">
  <a href="https://github.com/VonderVuflya/Yggdrasil/releases/latest"><img src="https://img.shields.io/github/v/release/VonderVuflya/Yggdrasil?label=release&color=blue" alt="Latest release"></a>
  <a href="https://pypi.org/project/yggdrasil-memory/"><img src="https://img.shields.io/pypi/v/yggdrasil-memory?label=PyPI&color=blue" alt="PyPI"></a>
  <a href="https://glama.ai/mcp/servers/VonderVuflya/Yggdrasil"><img src="https://glama.ai/mcp/servers/VonderVuflya/Yggdrasil/badges/score.svg" alt="Glama quality score"></a>
  <a href="../BENCHMARKS.md"><img src="https://img.shields.io/badge/recall@1-0.94%20·%20reproducible-brightgreen" alt="Benchmarks"></a>
  <a href="https://pypistats.org/packages/yggdrasil-memory"><img src="https://img.shields.io/pypi/dm/yggdrasil-memory?label=PyPI%20downloads&color=blue" alt="PyPI downloads"></a>
  <a href="https://www.npmjs.com/package/yggdrasil-memory"><img src="https://img.shields.io/npm/dm/yggdrasil-memory?label=npm%20downloads&color=red" alt="npm downloads"></a>
  <a href="https://pepy.tech/project/yggdrasil-memory"><img src="https://img.shields.io/pepy/dt/yggdrasil-memory?label=total%20downloads&color=8b5cf6" alt="Total downloads"></a>
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-AGPL%203.0-blue.svg" alt="AGPL-3.0"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/deps-zero%20(stdlib)-brightgreen" alt="zero deps">
  <img src="https://img.shields.io/badge/MCP-Claude%20·%20Codex%20·%20Desktop-purple" alt="MCP">
  <img src="https://img.shields.io/badge/local--first-100%25%20private-success" alt="local-first">
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="alpha">
</p>

<p align="center">
  <a href="#-快速开始">快速开始</a> ·
  <a href="#-工作原理">工作原理</a> ·
  <a href="#-yggdrasil-与同类方案对比">对比</a> ·
  <a href="#-命令">命令</a> ·
  <a href="#️-配置">配置</a> ·
  <a href="#-常见问题">常见问题</a>
</p>

<p align="center">
  <a href="../README.md"><img src="https://img.shields.io/badge/README-English-blue" alt="English"></a>
  <a href="./README.ru.md"><img src="https://img.shields.io/badge/docs-Русский-darkblue" alt="Русский"></a>
  <a href="./README.zh.md"><img src="https://img.shields.io/badge/docs-简体中文-red" alt="简体中文"></a>
  <a href="./README.es.md"><img src="https://img.shields.io/badge/docs-Español-orange" alt="Español"></a>
  <a href="./README.fr.md"><img src="https://img.shields.io/badge/docs-Français-blue" alt="Français"></a>
  <a href="./README.ja.md"><img src="https://img.shields.io/badge/docs-日本語-red" alt="日本語"></a>
  <a href="./README.de.md"><img src="https://img.shields.io/badge/docs-Deutsch-yellow" alt="Deutsch"></a>
</p>

---

<p align="center">
  <img src="../docs/demo.gif" alt="Yggdrasil — a brand-new session already knows your project, and recalls a fix from another project" width="880">
</p>

每开一个新对话，你的 AI 都会忘得一干二净。于是你只能一遍又一遍地重新解释项目、决策、那些坑——每次都讲，每个工具里都讲。**Yggdrasil 是一个小巧、常驻的记忆大脑，任何助手都能接入它。** 在任何项目里、用任何 AI 开一个新会话，它都已经知道你定过什么、出过什么问题、还有什么没解决——而且它会在后台持续学习。

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

不用再说“让我提醒你一下我们昨天做了什么”。它本来就在那儿。

## 为什么

**没有 Yggdrasil 时**，你在每个新对话里都要重新解释背景，一个项目里的教训永远传不到下一个项目，从 Claude Code 换到 Codex 就得从零开始，来之不易的调试心得也会随会话一同消逝。

**有了 Yggdrasil：**

- 🧠 **持久记忆**——决策、教训和进度能跨越多个会话留存下来。
- 🔌 **众多助手，同一个大脑**——Claude Code、Codex 以及任何 MCP 宿主共享同一份记忆。
- 🌐 **跨项目回忆**——*“这看起来跟你在项目 B 里做过的事很像——要复用吗？”*
- 🌱 **自我学习**——一个本地模型在后台整合记忆（不消耗任何 API token）。
- 🪪 **一个灵魂**——给它起个名字、设定个性；它在每个工具里都以同样的形象出现。
- 🔒 **100% 本地且私密**——你的记忆就在你自己的机器上。无需云端，无需账号。

## 🚀 快速开始

> **环境要求：** macOS（Linux/Windows 即将支持）、Python 3.10+——或者让 `uv`/`npx` 替你获取 Python。语义搜索是可选的，使用一个本地 [Ollama](https://ollama.com) 模型。

**方案 A — 作为插件安装**（一步搞定，就在你的助手内部——零配置）。在 **Claude Code** 中：

```text
/plugin marketplace add VonderVuflya/Yggdrasil
/plugin install yggdrasil
```

引擎会在首次使用时惰性启动，并生成它自己的本地 token——**无需 API key，无需云端，无需任何配置。**（Codex 和 Cursor 使用同样的流程。）

**方案 B — 安装完整服务**（常驻守护进程 + 会话开始时自动注入 + 可选的本地模型）：

```bash
uvx --from yggdrasil-memory ygg install      # one-time guided setup
```

<details>
<summary>每一个安装渠道（同一个引擎）</summary>

| 宿主 / 工具 | 命令 |
| --- | --- |
| **Claude Code · Codex · Cursor**（插件） | `/plugin marketplace add VonderVuflya/Yggdrasil` → `/plugin install yggdrasil` |
| **uvx** _(推荐 CLI)_ | `uvx --from yggdrasil-memory ygg install` |
| **npm / npx** | `npx yggdrasil-memory install` |
| **pipx** | `pipx install yggdrasil-memory && ygg install` |
| **pip** | `pip install yggdrasil-memory && ygg install` |
| **Homebrew** _(macOS)_ | `brew install VonderVuflya/tap/yggdrasil && ygg install` |
| **Claude Desktop** _(应用)_ | 把 `.mcpb` 从[最新发布](https://github.com/VonderVuflya/Yggdrasil/releases/latest)拖到 Settings → Extensions（[指南](../packaging/mcpb/README.md)） |
| **从源码** | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` |

</details>

`ygg install` 是一次性的引导式设置：它会检测你的硬件并**推荐一个适合的本地模型**（或选择 `none` 进行零配置、仅词法的安装），生成一个私有的鉴权 token，安装一个**常驻的后台服务**，并**把工具注册到 Claude Code 和 Codex**。

**验证并使用：**
```bash
ygg doctor       # engine · models · MCP registration · hook — all green?
```
然后就开始干活吧。让你的助手*“回忆一下我们对这个项目定过什么”*，或者告诉它*“记住这个决策”*——到下一个会话时它就已经在那儿了。

**已经有历史积累？** 一键从你现有的 **Claude Code + Codex** 会话记录、Obsidian 库和 `CLAUDE.md` 仓库播种记忆——全部在本地提炼：

```bash
ygg seed --dry-run    # see what it'd import; drop --dry-run to distill for real
```

只想先试试引擎，不安装服务？`uvx --from yggdrasil-memory ygg serve --reset --db /tmp/ygg.sqlite`。

## 🔌 更多连接方式

除了上面的插件和 `ygg install` 之外：

- 🖥️ **Claude Desktop（桌面应用）** — 安装 MCP 扩展：从[最新发布](https://github.com/VonderVuflya/Yggdrasil/releases/latest)（或 `packaging/mcpb/`）获取 `yggdrasil-<版本>.mcpb`，把它拖到 **Settings → Extensions**，并粘贴你的令牌（`ygg token`）。桌面应用现在与你的 CLI 智能体共享**同一份记忆**。→ [安装指南](../packaging/mcpb/README.md)
- 🧠 **Skill（任意 Claude）** — [`yggdrasil-memory` 技能](../skills/)教会智能体工作流程：工作前回忆，工作后记录。通过 **Settings → Skills → Create skill → Upload a skill** 上传 `yggdrasil-memory.zip`。

> **MCP 与 Skill 的区别：** MCP 连接*工具*（如何访问记忆），Skill 教会*何时使用*它们。两者并用效果最佳。

## 🧠 工作原理

Yggdrasil 提供的是**记忆 + 工具**——*智能*来自你的 LLM。它只负责确保在恰当的时刻，把恰当的记忆送到恰当的助手面前。

- 🛎️ **常驻守护进程**——一个微小的本地服务（约 21 MB 内存），你的助手通过 MCP 工具（`ygg_search`、`ygg_recall`、`ygg_remember` …）访问它。
- 🪝 **会话开始**——一个钩子自动注入身份、项目状态和待办的后续事项。
- 📌 **排名**——被频繁回忆和置顶的记忆排名更靠前（存储与层级见下 ↓）。
- 🧹 **治理**——重复 / 冲突的记忆会被挑出来供你审查；所有改动都是非破坏性的（归档，绝不删除）。
- 📓 **Obsidian**——每一条记忆同时也是一份可读、可编辑的 Markdown 笔记。

## 🎛️ 记忆层级——默认零配置

开箱即用，Yggdrasil 运行在 **SQLite + FTS5 之上，零依赖**——即时的关键词（词法）搜索，无需模型，无需 GPU，无需下载任何东西。已经很有用了：recall@1 ≈ 0.77。

想让它按**含义**并跨语言匹配？只要你的硬件允许，`ygg install` 就能拉取可选的**本地模型，通过 [Ollama](https://ollama.com)**——它会检测你的 CPU/RAM/GPU 并推荐一个合适的（或者选择 `none` 以保持零配置）。两个可选、相互独立的层级：

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

| 层级 | 你添加 | 你获得 |
| --- | --- | --- |
| **0 · 默认** | 无——SQLite + FTS5 | 关键词搜索，零依赖，即时——recall@1 ≈ **0.77** |
| **1 · 语义** | 一个通过 Ollama 的**嵌入**模型（例如 `all-minilm` 45 MB · `paraphrase-multilingual` ~560 MB） | 按**含义**搜索 + 跨语言——recall@1 ≈ **0.94** |
| **2 · 自学习** | 一个通过 Ollama 的小型**整合** LLM（例如 `qwen2.5:1.5b` ~1 GB） | 后台对记忆去重/合并（提议安全） |

Ollama 只**计算**向量／运行后台模型——向量和所有记忆仍然存放在**同一个 SQLite** 里。各层级相互独立、按需启用。

<details>
<summary>完整模型菜单（或运行 <code>ygg recommend</code>）</summary>

**嵌入（语义搜索）：**

| 模型 | 大小 | 适用场景 |
| --- | --- | --- |
| `all-minilm` | 45 MB | 英文，小巧快速 |
| `nomic-embed-text` | 274 MB | 英文，质量更好 |
| `paraphrase-multilingual` | ~560 MB | 多语言（EN/RU + 50 种语言） |
| `bge-m3` | 1.2 GB | 多语言，顶级质量（更重） |

**后台整合（小型 LLM）：**

| 模型 | 大小 | 适用场景 |
| --- | --- | --- |
| `qwen2.5:0.5b` | ~400 MB | 小巧，在 CPU 上快速 |
| `qwen2.5:1.5b` | ~1 GB | 最佳 CPU 默认选择 |
| `llama3.2:3b` | ~2 GB | 质量更好，在 CPU 上更慢 |

</details>

一切都保持 **100% 本地——零 API token，无云端。** 安装程序会推荐适合你硬件的模型（或者选择 `none` 以保持零配置）。

> 引擎本身是可替换的——任何满足 `MemoryBackend` 契约的服务都能直接接入（把 `YGG_ENGINE_URL` 指向它）；SQLite 是零依赖的默认项。参见 [docs/backend-boundary.md](../docs/backend-boundary.md)。

## 🆚 Yggdrasil 与同类方案对比

最接近的工具是 **claude-mem**——它同样是为编程助手提供的持久记忆，但属于*更重、捕获一切*的系统：它会自动记录每一次会话并用 AI 压缩（需要 Node + Bun + 一个向量数据库）。**mem0** 是一个记忆 *SDK*，用于让应用记住它们的用户。context-mode 和 Context7 占据着**不同的层**（你的实时上下文窗口；最新的库文档）。Yggdrasil 是**装好即用、零依赖、本地优先的、对_你自己_工作的记忆**——经过精选，而非照单全收，以你可编辑的纯 Markdown 存储。

| | **Yggdrasil** | [claude-mem](https://github.com/thedotmack/claude-mem) | [mem0](https://github.com/mem0ai/mem0) | [context-mode](https://github.com/mksglu/context-mode) | [Context7](https://github.com/upstash/context7) |
| --- | --- | --- | --- | --- | --- |
| 对**你自己工作**的持久记忆（决策、教训、进度） | ✅ | ✅ | ✅ | ⚠️ 会话内 | ❌ |
| 为你的助手**即插即用**，*无需代码*（安装 + MCP） | ✅ | ✅ | ⚠️ *SDK* | ✅ | ✅ |
| **零依赖**（标准库 + SQLite；无需 Node/Bun/向量数据库） | ✅ | ❌ | ❌ | ❌ | — |
| **无需 LLM 与 API key** 也能用（默认词法） | ✅ | ❌ *AI 压缩* | ❌ *需要 LLM* | ✅ | ❌ |
| **精选**且可作为纯 Markdown 编辑（而非捕获一切） | ✅ | ❌ *自动捕获一切* | ⚠️ | ❌ | — |
| **100% 本地且私密**（默认无云端） | ✅ | ⚠️ | ⚠️ *默认云端* | ✅ | ☁️ 托管 |
| 跨**项目**回忆（“在项目 B 里解决过这个”） | ✅ | ⚠️ | ⚠️ | ❌ | — |
| 一份记忆**跨工具**共享（Claude Code · Codex · 任何 MCP 宿主） | ✅ | ✅ | ⚠️ *按应用* | ✅ | ✅ |
| 最新的公开**库文档** | ❌ *（用 Context7）* | ❌ | ❌ | ❌ | ✅ |

> **claude-mem vs Yggdrasil，一句话讲清：** claude-mem 自动捕获*一切*并用 AI 压缩（Node + Bun + 一个向量数据库；~84k★，自带一个加密 token）——存储会随每次会话不断增长。Yggdrasil 只保留*少数真正重要的东西*——经过精选并**语义去重**（近乎重复的经验会被合并，因此库始终小而高信噪比），零依赖，以你自己拥有、可检索可编辑的普通记录存储——无需 AI，无需 token。理念不同；两者可以并用。

> **mem0 vs Yggdrasil，一句话讲清：** mem0 是一个记忆 **SDK/平台，用于构建能记住其用户的应用**（你来写代码；它通常会调用一个 LLM，默认云端）。Yggdrasil 是**装好即用、本地优先的、对_你自己_工作的记忆，服务于你已经在用来写代码的助手。** 职责不同——按你的身份来选。

> 也能与 [**autoresearch**](https://github.com/karpathy/autoresearch) 很好地搭配——一个自主的实验循环（不是记忆工具）；Yggdrasil 为它提供它已经试过什么的长期记忆 → [集成](../integrations/autoresearch/)。

**一句话总结：** 想要跨多个 IDE 自动捕获一切，又不介意更重的技术栈 → **claude-mem**。要构建一款必须在大规模下记住其用户的 AI *产品* → **mem0**。想要一份小巧、本地、*精选*、由你自己拥有的记忆——零依赖、无需 AI——服务于你已经在用的编程助手 → **Yggdrasil**。

## 🧰 命令

助手能看到六个 MCP 工具：`ygg_health`、`ygg_bootstrap`、`ygg_search`、`ygg_recall`、`ygg_remember`、`ygg_materialize`。在 `ygg install` 之后，它们会自动注册到 Claude Code 和 Codex——只管打开一个项目开始干活。

<details>
<summary>完整的 <code>ygg</code> CLI 参考</summary>

**内存操作**

| 命令 | 作用 |
| --- | --- |
| `ygg recall --query "…"` | **跨项目**搜索——“我在哪儿做过这件事吗？” |
| `ygg search --project P --query "…"` | 项目范围内的搜索（`--type`、`--tag`、`--limit`、`--json`） |
| `ygg remember --project P --type debugging_lesson --content "…"` | 保存一条持久记忆（有密钥防护，会去重；用 `--tag` 打标签） |
| `ygg bootstrap --project P` | 开始工作前拉取某个项目的记忆 |
| `ygg pin --id ID` · `ygg unpin --id ID` | 置顶一条记忆，让它可靠地浮现出来 |
| `ygg supersede --id ID` | 归档一条被更新记忆所替代的过期记忆 |
| `ygg materialize --id ID --project P` | 把一条记忆导出为一份 Obsidian 笔记 |

**冷启动——从你已有的工作中播种**

| 命令 | 作用 |
| --- | --- |
| `ygg seed` | 把你的 **Claude Code + Codex** 会话记录、Obsidian 库和 `CLAUDE.md` 仓库提炼为教训——增量、去重、完全本地 |
| `ygg seed --dry-run` · `--force` | 仅发现 + 估算 · 重新提炼所有内容 |
| `ygg distill --source PATH` | 把单个目录/文件提炼为教训 |
| `ygg reindex` | 为缺失嵌入的记忆补建嵌入（恢复稠密检索） |

在小模型上，大型会话可能会很慢——把提炼工作指向你局域网里一台更强的机器（[配置](#️-配置) ↓）：

```bash
ygg seed --ollama-url http://192.168.3.124:11434 --model llama3.2:3b --timeout 240
```

**服务与设置**

| 命令 | 作用 |
| --- | --- |
| `ygg install` · `ygg setup` | 引导式设置 → 后台服务 + MCP 注册 |
| `ygg doctor` · `ygg update` | 诊断安装（给出可执行的修复建议）· 升级 + 重新部署 |
| `ygg config` | 显示/设置持久化配置——`list` · `get` · `set` · `unset` |
| `ygg register` | 把 MCP 服务器（重新）注册到 Claude Code / Codex |
| `ygg status` · `start` · `stop` · `restart` · `logs` | 管理这个常驻守护进程 |
| `ygg hooks` · `unhooks` | 启用/停用 SessionStart 自动 bootstrap 钩子 |
| `ygg recommend` | 显示与硬件匹配的模型目录 |
| `ygg token` · `uninstall` | 打印鉴权 token · 移除服务 + 注册 |

给它设定个性——编辑 `~/.yggdrasil/identity.json`：

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

</details>

## ⚙️ 配置

Yggdrasil 零配置即可工作。当你*确实*想改点什么时，每一项设置都遵循同样的解析顺序：

> **`--flag`  >  环境变量  >  `~/.yggdrasil/config.json`  >  默认值**

临时用一次就加个 flag，想让它长期生效就用 `ygg config set`：

```bash
ygg config list                       # effective values + where each one comes from
ygg config set distill_timeout 240    # persist a setting
ygg config get distill_url
ygg config unset bg_model             # back to the default
```

| 设置项 | 默认值 | 控制什么 |
| --- | --- | --- |
| `distill_url` | 本地 Ollama | `ygg seed` / 整合所用的端点——可指向一台更强的机器 |
| `distill_timeout` | `120` | 单个文件的提炼超时（秒）——会话较大时调高 |
| `bg_model` | `qwen2.5:1.5b` | 用于提炼与整合的模型 |
| `embed_model` · `embed_url` | 本地 | 嵌入模型 + 端点（守护进程级；运行 `ygg redeploy` 生效） |
| `user_id` · `namespace` | `demo-user` · `yggdrasil-demo` | 存储记忆所用的身份 / 命名空间 |

**在另一台机器上提炼。** 提炼（`ygg seed`）很重但只是偶尔进行；嵌入很轻却持续不断。所以 `distill_url` 被刻意与 `embed_url` 分开——把提炼工作发往你局域网里一台强劲的机器，而嵌入（以及你的数据）始终留在本地、常驻在线：

```bash
# on the beefy box (B): expose Ollama to the LAN + pull the model
OLLAMA_HOST=0.0.0.0:11434 ollama serve
ollama pull llama3.2:3b

# on your laptop (A): make B the default distill endpoint
ygg config set distill_url http://192.168.3.124:11434
ygg config set bg_model    llama3.2:3b
ygg seed     # distills on B; your SQLite DB + embeddings never leave A
```

## ❓ 常见问题

<details>
<summary><b>它会把我的代码或记忆发到云端吗？</b></summary>

不会。引擎、数据库以及那些可选的模型全都在本地运行。没有账号，没有遥测。你的记忆永远不会离开你的机器。
</details>

<details>
<summary><b>它会自动记住所有东西吗？</b></summary>

不会——这是刻意的设计。检索是自动的；但*写入*是慎重的（助手会针对那些值得长期保留的教训调用 `ygg_remember`）。自动记录一切会污染记忆，所以我们不这么做。一个后台模型会整合已经保存下来的内容（默认仅提议）。
</details>

<details>
<summary><b>我需要 GPU 或 API key 吗？</b></summary>

不需要。默认是纯词法搜索——零依赖，即时可用。语义搜索是可选启用的，通过 Ollama 使用一个*本地*模型（无需 API key）。安装程序会推荐一个适合你硬件的模型。
</details>

<details>
<summary><b>它有多占资源，要花多少 token？</b></summary>

非常轻。引擎占用**约 21 MB 内存、约 0% 空闲 CPU、零依赖**（Python 标准库）；磁盘占用约为每条记忆几十 KB。会话开始时注入约 300 token 的记忆，每次工具调用返回的也只是一小段内容——所有繁重的工作（索引、嵌入、整合）都在你机器上、LLM 之外完成。
</details>

<details>
<summary><b>检索效果怎么样？</b></summary>

由 `eval/ygg_eval.py` 测得（35 个带标注的用例，按 dev/holdout 划分），recall@1：

| 模式 | recall@1 | 同义改写 | 跨语言（EN→RU） |
| --- | --- | --- | --- |
| lexical（默认） | 0.77 | 0.63 | 0.00 |
| dense · `all-minilm`（45 MB，EN） | 0.83 | 0.88 | 0.00 |
| dense · `paraphrase-multilingual`（约 560 MB） | **0.94** | 0.88 | **0.80** |

`keyword` 与 `identifier` 类查询在所有模式下都是 1.0；使用多语言模型时 **recall@3 = 1.0**（每个目标都进入前 3）。
</details>

<details>
<summary><b>我可以手动编辑或删除记忆吗？</b></summary>

可以。记忆会物化为 Obsidian 库中的 Markdown 笔记——你可以像对待任何文件一样读取、编辑或移除它们。引擎从不硬删除；它只做归档（可逆）。
</details>

<details>
<summary><b>它能用于生产环境了吗？</b></summary>

它是一个诚实的 **alpha** 版：常规流程和完整的治理闭环都有通过的门禁覆盖（`scripts/run_gates.sh`）。尚未针对多用户/生产环境做加固。
</details>

## 🗺️ 路线图

- 🛰️ **跨界面同步**——从网页版和移动版的 ChatGPT / Claude 连接；一份记忆贯通 CLI、浏览器和手机。
- 🔗 关系图谱（`SOLVES` / `SUPERSEDES` / `CONTRADICTS`），实现更丰富的推理。
- 🐧 Linux/Windows 服务安装器（已实现；正在做最后的设备端测试）。

## 🤝 参与贡献

欢迎提交 Issue 和 PR。提交前请运行 `scripts/run_gates.sh` 和 `python3 -m unittest discover -s tests`——所有门禁都必须保持绿色。

## 📜 许可证

**GNU AGPL v3.0**——参见 [LICENSE](../LICENSE)。自由开源（OSI 认可）：你可以自由使用、修改、自托管和分发 Yggdrasil。根据 AGPL 的网络 copyleft 条款，如果你修改它**或**将其作为托管/网络服务提供给他人，你必须以相同的协议公开你的源代码。
