<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>すべての AI コーディングエージェントのための、共有・永続する単一のメモリ。</b><br/>
Claude Code、Codex、あらゆる MCP ホストが、あなたの決定・教訓・プロジェクトの状況を記憶します — セッション・ツール・プロジェクトをまたいで。</p>

<p align="center">
  <a href="https://github.com/VonderVuflya/Yggdrasil/releases/latest"><img src="https://img.shields.io/github/v/release/VonderVuflya/Yggdrasil?label=release&color=blue" alt="Latest release"></a>
  <a href="https://pypi.org/project/yggdrasil-memory/"><img src="https://img.shields.io/pypi/v/yggdrasil-memory?label=PyPI&color=blue" alt="PyPI"></a>
  <a href="https://pypistats.org/packages/yggdrasil-memory"><img src="https://img.shields.io/pypi/dm/yggdrasil-memory?label=PyPI%20downloads&color=blue" alt="PyPI downloads"></a>
  <a href="https://www.npmjs.com/package/yggdrasil-memory"><img src="https://img.shields.io/npm/dm/yggdrasil-memory?label=npm%20downloads&color=red" alt="npm downloads"></a>
  <a href="https://github.com/VonderVuflya/Yggdrasil/stargazers"><img src="https://img.shields.io/github/stars/VonderVuflya/Yggdrasil?style=flat&color=yellow" alt="GitHub stars"></a>
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-Elastic%202.0-blue.svg" alt="Elastic License 2.0"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/deps-zero%20(stdlib)-brightgreen" alt="zero deps">
  <img src="https://img.shields.io/badge/MCP-Claude%20·%20Codex%20·%20Desktop-purple" alt="MCP">
  <img src="https://img.shields.io/badge/local--first-100%25%20private-success" alt="local-first">
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="alpha">
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

新しいチャットを始めるたびに、AI はすべてを忘れています。プロジェクト、決定事項、ハマりどころを — 毎回、どのツールでも — 一から説明し直すことになります。**Yggdrasil は、どんなエージェントでも接続できる、常時稼働の小さなメモリの頭脳です。** どのプロジェクトでも、どの AI でも、新しいセッションを開けば、あなたが何を決め、何が壊れ、何がまだ未解決なのかをすでに把握しています — しかもバックグラウンドで学習し続けます。

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

「昨日やったことを思い出させてください」は不要です。最初からそこにあります。

## なぜ Yggdrasil なのか

**Yggdrasil がないと** 新しいチャットのたびにコンテキストを説明し直し、あるプロジェクトの教訓は次のプロジェクトに届かず、Claude Code → Codex への切り替えはゼロから始まり、苦労して得たデバッグの知見はセッションとともに消えてしまいます。

**Yggdrasil があれば:**

- 🧠 **永続するメモリ** — 決定・教訓・状況がセッションをまたいで残ります。
- 🔌 **どのエージェントでも、頭脳はひとつ** — Claude Code、Codex、あらゆる MCP ホストが同じメモリを共有します。
- 🌐 **プロジェクト横断の想起** — *「これはプロジェクト B でやったことに似ています — 再利用しますか?」*
- 🌱 **自己学習** — ローカルモデルがバックグラウンドでメモリを整理・統合します（API トークンはゼロ)。
- 🪪 **魂を持つ** — 名前と人格を与えれば、どのツールでも同じ姿で現れます。
- 🔒 **100% ローカル & プライベート** — あなたのメモリはあなたのマシンに置かれます。クラウドもアカウントも不要。

## 🚀 クイックスタート

> **必要条件:** macOS（Linux/Windows は近日対応）、Python 3.10+ — もしくは `uv`/`npx` に Python を取得させても構いません。セマンティック検索はオプションで、ローカルの [Ollama](https://ollama.com) モデルを使用します。

**オプション A — プラグインとしてインストール**（ワンステップ、エージェントの中で完結 — 設定不要)。**Claude Code** では:

```text
/plugin marketplace add VonderVuflya/Yggdrasil
/plugin install yggdrasil
```

エンジンは初回利用時に遅延起動し、独自のローカルトークンを生成します — **API キー不要、クラウド不要、設定するものは何もありません。**（Codex と Cursor も同じ流れです)

**オプション B — フルサービスをインストール**（常時稼働のデーモン + セッション開始時の自動注入 + オプションのローカルモデル):

```bash
uvx --from yggdrasil-memory ygg install      # one-time guided setup
```

<details>
<summary>すべてのインストール経路（エンジンは同じです)</summary>

| ホスト / ツール | コマンド |
| --- | --- |
| **Claude Code · Codex · Cursor**（プラグイン) | `/plugin marketplace add VonderVuflya/Yggdrasil` → `/plugin install yggdrasil` |
| **uvx** _(推奨 CLI)_ | `uvx --from yggdrasil-memory ygg install` |
| **npm / npx** | `npx yggdrasil-memory install` |
| **pipx** | `pipx install yggdrasil-memory && ygg install` |
| **pip** | `pip install yggdrasil-memory && ygg install` |
| **Homebrew** _(macOS)_ | `brew install VonderVuflya/tap/yggdrasil && ygg install` |
| **Claude Desktop** _(アプリ)_ | [最新リリース](https://github.com/VonderVuflya/Yggdrasil/releases/latest) から `.mcpb` を Settings → Extensions にドラッグ（[ガイド](../packaging/mcpb/README.md)) |
| **ソースから** | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` |

</details>

`ygg install` は一度きりのガイド付きセットアップです。ハードウェアを検出して**適合するローカルモデルを推奨し**（または `none` を選べば設定不要・字句検索のみの構成になります）、プライベートな認証トークンを生成し、**常時稼働のバックグラウンドサービス**をインストールし、**Claude Code と Codex にツールを登録**します。

**確認して使う:**
```bash
ygg doctor       # engine · models · MCP registration · hook — all green?
```
あとは作業するだけです。エージェントに *「このプロジェクトについて決めたことを思い出して」* と尋ねたり、*「この決定を記憶して」* と伝えたりすれば — 次のセッションではもうそこにあります。

**すでに履歴がありますか?** 既存の **Claude Code + Codex** のトランスクリプト、Obsidian vault、`CLAUDE.md` リポジトリから、メモリを一気にシードできます — すべてローカルで蒸留されます:

```bash
ygg seed --dry-run    # see what it'd import; drop --dry-run to distill for real
```

サービスをインストールせずに気軽に試したいだけですか? `uvx --from yggdrasil-memory ygg serve --reset --db /tmp/ygg.sqlite`。

## 🔌 さらに接続する方法

上記のプラグインと `ygg install` に加えて:

- 🖥️ **Claude Desktop（アプリ)** — MCP 拡張機能をインストールします。[最新リリース](https://github.com/VonderVuflya/Yggdrasil/releases/latest)（または `packaging/mcpb/`）から `yggdrasil-<version>.mcpb` を取得し、**Settings → Extensions** にドラッグして、トークン（`ygg token`）を貼り付けます。これでデスクトップアプリは CLI エージェントと**同じメモリ**を共有します。→ [セットアップガイド](../packaging/mcpb/README.md)
- 🧠 **Skill（あらゆる Claude)** — [`yggdrasil-memory` skill](../skills/) は、作業前に想起し、作業後に記憶するというワークフローをエージェントに教えます。`yggdrasil-memory.zip` を **Settings → Skills → Create skill → Upload a skill** からアップロードしてください。

> **MCP と Skill の違い:** MCP は*ツール*を接続し（メモリへの到達方法)、Skill は*いつ使うか*を教えます。最良の挙動を得るには両方を使ってください。

## 🧠 仕組み

Yggdrasil は **メモリ + ツール** です — *知能*はあなたの LLM が担います。Yggdrasil は、適切なメモリを適切なエージェントの前に適切なタイミングで届けることだけを行います。

- 🛎️ **常時稼働のデーモン** — エージェントが MCP ツール（`ygg_search`、`ygg_recall`、`ygg_remember` …）で接続する小さなローカルサービス（RAM 約 21 MB)。
- 🪝 **セッション開始時** — フックが識別情報・プロジェクトの状況・未解決のフォローアップを自動的に注入します。
- 📌 **ランキング** — 頻繁に想起されたメモリやピン留めしたメモリがより上位に表示されます（ストレージとティアは下記 ↓)。
- 🧹 **ガバナンス** — 重複や矛盾はレビューのために提示され、変更は非破壊的です（アーカイブのみ、削除はしません)。
- 📓 **Obsidian** — すべてのメモリは、読んだり編集したりできる Markdown ノートでもあります。

## 🎛️ メモリのティア — 既定では設定不要

Yggdrasil は箱を開けてすぐ、**依存ゼロの SQLite + FTS5** で動作します — 即時のキーワード（字句）検索で、モデルも GPU も不要、ダウンロードするものもありません。これだけでも十分役立ちます: recall@1 ≈ 0.77。

**意味**で、そして言語をまたいでマッチさせたいですか? ハードウェアが許せば、`ygg install` は**オプションのローカルモデルを [Ollama](https://ollama.com) 経由で**取得できます — CPU/RAM/GPU を検出して適合するものを推奨します（または `none` を選べば設定不要のままにできます)。オプションかつ独立した 2 つのティアがあります:

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

| ティア | 追加するもの | 得られるもの |
| --- | --- | --- |
| **0 · 既定** | 何も不要 — SQLite + FTS5 | キーワード検索、依存ゼロ、即時 — recall@1 ≈ **0.77** |
| **1 · セマンティック** | Ollama 経由の**埋め込み**モデル（例: `all-minilm` 45 MB · `paraphrase-multilingual` ~560 MB) | **意味**による検索 + 言語横断 — recall@1 ≈ **0.94** |
| **2 · 自己学習** | Ollama 経由の小さな**統合用**LLM（例: `qwen2.5:1.5b` ~1 GB) | バックグラウンドでのメモリの重複排除/統合（提案のみで安全) |

Ollama はベクトルの**計算**とバックグラウンドモデルの実行だけを行います — ベクトルとすべてのメモリは依然として**同じ SQLite** に置かれます。ティアは独立しており、オプトイン方式です。

<details>
<summary>モデルの全メニュー（または <code>ygg recommend</code> を実行)</summary>

**埋め込み（セマンティック検索):**

| モデル | サイズ | 適した用途 |
| --- | --- | --- |
| `all-minilm` | 45 MB | 英語、極小で高速 |
| `nomic-embed-text` | 274 MB | 英語、より高品質 |
| `paraphrase-multilingual` | ~560 MB | 多言語（EN/RU + 50 言語) |
| `bge-m3` | 1.2 GB | 多言語、最高品質（より重い) |

**バックグラウンド統合（小型 LLM):**

| モデル | サイズ | 適した用途 |
| --- | --- | --- |
| `qwen2.5:0.5b` | ~400 MB | 極小、CPU で高速 |
| `qwen2.5:1.5b` | ~1 GB | CPU での最適な既定 |
| `llama3.2:3b` | ~2 GB | より高品質、CPU では低速 |

</details>

すべては **100% ローカルのまま — API トークンはゼロ、クラウドもなし。** インストーラーはあなたのハードウェアに適合するモデルを推奨します（または `none` を選べば設定不要のままにできます)。

> エンジン自体は差し替え可能です — `MemoryBackend` 契約を満たすサービスならどれでもそのまま組み込めます（`YGG_ENGINE_URL` をそこに向けてください)。SQLite は依存ゼロの既定です。[docs/backend-boundary.md](../docs/backend-boundary.md) を参照してください。

## 🆚 Yggdrasil と他ツールの比較

最も近いツールは **claude-mem** です — これもコーディングエージェント向けの永続メモリですが、*より重い「すべてをキャプチャする」*システムです: あらゆるセッションを自動記録し、AI で圧縮します（Node + Bun + ベクトル DB が必要)。**mem0** は、アプリがそのユーザーを記憶するためのメモリ *SDK* です。context-mode と Context7 は**異なるレイヤー**を担っています（前者はライブのコンテキストウィンドウ、後者は最新のライブラリドキュメント)。Yggdrasil は **インストールするだけで使える、依存ゼロでローカルファーストな、_あなた自身の_ 作業のメモリ**です — 大量に垂れ流すのではなく厳選され、編集できるプレーンな Markdown として保存されます。

| | **Yggdrasil** | [claude-mem](https://github.com/thedotmack/claude-mem) | [mem0](https://github.com/mem0ai/mem0) | [context-mode](https://github.com/mksglu/context-mode) | [Context7](https://github.com/upstash/context7) |
| --- | --- | --- | --- | --- | --- |
| **あなた自身の作業**の永続メモリ（決定・教訓・状況) | ✅ | ✅ | ✅ | ⚠️ セッション内 | ❌ |
| エージェントへの **ドロップイン**、*コード不要*（インストール + MCP) | ✅ | ✅ | ⚠️ *SDK* | ✅ | ✅ |
| **依存ゼロ**（標準ライブラリ + SQLite。Node/Bun/ベクトル DB 不要) | ✅ | ❌ | ❌ | ❌ | — |
| **LLM も API キーも不要**で動作（字句検索が既定) | ✅ | ❌ *AI で圧縮* | ❌ *LLM が必要* | ✅ | ❌ |
| **厳選**され、プレーンな Markdown として編集可能（すべてをキャプチャしない) | ✅ | ❌ *すべて自動キャプチャ* | ⚠️ | ❌ | — |
| **100% ローカル & プライベート**（既定でクラウドなし) | ✅ | ⚠️ | ⚠️ *既定でクラウド* | ✅ | ☁️ ホスト型 |
| **プロジェクト**横断の想起（「これはプロジェクト B で解決した」) | ✅ | ⚠️ | ⚠️ | ❌ | — |
| **ツール横断**で共有される単一のメモリ（Claude Code · Codex · あらゆる MCP ホスト) | ✅ | ✅ | ⚠️ *アプリごと* | ✅ | ✅ |
| 最新の公開**ライブラリドキュメント** | ❌ *(Context7 を使用)* | ❌ | ❌ | ❌ | ✅ |

> **claude-mem と Yggdrasil を一行で:** claude-mem は*すべて*を自動キャプチャして AI で圧縮します（Node + Bun + ベクトル DB。~84k★、暗号トークンを同梱)——ストアはセッションごとに増え続けます。Yggdrasil は*重要な数少ないもの*だけを保持します — 厳選され、**意味的に重複排除**され（ほぼ同一の教訓は統合され、小さく高信号のまま保たれます）、依存ゼロで、grep・編集でき、あなた自身が所有する素のレコードとして保存されます — AI 不要、トークン不要。哲学が異なります。両方を併用できます。

> **mem0 と Yggdrasil を一行で:** mem0 は**ユーザーを記憶するアプリを構築するためのメモリ SDK/プラットフォーム**です（コードを書く必要があり、通常は LLM を呼び出し、既定でクラウド)。Yggdrasil は **ドロップインで使えるローカルファーストのメモリで、すでにコーディングしているエージェントのために _あなた自身の_ 作業を記憶します。** 役割が異なります — あなたが何者かで選んでください。

> [**autoresearch**](https://github.com/karpathy/autoresearch) ともよく組み合わせられます — これは自律的な実験ループ（メモリツールではありません）で、Yggdrasil はすでに試したことの長期メモリを提供します → [統合](../integrations/autoresearch/)。

**要するに:** 多くの IDE をまたいで自動的にすべてをキャプチャしたい、重めのスタックも気にしない → **claude-mem**。ユーザーを大規模に記憶しなければならない AI *製品*を構築している → **mem0**。すでに使っているコーディングエージェントのために、自分が所有する小さくてローカルな*厳選された*メモリが欲しい — 依存ゼロ、AI 不要 → **Yggdrasil**。

## 🧰 コマンド

エージェントには 6 つの MCP ツールが見えます: `ygg_health`、`ygg_bootstrap`、`ygg_search`、`ygg_recall`、`ygg_remember`、`ygg_materialize`。`ygg install` の後はこれらが Claude Code と Codex に自動登録されます — プロジェクトを開いて作業を始めるだけです。

<details>
<summary><code>ygg</code> CLI の完全リファレンス</summary>

**メモリ操作**

| コマンド | 何をするか |
| --- | --- |
| `ygg recall --query "…"` | **プロジェクト横断**検索 — 「これをどこかでやったことはあるか?」 |
| `ygg search --project P --query "…"` | プロジェクトに絞った検索（`--type`、`--tag`、`--limit`、`--json`) |
| `ygg remember --project P --type debugging_lesson --content "…"` | 永続メモリを保存（シークレット保護つき、重複排除あり。`--tag` でラベル付け) |
| `ygg bootstrap --project P` | 作業を始める前にプロジェクトのメモリを取り込む |
| `ygg pin --id ID` · `ygg unpin --id ID` | メモリをピン留めして確実に表示されるようにする |
| `ygg supersede --id ID` | 新しいメモリが置き換える古いメモリをアーカイブする |
| `ygg materialize --id ID --project P` | 1 つのメモリを Obsidian ノートにエクスポートする |

**コールドスタート — 既存の作業からシードする**

| コマンド | 何をするか |
| --- | --- |
| `ygg seed` | あなたの **Claude Code + Codex** のトランスクリプト、Obsidian vault、`CLAUDE.md` リポジトリを教訓へと蒸留する — 増分的・重複排除済み・完全ローカル |
| `ygg seed --dry-run` · `--force` | 発見と見積もりのみ · すべてを再蒸留 |
| `ygg distill --source PATH` | 1 つのディレクトリ/ファイルを教訓へ蒸留する |
| `ygg reindex` | 埋め込みが欠けているメモリを補完する（密な想起を復元) |

大きなセッションは小さなモデルでは遅くなることがあります — 蒸留処理を LAN 上のより高性能なマシンに向けましょう（設定 ↓):

```bash
ygg seed --ollama-url http://192.168.3.124:11434 --model llama3.2:3b --timeout 240
```

**サービスとセットアップ**

| コマンド | 何をするか |
| --- | --- |
| `ygg install` · `ygg setup` | ガイド付きセットアップ → バックグラウンドサービス + MCP 登録 |
| `ygg doctor` · `ygg update` | インストールを診断（実行可能な修正を提示) · アップグレード + 再デプロイ |
| `ygg config` | 永続的な設定を表示/変更 — `list` · `get` · `set` · `unset` |
| `ygg register` | MCP サーバーを Claude Code / Codex に(再)登録する |
| `ygg status` · `start` · `stop` · `restart` · `logs` | 常時稼働デーモンを管理 |
| `ygg hooks` · `unhooks` | SessionStart 自動ブートストラップフックを有効化/無効化 |
| `ygg recommend` | ハードウェアに応じたモデルカタログを表示 |
| `ygg token` · `uninstall` | 認証トークンを表示 · サービス + 登録を削除 |

人格を与えましょう — `~/.yggdrasil/identity.json` を編集します:

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

</details>

## ⚙️ 設定

Yggdrasil は設定不要で動作します。それでも何かを変えたくなったとき、すべての設定は同じ順序で解決されます:

> **`--flag`  >  環境変数  >  `~/.yggdrasil/config.json`  >  既定値**

1 回の実行だけならフラグを、恒久的に効かせたいなら `ygg config set` を使ってください:

```bash
ygg config list                       # effective values + where each one comes from
ygg config set distill_timeout 240    # persist a setting
ygg config get distill_url
ygg config unset bg_model             # back to the default
```

| 設定 | 既定値 | 制御する内容 |
| --- | --- | --- |
| `distill_url` | ローカルの Ollama | `ygg seed` / 統合処理のエンドポイント — より高性能なマシンを指定可能 |
| `distill_timeout` | `120` | ファイルごとの蒸留タイムアウト（秒) — 大きなセッションでは引き上げる |
| `bg_model` | `qwen2.5:1.5b` | 蒸留と統合に使うモデル |
| `embed_model` · `embed_url` | ローカル | 埋め込みモデル + エンドポイント（デーモンレベル。適用するには `ygg redeploy` を実行) |
| `user_id` · `namespace` | `demo-user` · `yggdrasil-demo` | 保存されるメモリの識別子 / 名前空間 |

**別のマシンで蒸留する。** 蒸留（`ygg seed`）は重い処理ですが、行うのは時々だけです。埋め込みは軽い処理ですが、常に行われます。そのため `distill_url` は意図的に `embed_url` とは分けてあります — 蒸留を LAN 上の高性能なマシンに送りつつ、埋め込み（とあなたのデータ)はローカルで常時稼働させたままにできます:

```bash
# on the beefy box (B): expose Ollama to the LAN + pull the model
OLLAMA_HOST=0.0.0.0:11434 ollama serve
ollama pull llama3.2:3b

# on your laptop (A): make B the default distill endpoint
ygg config set distill_url http://192.168.3.124:11434
ygg config set bg_model    llama3.2:3b
ygg seed     # distills on B; your SQLite DB + embeddings never leave A
```

## ❓ よくある質問

<details>
<summary><b>コードやメモリをクラウドに送信しますか?</b></summary>

いいえ。エンジン、データベース、オプションのモデルはすべてローカルで動作します。アカウントもテレメトリもありません。あなたのメモリがマシンの外に出ることはありません。
</details>

<details>
<summary><b>すべてを自動的に記憶しますか?</b></summary>

いいえ — 設計上そうしています。取り出しは自動ですが、*書き込み*は意図的です（エージェントは永続的な教訓のために `ygg_remember` を呼び出します)。すべてを自動でキャプチャするとメモリが汚染されるため、そうはしません。バックグラウンドのモデルがすでに保存済みのものを統合します（既定では提案のみ)。
</details>

<details>
<summary><b>GPU や API キーは必要ですか?</b></summary>

いいえ。既定は純粋な字句検索です — 依存ゼロで即時。セマンティック検索はオプトインで、Ollama 経由の*ローカル*モデルを使います（API キー不要)。インストーラーがあなたのハードウェアに適合するモデルを推奨します。
</details>

<details>
<summary><b>どれくらい重く、トークンはどれくらいかかりますか?</b></summary>

ごくわずかです。エンジンは **RAM 約 21 MB、アイドル時の CPU 約 0%、依存ゼロ**（Python 標準ライブラリ)。ディスクはメモリ 1 件あたり数十 KB です。セッション開始時に約 300 トークン分のメモリが注入され、各ツール呼び出しは小さな抜粋を返します — 重い処理（インデックス作成、埋め込み、統合）はすべて LLM の外側、あなたのマシン上で実行されます。
</details>

<details>
<summary><b>取り出しの精度はどれくらいですか?</b></summary>

`eval/ygg_eval.py`（ラベル付き 35 ケース、dev/holdout 分割）で測定した recall@1:

| モード | recall@1 | パラフレーズ | 言語横断 (EN→RU) |
| --- | --- | --- | --- |
| 字句（既定) | 0.77 | 0.63 | 0.00 |
| 密 · `all-minilm` (45 MB, EN) | 0.83 | 0.88 | 0.00 |
| 密 · `paraphrase-multilingual` (~560 MB) | **0.94** | 0.88 | **0.80** |

`keyword` および `identifier` クエリはどのモードでも 1.0 です。多言語モデルでは **recall@3 = 1.0**（すべての対象が上位 3 件に入ります)。
</details>

<details>
<summary><b>メモリを手作業で編集・削除できますか?</b></summary>

はい。メモリは Obsidian vault 内の Markdown ノートとして具現化されます — 他のファイルと同じように読んだり、編集したり、削除したりできます。エンジンが完全削除を行うことはなく、アーカイブします（取り消し可能)。
</details>

<details>
<summary><b>本番環境で使える状態ですか?</b></summary>

正直に言って**アルファ**です: ハッピーパスと完全なガバナンスループは、合格しているゲート（`scripts/run_gates.sh`）でカバーされています。マルチユーザー/本番向けにはまだ堅牢化されていません。
</details>

## 🗺️ ロードマップ

- 🛰️ **サーフェス横断の同期** — Web 版やモバイル版の ChatGPT / Claude から接続。CLI・ブラウザ・スマートフォンをまたいだ単一のメモリ。
- 🔗 リレーショングラフ（`SOLVES` / `SUPERSEDES` / `CONTRADICTS`）でより豊かな推論を実現。
- 🐧 Linux/Windows のサービスインストーラー（実装済み。デバイス上での最終テスト中)。

## 🤝 コントリビュート

Issue や PR を歓迎します。提出前に `scripts/run_gates.sh` と `python3 -m unittest discover -s tests` を実行してください — すべてのゲートがグリーンを保つ必要があります。

## 📜 ライセンス

**Elastic License 2.0** — [LICENSE](../LICENSE) を参照してください。Yggdrasil を自由に使用・改変・セルフホスト・再配布できます。ただし、製品として販売したり、ホスト型/マネージド型のサービスとして他者に提供したりすることは**できません**。ソースは公開されています（source-available）が、OSI 定義のオープンソースではありません。
