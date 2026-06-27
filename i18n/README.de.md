<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>Ein einziges, gemeinsames und dauerhaftes Gedächtnis für all deine KI-Coding-Agents.</b><br/>
Claude Code, Codex und jeder MCP-Host erinnern sich an deine Entscheidungen, Erkenntnisse und den Projektstatus — über Sessions, Tools und Projekte hinweg.</p>

<p align="center">
  <a href="https://github.com/VonderVuflya/Yggdrasil/releases/latest"><img src="https://img.shields.io/github/v/release/VonderVuflya/Yggdrasil?label=release&color=blue" alt="Latest release"></a>
  <a href="https://pypi.org/project/yggdrasil-memory/"><img src="https://img.shields.io/pypi/v/yggdrasil-memory?label=PyPI&color=blue" alt="PyPI"></a>
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-Elastic%202.0-blue.svg" alt="Elastic License 2.0"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/deps-zero%20(stdlib)-brightgreen" alt="zero deps">
  <img src="https://img.shields.io/badge/MCP-Claude%20·%20Codex%20·%20Desktop-purple" alt="MCP">
  <img src="https://img.shields.io/badge/local--first-100%25%20private-success" alt="local-first">
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="alpha">
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> ·
  <a href="#-so-funktioniert-es">So funktioniert es</a> ·
  <a href="#-yggdrasil-im-vergleich">Vergleich</a> ·
  <a href="#-befehle">Befehle</a> ·
  <a href="#-faq">FAQ</a>
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

Bei jedem neuen Chat vergisst deine KI alles. Du erklärst das Projekt, die Entscheidungen, die Stolperfallen erneut — jedes Mal, in jedem Tool. **Yggdrasil ist ein kleines, immer aktives Gedächtnis-Gehirn, an das sich jeder Agent anschließt.** Öffne eine neue Session, in einem beliebigen Projekt, mit einer beliebigen KI, und sie weiß bereits, was du entschieden hast, was kaputtgegangen ist und was noch offen ist — und sie lernt im Hintergrund ständig weiter.

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

Kein „lass mich dir kurz in Erinnerung rufen, was wir gestern gemacht haben“ mehr. Es ist einfach da.

## Warum

**Ohne Yggdrasil** erklärst du den Kontext in jedem neuen Chat erneut, Erkenntnisse aus einem Projekt erreichen nie das nächste, der Wechsel von Claude Code zu Codex beginnt bei null, und mühsam erarbeitete Debugging-Einsichten sterben mit der Session.

**Mit Yggdrasil:**

- 🧠 **Dauerhaftes Gedächtnis** — Entscheidungen, Erkenntnisse und Status überdauern Sessions hinweg.
- 🔌 **Jeder Agent, ein Gehirn** — Claude Code, Codex und jeder MCP-Host teilen sich dasselbe Gedächtnis.
- 🌐 **Projektübergreifender Recall** — *„das sieht aus wie das, was du in Projekt B gemacht hast — wiederverwenden?“*
- 🌱 **Selbstlernend** — ein lokales Modell konsolidiert das Gedächtnis im Hintergrund (null API-Tokens).
- 🪪 **Eine Seele** — gib ihm einen Namen und eine Persönlichkeit; in jedem Tool tritt es identisch auf.
- 🔒 **100 % lokal & privat** — dein Gedächtnis lebt auf deiner Maschine. Keine Cloud, kein Konto.

## 🚀 Quick Start

> **Voraussetzungen:** macOS (Linux/Windows bald), Python 3.10+ — oder lass `uv`/`npx` Python für dich holen. Die semantische Suche ist optional und nutzt ein lokales [Ollama](https://ollama.com)-Modell.

**Option A — als Plugin installieren** (ein Schritt, direkt in deinem Agent — ohne Konfiguration). In **Claude Code**:

```text
/plugin marketplace add VonderVuflya/Yggdrasil
/plugin install yggdrasil
```

Die Engine startet beim ersten Gebrauch von selbst (lazy) und erzeugt ihr eigenes lokales Token — **kein API-Key, keine Cloud, nichts zu konfigurieren.** (Codex und Cursor nutzen denselben Ablauf.)

**Option B — den vollständigen Dienst installieren** (immer aktiver Daemon + Auto-Inject beim Session-Start + optionale lokale Modelle):

```bash
uvx --from yggdrasil-memory ygg install      # one-time guided setup
```

<details>
<summary>Jeder Installationskanal (gleiche Engine)</summary>

| Host / Tool | Befehl |
| --- | --- |
| **Claude Code · Codex · Cursor** (Plugin) | `/plugin marketplace add VonderVuflya/Yggdrasil` → `/plugin install yggdrasil` |
| **uvx** _(empfohlene CLI)_ | `uvx --from yggdrasil-memory ygg install` |
| **npm / npx** | `npx yggdrasil-memory install` |
| **pipx** | `pipx install yggdrasil-memory && ygg install` |
| **pip** | `pip install yggdrasil-memory && ygg install` |
| **Homebrew** _(macOS)_ | `brew install VonderVuflya/tap/yggdrasil && ygg install` |
| **Claude Desktop** _(App)_ | zieh die `.mcpb` aus der [neuesten Release](https://github.com/VonderVuflya/Yggdrasil/releases/latest) auf Settings → Extensions ([Anleitung](../packaging/mcpb/README.md)) |
| **aus den Quellen** | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` |

</details>

`ygg install` ist ein einmaliges, geführtes Setup: Es erkennt deine Hardware und **empfiehlt ein passendes lokales Modell** (oder wähle `none` für ein konfigurationsfreies, rein lexikalisches Setup), erzeugt ein privates Auth-Token, installiert einen **immer aktiven Hintergrunddienst** und **registriert die Tools bei Claude Code und Codex**.

**Prüfen & nutzen:**
```bash
ygg doctor       # engine · models · MCP registration · hook — all green?
```
Dann arbeite einfach. Bitte deinen Agent *„ruf ab, was wir über dieses Projekt entschieden haben“*, oder sag ihm *„merk dir diese Entscheidung“* — und in der nächsten Session ist es bereits da.

Du willst nur mal reinschnuppern? `uvx --from yggdrasil-memory ygg serve --reset --db /tmp/ygg.sqlite`.

## 🔌 Mehr Wege zum Verbinden

Über das Plugin und `ygg install` oben hinaus:

- 🖥️ **Claude Desktop (App)** — installiere die MCP-Erweiterung: hol dir `yggdrasil-<version>.mcpb` aus der [neuesten Release](https://github.com/VonderVuflya/Yggdrasil/releases/latest) (oder aus `packaging/mcpb/`), zieh sie auf **Settings → Extensions** und füge dein Token ein (`ygg token`). Die Desktop-App teilt sich nun das **gleiche Gedächtnis** wie deine CLI-Agents. → [Einrichtungsanleitung](../packaging/mcpb/README.md)
- 🧠 **Skill (jedes Claude)** — der [`yggdrasil-memory`-Skill](../skills/) bringt dem Agent den Workflow bei: vor der Arbeit erinnern (recall), danach merken (remember). Lade `yggdrasil-memory.zip` über **Settings → Skills → Create skill → Upload a skill** hoch.

> **MCP vs. Skill:** MCP verbindet die *Tools* (wie das Gedächtnis erreicht wird); der Skill lehrt, *wann* sie zu nutzen sind. Verwende beides für das beste Verhalten.

## 🧠 So funktioniert es

Yggdrasil ist **Gedächtnis + Tools** — die *Intelligenz* ist dein LLM. Es sorgt nur dafür, dass das richtige Gedächtnis im richtigen Moment vor dem richtigen Agent liegt.

- 🛎️ **Immer aktiver Daemon** — ein winziger lokaler Dienst (~21 MB RAM), den deine Agents über MCP-Tools erreichen (`ygg_search`, `ygg_recall`, `ygg_remember` …).
- 🪝 **Session-Start** — ein Hook injiziert automatisch Identität, Projektstatus und offene Follow-ups.
- 📌 **Ranking** — häufig abgerufene und angepinnte Erinnerungen werden weiter oben angezeigt (Speicher & Tiers unten ↓).
- 🧹 **Governance** — Duplikate / Konflikte werden zur Überprüfung angezeigt; Änderungen sind nicht-destruktiv (archivieren, nie löschen).
- 📓 **Obsidian** — jede Erinnerung ist auch eine Markdown-Notiz, die du lesen und bearbeiten kannst.

## 🎛️ Gedächtnis-Tiers — standardmäßig ohne Konfiguration

Von Haus aus läuft Yggdrasil auf **SQLite + FTS5 ohne jede Abhängigkeit** — sofortige Stichwortsuche (lexikalisch), keine Modelle, kein GPU, nichts herunterzuladen. Schon jetzt nützlich: recall@1 ≈ 0.77.

Du willst, dass es nach **Bedeutung** und über Sprachen hinweg trifft? Wenn deine Hardware es zulässt, kann `ygg install` optionale **lokale Modelle über [Ollama](https://ollama.com)** holen — es erkennt deine CPU/RAM/GPU und empfiehlt eine passende Wahl (oder wähle `none`, um konfigurationsfrei zu bleiben). Zwei optionale, unabhängige Tiers:

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

| Tier | Du fügst hinzu | Du gewinnst |
| --- | --- | --- |
| **0 · Standard** | nichts — SQLite + FTS5 | Stichwortsuche, null Abhängigkeiten, sofort — recall@1 ≈ **0.77** |
| **1 · semantisch** | ein **Embedding**-Modell über Ollama (z. B. `all-minilm` 45 MB · `paraphrase-multilingual` ~560 MB) | Suche nach **Bedeutung** + sprachübergreifend — recall@1 ≈ **0.94** |
| **2 · selbstlernend** | ein kleines **Konsolidierungs**-LLM über Ollama (z. B. `qwen2.5:1.5b` ~1 GB) | Dedup/Merge des Gedächtnisses im Hintergrund (vorschlagssicher) |

Ollama **berechnet** nur die Vektoren / führt das Hintergrundmodell aus — die Vektoren und alle Erinnerungen leben weiterhin in **derselben SQLite**. Die Tiers sind unabhängig und opt-in.

<details>
<summary>Vollständiges Modell-Menü (oder führe <code>ygg recommend</code> aus)</summary>

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

</details>

Alles bleibt **100 % lokal — null API-Tokens, keine Cloud.** Der Installer empfiehlt Modelle, die zu deiner Hardware passen (oder wähle `none`, um konfigurationsfrei zu bleiben).

> Die Engine selbst ist austauschbar — jeder Dienst, der den `MemoryBackend`-Vertrag erfüllt, lässt sich direkt einsetzen (richte `YGG_ENGINE_URL` darauf aus); SQLite ist der abhängigkeitsfreie Standard. Siehe [docs/backend-boundary.md](../docs/backend-boundary.md).

## 🆚 Yggdrasil im Vergleich

Das nächstgelegene Tool ist **claude-mem** — ebenfalls dauerhaftes Gedächtnis für Coding-Agents, aber ein *schwergewichtigeres, alles-erfassendes* System: Es zeichnet jede Session automatisch auf und komprimiert sie per KI (braucht Node + Bun + eine Vektor-DB). **mem0** ist ein Gedächtnis-*SDK*, damit Apps sich an ihre Nutzer erinnern. context-mode und Context7 besetzen **andere Ebenen** (dein aktives Kontextfenster; frische Bibliotheks-Docs). Yggdrasil ist **installieren-und-loslegen, abhängigkeitsfreies, local-first-Gedächtnis _deiner eigenen_ Arbeit** — kuratiert, kein Datenschwall, gespeichert als reines Markdown, das du bearbeiten kannst.

| | **Yggdrasil** | [claude-mem](https://github.com/thedotmack/claude-mem) | [mem0](https://github.com/mem0ai/mem0) | [context-mode](https://github.com/mksglu/context-mode) | [Context7](https://github.com/upstash/context7) |
| --- | --- | --- | --- | --- | --- |
| Dauerhaftes Gedächtnis **deiner eigenen Arbeit** (Entscheidungen, Erkenntnisse, Status) | ✅ | ✅ | ✅ | ⚠️ in-session | ❌ |
| **Drop-in** für deine Agents, *ohne Code* (Install + MCP) | ✅ | ✅ | ⚠️ *SDK* | ✅ | ✅ |
| **Null Abhängigkeiten** (stdlib + SQLite; kein Node/Bun/Vektor-DB) | ✅ | ❌ | ❌ | ❌ | — |
| Funktioniert **ohne LLM & ohne API-Key** (lexikalisch als Standard) | ✅ | ❌ *KI-komprimiert* | ❌ *braucht ein LLM* | ✅ | ❌ |
| **Kuratiert** & als reines Markdown bearbeitbar (nicht alles-erfassend) | ✅ | ❌ *erfasst alles automatisch* | ⚠️ | ❌ | — |
| **100 % lokal & privat** (standardmäßig keine Cloud) | ✅ | ⚠️ | ⚠️ *Cloud als Standard* | ✅ | ☁️ gehostet |
| Projekt**übergreifender** Recall („in Projekt B gelöst“) | ✅ | ⚠️ | ⚠️ | ❌ | — |
| Ein Gedächtnis, geteilt **über Tools hinweg** (Claude Code · Codex · jeder MCP-Host) | ✅ | ✅ | ⚠️ *pro App* | ✅ | ✅ |
| Aktuelle öffentliche **Bibliotheks-Docs** | ❌ *(nimm Context7)* | ❌ | ❌ | ❌ | ✅ |

> **claude-mem vs. Yggdrasil, in einem Satz:** claude-mem erfasst automatisch *alles* und komprimiert es per KI (Node + Bun + eine Vektor-DB; ~84k★, bringt einen Krypto-Token mit). Yggdrasil behält die *wenigen Dinge, die zählen* — kuratiert, dedupliziert, abhängigkeitsfrei, gespeichert als Markdown, das dir gehört — keine KI nötig, kein Token. Andere Philosophie; du kannst beide nutzen.

> **mem0 vs. Yggdrasil, in einem Satz:** mem0 ist ein Gedächtnis-**SDK/eine Plattform zum Bauen von Apps, die sich an ihre Nutzer erinnern** (du schreibst Code; es ruft meist ein LLM auf, standardmäßig Cloud). Yggdrasil ist **Drop-in-, local-first-Gedächtnis _deiner eigenen_ Arbeit für die Agents, mit denen du bereits codest.** Andere Aufgabe — wähle danach, wer du bist.

> Passt außerdem gut zu [**autoresearch**](https://github.com/karpathy/autoresearch) — einer autonomen Experimentier-Schleife (kein Gedächtnis-Tool); Yggdrasil verleiht ihr ein Langzeitgedächtnis dessen, was sie bereits ausprobiert hat → [Integration](../integrations/autoresearch/).

**TL;DR:** Du willst automatisches Alles-Erfassen über viele IDEs hinweg und hast nichts gegen einen schwereren Stack → **claude-mem**. Du baust ein KI-*Produkt*, das sich in großem Maßstab an seine Nutzer erinnern muss → **mem0**. Du willst ein winziges, lokales, *kuratiertes* Gedächtnis, das dir gehört — null Abhängigkeiten, keine KI nötig — für die Coding-Agents, die du bereits nutzt → **Yggdrasil**.

## 🧰 Befehle

Agents sehen sechs MCP-Tools: `ygg_health`, `ygg_bootstrap`, `ygg_search`, `ygg_recall`, `ygg_remember`, `ygg_materialize`. Nach `ygg install` sind sie automatisch bei Claude Code und Codex registriert — öffne einfach ein Projekt und arbeite.

<details>
<summary>Vollständige <code>ygg</code>-CLI-Referenz</summary>

**Gedächtnis-Operationen**

| Befehl | Was er macht |
| --- | --- |
| `ygg recall --query "…"` | **Projektübergreifende** Suche — „habe ich das schon irgendwo gemacht?“ |
| `ygg search --project P --query "…"` | Projektbezogene Suche (`--type`, `--tag`, `--limit`, `--json`) |
| `ygg remember --project P --type debugging_lesson --content "…"` | Eine dauerhafte Erinnerung speichern (geheimnisgeschützt, dedupliziert; `--tag` zum Beschriften) |
| `ygg bootstrap --project P` | Das Gedächtnis eines Projekts laden, bevor die Arbeit beginnt |
| `ygg pin --id ID` · `ygg unpin --id ID` | Eine Erinnerung anpinnen, damit sie zuverlässig erscheint |
| `ygg supersede --id ID` | Eine veraltete Erinnerung archivieren, die eine neuere ersetzt |
| `ygg materialize --id ID --project P` | Eine Erinnerung in eine Obsidian-Notiz exportieren |

**Dienst & Einrichtung**

| Befehl | Was er macht |
| --- | --- |
| `ygg install` · `ygg setup` | Geführtes Setup → Hintergrunddienst + MCP-Registrierung |
| `ygg doctor` · `ygg update` | Die Installation diagnostizieren · den neuesten Code neu deployen |
| `ygg status` · `start` · `stop` · `restart` · `logs` | Den immer aktiven Daemon verwalten |
| `ygg hooks` · `unhooks` | Den SessionStart-Auto-Bootstrap-Hook aktivieren/deaktivieren |
| `ygg recommend` | Den hardwarebewussten Modellkatalog anzeigen |
| `ygg token` · `uninstall` | Das Auth-Token ausgeben · Dienst + Registrierung entfernen |

Gib ihm eine Persönlichkeit — bearbeite `~/.yggdrasil/identity.json`:

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

</details>

## ❓ FAQ

<details>
<summary><b>Schickt es meinen Code oder mein Gedächtnis in die Cloud?</b></summary>

Nein. Die Engine, die Datenbank und die optionalen Modelle laufen alle lokal. Kein Konto, keine Telemetrie. Dein Gedächtnis verlässt nie deine Maschine.
</details>

<details>
<summary><b>Merkt es sich automatisch alles?</b></summary>

Nein — bewusst nicht. Das Abrufen ist automatisch; das *Schreiben* ist absichtlich (der Agent ruft `ygg_remember` für dauerhafte Erkenntnisse auf). Alles automatisch zu erfassen verschmutzt das Gedächtnis, also tun wir das nicht. Ein Hintergrundmodell konsolidiert das bereits Gespeicherte (standardmäßig nur als Vorschlag).
</details>

<details>
<summary><b>Brauche ich ein GPU oder einen API-Key?</b></summary>

Nein. Der Standard ist reine lexikalische Suche — null Abhängigkeiten, sofort. Die semantische Suche ist optional und nutzt ein *lokales* Modell über Ollama (kein API-Key). Der Installer empfiehlt ein Modell, das zu deiner Hardware passt.
</details>

<details>
<summary><b>Wie schwergewichtig ist es, und wie viele Tokens kostet es?</b></summary>

Winzig. Die Engine braucht **~21 MB RAM, ~0 % CPU im Leerlauf, null Abhängigkeiten** (Python-stdlib); der Speicher liegt bei zig KB pro Erinnerung. Der Session-Start injiziert ~300 Tokens an Gedächtnis und jeder Tool-Aufruf liefert einen kleinen Ausschnitt zurück — die ganze schwere Arbeit (Indexierung, Embeddings, Konsolidierung) läuft off-LLM auf deiner Maschine.
</details>

<details>
<summary><b>Wie gut ist das Abrufen?</b></summary>

Gemessen mit `eval/ygg_eval.py` (35 gelabelte Fälle, dev/holdout-Split), recall@1:

| Modus | recall@1 | Paraphrase | sprachübergreifend (EN→RU) |
| --- | --- | --- | --- |
| lexikalisch (Standard) | 0.77 | 0.63 | 0.00 |
| dense · `all-minilm` (45 MB, EN) | 0.83 | 0.88 | 0.00 |
| dense · `paraphrase-multilingual` (~560 MB) | **0.94** | 0.88 | **0.80** |

`keyword`- und `identifier`-Anfragen liegen in jedem Modus bei 1.0; mit dem mehrsprachigen Modell **recall@3 = 1.0** (jedes Ziel in den Top 3).
</details>

<details>
<summary><b>Kann ich Erinnerungen von Hand bearbeiten oder löschen?</b></summary>

Ja. Erinnerungen materialisieren sich als Markdown-Notizen in einem Obsidian-Vault — lies, bearbeite oder entferne sie wie jede andere Datei. Die Engine löscht nie endgültig; sie archiviert (umkehrbar).
</details>

<details>
<summary><b>Ist es produktionsreif?</b></summary>

Es ist eine ehrliche **Alpha**: Der Happy Path und die vollständige Governance-Schleife sind durch bestehende Gates abgedeckt (`scripts/run_gates.sh`). Noch nicht gehärtet für Multi-User/Produktion.
</details>

## 🗺️ Roadmap

- 🛰️ **Surface-übergreifende Synchronisierung** — verbinde dich von ChatGPT / Claude im Web und auf dem Handy; ein Gedächtnis über CLI, Browser und Telefon hinweg.
- 🔗 Relationsgraph (`SOLVES` / `SUPERSEDES` / `CONTRADICTS`) für reichhaltigeres Schlussfolgern.
- 🐧 Linux/Windows-Dienst-Installer (implementiert; finale Tests am Gerät).

## 🤝 Mitwirken

Issues und PRs willkommen. Führe `scripts/run_gates.sh` und `python3 -m unittest discover -s tests` vor dem Einreichen aus — alle Gates müssen grün bleiben.

## 📜 Lizenz

**Elastic License 2.0** — siehe [LICENSE](../LICENSE). Du darfst Yggdrasil frei nutzen, modifizieren, selbst hosten und weitergeben. Du darfst es **nicht** als Produkt verkaufen oder anderen als gehosteten/verwalteten Dienst anbieten. Es ist source-available — kein OSI-Open-Source.
