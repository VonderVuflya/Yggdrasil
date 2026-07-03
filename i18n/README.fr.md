<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>Arrêtez de réexpliquer votre projet à chaque nouvelle session IA.</b><br/>
Une seule mémoire locale pour Claude Code, Codex et tous les agents MCP — partagée entre les sessions, les outils et les projets. Zéro dépendance. Rien ne quitte votre machine.</p>

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
  <a href="#-comment-ça-marche">Comment ça marche</a> ·
  <a href="#-les-chiffres">Les chiffres</a> ·
  <a href="#-yggdrasil-face-aux-autres">Comparatif</a> ·
  <a href="#-faq">FAQ</a>
</p>

<p align="center">
  Lire dans une autre langue : <a href="../README.md">English</a> · <a href="./README.ru.md">Русский</a> · <a href="./README.zh.md">简体中文</a> · <a href="./README.es.md">Español</a> · <a href="./README.ja.md">日本語</a> · <a href="./README.de.md">Deutsch</a>
</p>

---

<p align="center">
  <img src="../docs/demo.gif" alt="Yggdrasil — a brand-new session already knows your project, and recalls a fix from another project" width="880">
</p>

À chaque nouvelle conversation, votre IA oublie tout. Vous réexpliquez le projet, les décisions, les pièges — à chaque fois, dans chaque outil. **Yggdrasil est une petite mémoire toujours active à laquelle n'importe quel agent se branche.** Ouvrez une nouvelle session, dans n'importe quel projet, avec n'importe quelle IA : elle sait déjà ce que vous avez décidé, ce qui a cassé et ce qui reste ouvert.

```text
$ cd ~/projects/checkout-api && claude        # a brand-new session

🌳 Yggdrasil  (injected automatically at session start)
   • [project_status] payments refactor: idempotency keys added; open: e2e tests
   • [lesson] webhook 401 → signing secret rotated; update env + redeploy

> "have I solved a flaky websocket reconnect anywhere before?"

🌳 recall → found in project `realtime-dash`:
   refresh the token *before* opening the socket, then retry with capped backoff.
```

Fini le « laissez-moi vous rappeler ce qu'on a fait hier ». C'est simplement là.

## 🚀 Installation

Deux commandes, directement dans **Claude Code** (le plugin se lance via [`uv`](https://docs.astral.sh/uv/)) :

```text
/plugin marketplace add VonderVuflya/Yggdrasil
/plugin install yggdrasil
```

Le moteur démarre paresseusement à la première utilisation et génère son propre jeton local — pas de clé d'API, pas de cloud, rien à configurer. Codex et Cursor utilisent le même flux.

<details>
<summary>Tous les autres canaux — daemon CLI, Homebrew, npm, Claude Desktop, depuis les sources…</summary>

| Hôte / outil | Commande |
| --- | --- |
| **uvx** _(CLI recommandée)_ | `uvx --from yggdrasil-memory ygg install` |
| **npm / npx** | `npx yggdrasil-memory install` |
| **pipx** | `pipx install yggdrasil-memory && ygg install` |
| **pip** | `pip install yggdrasil-memory && ygg install` |
| **Homebrew** _(macOS)_ | `brew install VonderVuflya/tap/yggdrasil && ygg install` |
| **Claude Desktop** _(application)_ | glissez le `.mcpb` depuis la [dernière release](https://github.com/VonderVuflya/Yggdrasil/releases/latest) dans Settings → Extensions, collez votre jeton (`ygg token`) — l'application de bureau partage alors la même mémoire que vos agents CLI ([guide](../packaging/mcpb/README.md)) |
| **depuis les sources** | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` |

`ygg install` est une configuration guidée à effectuer une seule fois : elle installe un service d'arrière-plan toujours actif, enregistre les outils MCP auprès de Claude Code et Codex, et — si votre matériel le permet — recommande des modèles locaux optionnels (ou choisissez `none` pour rester sans configuration).

Il existe aussi une [skill `yggdrasil-memory`](../skills/) pour n'importe quelle surface Claude : MCP connecte les *outils*, la skill apprend à l'agent *quand* les utiliser. Utilisez les deux pour un comportement optimal.

Essayez-le sans rien installer, avec une base jetable : `uvx --from yggdrasil-memory ygg serve --reset --db /tmp/ygg.sqlite`.

</details>

Ensuite, travaillez, tout simplement : demandez à votre agent *« rappelle ce qu'on a décidé sur ce projet »*, dites-lui *« mémorise cette décision »* — à la session suivante, c'est déjà là. Vérifiez l'installation à tout moment avec `ygg doctor`.

**Vous avez déjà un historique ?** Amorcez la mémoire à partir de vos transcriptions Claude Code + Codex existantes, de vos coffres Obsidian et de vos dépôts `CLAUDE.md` — le tout distillé localement :

```bash
ygg seed --dry-run    # see what it would import; drop the flag to distill for real
```

**Vous quittez un autre outil de mémoire ?** `ygg import --from mcp-memory --path memory.json` importe tout son stock dans Yggdrasil (dédupliqué, protégé contre les secrets) — vous pouvez ensuite le supprimer.

## Pourquoi

- 🧠 **Persistant** — décisions, leçons et statut de projet survivent d'une session à l'autre.
- 🔌 **Un seul cerveau, tous les outils** — Claude Code, Codex et n'importe quel hôte MCP partagent la même mémoire.
- 🌐 **Rappel inter-projets** — *« ça ressemble à ce que vous avez fait dans le projet B — le réutiliser ? »*
- 🧹 **Soignée, pas capturée** — votre agent n'enregistre que les quelques choses qui comptent ; la gouvernance déduplique et archive, sans jamais supprimer.
- 🌱 **Auto-entretenue** *(opt-in)* — un petit modèle local consolide la mémoire en arrière-plan. Zéro jeton d'API.
- 🪪 **Une seule identité partout** — un nom et une personnalité optionnels que chaque agent reprend, pour que Claude Code et Codex donnent l'impression d'être le même assistant.
- 🔒 **100 % local** — votre mémoire vit sur votre machine. Pas de cloud, pas de compte, pas de télémétrie.

## 🧠 Comment ça marche

Yggdrasil, c'est **mémoire + outils** — l'*intelligence*, c'est votre LLM. Il veille simplement à ce que la bonne mémoire soit devant le bon agent au bon moment.

- 🛎️ **Daemon toujours actif** — un petit service local (~21 Mo de RAM) que vos agents atteignent via les outils MCP (`ygg_search`, `ygg_recall`, `ygg_remember` …).
- 🪝 **Hooks** — le démarrage de session injecte automatiquement l'identité, l'état du projet et les suivis en cours (~300 jetons) ; un hook optionnel par prompt rappelle automatiquement la mémoire pertinente pour *chaque requête*.
- 📌 **Classement** — les mémoires épinglées et fréquemment rappelées remontent en premier.
- 🧹 **Gouvernance** — doublons et conflits sont mis en file pour relecture ; les modifications sont non destructives (archivage, jamais de suppression).
- 📓 **Obsidian** — chaque mémoire est aussi une note Markdown brute que vous pouvez lire, éditer et grep.

## 🎛️ Niveaux de mémoire — sans configuration par défaut

Dès le départ, Yggdrasil fonctionne sur **SQLite + FTS5 sans aucune dépendance** — recherche instantanée par mots-clés, aucun modèle, rien à télécharger. Des modèles **locaux** optionnels via [Ollama](https://ollama.com) ajoutent deux niveaux indépendants :

| Niveau | Ce que vous ajoutez | Ce que vous gagnez |
| --- | --- | --- |
| **0 · par défaut** | rien — SQLite + FTS5 | recherche par mots-clés, zéro dépendance, instantanée — recall@1 = **0.77** |
| **1 · sémantique** | un modèle d'**embedding** (`all-minilm` 45 MB · `paraphrase-multilingual` ~560 MB) | recherche par **sens**, entre les langues — recall@1 = **0.93**, recall@3 **1.00** |
| **2 · auto-entretenu** | un petit **LLM** (`qwen2.5:1.5b` ~1 GB) | dédup/fusion de la mémoire en arrière-plan (proposition seule) |

Ollama se contente de *calculer* les vecteurs et d'exécuter le modèle d'arrière-plan — chaque mémoire et chaque vecteur reste dans la même base SQLite locale. `ygg install` détecte votre matériel et recommande un modèle adapté (`ygg recommend` affiche le catalogue complet).

<details>
<summary>Menu complet des modèles</summary>

**Embeddings (recherche sémantique) :**

| Modèle | Taille | Idéal pour |
| --- | --- | --- |
| `all-minilm` | 45 MB | anglais, minuscule et rapide |
| `nomic-embed-text` | 274 MB | anglais, meilleure qualité |
| `paraphrase-multilingual` | ~560 MB | multilingue (EN/RU + 50 langues) |
| `bge-m3` | 1.2 GB | multilingue, qualité maximale (plus lourd) |

**Consolidation en arrière-plan (petit LLM) :**

| Modèle | Taille | Idéal pour |
| --- | --- | --- |
| `qwen2.5:0.5b` | ~400 MB | minuscule, rapide sur CPU |
| `qwen2.5:1.5b` | ~1 GB | meilleur choix par défaut sur CPU |
| `llama3.2:3b` | ~2 GB | meilleure qualité, plus lent sur CPU |

Le moteur lui-même est interchangeable — n'importe quel service respectant le contrat `MemoryBackend` se branche directement (`YGG_ENGINE_URL`) ; voir [docs/backend-boundary.md](../docs/backend-boundary.md).

</details>

## 📊 Les chiffres

Mesuré par [`eval/ygg_eval.py`](../eval/ygg_eval.py) — 35 requêtes étiquetées, poids de classement ajustés uniquement sur le split *dev*, donc **le holdout est le chiffre non biaisé** (recall@1, avec le modèle `paraphrase-multilingual`) :

| Mode de recherche | holdout recall@1 | recall@3 | lexical zéro dépendance |
| --- | --- | --- | --- |
| **Au sein d'un projet** (le vrai chemin, pool ~6) | **0.93** | **1.00** | 0.77 |
| **Base entière** (sans filtre, pool 35) | 0.80 | **1.00** | 0.77 |

**recall@3 = 1.00 dans les deux modes** — avec le modèle local, la bonne mémoire est *toujours* dans le top 3, même en cherchant dans toute la base ; elle est en position #1 dans 0.93 des cas au sein d'un projet. Le mode lexical zéro dépendance résout déjà les requêtes par mots-clés et par identifiants de code (1.00). Petit corpus (n=35), donc le [détail complet dans BENCHMARKS.md](../BENCHMARKS.md) présente les IC à 95 %, les tailles de pool et les scores par classe — et vous pouvez tout relancer en une minute : `python3 eval/ygg_eval.py --report`.

## 🆚 Yggdrasil face aux autres

Tous les autres capturent automatiquement les transcriptions ou vous vendent un cloud. Le pari d'Yggdrasil : garder les **quelques choses qui comptent**, soignées et dédupliquées, dans des enregistrements simples qui vous appartiennent — et les partager entre **tous** les outils et projets.

| | **Yggdrasil** | Mémoire intégrée <sub>(Claude Code · Codex)</sub> | [claude-mem](https://github.com/thedotmack/claude-mem) | [mem0](https://github.com/mem0ai/mem0) / OpenMemory | [basic-memory](https://github.com/basicmachines-co/basic-memory) |
| --- | --- | --- | --- | --- | --- |
| Décisions / leçons / statut soignés (pas des transcriptions) | ✅ | ⚠️ notes auto | ❌ capture tout | ⚠️ | ⚠️ notes libres |
| Une seule mémoire **entre les outils** | ✅ | ❌ cloisonnée par éditeur | ✅ | ✅ | ✅ |
| Rappel **inter-projets** (« résolu ça dans le projet B ») | ✅ | ❌ limité au dépôt | ⚠️ | ⚠️ | ⚠️ |
| **100 % local** par défaut | ✅ | ✅ | ⚠️ sync cloud en option | ❌ hébergé d'abord | ✅ |
| **Zéro dépendance** (stdlib + SQLite) | ✅ | — | ❌ Node + Bun + daemon worker | ❌ Docker + Qdrant + clé LLM | ❌ |
| Fonctionne **sans LLM ni clé d'API** | ✅ | ✅ | ❌ compresse par IA | ❌ | ✅ |
| **Recherche sémantique, 100 % locale** | ✅ Ollama opt-in | ❌ grep uniquement | ⚠️ Chroma en option | ⚠️ exige une clé d'API ou un stack Docker | ❌ |
| **Markdown brut qui vous appartient** (prêt pour Obsidian) | ✅ | ✅ | ❌ | ❌ | ✅ |

**Le voisin le plus proche — claude-mem :** une mémoire qui capture tout, enregistre chaque session et la compresse par IA (Node 20+ *et* Bun, un daemon worker persistant ; Chroma en option). Yggdrasil fait le pari inverse : un petit stock à fort signal plutôt qu'un déluge qui grossit. **mem0** est un SDK plus une plateforme hébergée pour construire des *applis* qui se souviennent de *leurs utilisateurs* — même auto-hébergé, il lui faut une clé d'API LLM. **Les mémoires intégrées** sont réellement utiles — et structurellement cloisonnées : un éditeur, un dépôt, une machine, du grep littéral. Yggdrasil est la couche au-dessus (et `ygg seed` peut s'amorcer à partir de ces mêmes transcriptions). Couche entièrement différente : [context-mode](https://github.com/mksglu/context-mode) (fenêtre de contexte vive) et [Context7](https://github.com/upstash/context7) (doc fraîche des bibliothèques) — les deux se marient très bien avec Yggdrasil.

## 🧰 Commandes

Les agents voient six outils MCP : `ygg_health`, `ygg_bootstrap`, `ygg_search`, `ygg_recall`, `ygg_remember`, `ygg_materialize` — enregistrés automatiquement par le plugin ou `ygg install`.

<details>
<summary>Référence complète de la CLI <code>ygg</code></summary>

**Opérations de mémoire**

| Commande | Ce qu'elle fait |
| --- | --- |
| `ygg recall --query "…"` | Recherche **inter-projets** — « ai-je déjà fait ça quelque part ? » |
| `ygg search --project P --query "…"` | Recherche limitée au projet (`--type`, `--tag`, `--limit`, `--json`) |
| `ygg remember --project P --type lesson --content "…"` | Enregistrer une mémoire durable (protégée contre les secrets, dédupliquée) |
| `ygg bootstrap --project P` | Charger la mémoire d'un projet avant de commencer le travail |
| `ygg pin --id ID` · `ygg unpin --id ID` | Épingler une mémoire pour qu'elle remonte de façon fiable |
| `ygg supersede --id ID` | Archiver une mémoire obsolète qu'une plus récente remplace |
| `ygg materialize --id ID --project P` | Exporter une mémoire vers une note Obsidian |
| `ygg export-native --project P` | Écrire une synthèse triée dans `AGENTS.md`/`MEMORY.md` — alimenter la mémoire native de Claude Code et Codex |
| `ygg import --from TOOL --path P` | Migrer le stock d'un autre outil de mémoire vers Yggdrasil (`mcp-memory`, `basic-memory` ; `--dry-run` d'abord) |
| `ygg review [--apply]` | Traiter la file de gouvernance — consolider les doublons, signaler les mémoires obsolètes/en conflit (archivage uniquement, réversible) |
| `ygg delete --id ID` · `ygg reset …` | Supprimer définitivement une mémoire · annuler en masse un `ygg seed` raté (demande confirmation d'abord) |

**Démarrage à froid**

| Commande | Ce qu'elle fait |
| --- | --- |
| `ygg seed` | Distille les transcriptions Claude Code + Codex, les coffres Obsidian, les dépôts `CLAUDE.md` — incrémental, dédupliqué, entièrement local |
| `ygg seed --dry-run` · `--force` | Découverte + estimation uniquement · tout redistiller |
| `ygg distill --source PATH` | Distiller un dossier/fichier en leçons |
| `ygg reindex` | Compléter les embeddings manquants (restaure le rappel dense) |

**Service et configuration**

| Commande | Ce qu'elle fait |
| --- | --- |
| `ygg install` · `ygg doctor` · `ygg update` | Configuration guidée · diagnostic avec corrections concrètes · mise à jour |
| `ygg config` | Afficher/définir les réglages persistants (`list` · `get` · `set` · `unset`) |
| `ygg status` · `start` · `stop` · `restart` · `logs` | Gérer le daemon toujours actif |
| `ygg hooks` · `unhooks` · `register` | Hook SessionStart on/off · (ré)enregistrer MCP |
| `ygg recommend` · `token` · `uninstall` | Catalogue de modèles · afficher le jeton d'authentification · tout supprimer |

Donnez-lui une personnalité — éditez `~/.yggdrasil/identity.json` :

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

Amorçage lourd, portable modeste ? Pointez la distillation vers *n'importe quelle* machine de votre réseau local — un poste avec Ollama, LM Studio, llama.cpp, **même un iPhone qui fait tourner une appli de serveur LLM local** : `ygg config set distill_url http://<box>:11434`. Yggdrasil détecte automatiquement le dialecte d'API (Ollama ou compatible OpenAI) ; vos données ne quittent toujours jamais votre réseau — détails dans [docs/ygg-cli.md](../docs/ygg-cli.md).

</details>

## ❓ FAQ

<details>
<summary><b>Claude Code a déjà une mémoire intégrée — pourquoi Yggdrasil ?</b></summary>

Les mémoires intégrées sont propres à un éditeur, à un dépôt, à une machine, et récupérées par correspondance textuelle littérale. Yggdrasil est la couche au-dessus : la *même* mémoire dans Claude Code, Codex et n'importe quel hôte MCP, un rappel *entre* les projets, une recherche sémantique optionnelle — toujours 100 % local. Les deux se complètent : gardez la mémoire native, et laissez `ygg seed` distiller votre historique existant dans le cerveau partagé.
</details>

<details>
<summary><b>Envoie-t-il mon code ou ma mémoire dans le cloud ?</b></summary>

Non. Le moteur, la base de données et les modèles optionnels tournent tous localement. Pas de compte, pas de télémétrie. Le seul appel sortant est une vérification de version auprès de PyPI.
</details>

<details>
<summary><b>Mémorise-t-il automatiquement tout ?</b></summary>

Non — c'est voulu. La récupération est automatique ; l'*écriture* est délibérée (l'agent appelle `ygg_remember` pour les leçons durables). Tout capturer pollue la mémoire et brûle des jetons, donc on ne le fait pas. Le modèle d'arrière-plan optionnel consolide ce qui est déjà enregistré (proposition seule).
</details>

<details>
<summary><b>Ai-je besoin d'un GPU ou d'une clé d'API ?</b></summary>

Non. Par défaut, c'est de la recherche purement lexicale — zéro dépendance, instantanée. La recherche sémantique est opt-in et utilise un modèle *local* via Ollama. L'installateur en recommande un adapté à votre matériel.
</details>

<details>
<summary><b>Quelle est sa lourdeur, et combien de jetons coûte-t-il ?</b></summary>

Le moteur tourne au repos à **~21 Mo de RAM** (mode lexical par défaut) avec ~0 % de CPU ; le disque représente des dizaines de Ko par mémoire. Le démarrage de session injecte ~300 jetons ; chaque appel d'outil renvoie un petit extrait. Tout le gros travail (indexation, embeddings, consolidation) tourne hors LLM, sur votre machine.
</details>

<details>
<summary><b>Puis-je éditer ou supprimer des mémoires à la main ?</b></summary>

Oui. Les mémoires se matérialisent en notes Markdown dans un coffre Obsidian — lisez-les, éditez-les ou supprimez-les comme n'importe quel fichier. Le moteur ne supprime jamais définitivement ; il archive (réversible).
</details>

## 🚦 Statut et feuille de route

**Alpha.** Le chemin nominal et la boucle de gouvernance sont couverts par des gates (`scripts/run_gates.sh`) ; pas encore durci pour le multi-utilisateur ni la production. macOS aujourd'hui ; les installateurs de service Linux/Windows sont prêts et en phase finale de tests sur appareil.

À venir : 🛰️ synchronisation inter-surfaces (une seule mémoire entre CLI, web et téléphone) · 🔗 graphe de relations (`SOLVES` / `SUPERSEDES` / `CONTRADICTS`) · 🐧 disponibilité générale Linux/Windows.

## 🤝 Contribuer

Issues et PR bienvenues. Lancez `scripts/run_gates.sh` et `python3 -m unittest discover -s tests` avant de soumettre — tous les gates doivent rester verts.

## 📜 Licence

**GNU AGPL v3.0** — voir [LICENSE](../LICENSE). Libre et open source : utilisez, modifiez, auto-hébergez, redistribuez. Si vous le modifiez ou le proposez en tant que service réseau, vous devez publier votre code source sous la même licence.
