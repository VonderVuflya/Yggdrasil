<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>新しい AI セッションのたびにプロジェクトを説明し直すのは、もう終わりにしましょう。</b><br/>
Claude Code、Codex、あらゆる MCP エージェントのための、たったひとつのローカルメモリ — セッション・ツール・プロジェクトをまたいで共有されます。依存関係ゼロ。データがあなたのマシンの外に出ることはありません。</p>

<p align="center">
  <a href="https://github.com/VonderVuflya/Yggdrasil/releases/latest"><img src="https://img.shields.io/github/v/release/VonderVuflya/Yggdrasil?label=release&color=blue" alt="Latest release"></a>
  <a href="https://pypi.org/project/yggdrasil-memory/"><img src="https://img.shields.io/pypi/v/yggdrasil-memory?label=PyPI&color=blue" alt="PyPI"></a>
  <a href="https://glama.ai/mcp/servers/VonderVuflya/Yggdrasil"><img src="https://glama.ai/mcp/servers/VonderVuflya/Yggdrasil/badges/score.svg" alt="Glama quality score"></a>
  <a href="../BENCHMARKS.md"><img src="https://img.shields.io/badge/recall@1-0.93%20·%20reproducible-brightgreen" alt="Benchmarks"></a>
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-AGPL%203.0-blue.svg" alt="AGPL-3.0"></a>
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="alpha">
</p>

<p align="center">
  <a href="#-インストール">インストール</a> ·
  <a href="#-仕組み">仕組み</a> ·
  <a href="#-数字で見る">数字で見る</a> ·
  <a href="#-yggdrasil-と他ツールの比較">比較</a> ·
  <a href="#-よくある質問">FAQ</a>
</p>

<p align="center">
  他の言語で読む: <a href="../README.md">English</a> · <a href="./README.ru.md">Русский</a> · <a href="./README.zh.md">简体中文</a> · <a href="./README.es.md">Español</a> · <a href="./README.fr.md">Français</a> · <a href="./README.de.md">Deutsch</a>
</p>

---

<p align="center">
  <img src="../docs/demo.gif" alt="Yggdrasil — a brand-new session already knows your project, and recalls a fix from another project" width="880">
</p>

新しいチャットを始めるたびに、AI はすべてを忘れています。プロジェクト、決定事項、ハマりどころを — 毎回、どのツールでも — 説明し直すことになります。**Yggdrasil は、どんなエージェントでも接続できる、常時稼働の小さなメモリです。** どのプロジェクトでも、どの AI でも、新しいセッションを開けば、あなたが何を決め、何が壊れ、何がまだ未解決なのかをすでに把握しています。

```text
$ cd ~/projects/checkout-api && claude        # a brand-new session

🌳 Yggdrasil  (injected automatically at session start)
   • [project_status] payments refactor: idempotency keys added; open: e2e tests
   • [lesson] webhook 401 → signing secret rotated; update env + redeploy

> "have I solved a flaky websocket reconnect anywhere before?"

🌳 recall → found in project `realtime-dash`:
   refresh the token *before* opening the socket, then retry with capped backoff.
```

「昨日やったことを思い出させてください」は不要です。最初からそこにあります。

## 🚀 インストール

**Claude Code** の中で、コマンドは 2 つだけ（プラグインは [`uv`](https://docs.astral.sh/uv/) 経由で起動します):

```text
/plugin marketplace add VonderVuflya/Yggdrasil
/plugin install yggdrasil
```

エンジンは初回利用時に遅延起動し、独自のローカルトークンを生成します — API キー不要、クラウド不要、設定するものは何もありません。Codex と Cursor も同じ流れです。

<details>
<summary>その他すべての経路 — CLI デーモン、Homebrew、npm、Claude Desktop、ソースから…</summary>

| ホスト / ツール | コマンド |
| --- | --- |
| **uvx** _(推奨 CLI)_ | `uvx --from yggdrasil-memory ygg install` |
| **npm / npx** | `npx yggdrasil-memory install` |
| **pipx** | `pipx install yggdrasil-memory && ygg install` |
| **pip** | `pip install yggdrasil-memory && ygg install` |
| **Homebrew** _(macOS)_ | `brew install VonderVuflya/tap/yggdrasil && ygg install` |
| **Claude Desktop** _(アプリ)_ | [最新リリース](https://github.com/VonderVuflya/Yggdrasil/releases/latest) から `.mcpb` を Settings → Extensions にドラッグし、トークン（`ygg token`）を貼り付けます — これでデスクトップアプリは CLI エージェントと同じメモリを共有します（[ガイド](../packaging/mcpb/README.md)) |
| **ソースから** | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` |

`ygg install` は一度きりのガイド付きセットアップです。常時稼働のバックグラウンドサービスをインストールし、MCP ツールを Claude Code と Codex に登録し、ハードウェアが許せばオプションのローカルモデルを推奨します（`none` を選べば設定不要のままにできます)。

あらゆる Claude サーフェス向けに [`yggdrasil-memory` skill](../skills/) もあります。MCP は*ツール*を接続し、skill はエージェントに*いつ使うか*を教えます。最良の挙動を得るには両方を使ってください。

何もインストールせず、使い捨ての DB で試すには: `uvx --from yggdrasil-memory ygg serve --reset --db /tmp/ygg.sqlite`。

</details>

あとは作業するだけです。エージェントに *「このプロジェクトについて決めたことを思い出して」* と尋ねたり、*「この決定を記憶して」* と伝えたりすれば — 次のセッションではもうそこにあります。インストールの確認はいつでも `ygg doctor` でできます。

**すでに履歴がありますか?** 既存の Claude Code + Codex のトランスクリプト、Obsidian vault、`CLAUDE.md` リポジトリからメモリをシードできます — すべてローカルで蒸留されます:

```bash
ygg seed --dry-run    # see what it would import; drop the flag to distill for real
```

## なぜ Yggdrasil なのか

- 🧠 **永続する** — 決定・教訓・プロジェクトの状況がセッションをまたいで残ります。
- 🔌 **どのツールでも、頭脳はひとつ** — Claude Code、Codex、あらゆる MCP ホストが同じメモリを共有します。
- 🌐 **プロジェクト横断の想起** — *「これはプロジェクト B でやったことに似ています — 再利用しますか?」*
- 🧹 **キャプチャではなく、厳選** — エージェントは本当に重要な数少ないものだけを保存します。ガバナンスが重複排除とアーカイブを行い、削除は決してしません。
- 🌱 **自己メンテナンス** *（オプトイン)* — 小さなローカルモデルがバックグラウンドでメモリを統合します。API トークンはゼロ。
- 🪪 **どこでも同じアイデンティティ** — オプションの名前と人格をすべてのエージェントが引き継ぎ、Claude Code と Codex が同じアシスタントのように感じられます。
- 🔒 **100% ローカル** — あなたのメモリはあなたのマシンに置かれます。クラウドなし、アカウント不要、テレメトリなし。

## 🧠 仕組み

Yggdrasil は **メモリ + ツール** です — *知能*はあなたの LLM が担います。Yggdrasil は、適切なメモリを適切なエージェントの前に適切なタイミングで届けることだけを行います。

- 🛎️ **常時稼働のデーモン** — エージェントが MCP ツール（`ygg_search`、`ygg_recall`、`ygg_remember` …）で接続する小さなローカルサービス（RAM 約 21 MB)。
- 🪝 **セッション開始時** — フックがアイデンティティ・プロジェクトの状況・未解決のフォローアップを自動注入します（約 300 トークン)。
- 📌 **ランキング** — ピン留めされたメモリや頻繁に想起されるメモリが最初に表示されます。
- 🧹 **ガバナンス** — 重複や矛盾はレビュー待ちのキューに入り、変更は非破壊的です（アーカイブのみ、削除はしません)。
- 📓 **Obsidian** — すべてのメモリは、読む・編集する・grep するができるプレーンな Markdown ノートでもあります。

## 🎛️ メモリのティア — 既定では設定不要

Yggdrasil は箱から出してすぐ、**依存ゼロの SQLite + FTS5** で動作します — 即時のキーワード検索、モデル不要、ダウンロードするものもありません。[Ollama](https://ollama.com) 経由のオプションの**ローカル**モデルで、独立した 2 つのティアを追加できます:

| ティア | 追加するもの | 得られるもの |
| --- | --- | --- |
| **0 · 既定** | 何も不要 — SQLite + FTS5 | キーワード検索、依存ゼロ、即時 — recall@1 = **0.77** |
| **1 · セマンティック** | **埋め込み**モデル（`all-minilm` 45 MB · `paraphrase-multilingual` ~560 MB) | **意味**による、言語をまたいだ検索 — recall@1 = **0.93**、recall@3 **1.00** |
| **2 · 自己メンテナンス** | 小さな **LLM**（`qwen2.5:1.5b` ~1 GB) | バックグラウンドでのメモリの重複排除/統合（提案のみ) |

Ollama はベクトルの*計算*とバックグラウンドモデルの実行だけを行います — すべてのメモリとベクトルは同じローカルの SQLite に置かれたままです。`ygg install` はハードウェアを検出して適合するモデルを推奨します（`ygg recommend` で全カタログを表示できます)。

<details>
<summary>モデルの全メニュー</summary>

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

エンジン自体は差し替え可能です — `MemoryBackend` 契約を満たすサービスならどれでもそのまま組み込めます（`YGG_ENGINE_URL`)。[docs/backend-boundary.md](../docs/backend-boundary.md) を参照してください。

</details>

## 📊 数字で見る

[`eval/ygg_eval.py`](../eval/ygg_eval.py) で測定 — ラベル付きクエリ 35 件、ランキングの重みは *dev* 分割のみで調整しているため、**holdout こそがバイアスのない数字**です（recall@1、`paraphrase-multilingual` モデル):

| 検索ビュー | holdout recall@1 | recall@3 | 依存ゼロの字句 |
| --- | --- | --- | --- |
| **プロジェクト内**（実際の経路、プール約 6) | **0.93** | **1.00** | 0.77 |
| **ストア全体**（フィルタなし、プール 35) | 0.80 | **1.00** | 0.77 |

**どちらのビューでも recall@3 = 1.00** — ローカルモデルなら、ストア全体を検索しても正しいメモリは*常に*トップ 3 に入り、プロジェクト内では 0.93 の確率で 1 位です。依存ゼロの字句モードは、キーワードとコード識別子のクエリをすでに解決できます（1.00）。コーパスが小さい（n=35）ため、[BENCHMARKS.md の完全な内訳](../BENCHMARKS.md)では 95% 信頼区間、プールサイズ、クラス別スコアを示しています — そして約 1 分で再実行できます: `python3 eval/ygg_eval.py --report`。

## 🆚 Yggdrasil と他ツールの比較

他のツールは、トランスクリプトを自動キャプチャするか、クラウドを売りつけるかのどちらかです。Yggdrasil の賭けはこうです: **本当に重要な数少ないもの**だけを、厳選・重複排除して、あなたが所有する素のレコードとして保持し — それを**すべて**のツールとプロジェクトで共有すること。

| | **Yggdrasil** | 組み込みメモリ <sub>(Claude Code · Codex)</sub> | [claude-mem](https://github.com/thedotmack/claude-mem) | [mem0](https://github.com/mem0ai/mem0) / OpenMemory | [basic-memory](https://github.com/basicmachines-co/basic-memory) |
| --- | --- | --- | --- | --- | --- |
| 厳選された決定 / 教訓 / 状況（トランスクリプトではなく) | ✅ | ⚠️ 自動メモ | ❌ すべてキャプチャ | ⚠️ | ⚠️ 自由形式ノート |
| **ツール横断**の単一メモリ | ✅ | ❌ ベンダー内に閉じる | ✅ | ✅ | ✅ |
| **プロジェクト横断**の想起（「プロジェクト B で解決済み」) | ✅ | ❌ リポジトリ単位 | ⚠️ | ⚠️ | ⚠️ |
| 既定で **100% ローカル** | ✅ | ✅ | ⚠️ クラウド同期アドオン | ❌ ホスト型が主 | ✅ |
| **依存ゼロ**（stdlib + SQLite) | ✅ | — | ❌ Node + Bun + 常駐ワーカー | ❌ Docker + Qdrant + LLM キー | ❌ |
| **LLM も API キーも不要**で動作 | ✅ | ✅ | ❌ AI で圧縮 | ❌ | ✅ |
| **完全ローカルのセマンティック検索** | ✅ オプトインの Ollama | ❌ grep のみ | ⚠️ オプションの Chroma | ⚠️ API キーか Docker スタックが必要 | ❌ |
| あなたが所有するプレーンな **Markdown**（Obsidian 対応) | ✅ | ✅ | ❌ | ❌ | ✅ |

**最も近い隣人 — claude-mem:** すべてのセッションを記録して AI で圧縮する「すべてをキャプチャする」メモリです（Node 20+ *と* Bun、常駐ワーカーデーモンが必要。Chroma はオプション)。Yggdrasil はその正反対の賭けです: 増え続ける奔流ではなく、小さく高信号なストア。**mem0** は、*アプリ*が*そのユーザー*を記憶するための SDK + ホスト型プラットフォームで、セルフホストでも LLM の API キーが必要です。**組み込みメモリ**は本当に便利です — そして構造的に閉じています: ひとつのベンダー、ひとつのリポジトリ、ひとつのマシン、文字どおりの grep。Yggdrasil はその一段上のレイヤーです（そして `ygg seed` は、まさにそのトランスクリプトから自身をブートストラップできます)。まったく別のレイヤーとして: [context-mode](https://github.com/mksglu/context-mode)（ライブなコンテキストウィンドウ）と [Context7](https://github.com/upstash/context7)（最新のライブラリドキュメント) — どちらも Yggdrasil と問題なく併用できます。

## 🧰 コマンド

エージェントには 6 つの MCP ツールが見えます: `ygg_health`、`ygg_bootstrap`、`ygg_search`、`ygg_recall`、`ygg_remember`、`ygg_materialize` — プラグインまたは `ygg install` により自動登録されます。

<details>
<summary><code>ygg</code> CLI の完全リファレンス</summary>

**メモリ操作**

| コマンド | 何をするか |
| --- | --- |
| `ygg recall --query "…"` | **プロジェクト横断**検索 — 「これをどこかでやったことはあるか?」 |
| `ygg search --project P --query "…"` | プロジェクトに絞った検索（`--type`、`--tag`、`--limit`、`--json`) |
| `ygg remember --project P --type lesson --content "…"` | 永続メモリを保存（シークレット保護つき、重複排除あり) |
| `ygg bootstrap --project P` | 作業を始める前にプロジェクトのメモリを取り込む |
| `ygg pin --id ID` · `ygg unpin --id ID` | メモリをピン留めして確実に表示されるようにする |
| `ygg supersede --id ID` | 新しいメモリが置き換える古いメモリをアーカイブする |
| `ygg materialize --id ID --project P` | 1 つのメモリを Obsidian ノートにエクスポートする |

**コールドスタート**

| コマンド | 何をするか |
| --- | --- |
| `ygg seed` | Claude Code + Codex のトランスクリプト、Obsidian vault、`CLAUDE.md` リポジトリを蒸留 — 増分的・重複排除済み・完全ローカル |
| `ygg seed --dry-run` · `--force` | 発見と見積もりのみ · すべてを再蒸留 |
| `ygg distill --source PATH` | 1 つのディレクトリ/ファイルを教訓へ蒸留 |
| `ygg reindex` | 欠けている埋め込みを補完（密な想起を復元) |

**サービスとセットアップ**

| コマンド | 何をするか |
| --- | --- |
| `ygg install` · `ygg doctor` · `ygg update` | ガイド付きセットアップ · 実行可能な修正つきの診断 · アップグレード |
| `ygg config` | 永続的な設定の表示/変更（`list` · `get` · `set` · `unset`) |
| `ygg status` · `start` · `stop` · `restart` · `logs` | 常時稼働デーモンを管理 |
| `ygg hooks` · `unhooks` · `register` | SessionStart フックの有効化/無効化 · MCP の(再)登録 |
| `ygg recommend` · `token` · `uninstall` | モデルカタログ · 認証トークンの表示 · すべてを削除 |

人格を与えましょう — `~/.yggdrasil/identity.json` を編集します:

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

シードが重く、ラップトップが非力? 蒸留処理を LAN 上のより高性能なマシンに向けましょう: `ygg config set distill_url http://<box>:11434` — 詳細は [docs/ygg-cli.md](../docs/ygg-cli.md) を参照してください。

</details>

## ❓ よくある質問

<details>
<summary><b>Claude Code にはすでに組み込みメモリがあります — なぜ Yggdrasil が必要?</b></summary>

組み込みメモリはベンダーごと・リポジトリごと・マシンごとに閉じており、取り出しは文字どおりのテキスト一致です。Yggdrasil はその一段上のレイヤーです: Claude Code、Codex、あらゆる MCP ホストで*同じ*メモリ、プロジェクトを*またいだ*想起、オプションのセマンティック検索 — それでいて 100% ローカル。両者は組み合わせられます: ネイティブのメモリはそのままに、`ygg seed` に既存の履歴を蒸留させて共有の頭脳に取り込みましょう。
</details>

<details>
<summary><b>コードやメモリをクラウドに送信しますか?</b></summary>

いいえ。エンジン、データベース、オプションのモデルはすべてローカルで動作します。アカウントもテレメトリもありません。唯一の外向き通信は PyPI へのバージョンチェックです。
</details>

<details>
<summary><b>すべてを自動的に記憶しますか?</b></summary>

いいえ — 意図的な設計です。取り出しは自動ですが、*書き込み*は意図的です（エージェントは永続的な教訓のために `ygg_remember` を呼び出します)。すべてをキャプチャするとメモリが汚染されトークンを浪費するため、そうはしません。オプションのバックグラウンドモデルは、すでに保存済みのものを統合します（提案のみ)。
</details>

<details>
<summary><b>GPU や API キーは必要ですか?</b></summary>

いいえ。既定は純粋な字句検索です — 依存ゼロで即時。セマンティック検索はオプトインで、Ollama 経由の*ローカル*モデルを使います。インストーラーがあなたのハードウェアに適合するモデルを推奨します。
</details>

<details>
<summary><b>どれくらい重く、トークンはどれくらいかかりますか?</b></summary>

エンジンのアイドル時は **RAM 約 21 MB**（字句検索の既定）、CPU 約 0%。ディスクはメモリ 1 件あたり数十 KB です。セッション開始時に約 300 トークンが注入され、各ツール呼び出しは小さな抜粋を返します。重い処理（インデックス作成、埋め込み、統合）はすべて LLM の外側、あなたのマシン上で実行されます。
</details>

<details>
<summary><b>メモリを手作業で編集・削除できますか?</b></summary>

はい。メモリは Obsidian vault 内の Markdown ノートとして具現化されます — 他のファイルと同じように読んだり、編集したり、削除したりできます。エンジンが完全削除を行うことはなく、アーカイブします（取り消し可能)。
</details>

## 🚦 ステータスとロードマップ

**アルファ版です。** ハッピーパスとガバナンスループはゲートテスト済みです（`scripts/run_gates.sh`)。マルチユーザーや本番用途向けにはまだ堅牢化されていません。現在は macOS 対応で、Linux/Windows のサービスインストーラーは実装済み・デバイス上での最終テスト中です。

次の予定: 🛰️ サーフェス横断の同期（CLI・Web・スマートフォンをまたぐ単一のメモリ） · 🔗 リレーショングラフ（`SOLVES` / `SUPERSEDES` / `CONTRADICTS`） · 🐧 Linux/Windows の GA。

## 🤝 コントリビュート

Issue や PR を歓迎します。提出前に `scripts/run_gates.sh` と `python3 -m unittest discover -s tests` を実行してください — すべてのゲートがグリーンを保つ必要があります。

## 📜 ライセンス

**GNU AGPL v3.0** — [LICENSE](../LICENSE) を参照してください。自由なオープンソースです: 使用・改変・セルフホスト・再配布が可能です。改変する場合、またはネットワークサービスとして提供する場合は、同じライセンスでソースコードを公開する必要があります。
