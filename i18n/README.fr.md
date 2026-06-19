<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>Une mémoire unique, partagée et durable pour tous vos agents de codage IA.</b><br/>
Claude Code, Codex et n'importe quel hôte MCP se souviennent de vos décisions, de vos leçons et de l'état de vos projets — d'une session, d'un outil et d'un projet à l'autre.</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-Elastic%202.0-blue.svg" alt="Elastic License 2.0">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/deps-zero%20(stdlib)-brightgreen" alt="zero deps">
  <img src="https://img.shields.io/badge/MCP-Claude%20·%20Codex%20·%20any%20host-purple" alt="MCP">
  <img src="https://img.shields.io/badge/local--first-100%25%20private-success" alt="local-first">
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="alpha">
</p>

<p align="center">
  <a href="../README.md"><img src="https://img.shields.io/badge/README-English-blue" alt="English"></a>
  <a href="./README.ru.md"><img src="https://img.shields.io/badge/docs-Русский-darkblue" alt="Русский"></a>
  <a href="./README.zh.md"><img src="https://img.shields.io/badge/docs-简体中文-red" alt="简体中文"></a>
  <a href="./README.es.md"><img src="https://img.shields.io/badge/docs-Español-orange" alt="Español"></a>
  <a href="./README.fr.md"><img src="https://img.shields.io/badge/docs-Français-blue" alt="Français"></a>
</p>

---

À chaque nouvelle conversation, votre IA oublie tout. Vous réexpliquez le projet, les décisions, les pièges — à chaque fois, dans chaque outil. **Yggdrasil est un petit cerveau-mémoire toujours actif auquel n'importe quel agent se branche.** Ouvrez une nouvelle session, dans n'importe quel projet, avec n'importe quelle IA, et elle sait déjà ce que vous avez décidé, ce qui a cassé et ce qui reste ouvert — et elle continue d'apprendre en arrière-plan.

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

Fini le « laissez-moi vous rappeler ce qu'on a fait hier ». C'est simplement là.

## Pourquoi

**Sans Yggdrasil**, vous réexpliquez le contexte à chaque nouvelle conversation, les leçons d'un projet n'atteignent jamais le suivant, passer de Claude Code à Codex repart de zéro, et les précieuses découvertes de débogage meurent avec la session.

**Avec Yggdrasil :**

- 🧠 **Mémoire persistante** — décisions, leçons et statuts survivent d'une session à l'autre.
- 🔌 **N'importe quel agent, un seul cerveau** — Claude Code, Codex et tout hôte MCP partagent la même mémoire.
- 🌐 **Rappel inter-projets** — *« ça ressemble à ce que vous avez fait dans le projet B — le réutiliser ? »*
- 🌱 **Auto-apprentissage** — un modèle local consolide la mémoire en arrière-plan (zéro jeton d'API).
- 🪪 **Une âme** — donnez-lui un nom et une personnalité ; il apparaît à l'identique dans chaque outil.
- 🔒 **100 % local et privé** — votre mémoire vit sur votre machine. Pas de cloud, pas de compte.

## 🚀 Installation

> **Prérequis :** macOS (Linux/Windows bientôt), Python 3.10+ — ou laissez `uv`/`npx` récupérer Python pour vous. La recherche sémantique est optionnelle et utilise un modèle [Ollama](https://ollama.com) local.

```bash
uvx --from yggdrasil-memory ygg install      # recommended
```

<details>
<summary>Vous préférez npm, pipx, pip, Homebrew ou les sources ? (même moteur)</summary>

| Outil | Commande |
| --- | --- |
| **npm / npx** | `npx yggdrasil-memory install` |
| **pipx** | `pipx install yggdrasil-memory && ygg install` |
| **pip** | `pip install yggdrasil-memory && ygg install` |
| **Homebrew** _(macOS)_ | `brew install VonderVuflya/tap/yggdrasil && ygg install` |
| **depuis les sources** | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` |

</details>

`ygg install` est une configuration guidée à effectuer une seule fois : il détecte votre matériel et **recommande un modèle local adapté** (ou choisissez `none` pour une configuration purement lexicale, sans réglage), génère un jeton d'authentification privé, installe un **service d'arrière-plan toujours actif** et **enregistre les outils auprès de Claude Code et Codex**. Vérifiez-le à tout moment avec `ygg doctor` ; mettez à jour avec `ygg update`.

Vous voulez juste essayer sans installer de service ? `uvx --from yggdrasil-memory ygg serve --reset --db /tmp/ygg.sqlite`.

## 🧠 Comment ça marche

Yggdrasil, c'est **mémoire + outils** — l'*intelligence*, c'est votre LLM. Il veille simplement à ce que la bonne mémoire soit devant le bon agent au bon moment.

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

- **Moteur** — un serveur HTTP reposant uniquement sur la stdlib, au-dessus de SQLite + FTS5. Zéro dépendance, ~21 Mo de RAM.
- **Récupération** — lexicale par défaut ; ajoutez un modèle d'embedding local pour une recherche sémantique et translingue. Les mémoires fréquemment rappelées et épinglées sont mieux classées.
- **Gouvernance** — doublons / conflits sont signalés pour relecture ; les modifications sont non destructives (archivage, jamais de suppression).
- **Obsidian** — chaque mémoire est aussi une note Markdown que vous pouvez lire et éditer.

## 🆚 Yggdrasil face aux autres

Chacun de ces outils occupe une **couche différente** de la pile de contexte IA. La couche que personne n'avait comblée — **une mémoire durable, inter-sessions et inter-agents de _votre propre_ travail** — est exactement là où se place Yggdrasil. Il ne les concurrence pas ; c'est la mémoire à laquelle ils se branchent tous.

| Outil | Ce dont il a la charge | Utilisez-le *avec* Yggdrasil parce que… |
| --- | --- | --- |
| **[context-mode](https://github.com/mksglu/context-mode)** | garde la **fenêtre de contexte vive** légère — met en bac à sable la sortie des outils, « think in code », continuité en session. Éphémère par conception (« nouvelle session = ardoise vierge »). | context-mode élague la session *du jour* ; Yggdrasil est la mémoire durable qu'il jette délibérément. Des horizons temporels différents — faites tourner les deux. |
| **[Context7](https://github.com/upstash/context7)** | la **doc publique à jour des bibliothèques** (la dernière API React/Stripe), en lecture seule. | Context7 connaît l'API *de la bibliothèque* ; Yggdrasil connaît *vos* décisions et vos pièges. |
| **[autoresearch](https://github.com/karpathy/autoresearch)** | une **boucle d'expérimentation** autonome (éditer → exécuter → mesurer → garder/revenir en arrière). | la boucle se réveille à froid à chaque fois ; Yggdrasil lui donne une mémoire à long terme de ce qu'elle a déjà essayé → [intégration](../integrations/autoresearch/). |
| **« mémoire » d'un simple LLM** | un brouillon par session, un seul outil à la fois. | Yggdrasil est durable, inter-projets, inter-agents, gouverné et local. |

**En bref :** les autres outils récupèrent de la doc, lancent des expériences ou compriment une session. **Yggdrasil est la mémoire durable de _votre propre_ travail qui leur manquait à tous — utilisez-le à leurs côtés : vous ne pouvez qu'y gagner.**

## 🧰 Commandes

Les agents voient six outils MCP : `ygg_health`, `ygg_bootstrap`, `ygg_search`, `ygg_recall`, `ygg_remember`, `ygg_materialize`. Après `ygg install`, ils sont automatiquement enregistrés auprès de Claude Code et Codex — il suffit d'ouvrir un projet et de travailler.

<details>
<summary>Référence complète de la CLI <code>ygg</code></summary>

**Opérations de mémoire**

| Commande | Ce qu'elle fait |
| --- | --- |
| `ygg recall --query "…"` | Recherche **inter-projets** — « ai-je déjà fait ça quelque part ? » |
| `ygg search --project P --query "…"` | Recherche limitée au projet (`--type`, `--tag`, `--limit`, `--json`) |
| `ygg remember --project P --type debugging_lesson --content "…"` | Enregistrer une mémoire durable (protégée contre les secrets, dédupliquée ; `--tag` pour étiqueter) |
| `ygg bootstrap --project P` | Charger la mémoire d'un projet avant de commencer le travail |
| `ygg pin --id ID` · `ygg unpin --id ID` | Épingler une mémoire pour qu'elle remonte de façon fiable |
| `ygg supersede --id ID` | Archiver une mémoire obsolète qu'une plus récente remplace |
| `ygg materialize --id ID --project P` | Exporter une mémoire vers une note Obsidian |

**Service et configuration**

| Commande | Ce qu'elle fait |
| --- | --- |
| `ygg install` · `ygg setup` | Configuration guidée → service d'arrière-plan + enregistrement MCP |
| `ygg doctor` · `ygg update` | Diagnostiquer l'installation · redéployer le dernier code |
| `ygg status` · `start` · `stop` · `restart` · `logs` | Gérer le démon toujours actif |
| `ygg hooks` · `unhooks` | Activer/désactiver le hook d'auto-bootstrap SessionStart |
| `ygg recommend` | Afficher le catalogue de modèles adapté au matériel |
| `ygg token` · `uninstall` | Afficher le jeton d'authentification · supprimer service + enregistrement |

Donnez-lui une personnalité — éditez `~/.yggdrasil/identity.json` :

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

</details>

## ❓ FAQ

<details>
<summary><b>Envoie-t-il mon code ou ma mémoire dans le cloud ?</b></summary>

Non. Le moteur, la base de données et les modèles optionnels tournent tous localement. Pas de compte, pas de télémétrie. Votre mémoire ne quitte jamais votre machine.
</details>

<details>
<summary><b>Mémorise-t-il automatiquement tout ?</b></summary>

Non — c'est voulu. La récupération est automatique ; l'*écriture* est délibérée (l'agent appelle `ygg_remember` pour les leçons durables). Tout capturer automatiquement pollue la mémoire, donc on ne le fait pas. Un modèle d'arrière-plan consolide ce qui est déjà enregistré (en mode proposition seule par défaut).
</details>

<details>
<summary><b>Ai-je besoin d'un GPU ou d'une clé d'API ?</b></summary>

Non. Par défaut, c'est de la recherche purement lexicale — zéro dépendance, instantanée. La recherche sémantique est optionnelle et utilise un modèle *local* via Ollama (pas de clé d'API). L'installateur recommande un modèle adapté à votre matériel.
</details>

<details>
<summary><b>Quelle est sa lourdeur, et combien de jetons coûte-t-il ?</b></summary>

Minuscule. Le moteur fait **~21 Mo de RAM, ~0 % de CPU au repos, zéro dépendance** (stdlib Python) ; le disque représente des dizaines de Ko par mémoire. Le démarrage de session injecte ~300 jetons de mémoire et chaque appel d'outil renvoie un petit extrait — tout le gros travail (indexation, embeddings, consolidation) tourne hors LLM sur votre machine.
</details>

<details>
<summary><b>Quelle est la qualité de la récupération ?</b></summary>

Mesurée par `eval/ygg_eval.py` (35 cas étiquetés, partage dev/holdout), recall@1 :

| Mode | recall@1 | paraphrase | translingue (EN→RU) |
| --- | --- | --- | --- |
| lexical (par défaut) | 0.77 | 0.63 | 0.00 |
| dense · `all-minilm` (45 Mo, EN) | 0.83 | 0.88 | 0.00 |
| dense · `paraphrase-multilingual` (~560 Mo) | **0.94** | 0.88 | **0.80** |

Les requêtes `keyword` et `identifier` sont à 1.0 dans tous les modes ; avec le modèle multilingue **recall@3 = 1.0** (toutes les cibles dans le top 3).
</details>

<details>
<summary><b>Puis-je éditer ou supprimer des mémoires à la main ?</b></summary>

Oui. Les mémoires se matérialisent en notes Markdown dans un coffre Obsidian — lisez-les, éditez-les ou supprimez-les comme n'importe quel fichier. Le moteur ne supprime jamais définitivement ; il archive (réversible).
</details>

<details>
<summary><b>Est-il prêt pour la production ?</b></summary>

C'est une **alpha** honnête : le chemin nominal et la boucle de gouvernance complète sont couverts par des gates qui passent (`scripts/run_gates.sh`). Pas encore durci pour le multi-utilisateur / la production.
</details>

## 🗺️ Feuille de route

- 🛰️ **Synchronisation inter-surfaces** — connectez-vous depuis ChatGPT / Claude sur le web et le mobile ; une seule mémoire entre la CLI, le navigateur et le téléphone.
- 🔗 Graphe de relations (`SOLVES` / `SUPERSEDES` / `CONTRADICTS`) pour un raisonnement plus riche.
- 🐧 Installateurs de service Linux/Windows (implémentés ; tests finaux sur appareil).

## 🤝 Contribuer

Issues et PR bienvenues. Lancez `scripts/run_gates.sh` et `python3 -m unittest discover -s tests` avant de soumettre — tous les gates doivent rester verts.

## 📜 Licence

**Elastic License 2.0** — voir [LICENSE](../LICENSE). Vous pouvez librement utiliser, modifier, auto-héberger et redistribuer Yggdrasil. Vous ne pouvez **pas** le vendre en tant que produit ni le proposer à d'autres en tant que service hébergé/géré. Il est à source disponible — pas open source au sens de l'OSI.
