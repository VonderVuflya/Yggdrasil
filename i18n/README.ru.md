<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>Единая общая, долговечная память для всех ваших ИИ-агентов для написания кода.</b><br/>
Claude Code, Codex и любой MCP-хост помнят ваши решения, уроки и статус проекта — между сессиями, инструментами и проектами.</p>

<p align="center">
  <a href="https://github.com/VonderVuflya/Yggdrasil/releases/latest"><img src="https://img.shields.io/github/v/release/VonderVuflya/Yggdrasil?label=release&color=blue" alt="Latest release"></a>
  <a href="https://pypi.org/project/yggdrasil-memory/"><img src="https://img.shields.io/pypi/v/yggdrasil-memory?label=PyPI&color=blue" alt="PyPI"></a>
  <a href="https://pypistats.org/packages/yggdrasil-memory"><img src="https://img.shields.io/pypi/dm/yggdrasil-memory?label=PyPI%20downloads&color=blue" alt="PyPI downloads"></a>
  <a href="https://www.npmjs.com/package/yggdrasil-memory"><img src="https://img.shields.io/npm/dm/yggdrasil-memory?label=npm%20downloads&color=red" alt="npm downloads"></a>
  <a href="https://pepy.tech/project/yggdrasil-memory"><img src="https://img.shields.io/pepy/dt/yggdrasil-memory?label=total%20downloads&color=8b5cf6" alt="Total downloads"></a>
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

В каждом новом чате ваш ИИ всё забывает. Вы заново объясняете проект, решения, подводные камни — каждый раз, в каждом инструменте. **Yggdrasil — это крошечный всегда работающий «мозг памяти», к которому подключается любой агент.** Откройте новую сессию, в любом проекте, с любым ИИ — и он уже знает, что вы решили, что сломалось и что ещё не закрыто — и продолжает учиться в фоне.

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

Никаких «дай-ка напомню, что мы делали вчера». Оно просто там.

## Зачем

**Без Yggdrasil** вы заново объясняете контекст в каждом новом чате, уроки из одного проекта никогда не доходят до следующего, переключение Claude Code → Codex начинается с нуля, а тяжело добытые озарения от отладки умирают вместе с сессией.

**С Yggdrasil:**

- 🧠 **Постоянная память** — решения, уроки и статус переживают любые сессии.
- 🔌 **Любой агент, один мозг** — Claude Code, Codex, любой MCP-хост делят одну и ту же память.
- 🌐 **Кросс-проектный recall** — *«похоже на то, что вы делали в проекте B — переиспользовать?»*
- 🌱 **Самообучение** — локальная модель консолидирует память в фоне (ноль API-токенов).
- 🪪 **Душа** — дайте ему имя и характер; он одинаково проявляется в каждом инструменте.
- 🔒 **100% локально и приватно** — ваша память живёт на вашей машине. Ни облака, ни аккаунта.

## 🚀 Быстрый старт

> **Требования:** macOS (Linux/Windows скоро), Python 3.10+ — или позвольте `uv`/`npx` подтянуть Python за вас. Семантический поиск опционален и использует локальную модель [Ollama](https://ollama.com).

**Вариант A — установить как плагин** (один шаг, прямо внутри вашего агента — без настройки). В **Claude Code**:

```text
/plugin marketplace add VonderVuflya/Yggdrasil
/plugin install yggdrasil
```

Движок лениво запускается при первом использовании и генерирует собственный локальный токен — **ни API-ключа, ни облака, ничего настраивать не нужно.** (Codex и Cursor используют тот же процесс.)

**Вариант B — установить полный сервис** (всегда работающий демон + авто-впрыск при старте сессии + опциональные локальные модели):

```bash
uvx --from yggdrasil-memory ygg install      # one-time guided setup
```

<details>
<summary>Все каналы установки (тот же движок)</summary>

| Хост / инструмент | Команда |
| --- | --- |
| **Claude Code · Codex · Cursor** (плагин) | `/plugin marketplace add VonderVuflya/Yggdrasil` → `/plugin install yggdrasil` |
| **uvx** _(рекомендуемый CLI)_ | `uvx --from yggdrasil-memory ygg install` |
| **npm / npx** | `npx yggdrasil-memory install` |
| **pipx** | `pipx install yggdrasil-memory && ygg install` |
| **pip** | `pip install yggdrasil-memory && ygg install` |
| **Homebrew** _(macOS)_ | `brew install VonderVuflya/tap/yggdrasil && ygg install` |
| **Claude Desktop** _(приложение)_ | перетащите `.mcpb` из [последнего релиза](https://github.com/VonderVuflya/Yggdrasil/releases/latest) в Settings → Extensions ([инструкция](../packaging/mcpb/README.md)) |
| **из исходников** | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` |

</details>

`ygg install` — это одноразовая управляемая настройка: она определяет ваше железо и **рекомендует подходящую локальную модель** (или выберите `none` для конфигурации без настроек, только лексической), генерирует приватный токен авторизации, устанавливает **всегда работающий фоновый сервис** и **регистрирует инструменты в Claude Code и Codex**.

**Проверка и использование:**
```bash
ygg doctor       # engine · models · MCP registration · hook — all green?
```
Затем просто работайте. Попросите агента *«вспомни, что мы решили по этому проекту»* или скажите ему *«запомни это решение»* — и в следующей сессии оно уже там.

**Уже есть история?** Заполните память из ваших существующих транскриптов **Claude Code + Codex**, хранилищ Obsidian и репозиториев `CLAUDE.md` за один проход — всё дистиллируется локально:

```bash
ygg seed --dry-run    # see what it'd import; drop --dry-run to distill for real
```

Просто хотите попробовать? `uvx --from yggdrasil-memory ygg serve --reset --db /tmp/ygg.sqlite`.

## 🔌 Больше способов подключения

Помимо плагина и `ygg install` выше:

- 🖥️ **Claude Desktop (приложение)** — установите MCP-расширение: возьмите `yggdrasil-<версия>.mcpb` из [последнего релиза](https://github.com/VonderVuflya/Yggdrasil/releases/latest) (или из `packaging/mcpb/`), перетащите его в **Settings → Extensions** и вставьте свой токен (`ygg token`). Теперь приложение делит **ту же память**, что и ваши CLI-агенты. → [инструкция](../packaging/mcpb/README.md)
- 🧠 **Skill (любой Claude)** — [скилл `yggdrasil-memory`](../skills/) учит агента рабочему процессу: вспоминать перед работой, сохранять после. Загрузите `yggdrasil-memory.zip` через **Settings → Skills → Create skill → Upload a skill**.

> **MCP против Skill:** MCP подключает *инструменты* (как дотянуться до памяти), а Skill учит, *когда ими пользоваться*. Используйте оба для наилучшего поведения.

## 🧠 Как это работает

Yggdrasil — это **память + инструменты**, а *интеллект* — это ваша LLM. Он лишь следит за тем, чтобы нужная память оказалась перед нужным агентом в нужный момент.

- 🛎️ **Всегда работающий демон** — крошечный локальный сервис (~21 МБ RAM), к которому ваши агенты обращаются через MCP-инструменты (`ygg_search`, `ygg_recall`, `ygg_remember` …).
- 🪝 **Старт сессии** — хук автоматически внедряет идентичность, статус проекта и открытые задачи.
- 📌 **Ранжирование** — часто вызываемые и закреплённые воспоминания поднимаются выше (хранилище и уровни ниже ↓).
- 🧹 **Управление** — дубликаты / конфликты выносятся на проверку; изменения неразрушающие (архивирование, никогда не удаление).
- 📓 **Obsidian** — каждое воспоминание ещё и Markdown-заметка, которую можно читать и редактировать.

## 🎛️ Уровни памяти — без настройки по умолчанию

Из коробки Yggdrasil работает на **SQLite + FTS5 с нулём зависимостей** — мгновенный поиск по ключевым словам (лексический), без моделей, без GPU, ничего скачивать не нужно. Уже полезно: recall@1 ≈ 0.77.

Хотите, чтобы он искал по **смыслу** и между языками? Если позволяет железо, `ygg install` может подтянуть опциональные **локальные модели через [Ollama](https://ollama.com)** — он определяет ваш CPU/RAM/GPU и рекомендует подходящую (или выберите `none`, чтобы остаться без настройки). Два опциональных независимых уровня:

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

| Уровень | Что добавляете | Что получаете |
| --- | --- | --- |
| **0 · по умолчанию** | ничего — SQLite + FTS5 | поиск по ключевым словам, ноль зависимостей, мгновенно — recall@1 ≈ **0.77** |
| **1 · семантический** | модель **эмбеддингов** через Ollama (например, `all-minilm` 45 MB · `paraphrase-multilingual` ~560 MB) | поиск по **смыслу** + кросс-языковой — recall@1 ≈ **0.94** |
| **2 · самообучение** | небольшая LLM **консолидации** через Ollama (например, `qwen2.5:1.5b` ~1 GB) | фоновая дедупликация/слияние памяти (безопасно через предложения) |

Ollama только **вычисляет** векторы / запускает фоновую модель — сами векторы и вся память по-прежнему живут в **той же SQLite**. Уровни независимы и подключаются по желанию.

<details>
<summary>Полное меню моделей (или запустите <code>ygg recommend</code>)</summary>

**Эмбеддинги (семантический поиск):**

| Модель | Размер | Хорошо подходит для |
| --- | --- | --- |
| `all-minilm` | 45 MB | английский, крошечная и быстрая |
| `nomic-embed-text` | 274 MB | английский, качество получше |
| `paraphrase-multilingual` | ~560 MB | мультиязычная (EN/RU + 50 языков) |
| `bge-m3` | 1.2 GB | мультиязычная, топовое качество (тяжелее) |

**Фоновая консолидация (небольшая LLM):**

| Модель | Размер | Хорошо подходит для |
| --- | --- | --- |
| `qwen2.5:0.5b` | ~400 MB | крошечная, быстрая на CPU |
| `qwen2.5:1.5b` | ~1 GB | лучший вариант по умолчанию для CPU |
| `llama3.2:3b` | ~2 GB | качество получше, медленнее на CPU |

</details>

Всё остаётся **на 100% локальным — ноль API-токенов, никакого облака.** Установщик рекомендует модели, которые подходят под ваше железо (или выберите `none`, чтобы остаться без настройки).

> Сам движок взаимозаменяем — любой сервис, удовлетворяющий контракту `MemoryBackend`, подключается напрямую (направьте `YGG_ENGINE_URL` на него); SQLite — это вариант по умолчанию без зависимостей. См. [docs/backend-boundary.md](../docs/backend-boundary.md).

## 🆚 Yggdrasil против остальных

Ближайший инструмент — **claude-mem**: это тоже долговечная память для агентов написания кода, но *более тяжёлая система, захватывающая всё*: она автоматически записывает каждую сессию и сжимает её с помощью ИИ (нужны Node + Bun + векторная БД). **mem0** — это *SDK* памяти для приложений, чтобы они помнили своих пользователей. context-mode и Context7 владеют **разными слоями** (ваше живое контекстное окно; свежая документация библиотек). Yggdrasil — это **установил-и-работай, без зависимостей, local-first память _вашей собственной_ работы** — курируемая, а не пожарный шланг, хранимая как обычный Markdown, который вы можете редактировать.

| | **Yggdrasil** | [claude-mem](https://github.com/thedotmack/claude-mem) | [mem0](https://github.com/mem0ai/mem0) | [context-mode](https://github.com/mksglu/context-mode) | [Context7](https://github.com/upstash/context7) |
| --- | --- | --- | --- | --- | --- |
| Долговечная память **вашей собственной работы** (решения, уроки, статус) | ✅ | ✅ | ✅ | ⚠️ в рамках сессии | ❌ |
| **Подключается сразу** к вашим агентам, *без кода* (установка + MCP) | ✅ | ✅ | ⚠️ *SDK* | ✅ | ✅ |
| **Ноль зависимостей** (stdlib + SQLite; без Node/Bun/векторной БД) | ✅ | ❌ | ❌ | ❌ | — |
| Работает **без LLM и без API-ключа** (лексический по умолчанию) | ✅ | ❌ *сжимает ИИ* | ❌ *нужна LLM* | ✅ | ❌ |
| **Курируемая** и редактируемая как обычный Markdown (не захват всего) | ✅ | ❌ *автозахват всего* | ⚠️ | ❌ | — |
| **100% локально и приватно** (без облака по умолчанию) | ✅ | ⚠️ | ⚠️ *облако по умолчанию* | ✅ | ☁️ хостинг |
| Кросс-**проектный** recall («решал это в проекте B») | ✅ | ⚠️ | ⚠️ | ❌ | — |
| Одна память, общая **между инструментами** (Claude Code · Codex · любой MCP-хост) | ✅ | ✅ | ⚠️ *под каждое приложение* | ✅ | ✅ |
| Актуальная публичная **документация библиотек** | ❌ *(используйте Context7)* | ❌ | ❌ | ❌ | ✅ |

> **claude-mem против Yggdrasil, одной строкой:** claude-mem автоматически захватывает *всё* и сжимает это с помощью ИИ (Node + Bun + векторная БД; ~84k★, поставляется с крипто-токеном) — и хранилище растёт с каждой сессией. Yggdrasil хранит *немногое, что действительно важно* — курируемое и **семантически дедуплицированное** (почти одинаковые уроки схлопываются, поэтому база остаётся компактной и насыщенной), без зависимостей, хранимое как обычные записи, которые можно грепать, править и которыми владеете вы — без ИИ, без токена. Другая философия; можно использовать оба.

> **mem0 против Yggdrasil, одной строкой:** mem0 — это **SDK/платформа памяти для создания приложений, которые помнят своих пользователей** (вы пишете код; обычно вызывается LLM, облако по умолчанию). Yggdrasil — это **подключаемая сразу, local-first память _вашей собственной_ работы для агентов, с которыми вы уже пишете код.** Разные задачи — выбирайте по тому, кто вы.

> Также хорошо сочетается с [**autoresearch**](https://github.com/karpathy/autoresearch) — автономным циклом экспериментов (не инструмент памяти); Yggdrasil даёт ему долгосрочную память о том, что уже пробовалось → [интеграция](../integrations/autoresearch/).

**Вкратце:** хотите автоматический захват всего во множестве IDE и не против более тяжёлого стека → **claude-mem**. Строите ИИ-*продукт*, который должен помнить своих пользователей в масштабе → **mem0**. Хотите крошечную, локальную, *курируемую* память, которой владеете вы — ноль зависимостей, без ИИ — для агентов написания кода, которыми вы уже пользуетесь → **Yggdrasil**.

## 🧰 Команды

Агенты видят шесть MCP-инструментов: `ygg_health`, `ygg_bootstrap`, `ygg_search`, `ygg_recall`, `ygg_remember`, `ygg_materialize`. После `ygg install` они автоматически регистрируются в Claude Code и Codex — просто откройте проект и работайте.

<details>
<summary>Полный справочник CLI <code>ygg</code></summary>

**Операции с памятью**

| Команда | Что она делает |
| --- | --- |
| `ygg recall --query "…"` | **Кросс-проектный** поиск — «делал ли я это где-нибудь?» |
| `ygg search --project P --query "…"` | Поиск в рамках проекта (`--type`, `--tag`, `--limit`, `--json`) |
| `ygg remember --project P --type debugging_lesson --content "…"` | Сохранить долговечное воспоминание (с защитой от секретов, дедупликацией; `--tag` для метки) |
| `ygg bootstrap --project P` | Подтянуть память проекта перед началом работы |
| `ygg pin --id ID` · `ygg unpin --id ID` | Закрепить воспоминание, чтобы оно надёжно всплывало |
| `ygg supersede --id ID` | Архивировать устаревшее воспоминание, которое заменяет более новое |
| `ygg materialize --id ID --project P` | Экспортировать одно воспоминание в заметку Obsidian |

**Холодный старт — заполнение из вашей предыдущей работы**

| Команда | Что она делает |
| --- | --- |
| `ygg seed` | Дистиллировать ваши транскрипты **Claude Code + Codex**, хранилища Obsidian и репозитории `CLAUDE.md` в уроки — инкрементально, с дедупликацией, полностью локально |
| `ygg seed --dry-run` · `--force` | Только обнаружение + оценка · повторно дистиллировать всё |
| `ygg distill --source PATH` | Дистиллировать одну директорию/файл в уроки |
| `ygg reindex` | Дозаполнить эмбеддинги для воспоминаний без них (восстанавливает плотный recall) |

Большие сессии могут быть медленными на крошечной модели — направьте дистилляцию на более мощную машину в вашей локальной сети (Конфигурация ↓):

```bash
ygg seed --ollama-url http://192.168.3.124:11434 --model llama3.2:3b --timeout 240
```

**Сервис и настройка**

| Команда | Что она делает |
| --- | --- |
| `ygg install` · `ygg setup` | Управляемая настройка → фоновый сервис + регистрация MCP |
| `ygg doctor` · `ygg update` | Диагностировать установку (готовые исправления) · обновить + переразвернуть |
| `ygg config` | Показать/изменить постоянные настройки — `list` · `get` · `set` · `unset` |
| `ygg register` | (Пере)регистрировать MCP-сервер в Claude Code / Codex |
| `ygg status` · `start` · `stop` · `restart` · `logs` | Управление всегда работающим демоном |
| `ygg hooks` · `unhooks` | Включить/выключить хук авто-bootstrap при SessionStart |
| `ygg recommend` | Показать каталог моделей с учётом железа |
| `ygg token` · `uninstall` | Вывести токен авторизации · удалить сервис + регистрацию |

Дайте ему характер — отредактируйте `~/.yggdrasil/identity.json`:

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

</details>

## ⚙️ Конфигурация

Yggdrasil работает без всякой настройки. Когда вы *всё же* хотите что-то изменить, любая настройка разрешается одинаково:

> **`--flag`  >  переменная окружения  >  `~/.yggdrasil/config.json`  >  значение по умолчанию**

Используйте флаг для одного запуска или `ygg config set`, чтобы зафиксировать значение:

```bash
ygg config list                       # effective values + where each one comes from
ygg config set distill_timeout 240    # persist a setting
ygg config get distill_url
ygg config unset bg_model             # back to the default
```

| Настройка | По умолчанию | Чем управляет |
| --- | --- | --- |
| `distill_url` | локальная Ollama | Эндпоинт для `ygg seed` / консолидации — направьте на более мощную машину |
| `distill_timeout` | `120` | Таймаут дистилляции на файл (в секундах) — увеличьте для больших сессий |
| `bg_model` | `qwen2.5:1.5b` | Модель для дистилляции и консолидации |
| `embed_model` · `embed_url` | локально | Модель эмбеддингов + эндпоинт (на уровне демона; запустите `ygg redeploy`, чтобы применить) |
| `user_id` · `namespace` | `demo-user` · `yggdrasil-demo` | Идентичность / namespace для хранимых воспоминаний |

**Дистилляция на другой машине.** Дистилляция (`ygg seed`) тяжёлая, но редкая; эмбеддинги лёгкие, но постоянные. Поэтому `distill_url` намеренно держится отдельно от `embed_url` — отправляйте дистилляцию на мощную машину в вашей локальной сети, пока эмбеддинги (и ваши данные) остаются локальными и всегда доступны:

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
<summary><b>Отправляет ли он мой код или память в облако?</b></summary>

Нет. Движок, база данных и опциональные модели — всё работает локально. Ни аккаунта, ни телеметрии. Ваша память никогда не покидает вашу машину.
</details>

<details>
<summary><b>Запоминает ли он всё автоматически?</b></summary>

Нет — по задумке. Извлечение автоматическое; *запись* — осознанная (агент вызывает `ygg_remember` для долговечных уроков). Авто-захват всего загрязняет память, поэтому мы так не делаем. Фоновая модель консолидирует уже сохранённое (по умолчанию только предлагает).
</details>

<details>
<summary><b>Нужен ли мне GPU или API-ключ?</b></summary>

Нет. По умолчанию — чисто лексический поиск: ноль зависимостей, мгновенно. Семантический поиск подключается по желанию и использует *локальную* модель через Ollama (без API-ключа). Установщик рекомендует модель под ваше железо.
</details>

<details>
<summary><b>Насколько он тяжёлый и сколько токенов стоит?</b></summary>

Крошечный. Движок — **~21 МБ RAM, ~0% CPU в простое, ноль зависимостей** (Python stdlib); диск — десятки КБ на воспоминание. Старт сессии впрыскивает ~300 токенов памяти, а каждый вызов инструмента возвращает небольшой фрагмент — вся тяжёлая работа (индексация, эмбеддинги, консолидация) идёт вне LLM на вашей машине.
</details>

<details>
<summary><b>Насколько хорошо работает извлечение?</b></summary>

Замерено через `eval/ygg_eval.py` (35 размеченных кейсов, разбиение dev/holdout), recall@1:

| Режим | recall@1 | перефразирование | кросс-язык (EN→RU) |
| --- | --- | --- | --- |
| лексический (по умолчанию) | 0.77 | 0.63 | 0.00 |
| плотный · `all-minilm` (45 МБ, EN) | 0.83 | 0.88 | 0.00 |
| плотный · `paraphrase-multilingual` (~560 МБ) | **0.94** | 0.88 | **0.80** |

Запросы `keyword` и `identifier` дают 1.0 во всех режимах; с мультиязычной моделью **recall@3 = 1.0** (каждая цель в топ-3).
</details>

<details>
<summary><b>Могу ли я редактировать или удалять воспоминания вручную?</b></summary>

Да. Воспоминания материализуются в Markdown-заметки в хранилище Obsidian — читайте, редактируйте или удаляйте их как любой файл. Движок никогда не удаляет жёстко; он архивирует (обратимо).
</details>

<details>
<summary><b>Готов ли он к продакшену?</b></summary>

Это честная **альфа**: счастливый путь и полный цикл управления покрыты проходящими гейтами (`scripts/run_gates.sh`). Пока не закалён под многопользовательский/продакшен-режим.
</details>

## 🗺️ Дорожная карта

- 🛰️ **Кросс-поверхностная синхронизация** — подключение из ChatGPT / Claude в вебе и на мобильном; одна память на CLI, браузер и телефон.
- 🔗 Граф связей (`SOLVES` / `SUPERSEDES` / `CONTRADICTS`) для более богатых рассуждений.
- 🐧 Установщики сервиса для Linux/Windows (реализованы; финальное тестирование на устройствах).

## 🤝 Участие

Issues и PR приветствуются. Запустите `scripts/run_gates.sh` и `python3 -m unittest discover -s tests` перед отправкой — все гейты должны оставаться зелёными.

## 📜 Лицензия

**Elastic License 2.0** — см. [LICENSE](../LICENSE). Вы можете свободно использовать, изменять, размещать у себя и распространять Yggdrasil. Вы **не можете** продавать его как продукт или предлагать другим как хостинговый/управляемый сервис. Это source-available — не OSI open source.
