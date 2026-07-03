<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>Schluss damit, jeder neuen KI-Session dein Projekt neu zu erklären.</b><br/>
Ein lokales Gedächtnis für Claude Code, Codex und jeden MCP-Agent — geteilt über Sessions, Tools und Projekte hinweg. Null Abhängigkeiten. Nichts verlässt deine Maschine.</p>

<p align="center">
  <a href="https://github.com/VonderVuflya/Yggdrasil/releases/latest"><img src="https://img.shields.io/github/v/release/VonderVuflya/Yggdrasil?label=release&color=blue" alt="Latest release"></a>
  <a href="https://pypi.org/project/yggdrasil-memory/"><img src="https://img.shields.io/pypi/v/yggdrasil-memory?label=PyPI&color=blue" alt="PyPI"></a>
  <a href="https://glama.ai/mcp/servers/VonderVuflya/Yggdrasil"><img src="https://glama.ai/mcp/servers/VonderVuflya/Yggdrasil/badges/score.svg" alt="Glama quality score"></a>
  <a href="../BENCHMARKS.md"><img src="https://img.shields.io/badge/recall@1-0.93%20·%20reproducible-brightgreen" alt="Benchmarks"></a>
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-AGPL%203.0-blue.svg" alt="AGPL-3.0"></a>
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="alpha">
</p>

<p align="center">
  <a href="#-installation">Installation</a> ·
  <a href="#-so-funktioniert-es">So funktioniert es</a> ·
  <a href="#-die-zahlen">Zahlen</a> ·
  <a href="#-yggdrasil-im-vergleich">Vergleich</a> ·
  <a href="#-faq">FAQ</a>
</p>

<p align="center">
  Lies dies auf: <a href="../README.md">English</a> · <a href="./README.ru.md">Русский</a> · <a href="./README.zh.md">简体中文</a> · <a href="./README.es.md">Español</a> · <a href="./README.fr.md">Français</a> · <a href="./README.ja.md">日本語</a>
</p>

---

<p align="center">
  <img src="../docs/demo.gif" alt="Yggdrasil — a brand-new session already knows your project, and recalls a fix from another project" width="880">
</p>

Bei jedem neuen Chat vergisst deine KI alles. Du erklärst das Projekt, die Entscheidungen, die Stolperfallen erneut — jedes Mal, in jedem Tool. **Yggdrasil ist ein winziges, immer aktives Gedächtnis, an das sich jeder Agent anschließt.** Öffne eine neue Session — in einem beliebigen Projekt, mit einer beliebigen KI — und sie weiß bereits, was du entschieden hast, was kaputtging und was noch offen ist.

```text
$ cd ~/projects/checkout-api && claude        # a brand-new session

🌳 Yggdrasil  (injected automatically at session start)
   • [project_status] payments refactor: idempotency keys added; open: e2e tests
   • [lesson] webhook 401 → signing secret rotated; update env + redeploy

> "have I solved a flaky websocket reconnect anywhere before?"

🌳 recall → found in project `realtime-dash`:
   refresh the token *before* opening the socket, then retry with capped backoff.
```

Kein „lass mich dir kurz in Erinnerung rufen, was wir gestern gemacht haben“ mehr. Es ist einfach da.

## 🚀 Installation

Zwei Befehle, direkt in **Claude Code** (das Plugin startet über [`uv`](https://docs.astral.sh/uv/)):

```text
/plugin marketplace add VonderVuflya/Yggdrasil
/plugin install yggdrasil
```

Die Engine startet beim ersten Gebrauch von selbst (lazy) und erzeugt ihr eigenes lokales Token — kein API-Key, keine Cloud, nichts zu konfigurieren. Codex und Cursor nutzen denselben Ablauf.

<details>
<summary>Alle anderen Kanäle — CLI-Daemon, Homebrew, npm, Claude Desktop, aus den Quellen …</summary>

| Host / Tool | Befehl |
| --- | --- |
| **uvx** _(empfohlene CLI)_ | `uvx --from yggdrasil-memory ygg install` |
| **npm / npx** | `npx yggdrasil-memory install` |
| **pipx** | `pipx install yggdrasil-memory && ygg install` |
| **pip** | `pip install yggdrasil-memory && ygg install` |
| **Homebrew** _(macOS)_ | `brew install VonderVuflya/tap/yggdrasil && ygg install` |
| **Claude Desktop** _(App)_ | zieh die `.mcpb` aus der [neuesten Release](https://github.com/VonderVuflya/Yggdrasil/releases/latest) auf Settings → Extensions und füge dein Token ein (`ygg token`) — die Desktop-App teilt sich dann dasselbe Gedächtnis wie deine CLI-Agents ([Anleitung](../packaging/mcpb/README.md)) |
| **aus den Quellen** | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` |

`ygg install` ist ein einmaliges, geführtes Setup: Es installiert einen immer aktiven Hintergrunddienst, registriert die MCP-Tools bei Claude Code und Codex und empfiehlt — wenn deine Hardware es hergibt — optionale lokale Modelle (oder wähle `none`, um konfigurationsfrei zu bleiben).

Für jede Claude-Oberfläche gibt es außerdem einen [`yggdrasil-memory`-Skill](../skills/): MCP verbindet die *Tools*, der Skill lehrt den Agent, *wann* er sie nutzen soll. Verwende beides für das beste Verhalten.

Ausprobieren, ohne irgendetwas zu installieren — mit einer Wegwerf-DB: `uvx --from yggdrasil-memory ygg serve --reset --db /tmp/ygg.sqlite`.

</details>

Dann arbeite einfach: Bitte deinen Agent *„ruf ab, was wir über dieses Projekt entschieden haben“*, sag ihm *„merk dir diese Entscheidung“* — in der nächsten Session ist es schon da. Prüfe die Installation jederzeit mit `ygg doctor`.

**Schon Historie vorhanden?** Befülle das Gedächtnis aus deinen bestehenden Claude Code + Codex-Transkripten, Obsidian-Vaults und `CLAUDE.md`-Repos — lokal destilliert:

```bash
ygg seed --dry-run    # see what it would import; drop the flag to distill for real
```

**Du verlässt ein anderes Memory-Tool?** `ygg import --from mcp-memory --path memory.json` zieht dessen gesamten Speicher in Yggdrasil (dedupliziert, geheimnisgeschützt) — danach kannst du es löschen.

## Warum

- 🧠 **Persistent** — Entscheidungen, Erkenntnisse und Projektstatus überdauern jede Session.
- 🔌 **Ein Gehirn, jedes Tool** — Claude Code, Codex und jeder MCP-Host teilen sich dasselbe Gedächtnis.
- 🌐 **Projektübergreifender Recall** — *„das sieht aus wie das, was du in Projekt B gemacht hast — wiederverwenden?“*
- 🧹 **Kuratiert statt mitgeschnitten** — dein Agent speichert die wenigen Dinge, die zählen; die Governance dedupliziert und archiviert, löscht aber nie.
- 🌱 **Selbstpflegend** *(opt-in)* — ein kleines lokales Modell konsolidiert das Gedächtnis im Hintergrund. Null API-Tokens.
- 🪪 **Eine Identität überall** — ein optionaler Name samt Persona, den jeder Agent übernimmt — Claude Code und Codex fühlen sich wie derselbe Assistent an.
- 🔒 **100 % lokal** — dein Gedächtnis lebt auf deiner Maschine. Keine Cloud, kein Konto, keine Telemetrie.

## 🧠 So funktioniert es

Yggdrasil ist **Gedächtnis + Tools** — die *Intelligenz* ist dein LLM. Es sorgt nur dafür, dass das richtige Gedächtnis im richtigen Moment vor dem richtigen Agent liegt.

- 🛎️ **Immer aktiver Daemon** — ein winziger lokaler Dienst (~21 MB RAM), den deine Agents über MCP-Tools erreichen (`ygg_search`, `ygg_recall`, `ygg_remember` …).
- 🪝 **Hooks** — der Session-Start injiziert automatisch Identität, Projektstatus und offene Follow-ups (~300 Tokens); ein optionaler Hook pro Prompt ruft automatisch das für *jede Anfrage* relevante Gedächtnis ab.
- 📌 **Ranking** — angepinnte und häufig abgerufene Erinnerungen erscheinen zuerst.
- 🧹 **Governance** — Duplikate und Konflikte landen zur Überprüfung in einer Queue; Änderungen sind nicht-destruktiv (archivieren, nie löschen).
- 📓 **Obsidian** — jede Erinnerung ist zugleich eine einfache Markdown-Notiz, die du lesen, bearbeiten und greppen kannst.

## 🎛️ Gedächtnis-Tiers — standardmäßig ohne Konfiguration

Von Haus aus läuft Yggdrasil auf **SQLite + FTS5 mit null Abhängigkeiten** — sofortige Stichwortsuche, keine Modelle, nichts herunterzuladen. Optionale **lokale** Modelle über [Ollama](https://ollama.com) ergänzen zwei unabhängige Tiers:

| Tier | Du fügst hinzu | Du gewinnst |
| --- | --- | --- |
| **0 · Standard** | nichts — SQLite + FTS5 | Stichwortsuche, null Abhängigkeiten, sofort — recall@1 = **0.77** |
| **1 · semantisch** | ein **Embedding**-Modell (`all-minilm` 45 MB · `paraphrase-multilingual` ~560 MB) | Suche nach **Bedeutung**, über Sprachen hinweg — recall@1 = **0.93**, recall@3 **1.00** |
| **2 · selbstpflegend** | ein kleines **LLM** (`qwen2.5:1.5b` ~1 GB) | Dedup/Merge des Gedächtnisses im Hintergrund (nur Vorschläge) |

Ollama *berechnet* nur Vektoren und führt das Hintergrundmodell aus — jede Erinnerung und jeder Vektor bleibt in derselben lokalen SQLite. `ygg install` erkennt deine Hardware und empfiehlt eine passende Wahl (`ygg recommend` zeigt den vollständigen Katalog).

<details>
<summary>Vollständiges Modell-Menü</summary>

**Embeddings (semantische Suche):**

| Modell | Größe | Gut für |
| --- | --- | --- |
| `all-minilm` | 45 MB | Englisch, winzig & schnell |
| `nomic-embed-text` | 274 MB | Englisch, bessere Qualität |
| `paraphrase-multilingual` | ~560 MB | mehrsprachig (EN/RU + 50 Sprachen) |
| `bge-m3` | 1.2 GB | mehrsprachig, höchste Qualität (schwerer) |

**Hintergrund-Konsolidierung (kleines LLM):**

| Modell | Größe | Gut für |
| --- | --- | --- |
| `qwen2.5:0.5b` | ~400 MB | winzig, schnell auf CPU |
| `qwen2.5:1.5b` | ~1 GB | bester CPU-Standard |
| `llama3.2:3b` | ~2 GB | bessere Qualität, langsamer auf CPU |

Die Engine selbst ist austauschbar — jeder Dienst, der den `MemoryBackend`-Vertrag erfüllt, lässt sich direkt einsetzen (`YGG_ENGINE_URL`); siehe [docs/backend-boundary.md](../docs/backend-boundary.md).

</details>

## 📊 Die Zahlen

Gemessen mit [`eval/ygg_eval.py`](../eval/ygg_eval.py) — 35 gelabelte Anfragen, die Ranking-Gewichte werden nur auf dem *dev*-Split abgestimmt, deshalb ist **holdout die unverzerrte Zahl** (recall@1, mit dem `paraphrase-multilingual`-Modell):

| Suchansicht | holdout recall@1 | recall@3 | Null-Abh. lexikalisch |
| --- | --- | --- | --- |
| **Innerhalb eines Projekts** (der reale Pfad, Pool ~6) | **0.93** | **1.00** | 0.77 |
| **Gesamter Speicher** (kein Filter, Pool 35) | 0.80 | **1.00** | 0.77 |

**recall@3 = 1.00 in beiden Ansichten** — mit dem lokalen Modell liegt die richtige Erinnerung *immer* in den Top 3, selbst bei der Suche im gesamten Speicher; innerhalb eines Projekts ist sie in 0.93 der Fälle auf Platz 1. Der lexikalische Modus ohne Abhängigkeiten löst Stichwort- und Code-Identifier-Anfragen bereits vollständig (1.00). Kleiner Korpus (n=35), daher zeigt die [vollständige Aufschlüsselung in BENCHMARKS.md](../BENCHMARKS.md) 95-%-Konfidenzintervalle, Pool-Größen und Werte je Klasse — und du kannst sie in einer Minute neu ausführen: `python3 eval/ygg_eval.py --report`.

## 🆚 Yggdrasil im Vergleich

Alle anderen schneiden entweder automatisch Transkripte mit oder verkaufen dir eine Cloud. Yggdrasils Wette: Behalte die **wenigen Dinge, die zählen** — kuratiert und dedupliziert, in einfachen Datensätzen, die dir gehören — und teile sie über **jedes** Tool und Projekt hinweg.

| | **Yggdrasil** | Eingebautes Gedächtnis <sub>(Claude Code · Codex)</sub> | [claude-mem](https://github.com/thedotmack/claude-mem) | [mem0](https://github.com/mem0ai/mem0) / OpenMemory | [basic-memory](https://github.com/basicmachines-co/basic-memory) |
| --- | --- | --- | --- | --- | --- |
| Kuratierte Entscheidungen / Erkenntnisse / Status (keine Transkripte) | ✅ | ⚠️ Auto-Notizen | ❌ erfasst alles | ⚠️ | ⚠️ Freiform-Notizen |
| Ein Gedächtnis **über Tools hinweg** | ✅ | ❌ Vendor-Silo | ✅ | ✅ | ✅ |
| **Projektübergreifender** Recall („in Projekt B gelöst“) | ✅ | ❌ auf das Repo begrenzt | ⚠️ | ⚠️ | ⚠️ |
| **100 % lokal** als Standard | ✅ | ✅ | ⚠️ Cloud-Sync als Add-on | ❌ hosted-first | ✅ |
| **Null Abhängigkeiten** (stdlib + SQLite) | ✅ | — | ❌ Node + Bun + Worker-Daemon | ❌ Docker + Qdrant + LLM-Key | ❌ |
| Funktioniert **ohne LLM & ohne API-Key** | ✅ | ✅ | ❌ KI-komprimiert | ❌ | ✅ |
| **Semantische Suche, vollständig lokal** | ✅ opt-in über Ollama | ❌ nur grep | ⚠️ optional Chroma | ⚠️ braucht API-Key oder Docker-Stack | ❌ |
| Reines **Markdown, das dir gehört** (Obsidian-ready) | ✅ | ✅ | ❌ | ❌ | ✅ |

**Der nächste Nachbar — claude-mem:** Alles-Erfassen-Gedächtnis, das jede Session aufzeichnet und per KI komprimiert (Node 20+ *und* Bun, ein persistenter Worker-Daemon; Chroma optional). Yggdrasil ist die gegenteilige Wette: ein kleiner, signalstarker Speicher statt eines wachsenden Datenschwalls. **mem0** ist ein SDK plus gehostete Plattform, um *Apps* zu bauen, die sich an *ihre Nutzer* erinnern — selbst self-hosted braucht es einen LLM-API-Key. **Eingebaute Memories** sind wirklich nützlich — und strukturell isoliert: ein Anbieter, ein Repo, eine Maschine, wörtliches grep. Yggdrasil ist die Ebene darüber (und `ygg seed` kann sich aus genau diesen Transkripten selbst befüllen). Eine ganz andere Ebene: [context-mode](https://github.com/mksglu/context-mode) (aktives Kontextfenster) und [Context7](https://github.com/upstash/context7) (frische Bibliotheks-Docs) — beide vertragen sich bestens mit Yggdrasil.

## 🧰 Befehle

Agents sehen sechs MCP-Tools: `ygg_health`, `ygg_bootstrap`, `ygg_search`, `ygg_recall`, `ygg_remember`, `ygg_materialize` — automatisch registriert durch das Plugin oder `ygg install`.

<details>
<summary>Vollständige <code>ygg</code>-CLI-Referenz</summary>

**Gedächtnis-Operationen**

| Befehl | Was er macht |
| --- | --- |
| `ygg recall --query "…"` | **Projektübergreifende** Suche — „habe ich das schon irgendwo gemacht?“ |
| `ygg search --project P --query "…"` | Projektbezogene Suche (`--type`, `--tag`, `--limit`, `--json`) |
| `ygg remember --project P --type lesson --content "…"` | Eine dauerhafte Erinnerung speichern (geheimnisgeschützt, dedupliziert) |
| `ygg bootstrap --project P` | Das Gedächtnis eines Projekts laden, bevor die Arbeit beginnt |
| `ygg pin --id ID` · `ygg unpin --id ID` | Eine Erinnerung anpinnen, damit sie zuverlässig erscheint |
| `ygg supersede --id ID` | Eine veraltete Erinnerung archivieren, die von einer neueren ersetzt wird |
| `ygg materialize --id ID --project P` | Eine Erinnerung als Obsidian-Notiz exportieren |
| `ygg export-native --project P` | Einen kuratierten Digest nach `AGENTS.md`/`MEMORY.md` schreiben — natives Gedächtnis von Claude Code und Codex damit versorgen |
| `ygg import --from TOOL --path P` | Den Speicher eines anderen Memory-Tools nach Yggdrasil migrieren (`mcp-memory`, `basic-memory`; zuerst `--dry-run`) |
| `ygg review [--apply]` | Die Governance-Queue abarbeiten — Duplikate zusammenführen, veraltete/widersprüchliche Erinnerungen markieren (nur archivieren, umkehrbar) |
| `ygg delete --id ID` · `ygg reset …` | Eine Erinnerung endgültig löschen · einen missglückten `ygg seed` gesammelt rückgängig machen (fragt zuerst nach Bestätigung) |

**Kaltstart**

| Befehl | Was er macht |
| --- | --- |
| `ygg seed` | Destilliert Claude Code + Codex-Transkripte, Obsidian-Vaults, `CLAUDE.md`-Repos — inkrementell, dedupliziert, vollständig lokal |
| `ygg seed --dry-run` · `--force` | Nur erkennen + abschätzen · alles neu destillieren |
| `ygg distill --source PATH` | Ein Verzeichnis/eine Datei zu Lektionen destillieren |
| `ygg reindex` | Fehlende Embeddings nachtragen (stellt den dichten Recall wieder her) |

**Dienst & Einrichtung**

| Befehl | Was er macht |
| --- | --- |
| `ygg install` · `ygg doctor` · `ygg update` | Geführtes Setup · Diagnose mit umsetzbaren Korrekturen · Upgrade |
| `ygg config` | Persistente Einstellungen anzeigen/setzen (`list` · `get` · `set` · `unset`) |
| `ygg status` · `start` · `stop` · `restart` · `logs` | Den immer aktiven Daemon verwalten |
| `ygg hooks` · `unhooks` · `register` | SessionStart-Hook ein/aus · MCP (neu) registrieren |
| `ygg recommend` · `token` · `uninstall` | Modellkatalog · Auth-Token ausgeben · alles entfernen |

Gib ihm eine Persönlichkeit — bearbeite `~/.yggdrasil/identity.json`:

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

Schweres Seeding, schwaches Laptop? Richte die Destillation auf *jede beliebige* Maschine in deinem LAN — einen Desktop mit Ollama, LM Studio, llama.cpp, **sogar ein iPhone mit einer lokalen LLM-Server-App**: `ygg config set distill_url http://<box>:11434`. Yggdrasil erkennt den API-Dialekt automatisch (Ollama oder OpenAI-kompatibel); deine Daten verlassen weiterhin nie dein Netzwerk — Details in [docs/ygg-cli.md](../docs/ygg-cli.md).

</details>

## ❓ FAQ

<details>
<summary><b>Claude Code hat doch schon ein eingebautes Gedächtnis — warum Yggdrasil?</b></summary>

Eingebaute Memories sind pro Anbieter, pro Repo, pro Maschine — und werden per wörtlichem Textabgleich abgerufen. Yggdrasil ist die Ebene darüber: dasselbe Gedächtnis in Claude Code, Codex und jedem MCP-Host, Recall *über* Projekte hinweg, optionale semantische Suche — weiterhin 100 % lokal. Beides ergänzt sich: Behalte das native Gedächtnis und lass `ygg seed` deine bestehende Historie ins gemeinsame Gehirn destillieren.
</details>

<details>
<summary><b>Schickt es meinen Code oder mein Gedächtnis in die Cloud?</b></summary>

Nein. Die Engine, die Datenbank und die optionalen Modelle laufen alle lokal. Kein Konto, keine Telemetrie. Der einzige ausgehende Aufruf ist ein Versions-Check gegen PyPI.
</details>

<details>
<summary><b>Merkt es sich automatisch alles?</b></summary>

Nein — bewusst nicht. Das Abrufen ist automatisch; das *Schreiben* ist absichtlich (der Agent ruft `ygg_remember` für dauerhafte Erkenntnisse auf). Alles-Erfassen verschmutzt das Gedächtnis und verbrennt Tokens — also lassen wir es. Das optionale Hintergrundmodell konsolidiert nur, was bereits gespeichert ist (nur Vorschläge).
</details>

<details>
<summary><b>Brauche ich eine GPU oder einen API-Key?</b></summary>

Nein. Der Standard ist reine lexikalische Suche — null Abhängigkeiten, sofort. Die semantische Suche ist opt-in und nutzt ein *lokales* Modell über Ollama. Der Installer empfiehlt eines, das zu deiner Hardware passt.
</details>

<details>
<summary><b>Wie schwergewichtig ist es, und wie viele Tokens kostet es?</b></summary>

Die Engine läuft im Leerlauf mit **~21 MB RAM** (lexikalischer Standard) bei ~0 % CPU; auf der Platte sind es zig KB pro Erinnerung. Der Session-Start injiziert ~300 Tokens; jeder Tool-Aufruf liefert einen kleinen Ausschnitt zurück. Die ganze schwere Arbeit (Indexierung, Embeddings, Konsolidierung) läuft off-LLM auf deiner Maschine.
</details>

<details>
<summary><b>Kann ich Erinnerungen von Hand bearbeiten oder löschen?</b></summary>

Ja. Erinnerungen materialisieren sich als Markdown-Notizen in einem Obsidian-Vault — lies, bearbeite oder entferne sie wie jede andere Datei. Die Engine löscht nie hart; sie archiviert (umkehrbar).
</details>

## 🚦 Status & Roadmap

**Alpha.** Der Happy Path und die Governance-Schleife sind gate-getestet (`scripts/run_gates.sh`); noch nicht gehärtet für Multi-User- oder Produktionseinsatz. Heute macOS; die Linux/Windows-Dienst-Installer sind gebaut und in finalen Tests am Gerät.

Als Nächstes: 🛰️ surface-übergreifende Synchronisierung (ein Gedächtnis über CLI, Web und Telefon) · 🔗 Relationsgraph (`SOLVES` / `SUPERSEDES` / `CONTRADICTS`) · 🐧 Linux/Windows GA.

## 🤝 Mitwirken

Issues und PRs willkommen. Führe `scripts/run_gates.sh` und `python3 -m unittest discover -s tests` vor dem Einreichen aus — alle Gates müssen grün bleiben.

## 📜 Lizenz

**GNU AGPL v3.0** — siehe [LICENSE](../LICENSE). Frei und quelloffen: nutzen, modifizieren, selbst hosten, weitergeben. Wenn du es modifizierst oder als Netzwerkdienst anbietest, musst du deinen Quellcode unter derselben Lizenz veröffentlichen.
