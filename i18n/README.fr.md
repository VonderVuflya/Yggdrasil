<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>Une mémoire unique, partagée et durable pour tous vos agents de code IA.</b><br/>
Claude Code, Codex et n'importe quel hôte MCP se souviennent de vos projets — décisions, leçons, statut — d'une session, d'un outil et d'un projet à l'autre.</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-Elastic%202.0-blue.svg" alt="Elastic License 2.0">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/deps-zero%20(stdlib)-brightgreen" alt="zero deps">
  <img src="https://img.shields.io/badge/MCP-Claude%20·%20Codex%20·%20any%20host-purple" alt="MCP">
  <img src="https://img.shields.io/badge/local--first-100%25%20private-success" alt="local-first">
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="alpha">
</p>

<p align="center">
  <a href="#-démarrage-rapide">Démarrage rapide</a> ·
  <a href="#-comment-ça-marche">Comment ça marche</a> ·
  <a href="#%EF%B8%8F-commandes">Commandes</a> ·
  <a href="#-faq">FAQ</a> ·
  <a href="#-yggdrasil-face-aux-alternatives">Comparaison</a>
</p>

<p align="center">
  <a href="../README.md"><img src="https://img.shields.io/badge/README-English-blue" alt="English"></a>
  <a href="./README.ru.md"><img src="https://img.shields.io/badge/docs-Русский-darkblue" alt="Русский"></a>
  <a href="./README.zh.md"><img src="https://img.shields.io/badge/docs-简体中文-red" alt="简体中文"></a>
  <a href="./README.es.md"><img src="https://img.shields.io/badge/docs-Español-orange" alt="Español"></a>
  <a href="./README.fr.md"><img src="https://img.shields.io/badge/docs-Français-blue" alt="Français"></a>
</p>

---

À chaque nouvelle conversation, votre IA oublie tout. Vous ré-expliquez le projet, les décisions, les pièges — à chaque fois, dans chaque outil. **Yggdrasil est un petit cerveau-mémoire toujours actif auquel n'importe quel agent peut se brancher.** Ouvrez une nouvelle session dans n'importe quel projet, avec n'importe quelle IA, et elle sait déjà ce que vous avez décidé, ce qui a cassé et ce qui reste ouvert — et elle apprend discrètement de votre travail en arrière-plan.

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

Fini le « laisse-moi te rappeler ce qu'on a fait hier ». C'est tout simplement là.

## ❌ Sans Yggdrasil

- 🔁 Vous ré-expliquez le contexte du projet à l'IA à chaque nouvelle conversation.
- 🧩 Les leçons apprises dans un projet n'atteignent jamais le suivant.
- 🤖 Vous passez de Claude Code à Codex → le nouvel outil ne sait rien.
- 🗑️ Des enseignements de débogage durement acquis s'envolent à la fin de la session.

## ✅ Avec Yggdrasil

- 🧠 **Mémoire persistante** — décisions, leçons et statut survivent d'une session à l'autre.
- 🔌 **Tous les agents, un seul cerveau** — Claude Code, Codex et n'importe quel hôte MCP partagent la même mémoire.
- 🌐 **Rappel inter-projets** — *« ça ressemble à ce que tu as fait dans le projet B — on le réutilise ? »*
- 🌱 **Auto-apprentissage** — un modèle local consolide la mémoire en arrière-plan (zéro token d'API).
- 🪪 **Une âme** — donnez-lui un nom et une personnalité ; elle se présente de la même façon dans chaque outil.
- 🔒 **100 % local et privé** — votre mémoire reste sur votre machine. Pas de cloud, pas de compte.

## 🚀 Démarrage rapide

> **Prérequis :** macOS, Python 3.10+. Optionnel (pour la recherche sémantique) : [Ollama](https://ollama.com).

```bash
git clone https://github.com/VonderVuflya/yggdrasil.git
cd yggdrasil
scripts/install.sh install          # interactive wizard — detects your hardware,
                                    # recommends models, sets up the background service
```

C'est tout. L'installeur :
1. 🔍 détecte votre CPU/RAM/GPU et **recommande des modèles adaptés à votre machine**,
2. 🔑 génère un jeton d'authentification privé (jamais codé en dur),
3. 🛎️ installe un service d'arrière-plan toujours actif (démarre automatiquement à l'ouverture de session, redémarre en cas de plantage),
4. 🤝 enregistre les outils de mémoire auprès de **Claude Code et Codex**,
5. 🪝 (optionnel) active un hook de démarrage de session qui injecte automatiquement la mémoire de votre projet.

Vous préférez simplement essayer le moteur sans installer de service ?

```bash
python3 scripts/ygg_memory_server.py --reset --db /tmp/ygg.sqlite   # runs on :42069
scripts/run_gates.sh                                                # see all checks pass
```

## 🧠 Comment ça marche

Yggdrasil, c'est **de la mémoire + des outils** — l'*intelligence*, c'est votre LLM. Il se contente de mettre la bonne mémoire devant le bon agent au bon moment.

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

- **Moteur** — un serveur HTTP reposant uniquement sur la bibliothèque standard, au-dessus de SQLite + FTS5. Zéro dépendance, ~21 Mo de RAM.
- **Récupération** — lexicale par défaut ; ajoutez un modèle d'embedding local pour une recherche sémantique et translingue.
- **Gouvernance** — les mémoires en double / obsolètes / contradictoires sont remontées pour révision ; les modifications sont non destructives (archivage, jamais de suppression).
- **Obsidian** — chaque mémoire est aussi une note Markdown que vous pouvez lire et modifier.

## ⭐ Fonctionnalités

- 🧠 **Mémoire durable inter-sessions** pour tout agent compatible MCP.
- 🌐 **Rappel inter-projets** + un engagement proactif « tu as déjà résolu ça ».
- 🔎 **Récupération hybride** — BM25 + embeddings denses optionnels, fusionnés ; translingue (ex. EN↔RU).
- 🪪 **Identité / persona** injectée à chaque session (le « feeling Jarvis »).
- 📌 **Statut et suivis** remontés au démarrage de session — *« quel est le statut de X ? »* trouve sa réponse instantanément.
- 🌱 **Auto-apprentissage en arrière-plan** — un petit modèle local consolide la mémoire (en mode proposition sûre par défaut).
- 🧹 **Boucle de gouvernance** — file de révision + archivage/fusion non destructifs.
- 📓 **Matérialisation Obsidian** — lisible, modifiable, portable.
- 🔒 **Local d'abord et privé** — pas de cloud, pas de compte, vos données restent à leur place.
- 🪶 **Zéro dépendance contraignante** — pur Python standard ; modèles locaux optionnels via Ollama.

## 🛠️ Commandes

**CLI — `scripts/ygg.py`** (opérations de mémoire côté agent)

| Commande | Ce qu'elle fait |
| --- | --- |
| `health` | Vérifier que le moteur est en vie |
| `bootstrap --project P` | Récupérer la mémoire d'un projet avant de commencer le travail |
| `search --project P --query "…"` | Recherche limitée à un projet (`--type`, `--limit`, `--json`) |
| `recall --query "…"` | Recherche **inter-projets** — « ai-je déjà fait ça quelque part ? » |
| `remember --project P --type debugging_lesson --content "…"` | Enregistrer une mémoire durable (protégée des secrets, dédupliquée) |
| `materialize --id ID --project P` | Exporter une mémoire vers une note Obsidian |

**Service — `scripts/install.sh`** (cycle de vie et configuration)

| Commande | Ce qu'elle fait |
| --- | --- |
| `install` | Assistant guidé → service d'arrière-plan + enregistrement MCP |
| `recommend` | Afficher le catalogue de modèles adapté au matériel |
| `status` · `start` · `stop` · `restart` · `logs` | Gérer le démon toujours actif |
| `hooks` · `unhooks` | Activer/désactiver le hook d'auto-bootstrap au démarrage de session |
| `consolidate` · `unconsolidate` | Planifier/supprimer la consolidation de mémoire en arrière-plan |
| `token` · `uninstall` | Afficher le jeton d'authentification · retirer le service + l'enregistrement |

**Outils MCP** (ce que voient les agents) : `ygg_health`, `ygg_bootstrap`, `ygg_search`, `ygg_recall`, `ygg_remember`, `ygg_materialize`.

## 🔌 Utilisez-le avec votre agent

- **Claude Code** — après `install.sh install`, les outils sont enregistrés (`/mcp` affiche `yggdrasil`) et le hook SessionStart injecte automatiquement la mémoire. Ouvrez simplement un projet et travaillez.
- **Codex** — enregistré lui aussi ; approuvez l'appel d'outil `ygg_*` une fois par session.
- **N'importe quel hôte MCP** — pointez-le vers `scripts/ygg_mcp_server.py` (stdio) avec `YGG_MUNINN_URL` + `YGG_MUNINN_TOKEN`.

Donnez-lui une personnalité — modifiez `~/.yggdrasil/identity.json` :

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

## 📊 Empreinte et qualité

**Empreinte** (mesurée, 13 mémoires) : **~21 Mo de RAM**, **~0 % de CPU au repos**, **zéro dépendance** (bibliothèque standard Python 3.10+). Disque ≈ quelques dizaines de Ko par mémoire. La recherche dense est optionnelle et ajoute un modèle local Ollama (ex. `all-minilm`, 45 Mo).

**Qualité de la récupération** (`eval/ygg_eval.py`, recall@1) :

| Mode | recall@1 | paraphrase | translingue (EN→RU) |
| --- | --- | --- | --- |
| lexical (par défaut) | 0.63 | 0.00 | 0.00 |
| dense · `all-minilm` (45 Mo, EN) | 0.75 | 0.67 | 0.00 |
| dense · `paraphrase-multilingual` (~560 Mo) | **0.94** | 0.67 | **1.00** |

Les requêtes `keyword` et `identifier` atteignent 1.0 dans tous les modes. Essayez par vous-même : `python3 eval/ygg_eval.py`.

## ❓ FAQ

<details>
<summary><b>Envoie-t-il mon code ou ma mémoire dans le cloud ?</b></summary>

Non. Le moteur, la base de données et les modèles optionnels s'exécutent tous localement. Pas de compte, pas de télémétrie. Votre mémoire ne quitte jamais votre machine.
</details>

<details>
<summary><b>En quoi est-ce différent de Context7 / d'un RAG sur de la documentation ?</b></summary>

Context7 récupère la <i>documentation publique à jour de bibliothèques</i> (la dernière API React/Next.js). Yggdrasil se souvient de <i>votre propre travail</i> — vos décisions, vos leçons et le statut de vos projets. Les deux sont complémentaires ; utilisez-les ensemble. Voir la <a href="#-yggdrasil-face-aux-alternatives">comparaison</a>.
</details>

<details>
<summary><b>Mémorise-t-il automatiquement tout ?</b></summary>

Non — c'est volontaire. La récupération est automatique ; l'<i>écriture</i> est délibérée (l'agent appelle <code>ygg_remember</code> pour les leçons durables). Capturer tout automatiquement pollue la mémoire, alors nous ne le faisons pas. Un modèle d'arrière-plan consolide ce qui est déjà enregistré (en mode proposition seulement par défaut).
</details>

<details>
<summary><b>Ai-je besoin d'un GPU ou d'une clé d'API ?</b></summary>

Non. Par défaut, c'est de la pure recherche lexicale — zéro dépendance, instantanée. La recherche sémantique est optionnelle et utilise un modèle <i>local</i> via Ollama (pas de clé d'API). L'installeur recommande un modèle adapté à votre matériel.
</details>

<details>
<summary><b>Combien de tokens cela coûte-t-il à mon agent ?</b></summary>

Très peu. Le démarrage de session injecte ~300 tokens de mémoire ; chaque appel d'outil renvoie un petit extrait. Tout le gros du travail (indexation, embeddings, consolidation) s'exécute en dehors du LLM, sur votre machine.
</details>

<details>
<summary><b>Puis-je modifier ou supprimer des mémoires à la main ?</b></summary>

Oui. Les mémoires se matérialisent en notes Markdown dans un coffre Obsidian — vous pouvez les lire, les modifier ou les supprimer comme n'importe quel fichier. Le moteur ne supprime jamais définitivement ; il archive (réversible).
</details>

<details>
<summary><b>Est-ce prêt pour la production ?</b></summary>

C'est une <b>alpha</b> assumée : le parcours nominal et toute la boucle de gouvernance sont couverts par des gates qui passent (<code>scripts/run_gates.sh</code>). Pas encore durci pour le multi-utilisateur / la production.
</details>

## 🆚 Yggdrasil face aux alternatives

| | **Yggdrasil** | Context7 | Mémoire LLM standard |
| --- | --- | --- | --- |
| Connaît **vos** décisions/leçons | ✅ | ❌ | ⚠️ au sein d'une seule session |
| Documentation publique de bibliothèques à jour | ❌ (utilisez Context7) | ✅ | ❌ |
| Inter-sessions et inter-**agents** | ✅ | ✅ | ❌ |
| Rappel inter-**projets** | ✅ | — | ❌ |
| Écrit/accumule votre mémoire | ✅ | ❌ (lecture seule) | ⚠️ |
| Local et privé | ✅ | ☁️ hébergé | dépend |
| Auto-consolidant | ✅ | ❌ | ❌ |

**En bref :** Context7 = l'API correcte de la bibliothèque *de quelqu'un d'autre*. Yggdrasil = la mémoire de *votre propre* travail. Utilisez les deux.

## 🗺️ Feuille de route

- 🔗 Graphe de relations (`SOLVES` / `SUPERSEDES` / `CONTRADICTS`) pour un raisonnement plus riche.
- 🛰️ Synchronisation multi-appareils — reprendre littéralement depuis n'importe quelle machine.
- 🧪 Modèles optionnels plus puissants pour une consolidation autonome sûre.
- 🐧 Installeurs de service Linux/Windows (actuellement macOS launchd).

## 🤝 Contribuer

Issues et PR bienvenues. Lancez `scripts/run_gates.sh` et `python3 -m unittest discover -s tests` avant de soumettre — toutes les gates doivent rester au vert.

## 📜 Licence

**Elastic License 2.0** — voir [LICENSE](./LICENSE). Vous pouvez utiliser, modifier, auto-héberger et redistribuer Yggdrasil librement. Vous ne pouvez **pas** le vendre comme produit ni le proposer à des tiers comme service hébergé/géré. Il est source-available, pas open source au sens de l'OSI.

> Un backend **Muninn** externe (`github.com/wjohns989/Muninn`, Apache-2.0) est optionnel et **non inclus** ; pointez `YGG_MUNINN_URL` vers votre propre instance. Préservez son `NOTICE`/son attribution si vous le redistribuez.
