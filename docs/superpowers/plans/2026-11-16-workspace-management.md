# Workspace management and internationalization

User requested implementation of model discovery, right-hand source lists, seven README languages (English default), seed and full CLI/config management. This extends the previously approved design; CLI remains fully supported. No real user seed/config/service operations run during implementation tests.

## Shared interfaces

- Frontend translations: `web/src/lib/i18n.tsx` exports `useI18n()` returning `{t,language,setLanguage}`; `t(key:string, vars?:Record<string,string|number>):string`. Keys are English source strings. `I18nProvider` optional default context uses English. Locale persistence key `ygg-language`; language codes en/ru/de/es/fr/ja/zh. All frontend chrome translated; user content and raw CLI output preserved.
- `POST /api/models {provider:'ollama'|'openai',url:string,api_key?:string,purpose?:'chat'|'bg'|'embed'}` => `{models:[{id,kind:'llm'|'embed'|'unknown',size?,note?}], reachable:boolean, error?:string}`. Missing api_key uses saved key only if URL matches saved endpoint for purpose. Probe only, no downloads/start. Ollama tags, LM Studio /api/v0/models then /v1/models; no redirects/secret exposure. Distinguish inaccessible/empty catalog. Only models of appropriate kind offered.
- `GET /api/config` => `{groups:[{id,label,settings:[{key,value,stored_value,source,default,description,secret,has_value,restart_required,type:'string'|'number'|'select',options?:string[]}]}],identity:{user_id,namespace}}`; secret value/stored_value/default always empty; has_value boolean. settings registry is ygg_config.SETTINGS/GROUPS.
- `PUT /api/config {values:Record<string,string>,unset?:string[]}` => same config response. Validate complete payload before writing; preserve unrelated config. Honor env precedence and show override; keys remain separate 0600 files. Save identity affects next workspace session/restart; existing pinned chats keep identity.
- `GET /api/commands` => `{commands:[{name,description,group,interactive:boolean,confirmation:boolean,example:string[]}]}` mirrors all CLI commands and aliases, no shell.
- `GET /api/jobs` => `{jobs:Job[]}`; `POST /api/jobs {command:string,args:string[],confirmed?:boolean}` => Job.
- `GET /api/jobs/<id>` => Job; `POST /api/jobs/<id>/input {text:string,secret?:boolean}` => Job; `POST /api/jobs/<id>/stop {}` => Job.
- Job: `{id,command,args:string[],status:'running'|'completed'|'failed'|'stopped',output:string,exit_code:number|null,created_at:number,finished_at:number|null,interactive:boolean,truncated:boolean}`. Only server-owned processes; bounded retained output, redact configured secrets in args/output, refuse unsupported command; python module cli via sys.executable, shell=False. One active mutating job avoids racing seed/config. POSIX PTY for prompts, fallback pipes on Windows with explicit availability. Input text sent verbatim (UI appends newline for answers, buttons for arrows/Enter/interrupt). Job outputs memory-only; no secret persisted to logs. Refresh keeps current jobs during server lifetime; restart ends tracking and no auto restart. Destructive actions require confirmed flag from UI confirmation.
- No arbitrary browser-supplied cwd, env or executable. Default job cwd is home, file path CLI args remain user's explicit local operations. Long-running serve/mcp lifecycle commands start jobs and stop via process group, never kill external existing processes.

## Work split and tests

1. Backend management agent: ygg_workspace_management.py + tests, configuration registry and job executor/catalog. Exact public API `Management(home:Path).configuration()`, `.save_configuration(body)`, `.commands()`, `.jobs()`, `.start(body)`, `.get(id)`, `.input(id,text,secret=False)`, `.stop(id)`. Agent owns only module/test files; root integrates routes.
2. Localization agent: all EXISTING web files except settings.tsx and styles.css; add i18n and seven complete catalogs, language picker, source panel layout markup in chat (new classes root styles). Preserve behavior, tests update English. Root adds management page and settings model picker. Translation new management/settings keys incorporated after root sends list.
3. Model discovery agent: ygg_workspace_models.py + tests, `discover_models(body,chat_service)->dict`, API per above. No live endpoint access in tests.
4. Root: HTTP integration, new settings/operations UI, CSS source panel, `-help`, integration tests, final reviews/tests/build/package/docs.

## Checks

- Model fixture tests: catalogs only installed/available, unreachable/empty distinction, auth, no redirected keys.
- Config: every registry setting present, cross CLI/web persistence, env override, secret redaction, atomic validation.
- Jobs: allowlist/no shell, stdout/stderr, interactive input, stop only owned process, output bounds, required confirmation, job failure/reload.
- Localization: language set exactly README locales, default English, persistence, matching catalog keys/interpolation; no translating user memories.
- UI: source sidebar selected response, mobile collapse, no duplicate source cards, existing scope regressions retained.
- Full Python and UI test suites, production build, standalone wheel smoke.

## Completion evidence

Implemented configuration and operations pages, installed-model discovery, seven complete language catalogs (English default), per-answer source sidebar, CLI help alias and authenticated Workspace restart. Reviews found endpoint-key reuse, reset-preview resolution and TIME_WAIT restart issues; each was fixed with regression coverage.

Validation: 465 Python tests passed; 27 frontend tests passed; TypeScript and Vite production build passed. Built wheel/sdist and installed the wheel in a temporary Python 3.10 environment: CLI cold start/reuse, authenticated session, real fixture-engine projects, static assets, management routes, actual help job, restart with changed namespace and old-session rejection passed with Node.js absent from PATH. No browser or live model inference check, no user seed/config mutations, no working-install replacement and no commit/push performed.
