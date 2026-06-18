<h1 align="center">🌳 Yggdrasil</h1>

<p align="center"><b>Una memoria compartida y duradera para todos tus agentes de IA para programar.</b><br/>
Claude Code, Codex y cualquier host MCP recuerdan tus proyectos — decisiones, lecciones, estado — a través de sesiones, herramientas y proyectos.</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-Elastic%202.0-blue.svg" alt="Elastic License 2.0">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/deps-zero%20(stdlib)-brightgreen" alt="zero deps">
  <img src="https://img.shields.io/badge/MCP-Claude%20·%20Codex%20·%20any%20host-purple" alt="MCP">
  <img src="https://img.shields.io/badge/local--first-100%25%20private-success" alt="local-first">
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="alpha">
</p>

<p align="center">
  <a href="#-inicio-rápido">Inicio rápido</a> ·
  <a href="#-cómo-funciona">Cómo funciona</a> ·
  <a href="#%EF%B8%8F-comandos">Comandos</a> ·
  <a href="#-preguntas-frecuentes">Preguntas frecuentes</a> ·
  <a href="#-yggdrasil-frente-a-las-alternativas">Comparación</a>
</p>

<p align="center">
  <a href="../README.md"><img src="https://img.shields.io/badge/README-English-blue" alt="English"></a>
  <a href="./README.ru.md"><img src="https://img.shields.io/badge/docs-Русский-darkblue" alt="Русский"></a>
  <a href="./README.zh.md"><img src="https://img.shields.io/badge/docs-简体中文-red" alt="简体中文"></a>
  <a href="./README.es.md"><img src="https://img.shields.io/badge/docs-Español-orange" alt="Español"></a>
  <a href="./README.fr.md"><img src="https://img.shields.io/badge/docs-Français-blue" alt="Français"></a>
</p>

---

En cada chat nuevo, tu IA olvida. Vuelves a explicar el proyecto, las decisiones, las trampas — una y otra vez, en cada herramienta. **Yggdrasil es un pequeño cerebro de memoria siempre activo al que se conecta cualquier agente.** Abre una sesión nueva en cualquier proyecto, con cualquier IA, y ya sabe qué decidiste, qué se rompió y qué sigue pendiente — y aprende discretamente de tu trabajo en segundo plano.

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

Nada de "déjame recordarte lo que hicimos ayer". Simplemente está ahí.

## ❌ Sin Yggdrasil

- 🔁 Vuelves a explicar el contexto del proyecto a la IA en cada chat nuevo.
- 🧩 Las lecciones aprendidas en un proyecto nunca llegan al siguiente.
- 🤖 Cambias de Claude Code a Codex → la nueva herramienta no sabe nada.
- 🗑️ Las valiosas ideas de depuración desaparecen cuando termina la sesión.

## ✅ Con Yggdrasil

- 🧠 **Memoria persistente** — las decisiones, las lecciones y el estado sobreviven entre sesiones.
- 🔌 **Cualquier agente, un solo cerebro** — Claude Code, Codex y cualquier host MCP comparten la misma memoria.
- 🌐 **Recuerdo entre proyectos** — *"esto se parece a lo que hiciste en el proyecto B — ¿lo reutilizamos?"*
- 🌱 **Autoaprendizaje** — un modelo local consolida la memoria en segundo plano (cero tokens de API).
- 🪪 **Un alma** — dale un nombre y una personalidad; aparece igual en cada herramienta.
- 🔒 **100% local y privado** — tu memoria vive en tu máquina. Sin nube, sin cuenta.

## 🚀 Inicio rápido

> **Requisitos:** macOS, Python 3.10+ *(o deja que `uv`/`npx` obtengan Python por ti)*. Opcional (para búsqueda semántica): [Ollama](https://ollama.com).

Instala con lo que ya usas: **todos los canales instalan el mismo motor:**

| Herramienta | Comando |
| --- | --- |
| **uv** _(recomendado)_ | `uvx --from yggdrasil-memory ygg install` |
| **npm / npx** | `npx yggdrasil-memory install` |
| **pipx** | `pipx install yggdrasil-memory && ygg install` |
| **pip** | `pip install yggdrasil-memory && ygg install` |
| **Homebrew** _(macOS)_ | `brew install VonderVuflya/tap/yggdrasil && ygg install` |
| **desde el código** | `uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg install` |

> Los canales de los registros se habilitan a medida que se publican (consulta [RELEASING.md](../RELEASING.md)); la línea **desde el código** ya funciona con este repositorio. `npx` y `uvx` pueden obtener Python por ti.

Eso es todo. `ygg install`:
1. 🔍 detecta tu CPU/RAM/GPU y **recomienda modelos que se ajusten a tu máquina** (o elige `none` para una configuración cero, solo léxica),
2. 🔑 genera un token de autenticación privado (nunca codificado en el código),
3. 🛎️ instala un servicio en segundo plano siempre activo (se inicia automáticamente al iniciar sesión, se reinicia tras un fallo),
4. 🤝 registra las herramientas de memoria con **Claude Code y Codex**,
5. 🪝 (opcional) habilita un hook de inicio de sesión que inyecta automáticamente la memoria de tu proyecto.

Comprueba la instalación cuando quieras con `ygg doctor`; actualiza después con `ygg update`. ¿Prefieres simplemente probar el motor sin instalar un servicio?

```bash
uvx --from git+https://github.com/VonderVuflya/yggdrasil.git ygg serve --reset --db /tmp/ygg.sqlite   # se ejecuta en :42069
```

## 🧠 Cómo funciona

Yggdrasil es **memoria + herramientas** — la *inteligencia* es tu LLM. Solo se asegura de que la memoria correcta esté frente al agente correcto en el momento correcto.

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

- **Motor** — un servidor HTTP basado únicamente en la biblioteca estándar sobre SQLite + FTS5. Cero dependencias, ~21 MB de RAM.
- **Recuperación** — léxica de forma predeterminada; añade un modelo local de embeddings para búsqueda semántica + interlingüística.
- **Gobernanza** — las memorias duplicadas / obsoletas / en conflicto se sacan a la luz para su revisión; los cambios no son destructivos (archivar, nunca eliminar).
- **Obsidian** — cada memoria es también una nota en Markdown que puedes leer y editar.

## ⭐ Características

- 🧠 **Memoria duradera entre sesiones** para cualquier agente compatible con MCP.
- 🌐 **Recuerdo entre proyectos** + un contrato proactivo de "ya resolviste esto antes".
- 🔎 **Recuperación híbrida** — BM25 + embeddings densos opcionales, fusionados; interlingüística (p. ej. EN↔RU).
- 🪪 **Identidad / persona** inyectada en cada sesión (la "sensación Jarvis").
- 📌 **Estado y seguimientos** mostrados al inicio de la sesión — *"¿cuál es el estado de X?"* se responde al instante.
- 🌱 **Autoaprendizaje en segundo plano** — un pequeño modelo local consolida la memoria (propone de forma segura por defecto).
- 🧹 **Bucle de gobernanza** — cola de revisión + archivado/fusión no destructivos.
- 📓 **Materialización en Obsidian** — legible, editable, portátil.
- 🔒 **Local primero y privado** — sin nube, sin cuenta, tus datos se quedan donde están.
- 🪶 **Cero dependencias obligatorias** — Python puro de la biblioteca estándar; modelos locales opcionales vía Ollama.

## 🛠️ Comandos

**Operaciones de memoria — `ygg <command>`** (para agentes)

| Comando | Qué hace |
| --- | --- |
| `health` | Comprueba que el motor está activo |
| `bootstrap --project P` | Trae la memoria de un proyecto antes de empezar a trabajar |
| `search --project P --query "…"` | Búsqueda acotada al proyecto (`--type`, `--limit`, `--json`) |
| `recall --query "…"` | Búsqueda **entre proyectos** — "¿he hecho esto en algún sitio?" |
| `remember --project P --type debugging_lesson --content "…"` | Guarda una memoria duradera (protegida contra secretos, deduplicada) |
| `materialize --id ID --project P` | Exporta una memoria a una nota de Obsidian |

**Servicio y configuración — `ygg <command>`** (ciclo de vida)

| Comando | Qué hace |
| --- | --- |
| `install` | Asistente guiado → servicio en segundo plano + registro MCP |
| `recommend` | Muestra el catálogo de modelos según el hardware |
| `status` · `start` · `stop` · `restart` · `logs` | Gestiona el demonio siempre activo |
| `hooks` · `unhooks` | Habilita/deshabilita el hook de auto-bootstrap en SessionStart |
| `consolidate` · `unconsolidate` | Programa/elimina la consolidación de memoria en segundo plano |
| `token` · `uninstall` | Imprime el token de autenticación · elimina el servicio + registro |

**Herramientas MCP** (lo que ven los agentes): `ygg_health`, `ygg_bootstrap`, `ygg_search`, `ygg_recall`, `ygg_remember`, `ygg_materialize`.

## 🔌 Úsalo con tu agente

- **Claude Code** — tras `ygg install`, las herramientas quedan registradas (`/mcp` muestra `yggdrasil`) y el hook de SessionStart inyecta la memoria automáticamente. Solo abre un proyecto y ponte a trabajar.
- **Codex** — también registrado; aprueba la llamada a la herramienta `ygg_*` una vez por sesión.
- **Cualquier host MCP** — apúntalo a `ygg mcp` (stdio) con `YGG_ENGINE_URL` + `YGG_ENGINE_TOKEN`.

Dale una personalidad — edita `~/.yggdrasil/identity.json`:

```json
{ "name": "Jarvis", "persona": "concise, proactive, dry wit", "user_facts": ["prefers TypeScript", "ships small PRs"] }
```

## 📊 Huella y calidad

**Huella** (medida, 13 memorias): **~21 MB de RAM**, **~0% de CPU en reposo**, **cero dependencias** (biblioteca estándar de Python 3.10+). El disco ≈ decenas de KB por memoria. La búsqueda densa es opcional y añade un modelo local de Ollama (p. ej. `all-minilm`, 45 MB).

**Calidad de recuperación** (`eval/ygg_eval.py`, recall@1):

| Modo | recall@1 | paráfrasis | interlingüística (EN→RU) |
| --- | --- | --- | --- |
| léxica (predeterminada) | 0.63 | 0.00 | 0.00 |
| densa · `all-minilm` (45 MB, EN) | 0.75 | 0.67 | 0.00 |
| densa · `paraphrase-multilingual` (~560 MB) | **0.94** | 0.67 | **1.00** |

Las consultas de tipo `keyword` e `identifier` son 1.0 en todos los modos. Pruébalo tú mismo: `python3 eval/ygg_eval.py`.

## ❓ Preguntas frecuentes

<details>
<summary><b>¿Envía mi código o mi memoria a la nube?</b></summary>

No. El motor, la base de datos y los modelos opcionales se ejecutan todos localmente. Sin cuenta, sin telemetría. Tu memoria nunca sale de tu máquina.
</details>

<details>
<summary><b>¿En qué se diferencia esto de Context7 / RAG sobre documentación?</b></summary>

Context7 obtiene <i>documentación pública y actualizada de bibliotecas</i> (la última API de React/Next.js). Yggdrasil recuerda <i>tu propio trabajo</i> — tus decisiones, lecciones y el estado del proyecto. Son complementarios; usa ambos. Consulta la <a href="#-yggdrasil-frente-a-las-alternativas">comparación</a>.
</details>

<details>
<summary><b>¿Recuerda todo automáticamente?</b></summary>

No — por diseño. La recuperación es automática; la <i>escritura</i> es deliberada (el agente llama a <code>ygg_remember</code> para las lecciones duraderas). Capturar todo automáticamente contamina la memoria, así que no lo hacemos. Un modelo en segundo plano consolida lo que ya está guardado (solo propone de forma predeterminada).
</details>

<details>
<summary><b>¿Necesito una GPU o una clave de API?</b></summary>

No. La opción predeterminada es la búsqueda léxica pura — cero dependencias, instantánea. La búsqueda semántica es opcional y usa un modelo <i>local</i> vía Ollama (sin clave de API). El instalador recomienda un modelo que se ajuste a tu hardware.
</details>

<details>
<summary><b>¿Cuántos tokens le cuesta a mi agente?</b></summary>

Muy pocos. El inicio de sesión inyecta ~300 tokens de memoria; cada llamada a una herramienta devuelve un pequeño fragmento. Todo el trabajo pesado (indexación, embeddings, consolidación) se ejecuta fuera del LLM en tu máquina.
</details>

<details>
<summary><b>¿Puedo editar o eliminar memorias a mano?</b></summary>

Sí. Las memorias se materializan como notas en Markdown dentro de un vault de Obsidian — léelas, edítalas o elimínalas como cualquier archivo. El motor nunca elimina de forma permanente; archiva (reversible).
</details>

<details>
<summary><b>¿Está listo para producción?</b></summary>

Es una <b>alpha</b> honesta: el camino feliz y el bucle completo de gobernanza están cubiertos por gates que pasan (<code>scripts/run_gates.sh</code>). Aún no está endurecido para entornos multiusuario/producción.
</details>

## 🆚 Yggdrasil frente a las alternativas

La mayoría de las herramientas de "memoria/contexto de IA" se adueñan de una **capa diferente** del stack. La que nadie llenó — **memoria duradera, entre sesiones y entre agentes, de _tu propio_ trabajo** — es exactamente donde se sitúa Yggdrasil. No compite con ellas; es la memoria a la que todas se conectan.

| Herramienta | La capa de la que se adueña | Solapamiento con Yggdrasil | Mejor juntas |
| --- | --- | --- | --- |
| **[Context7](https://github.com/upstash/context7)** | **documentación pública de bibliotecas** actualizada (solo lectura) | ninguno | Context7 da la API actual de una biblioteca; Yggdrasil recuerda *tus* decisiones y lecciones |
| **[autoresearch](https://github.com/karpathy/autoresearch)** | **bucle de experimentos** autónomo (editar → entrenar → medir → conservar/revertir) | ninguno — es el *bucle*, no la memoria | Yggdrasil es la memoria a largo plazo de la que carece el bucle: recuerda lo que ya probaste, conserva cada resultado a través de noches y forks → [integración](../integrations/autoresearch/) |
| **context-mode** y compresores en contexto | compactación de contexto **en sesión** / análisis en sandbox | ninguno — por sesión | Yggdrasil persiste las *conclusiones* a través de sesiones, herramientas y máquinas |
| **memoria de LLM simple** | borrador por sesión | parcial | Yggdrasil es duradera, entre proyectos, gobernada y local |

Matriz de capacidades:

| | **Yggdrasil** | Context7 | Memoria de LLM simple |
| --- | --- | --- | --- |
| Conoce **tus** decisiones/lecciones | ✅ | ❌ | ⚠️ dentro de una sesión |
| Documentación pública de bibliotecas actualizada | ❌ (usa Context7) | ✅ | ❌ |
| Entre sesiones y entre **agentes** | ✅ | ✅ | ❌ |
| Recuerdo entre **proyectos** | ✅ | — | ❌ |
| Escribe/acumula tu memoria | ✅ | ❌ (solo lectura) | ⚠️ |
| Local y privado | ✅ | ☁️ alojado | depende |
| Autoconsolidante | ✅ | ❌ | ❌ |

**En resumen:** estas herramientas obtienen documentación, ejecutan experimentos o comprimen una sesión. **Yggdrasil es la memoria duradera de _tu propio_ trabajo que a todas les faltaba — úsala *con* ellas y solo ganas.**

## 🗺️ Hoja de ruta

- 🔗 Grafo de relaciones (`SOLVES` / `SUPERSEDES` / `CONTRADICTS`) para un razonamiento más rico.
- 🛰️ Sincronización multidispositivo — continúa literalmente desde cualquier máquina.
- 🧪 Modelos opcionales más potentes para una consolidación autónoma y segura.
- 🐧 Instaladores de servicio para Linux/Windows (actualmente launchd de macOS).

## 🤝 Contribuir

Issues y PRs son bienvenidos. Ejecuta `scripts/run_gates.sh` y `python3 -m unittest discover -s tests` antes de enviar — todos los gates deben permanecer en verde.

## 📜 Licencia

**Elastic License 2.0** — consulta [LICENSE](./LICENSE). Puedes usar, modificar, autoalojar y redistribuir Yggdrasil libremente. **No** puedes venderlo como producto ni ofrecerlo a terceros como servicio alojado/gestionado. Es source-available, no open source según la OSI.

