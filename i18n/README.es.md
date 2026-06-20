<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>Una memoria única, compartida y duradera para todos tus agentes de IA para programar.</b><br/>
Claude Code, Codex y cualquier host MCP recuerdan tus decisiones, lecciones y el estado del proyecto — entre sesiones, herramientas y proyectos.</p>

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

En cada chat nuevo, tu IA olvida. Vuelves a explicar el proyecto, las decisiones, los detalles peliagudos — cada vez, en cada herramienta. **Yggdrasil es un pequeño cerebro de memoria siempre activo al que se conecta cualquier agente.** Abre una sesión nueva, en cualquier proyecto, con cualquier IA, y ya sabe lo que decidiste, lo que se rompió y lo que sigue pendiente — y sigue aprendiendo en segundo plano.

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

Nada de "déjame recordarte lo que hicimos ayer". Simplemente está ahí.

## Por qué

**Sin Yggdrasil** vuelves a explicar el contexto en cada chat nuevo, las lecciones de un proyecto nunca llegan al siguiente, cambiar de Claude Code → Codex empieza de cero, y los conocimientos de depuración ganados con esfuerzo mueren con la sesión.

**Con Yggdrasil:**

- 🧠 **Memoria persistente** — decisiones, lecciones y estado sobreviven entre sesiones.
- 🔌 **Cualquier agente, un solo cerebro** — Claude Code, Codex y cualquier host MCP comparten la misma memoria.
- 🌐 **Recuerdo entre proyectos** — *"esto se parece a lo que hiciste en el proyecto B — ¿lo reutilizamos?"*
- 🌱 **Autoaprendizaje** — un modelo local consolida la memoria en segundo plano (cero tokens de API).
- 🪪 **Un alma** — dale un nombre y una personalidad; aparece igual en cada herramienta.
- 🔒 **100 % local y privado** — tu memoria vive en tu máquina. Sin nube, sin cuenta.

## 🚀 Instalación

> **Requisitos:** macOS (Linux/Windows pronto), Python 3.10+ — o deja que `uv`/`npx` obtengan Python por ti. La búsqueda semántica es opcional y usa un modelo local de [Ollama](https://ollama.com).

```bash
uvx --from yggdrasil-memory ygg install      # recommended
```

<details>
<summary>¿Prefieres npm, pipx, pip, Homebrew o el código fuente? (el mismo motor)</summary>

| Herramienta | Comando |
| --- | --- |
| **npm / npx** | `npx yggdrasil-memory install` |
| **pipx** | `pipx install yggdrasil-memory && ygg install` |
| **pip** | `pip install yggdrasil-memory && ygg install` |
| **Homebrew** _(macOS)_ | `brew install VonderVuflya/tap/yggdrasil && ygg install` |
| **desde el código fuente** | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` |

</details>

`ygg install` es una configuración guiada única: detecta tu hardware y **recomienda un modelo local que encaje** (o elige `none` para una configuración sin ajustes, solo léxica), genera un token de autenticación privado, instala un **servicio en segundo plano siempre activo** y **registra las herramientas con Claude Code y Codex**. Compruébalo en cualquier momento con `ygg doctor`; actualiza con `ygg update`.

¿Solo quieres probarlo sin instalar un servicio? `uvx --from yggdrasil-memory ygg serve --reset --db /tmp/ygg.sqlite`.

## 🧠 Cómo funciona

Yggdrasil es **memoria + herramientas** — la *inteligencia* es tu LLM. Solo se asegura de que la memoria correcta esté delante del agente correcto en el momento correcto.

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

- **Motor** — un servidor HTTP solo con stdlib sobre SQLite + FTS5. Cero dependencias, ~21 MB de RAM.
- **Recuperación** — léxica por defecto; añade un modelo de embeddings local para búsqueda semántica + multilingüe. Las memorias recordadas con frecuencia y las fijadas tienen mayor prioridad.
- **Gobernanza** — los duplicados / conflictos se exponen para su revisión; los cambios son no destructivos (archivar, nunca borrar).
- **Obsidian** — cada memoria es también una nota en Markdown que puedes leer y editar.

## 🎛️ Niveles de memoria — sin configuración por defecto

De fábrica, Yggdrasil funciona con **SQLite + FTS5 sin dependencias** — búsqueda instantánea por palabras clave (léxica), sin modelos, sin GPU, nada que descargar. Ya es útil: recall@1 ≈ 0.77.

¿Quieres que coincida por **significado** y entre idiomas? Si tu hardware lo permite, `ygg install` puede descargar **modelos locales opcionales vía [Ollama](https://ollama.com)** — detecta tu CPU/RAM/GPU y recomienda uno que encaje (o elige `none` para quedarte sin configuración). Dos niveles opcionales e independientes:

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

| Nivel | Lo que añades | Lo que ganas |
| --- | --- | --- |
| **0 · por defecto** | nada — SQLite + FTS5 | búsqueda por palabras clave, cero dependencias, instantánea — recall@1 ≈ **0.77** |
| **1 · semántico** | un modelo de **embeddings** vía Ollama (p. ej. `all-minilm` 45 MB · `paraphrase-multilingual` ~560 MB) | búsqueda por **significado** + translingüe — recall@1 ≈ **0.94** |
| **2 · autoaprendizaje** | un pequeño LLM de **consolidación** vía Ollama (p. ej. `qwen2.5:1.5b` ~1 GB) | deduplicación/fusión de memoria en segundo plano (con seguridad de propuesta) |

Ollama solo **calcula** los vectores / ejecuta el modelo en segundo plano — los vectores y todas las memorias siguen viviendo en la **misma SQLite**. Los niveles son independientes y opcionales.

<details>
<summary>Menú completo de modelos (o ejecuta <code>ygg recommend</code>)</summary>

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

</details>

Todo permanece **100 % local — cero tokens de API, sin nube.** El instalador recomienda modelos que encajen con tu hardware (o elige `none` para quedarte sin configuración).

> El motor en sí es intercambiable — cualquier servicio que cumpla el contrato `MemoryBackend` es un reemplazo directo (apunta `YGG_ENGINE_URL` a él); SQLite es el valor por defecto sin dependencias. Consulta [docs/backend-boundary.md](../docs/backend-boundary.md).

## 🆚 Yggdrasil frente al resto

context-mode y Context7 poseen **capas diferentes** (tu ventana de contexto en vivo; documentación de bibliotecas actualizada). **mem0** es la más cercana — también es una capa de memoria, pero de un *tipo* distinto: un SDK/plataforma para que las **aplicaciones de IA recuerden a sus usuarios**. Yggdrasil es **memoria que instalas y ya está, local-first, de _tu propio_ trabajo para los agentes de programación que ya usas** — sin código, sin nube, sin clave de API.

| | **Yggdrasil** | [mem0](https://github.com/mem0ai/mem0) | [context-mode](https://github.com/mksglu/context-mode) | [Context7](https://github.com/upstash/context7) |
| --- | --- | --- | --- | --- |
| Memoria duradera de **tu propio trabajo** (decisiones, lecciones, estado) | ✅ | ✅ | ⚠️ en sesión | ❌ |
| **Listo para usar** con tus agentes, *sin código* (instalar + MCP) | ✅ | ⚠️ *SDK / integración* | ✅ | ✅ |
| Funciona **sin LLM ni clave de API** (cero dependencias, léxico por defecto) | ✅ | ❌ *necesita un LLM* | ✅ | ❌ |
| **100 % local y privado** (sin nube por defecto) | ✅ | ⚠️ *nube por defecto* | ✅ | ☁️ alojado |
| Recuerdo entre **proyectos** ("esto lo resolví en el proyecto B") | ✅ | ⚠️ | ❌ | — |
| Una memoria compartida **entre herramientas** (Claude Code · Codex · cualquier host MCP) | ✅ | ⚠️ *por app* | ✅ | ✅ |
| Mantiene ligera la **ventana de contexto en vivo** | — | — | ✅ | ❌ |
| **Documentación pública de bibliotecas** actualizada | ❌ *usa Context7* | ❌ | ❌ | ✅ |

> **mem0 frente a Yggdrasil, en una línea:** mem0 es un **SDK/plataforma de memoria para construir aplicaciones que recuerdan a sus usuarios** (tú escribes código; normalmente llama a un LLM, con nube por defecto). Yggdrasil es **memoria lista para usar, local-first, de _tu propio_ trabajo para los agentes con los que ya programas.** Trabajo distinto — elige según quién seas.

> También combina bien con [**autoresearch**](https://github.com/karpathy/autoresearch) — un bucle de experimentación autónomo (no es una herramienta de memoria); Yggdrasil le da memoria a largo plazo de lo que ya intentó → [integración](../integrations/autoresearch/).

**En resumen:** construyes un *producto* de IA que debe recordar a sus usuarios a escala → **mem0**. Eres el *desarrollador* y quieres que Claude Code / Codex recuerden *tus* decisiones entre proyectos, instalado en una línea, totalmente local → **Yggdrasil**.

## 🧰 Comandos

Los agentes ven seis herramientas MCP: `ygg_health`, `ygg_bootstrap`, `ygg_search`, `ygg_recall`, `ygg_remember`, `ygg_materialize`. Tras `ygg install` quedan registradas automáticamente con Claude Code y Codex — simplemente abre un proyecto y trabaja.

<details>
<summary>Referencia completa de la CLI <code>ygg</code></summary>

**Operaciones de memoria**

| Comando | Qué hace |
| --- | --- |
| `ygg recall --query "…"` | Búsqueda **entre proyectos** — "¿he hecho esto en algún sitio?" |
| `ygg search --project P --query "…"` | Búsqueda acotada al proyecto (`--type`, `--tag`, `--limit`, `--json`) |
| `ygg remember --project P --type debugging_lesson --content "…"` | Guarda una memoria duradera (protegida contra secretos, deduplicada; `--tag` para etiquetar) |
| `ygg bootstrap --project P` | Carga la memoria de un proyecto antes de empezar a trabajar |
| `ygg pin --id ID` · `ygg unpin --id ID` | Fija una memoria para que aflore de forma fiable |
| `ygg supersede --id ID` | Archiva una memoria obsoleta que una más nueva reemplaza |
| `ygg materialize --id ID --project P` | Exporta una memoria a una nota de Obsidian |

**Servicio y configuración**

| Comando | Qué hace |
| --- | --- |
| `ygg install` · `ygg setup` | Configuración guiada → servicio en segundo plano + registro MCP |
| `ygg doctor` · `ygg update` | Diagnostica la instalación · redespliega el último código |
| `ygg status` · `start` · `stop` · `restart` · `logs` | Gestiona el daemon siempre activo |
| `ygg hooks` · `unhooks` | Activa/desactiva el hook de autoarranque SessionStart |
| `ygg recommend` | Muestra el catálogo de modelos según el hardware |
| `ygg token` · `uninstall` | Imprime el token de autenticación · elimina servicio + registro |

Dale una personalidad — edita `~/.yggdrasil/identity.json`:

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

</details>

## ❓ Preguntas frecuentes

<details>
<summary><b>¿Envía mi código o memoria a la nube?</b></summary>

No. El motor, la base de datos y los modelos opcionales se ejecutan todos localmente. Sin cuenta, sin telemetría. Tu memoria nunca sale de tu máquina.
</details>

<details>
<summary><b>¿Recuerda todo automáticamente?</b></summary>

No — por diseño. La recuperación es automática; la *escritura* es deliberada (el agente llama a `ygg_remember` para las lecciones duraderas). Capturar todo automáticamente contamina la memoria, así que no lo hacemos. Un modelo en segundo plano consolida lo que ya está guardado (solo propone, por defecto).
</details>

<details>
<summary><b>¿Necesito una GPU o una clave de API?</b></summary>

No. Por defecto es búsqueda puramente léxica — cero dependencias, instantánea. La búsqueda semántica es opcional y usa un modelo *local* vía Ollama (sin clave de API). El instalador recomienda un modelo que encaje con tu hardware.
</details>

<details>
<summary><b>¿Cuánto pesa y cuántos tokens cuesta?</b></summary>

Muy poco. El motor ocupa **~21 MB de RAM, ~0 % de CPU en reposo, cero dependencias** (stdlib de Python); el disco son decenas de KB por memoria. El inicio de sesión inyecta ~300 tokens de memoria y cada llamada a una herramienta devuelve un fragmento pequeño — todo el trabajo pesado (indexación, embeddings, consolidación) se ejecuta fuera del LLM, en tu máquina.
</details>

<details>
<summary><b>¿Qué tan buena es la recuperación?</b></summary>

Medida por `eval/ygg_eval.py` (35 casos etiquetados, división dev/holdout), recall@1:

| Modo | recall@1 | paráfrasis | translingüe (EN→RU) |
| --- | --- | --- | --- |
| léxica (por defecto) | 0.77 | 0.63 | 0.00 |
| densa · `all-minilm` (45 MB, EN) | 0.83 | 0.88 | 0.00 |
| densa · `paraphrase-multilingual` (~560 MB) | **0.94** | 0.88 | **0.80** |

Las consultas `keyword` e `identifier` son 1.0 en todos los modos; con el modelo multilingüe **recall@3 = 1.0** (cada objetivo entre los 3 primeros).
</details>

<details>
<summary><b>¿Puedo editar o borrar memorias a mano?</b></summary>

Sí. Las memorias se materializan como notas en Markdown en un vault de Obsidian — léelas, edítalas o elimínalas como cualquier archivo. El motor nunca borra de forma definitiva; archiva (reversible).
</details>

<details>
<summary><b>¿Está listo para producción?</b></summary>

Es un **alpha** honesto: el camino feliz y el ciclo completo de gobernanza están cubiertos por gates que pasan (`scripts/run_gates.sh`). Aún no está endurecido para multiusuario/producción.
</details>

## 🗺️ Hoja de ruta

- 🛰️ **Sincronización entre superficies** — conéctate desde ChatGPT / Claude en la web y el móvil; una memoria entre la CLI, el navegador y el teléfono.
- 🔗 Grafo de relaciones (`SOLVES` / `SUPERSEDES` / `CONTRADICTS`) para un razonamiento más rico.
- 🐧 Instaladores de servicio para Linux/Windows (implementados; pruebas finales en dispositivo).

## 🤝 Contribuir

Se aceptan issues y PRs. Ejecuta `scripts/run_gates.sh` y `python3 -m unittest discover -s tests` antes de enviar — todos los gates deben permanecer en verde.

## 📜 Licencia

**Elastic License 2.0** — consulta [LICENSE](../LICENSE). Puedes usar, modificar, autoalojar y redistribuir Yggdrasil libremente. **No** puedes venderlo como producto ni ofrecerlo a otros como un servicio alojado/gestionado. Es de código disponible (source-available) — no es código abierto OSI.
