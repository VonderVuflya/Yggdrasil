# Yggdrasil Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans; independent frontend and chat tasks may run through superpowers:dispatching-parallel-agents. No commits or pushes.

**Goal:** Реализовать утверждённый Workspace: проекты, данные, проектные и общие чаты, 2D/3D-граф и запуск `ygg`.
**Architecture:** Python Workspace раздаёт React и адаптирует авторизованный API движка. Движок выполняет чтение с серверными фильтрами; отдельная SQLite хранит диалоги. Браузер использует локальную сессию.
**Tech Stack:** Python stdlib, React/TypeScript, Vite, Tailwind, shadcn/ui, Three.js.
**Spec:** `docs/superpowers/specs/2026-11-16-workspace-design.md`

## Global Constraints

- Русский интерфейс, локальные ресурсы, Node.js только при сборке.
- Контекст диалога фиксирован: `user_id`, `namespace`, `project`.
- `project: null` — все проекты; `project: ""` — без проекта.
- Существующие пользовательские изменения сохранить. Работать в отдельной ветке текущего checkout; никаких commit/push.
- Пользователь утвердил дизайн и выполнение; дополнительных согласований метода исполнения не требуется.

## Review Focus

- Большие базы: счётчики не ограничены 1000 записями; пагинация на сервере.
- Подмена project/id: источники и диалоги не пересекают сохранённую область.
- Сбой потока: частичный ответ сохраняется как прерванный, повтор доступен.
- Враждебный Origin/Host: нет доступа к локальной памяти и настройкам.
- Смена проекта во время запроса: поздний ответ не попадает в другой экран.

## Контракты

Все `/api/*` возвращают JSON напрямую, ошибки `{error: string}`. Запросы изменений — JSON и `X-Ygg-Request: 1`; credentials same-origin. Cookie HttpOnly, SameSite=Strict. `POST /api/session {ticket}` обменивает одноразовый ticket из URL fragment, TTL 60 секунд; frontend удаляет fragment. `GET /api/status` → `{engine: boolean, user_id, namespace}`.

Memory: `{id, content, project: string, type: string, source: string, created_at: number, archived: boolean, metadata: object}`. Даты Unix seconds. Project: `{name, count, archived_count, latest_at, types: Record<string,number>}`.

- `GET /api/projects` → `{projects: Project[]}`.
- `POST /api/memories {project, query?, type?, source?, archived?: boolean, offset?: number, limit?: number}` → `{items: Memory[], total: number}`.
  Отсутствие source означает все источники; source:"" — только записи без источника.
- `POST /api/memory {id, project}` → `{memory: Memory, relations: Edge[]}`.
- `POST /api/sources {project}` → `{sources: {name: string, count: number}[]}`.
- `POST /api/graph {project, query?, type?, focus?}` → `{nodes: Memory[], edges: Edge[], total: number, truncated: boolean}`. Edge: `{from_id, to_id, rel_type, external?: boolean, other_project?: string}`. Лимит 300.
- `GET /api/settings` → `{configured, provider: 'ollama'|'openai', url, model, has_key, suggested_url, suggested_model}`.
- `PUT /api/settings {provider,url,model,api_key?}` → те же публичные поля. Пустой api_key очищает ключ, отсутствие сохраняет.
- `POST /api/chats/list {project}` → `{chats: Chat[]}`.
- `POST /api/chats {project, memory_id?}` → Chat.
- `GET /api/chats/<id>` → `{chat: Chat, messages: Message[]}`.
- `DELETE /api/chats/<id>` → `{ok: true}`.
- `POST /api/chats/<id>/messages {content}` → NDJSON события `{type:'sources', sources: Memory[], truncated:boolean}`, `{type:'delta',text}`, `{type:'done',message:Message}` или `{type:'error',error,message?:Message}`.
- `POST /api/chats/<id>/stop` → `{ok:true}`.

Chat: `{id,project,title,created_at,updated_at,memory_id?:string}`. Message: `{id,role:'user'|'assistant',content,status:'complete'|'stopped'|'error'|'search_only',sources:Memory[],created_at,truncated?:boolean}`.

Движок: `POST /workspace/query` с `{op,user_id,namespace,...}` → `{success:true,data:<result>}`. op: projects/memories/memory/sources/graph/search. search принимает `{project,query,limit}` и возвращает `{items:Memory[]}`. project всегда передаётся явно. Никаких операций записи.

ChatService(home:Path, query:Callable[[dict],dict], user_id:str, namespace:str): settings(), save_settings(body), list_chats(project), create_chat(project,memory_id=None), get_chat(id), delete_chat(id), stream(id,content), stop(id). query получает op/project и другие параметры, адаптер добавляет identity. ChatService возвращает формы выше; stream — итератор событий. ValueError→400, KeyError→404, RuntimeError→409/502.

## Task 1: Чтение движка и Workspace HTTP

Files: `yggdrasil/ygg_workspace_data.py`, `yggdrasil/ygg_workspace.py`, `yggdrasil/ygg_memory_server.py`, `tests/test_workspace_data.py`, `tests/test_workspace_http.py`.
- [x] Написать тесты агрегации >1000, namespace/project, отсутствующего проекта, чужого id, внешних связей, пагинации и лимитов.
- [x] Запустить и увидеть отсутствие нового API, затем реализовать запросы под lock движка.
- [x] Написать HTTP-тесты session/Host/Origin/CSRF/path traversal/неизвестных маршрутов.
- [x] Реализовать Workspace-сервер и адаптер engine, проверить тесты.

## Task 2: Сохранённые диалоги и генерация

Files: `yggdrasil/ygg_workspace_chat.py`, `tests/test_workspace_chat.py` (независимый исполнитель).
- [x] Тесты фиксированного проекта, persistence, attachment, ошибок провайдера, остановки, пустой выдачи, ограничения контекста, конфигурации и отсутствия секретов в ответе.
- [x] Реализовать ChatService по контракту; Ollama/OpenAI streaming, конечные timeout, отдельный config и SQLite.
- [x] Запустить тесты на подменённом сетевом провайдере; явно отличить от проверки реальной модели.

## Task 3: React Workspace

Files: `web/` и `yggdrasil/workspace_static/` (независимый исполнитель).
- [x] Настроить Vite/React/Tailwind/shadcn и тесты значимых взаимодействий.
- [x] Реализовать навигацию, проекты, вкладки, источники, оба чата, настройки, ошибки/пустые состояния, локальные шрифты и темы по дизайн-документу.
- [x] Реализовать ленивый граф Three.js и 2D fallback, реальные рёбра, выбор/поиск/фокус узлов.
- [x] Проверить тесты, типы и production build, сохранить сборку для Python-пакета.

## Task 4: CLI, упаковка, интеграция

Files: `yggdrasil/cli.py`, `pyproject.toml`, `tests/test_workspace_launch.py`, `docs/workspace.md`.
- [x] Тесты выбора команды по умолчанию, повторного запуска, конфликтов порта и no-open.
- [x] Реализовать `ygg ui`, запуск без аргументов, PID/локальный launch ticket, ограничить права служебных файлов.
- [x] Собрать wheel/sdist и проверить, что установленный пакет отдаёт статику без Node.js.
- [x] Интеграционные тесты движок→Workspace→чат с временными данными.
- [x] Выполнить весь Python suite, frontend tests/build и свежий review; исправить существенные замечания.

## Progress

- План и контракты подготовлены; дизайн утверждён пользователем.
- Решение: текущий checkout на новой ветке сохраняет незакоммиченные зависимости пользователя и видимость результата в этом сеансе.

## Результат проверки

- Python: `python3 -m unittest discover -s tests` — 412 тестов, OK.
- Frontend: `npm test` — 11 тестов; `npm run build` — TypeScript и Vite успешно.
- Независимое ревью backend и UI выполнено; 5 существенных замечаний исправлены с регрессионными тестами.
- wheel и sdist собраны; wheel установлен во временный venv Python 3.10.
- Проверен запуск установленного `ygg ui --no-open` вне репозитория с Node.js отсутствующим в PATH: холодный запуск, повторное использование процесса, одноразовая сессия, реальные данные временного движка, прямой URL проекта и загрузка статики. Все процессы проверки остановлены.
- Рабочая pipx-установка, пользовательская база и рабочий движок не менялись.
- Браузерная визуальная проверка и запрос к реальной модели не выполнялись; провайдеры проверены локальными HTTP-фикстурами.
- Решение при реализации: `latest_at` означает последнее добавление, поскольку движок не хранит время редактирования. Подписи UI/документация отражают это.
- Решение при интеграции: cookies разделены по портам; source отсутствует = все, source пустой = без источника; Deep link `/project` поддержан сервером.
