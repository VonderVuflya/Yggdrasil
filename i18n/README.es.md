<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>Deja de volver a explicar tu proyecto a cada nueva sesión de IA.</b><br/>
Una memoria local para Claude Code, Codex y cualquier agente MCP — compartida entre sesiones, herramientas y proyectos. Cero dependencias. Nada sale de tu máquina.</p>

<p align="center">
  <a href="https://github.com/VonderVuflya/Yggdrasil/releases/latest"><img src="https://img.shields.io/github/v/release/VonderVuflya/Yggdrasil?label=release&color=blue" alt="Latest release"></a>
  <a href="https://pypi.org/project/yggdrasil-memory/"><img src="https://img.shields.io/pypi/v/yggdrasil-memory?label=PyPI&color=blue" alt="PyPI"></a>
  <a href="https://glama.ai/mcp/servers/VonderVuflya/Yggdrasil"><img src="https://glama.ai/mcp/servers/VonderVuflya/Yggdrasil/badges/score.svg" alt="Glama quality score"></a>
  <a href="../BENCHMARKS.md"><img src="https://img.shields.io/badge/recall@1-0.94%20·%20reproducible-brightgreen" alt="Benchmarks"></a>
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-AGPL%203.0-blue.svg" alt="AGPL-3.0"></a>
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="alpha">
</p>

<p align="center">
  <a href="#-instalación">Instalación</a> ·
  <a href="#-cómo-funciona">Cómo funciona</a> ·
  <a href="#-las-cifras">Cifras</a> ·
  <a href="#-yggdrasil-frente-al-resto">Comparativa</a> ·
  <a href="#-preguntas-frecuentes">FAQ</a>
</p>

<p align="center">
  Léelo en: <a href="../README.md">English</a> · <a href="./README.ru.md">Русский</a> · <a href="./README.zh.md">简体中文</a> · <a href="./README.fr.md">Français</a> · <a href="./README.ja.md">日本語</a> · <a href="./README.de.md">Deutsch</a>
</p>

---

<p align="center">
  <img src="../docs/demo.gif" alt="Yggdrasil — a brand-new session already knows your project, and recalls a fix from another project" width="880">
</p>

En cada chat nuevo, tu IA olvida. Vuelves a explicar el proyecto, las decisiones, los detalles peliagudos — cada vez, en cada herramienta. **Yggdrasil es una pequeña memoria siempre activa a la que se conecta cualquier agente.** Abre una sesión nueva, en cualquier proyecto, con cualquier IA, y ya sabe lo que decidiste, lo que se rompió y lo que sigue pendiente.

```text
$ cd ~/projects/checkout-api && claude        # a brand-new session

🌳 Yggdrasil  (injected automatically at session start)
   • [project_status] payments refactor: idempotency keys added; open: e2e tests
   • [lesson] webhook 401 → signing secret rotated; update env + redeploy

> "have I solved a flaky websocket reconnect anywhere before?"

🌳 recall → found in project `realtime-dash`:
   refresh the token *before* opening the socket, then retry with capped backoff.
```

Nada de "déjame recordarte lo que hicimos ayer". Simplemente está ahí.

## 🚀 Instalación

Dos comandos, dentro de **Claude Code** (el plugin se lanza vía [`uv`](https://docs.astral.sh/uv/)):

```text
/plugin marketplace add VonderVuflya/Yggdrasil
/plugin install yggdrasil
```

El motor se inicia de forma diferida en el primer uso y genera su propio token local — sin clave de API, sin nube, nada que configurar. Codex y Cursor usan el mismo flujo.

<details>
<summary>Todos los demás canales — daemon CLI, Homebrew, npm, Claude Desktop, desde el código fuente…</summary>

| Host / herramienta | Comando |
| --- | --- |
| **uvx** _(CLI recomendada)_ | `uvx --from yggdrasil-memory ygg install` |
| **npm / npx** | `npx yggdrasil-memory install` |
| **pipx** | `pipx install yggdrasil-memory && ygg install` |
| **pip** | `pip install yggdrasil-memory && ygg install` |
| **Homebrew** _(macOS)_ | `brew install VonderVuflya/tap/yggdrasil && ygg install` |
| **Claude Desktop** _(app)_ | arrastra el `.mcpb` desde la [última release](https://github.com/VonderVuflya/Yggdrasil/releases/latest) a Settings → Extensions, pega tu token (`ygg token`) — la app de escritorio pasa a compartir la misma memoria que tus agentes de CLI ([guía](../packaging/mcpb/README.md)) |
| **desde el código fuente** | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` |

`ygg install` es una configuración guiada de una sola vez: instala un servicio en segundo plano siempre activo, registra las herramientas MCP con Claude Code y Codex y — si tu hardware lo permite — recomienda modelos locales opcionales (o elige `none` para seguir sin configurar nada).

También hay una [skill `yggdrasil-memory`](../skills/) para cualquier superficie de Claude: MCP conecta las *herramientas*, la skill enseña al agente *cuándo* usarlas. Usa ambas para el mejor comportamiento.

Pruébalo sin instalar nada y con una base de datos desechable: `uvx --from yggdrasil-memory ygg serve --reset --db /tmp/ygg.sqlite`.

</details>

Luego simplemente trabaja: pídele a tu agente *"recuerda lo que decidimos sobre este proyecto"*, dile *"guarda esta decisión"* — en la siguiente sesión ya está ahí. Verifica la instalación en cualquier momento con `ygg doctor`.

**¿Ya tienes historial?** Siembra la memoria a partir de tus transcripciones existentes de Claude Code + Codex, tus vaults de Obsidian y tus repos con `CLAUDE.md` — todo destilado localmente:

```bash
ygg seed --dry-run    # see what it would import; drop the flag to distill for real
```

**¿Dejas otra herramienta de memoria?** `ygg import --from mcp-memory --path memory.json` importa todo su almacén a Yggdrasil (deduplicado y protegido contra secretos) — luego puedes borrarla.

## Por qué

- 🧠 **Persistente** — las decisiones, las lecciones y el estado del proyecto sobreviven entre sesiones.
- 🔌 **Un cerebro, todas las herramientas** — Claude Code, Codex y cualquier host MCP comparten la misma memoria.
- 🌐 **Recuerdo entre proyectos** — *"esto se parece a lo que hiciste en el proyecto B — ¿lo reutilizamos?"*
- 🧹 **Curada, no capturada** — tu agente guarda las pocas cosas que importan; la gobernanza deduplica y archiva, nunca borra.
- 🌱 **Automantenida** *(opcional)* — un pequeño modelo local consolida la memoria en segundo plano. Cero tokens de API.
- 🪪 **Una identidad en todas partes** — un nombre y una persona opcionales que cada agente adopta, para que Claude Code y Codex se sientan como el mismo asistente.
- 🔒 **100 % local** — tu memoria vive en tu máquina. Sin nube, sin cuenta, sin telemetría.

## 🧠 Cómo funciona

Yggdrasil es **memoria + herramientas** — la *inteligencia* es tu LLM. Solo se asegura de que la memoria correcta esté delante del agente correcto en el momento correcto.

- 🛎️ **Daemon siempre activo** — un pequeño servicio local (~21 MB de RAM) al que tus agentes acceden mediante herramientas MCP (`ygg_search`, `ygg_recall`, `ygg_remember` …).
- 🪝 **Hooks** — al iniciar sesión se inyectan automáticamente la identidad, el estado del proyecto y los seguimientos pendientes (~300 tokens); un hook opcional por cada prompt recupera automáticamente la memoria relevante para *cada solicitud*.
- 📌 **Ranking** — las memorias fijadas y las recordadas con frecuencia afloran primero.
- 🧹 **Gobernanza** — los duplicados y conflictos se ponen en cola para revisión; los cambios son no destructivos (archivar, nunca borrar).
- 📓 **Obsidian** — cada memoria es también una nota en Markdown plano que puedes leer, editar y buscar con grep.

## 🎛️ Niveles de memoria — sin configuración por defecto

De fábrica, Yggdrasil funciona con **SQLite + FTS5 y cero dependencias** — búsqueda instantánea por palabras clave, sin modelos, nada que descargar. Los modelos **locales** opcionales vía [Ollama](https://ollama.com) añaden dos niveles independientes:

| Nivel | Lo que añades | Lo que ganas |
| --- | --- | --- |
| **0 · por defecto** | nada — SQLite + FTS5 | búsqueda por palabras clave, cero dependencias, instantánea — recall@1 = **0.77** |
| **1 · semántico** | un modelo de **embeddings** (`all-minilm` 45 MB · `paraphrase-multilingual` ~560 MB) | búsqueda por **significado**, entre idiomas — recall@1 = **0.94**, recall@3 **1.00** |
| **2 · automantenido** | un **LLM** pequeño (`qwen2.5:1.5b` ~1 GB) | deduplicación/fusión de memoria en segundo plano (solo propone) |

Ollama solo *calcula* los vectores y ejecuta el modelo en segundo plano — cada memoria y cada vector se quedan en la misma SQLite local. `ygg install` detecta tu hardware y recomienda uno que encaje (`ygg recommend` muestra el catálogo completo).

<details>
<summary>Menú completo de modelos</summary>

**Embeddings (búsqueda semántica):**

| Modelo | Tamaño | Bueno para |
| --- | --- | --- |
| `all-minilm` | 45 MB | inglés, diminuto y rápido |
| `nomic-embed-text` | 274 MB | inglés, mejor calidad |
| `paraphrase-multilingual` | ~560 MB | multilingüe (EN/RU + 50 idiomas) |
| `bge-m3` | 1.2 GB | multilingüe, máxima calidad (más pesado) |

**Consolidación en segundo plano (LLM pequeño):**

| Modelo | Tamaño | Bueno para |
| --- | --- | --- |
| `qwen2.5:0.5b` | ~400 MB | diminuto, rápido en CPU |
| `qwen2.5:1.5b` | ~1 GB | mejor opción por defecto en CPU |
| `llama3.2:3b` | ~2 GB | mejor calidad, más lento en CPU |

El motor en sí es intercambiable — cualquier servicio que cumpla el contrato `MemoryBackend` es un reemplazo directo (`YGG_ENGINE_URL`); consulta [docs/backend-boundary.md](../docs/backend-boundary.md).

</details>

## 📊 Las cifras

Medidas por [`eval/ygg_eval.py`](../eval/ygg_eval.py) — 232 memorias, 110 consultas etiquetadas, pesos de ranking ajustados solo con la división *dev*, de modo que **el holdout es la cifra sin sesgo** (recall@1, con el modelo `paraphrase-multilingual`):

| Modo de búsqueda | recall@1 (holdout) | recall@3 | léxico sin dependencias |
| --- | --- | --- | --- |
| **Dentro de un proyecto** (la ruta real, pool ~11) | **0.94** | **1.00** | 0.76 |
| **Store completo** (sin filtro, pool 232) | 0.72 | **0.87** | 0.69 |

**Dentro de un proyecto — la ruta que usas — la memoria correcta es la #1 en el 0.94 de las consultas y siempre está entre las 3 primeras (recall@3 = 1.00).** Buscar en todo el store sin filtro es más difícil (recall@1 0.72, recall@3 0.87 sobre las 232). El modo léxico sin dependencias ya resuelve las consultas por palabra clave y por identificador de código (1.00); el modelo local añade significado y multilingüismo (crosslingual 0.25 → 0.95). El [desglose completo en BENCHMARKS.md](../BENCHMARKS.md) muestra intervalos de confianza al 95 %, tamaños de pool y puntuaciones por clase — y puedes volver a ejecutarlo en un minuto: `python3 eval/ygg_eval.py --report`.

## 🆚 Yggdrasil frente al resto

Los demás o capturan transcripciones automáticamente o te venden una nube. La apuesta de Yggdrasil: conservar las **pocas cosas que importan**, curadas y deduplicadas, en registros simples que te pertenecen — y compartirlas entre **todas** las herramientas y proyectos.

| | **Yggdrasil** | Memoria integrada <sub>(Claude Code · Codex)</sub> | [claude-mem](https://github.com/thedotmack/claude-mem) | [mem0](https://github.com/mem0ai/mem0) / OpenMemory | [basic-memory](https://github.com/basicmachines-co/basic-memory) |
| --- | --- | --- | --- | --- | --- |
| Decisiones / lecciones / estado curados (no transcripciones) | ✅ | ⚠️ notas automáticas | ❌ captura todo | ⚠️ | ⚠️ notas libres |
| Una memoria **entre herramientas** | ✅ | ❌ silo por proveedor | ✅ | ✅ | ✅ |
| Recuerdo **entre proyectos** ("esto lo resolví en el proyecto B") | ✅ | ❌ acotada al repo | ⚠️ | ⚠️ | ⚠️ |
| **100 % local** por defecto | ✅ | ✅ | ⚠️ add-on de sincronización en la nube | ❌ primero alojado | ✅ |
| **Cero dependencias** (stdlib + SQLite) | ✅ | — | ❌ Node + Bun + daemon worker | ❌ Docker + Qdrant + clave de LLM | ❌ |
| Funciona **sin LLM y sin clave de API** | ✅ | ✅ | ❌ comprime con IA | ❌ | ✅ |
| **Búsqueda semántica, totalmente local** | ✅ Ollama opcional | ❌ solo grep | ⚠️ Chroma opcional | ⚠️ necesita clave de API o stack Docker | ❌ |
| **Markdown plano que te pertenece** (listo para Obsidian) | ✅ | ✅ | ❌ | ❌ | ✅ |

**El vecino más cercano — claude-mem:** memoria de captura total que graba y comprime con IA cada sesión (Node 20+ *y* Bun, un daemon worker persistente; Chroma opcional). Yggdrasil es la apuesta contraria: un almacén pequeño y de alta señal en lugar de una manguera que no deja de crecer. **mem0** es un SDK más una plataforma alojada para construir *apps* que recuerdan a *sus usuarios* — incluso autoalojado necesita una clave de API de LLM. **Las memorias integradas** son genuinamente útiles — y estructuralmente aisladas: un proveedor, un repo, una máquina, grep literal. Yggdrasil es la capa por encima de ellas (y `ygg seed` puede arrancar a partir de esas mismas transcripciones). Una capa totalmente distinta: [context-mode](https://github.com/mksglu/context-mode) (ventana de contexto en vivo) y [Context7](https://github.com/upstash/context7) (documentación de bibliotecas actualizada) — ambos combinan bien con Yggdrasil.

## 🧰 Comandos

Los agentes ven seis herramientas MCP: `ygg_health`, `ygg_bootstrap`, `ygg_search`, `ygg_recall`, `ygg_remember`, `ygg_materialize` — registradas automáticamente por el plugin o por `ygg install`.

<details>
<summary>Referencia completa de la CLI <code>ygg</code></summary>

**Operaciones de memoria**

| Comando | Qué hace |
| --- | --- |
| `ygg recall --query "…"` | Búsqueda **entre proyectos** — "¿he hecho esto en algún sitio?" |
| `ygg search --project P --query "…"` | Búsqueda acotada al proyecto (`--type`, `--tag`, `--limit`, `--json`) |
| `ygg remember --project P --type lesson --content "…"` | Guarda una memoria duradera (protegida contra secretos, deduplicada) |
| `ygg bootstrap --project P` | Carga la memoria de un proyecto antes de empezar a trabajar |
| `ygg pin --id ID` · `ygg unpin --id ID` | Fija una memoria para que aflore de forma fiable |
| `ygg supersede --id ID` | Archiva una memoria obsoleta que una más nueva reemplaza |
| `ygg materialize --id ID --project P` | Exporta una memoria a una nota de Obsidian |
| `ygg export-native --project P` | Escribe un resumen curado en `AGENTS.md`/`MEMORY.md` — alimenta la memoria nativa de Claude Code y Codex |
| `ygg import --from TOOL --path P` | Migra el almacén de otra herramienta de memoria a Yggdrasil (`mcp-memory`, `basic-memory`; primero `--dry-run`) |
| `ygg review [--apply]` | Trabaja la cola de gobernanza — consolida duplicados, marca memorias obsoletas o en conflicto (solo archiva, reversible) |
| `ygg delete --id ID` · `ygg reset …` | Borra una memoria de forma permanente · deshace en bloque un `ygg seed` fallido (pide confirmación primero) |

**Arranque en frío**

| Comando | Qué hace |
| --- | --- |
| `ygg seed` | Destila las transcripciones de Claude Code + Codex, los vaults de Obsidian y los repos con `CLAUDE.md` — incremental, deduplicado, totalmente local |
| `ygg seed --dry-run` · `--force` | Solo descubre + estima · vuelve a destilar todo |
| `ygg distill --source PATH` | Destila un directorio/archivo en lecciones |
| `ygg reindex` | Rellena los embeddings que faltan (restaura el recall denso) |

**Servicio y configuración**

| Comando | Qué hace |
| --- | --- |
| `ygg install` · `ygg doctor` · `ygg update` | Configuración guiada · diagnóstico con correcciones accionables · actualización |
| `ygg config` | Muestra/establece la configuración persistente (`list` · `get` · `set` · `unset`) |
| `ygg status` · `start` · `stop` · `restart` · `logs` | Gestiona el daemon siempre activo |
| `ygg hooks` · `unhooks` · `register` | Hook SessionStart on/off · (re)registra MCP |
| `ygg recommend` · `token` · `uninstall` | Catálogo de modelos · imprime el token de autenticación · lo elimina todo |

Dale una personalidad — edita `~/.yggdrasil/identity.json`:

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

¿Siembra pesada y portátil flojo? Apunta la destilación a *cualquier* máquina de tu LAN — un escritorio con Ollama, LM Studio, llama.cpp, **incluso un iPhone con una app de servidor LLM local**: `ygg config set distill_url http://<box>:11434`. Yggdrasil detecta automáticamente el dialecto de la API (Ollama o compatible con OpenAI); tus datos siguen sin salir nunca de tu red — detalles en [docs/ygg-cli.md](../docs/ygg-cli.md).

</details>

## ❓ Preguntas frecuentes

<details>
<summary><b>Claude Code ya tiene memoria integrada — ¿por qué Yggdrasil?</b></summary>

Las memorias integradas son por proveedor, por repo, por máquina, y se recuperan por coincidencia literal de texto. Yggdrasil es la capa por encima: la *misma* memoria en Claude Code, Codex y cualquier host MCP, recuerdo *entre* proyectos, búsqueda semántica opcional — y sigue siendo 100 % local. Se complementan: conserva la memoria nativa y deja que `ygg seed` destile tu historial existente en el cerebro compartido.
</details>

<details>
<summary><b>¿Envía mi código o memoria a la nube?</b></summary>

No. El motor, la base de datos y los modelos opcionales se ejecutan todos localmente. Sin cuenta, sin telemetría. La única llamada saliente es una comprobación de versión contra PyPI.
</details>

<details>
<summary><b>¿Recuerda todo automáticamente?</b></summary>

No — por diseño. La recuperación es automática; la *escritura* es deliberada (el agente llama a `ygg_remember` para las lecciones duraderas). Capturarlo todo contamina la memoria y quema tokens, así que no lo hacemos. El modelo opcional en segundo plano consolida lo que ya está guardado (solo propone).
</details>

<details>
<summary><b>¿Necesito una GPU o una clave de API?</b></summary>

No. Por defecto es búsqueda puramente léxica — cero dependencias, instantánea. La búsqueda semántica es opcional y usa un modelo *local* vía Ollama. El instalador recomienda uno que encaje con tu hardware.
</details>

<details>
<summary><b>¿Cuánto pesa y cuántos tokens cuesta?</b></summary>

El motor en reposo ocupa **~21 MB de RAM** (léxico por defecto) con ~0 % de CPU; el disco son decenas de KB por memoria. El inicio de sesión inyecta ~300 tokens; cada llamada a una herramienta devuelve un fragmento pequeño. Todo el trabajo pesado (indexación, embeddings, consolidación) se ejecuta fuera del LLM, en tu máquina.
</details>

<details>
<summary><b>¿Puedo editar o borrar memorias a mano?</b></summary>

Sí. Las memorias se materializan como notas en Markdown en un vault de Obsidian — léelas, edítalas o elimínalas como cualquier archivo. El motor nunca borra de forma definitiva; archiva (reversible).
</details>

## 🚦 Estado y hoja de ruta

**Alpha.** El camino feliz y el ciclo de gobernanza están cubiertos por gates (`scripts/run_gates.sh`); aún no está endurecido para multiusuario ni producción. Hoy macOS; los instaladores de servicio para Linux/Windows están construidos y en pruebas finales en dispositivo.

Próximamente: 🛰️ sincronización entre superficies (una memoria entre CLI, web y móvil) · 🔗 grafo de relaciones (`SOLVES` / `SUPERSEDES` / `CONTRADICTS`) · 🐧 GA de Linux/Windows.

## 🤝 Contribuir

Se aceptan issues y PRs. Ejecuta `scripts/run_gates.sh` y `python3 -m unittest discover -s tests` antes de enviar — todos los gates deben permanecer en verde.

## 📜 Licencia

**GNU AGPL v3.0** — consulta [LICENSE](../LICENSE). Libre y de código abierto: úsalo, modifícalo, autoalójalo, redistribúyelo. Si lo modificas o lo ofreces como servicio de red, debes publicar tu código fuente bajo la misma licencia.
