# CLI UX plan — readable, informative, beautiful, interactive `ygg`

Drafted 2026-07-03. Design for upgrading every `ygg` output. Not yet implemented.

## Hard constraints (what makes this Yggdrasil-shaped)

1. **Zero-dependency stays.** No `rich`/`textual`/`click`. Pure stdlib ANSI — colors,
   box-drawing, `\r` progress. This is a selling point, not a limitation.
2. **Agent-safe by construction.** Colors/spinners/interactivity ONLY when
   `sys.stdout.isatty()` and `NO_COLOR`/`YGG_NO_COLOR` unset. The MCP facade captures
   stdout with `isatty() == False` → agents keep getting today's plain text, byte-for-byte.
   `--json` output is never touched. Gates prove non-TTY output is stable.
3. **One visual language everywhere**, from one tiny module (`yggdrasil/ygg_ui.py`,
   ~120 lines): palette, type badges, relevance bar, relative time, tables, progress,
   confirm prompts.

## Visual vocabulary

- **Type → color badge:** `decision`=cyan, `lesson`=green, `fix`=yellow,
  `convention`=blue, `project_status`=magenta, `follow_up`=red, `reference`=dim.
- **Relevance bar:** `▰▰▰▰▱` (5 cells, normalized to the top hit) instead of raw
  `score=1.0312` (the float stays in dim for power users).
- **Relative time:** `created_at` → `2d ago` / `3h ago` (exact date in `--json`).
- **Status marks:** `✓` green, `✗` red, `→` hints, `📌` pin, `~` nearest-fallback.
- **IDs demoted, not hidden:** dim + shortened (`ygg_41fd63…`); numbers `1. 2. 3.`
  become the interactive handles.

## Per-command redesign (before → after)

### `ygg search` / `ygg recall` / `ygg bootstrap` — the face of the product

Before (dense, id-first, no hierarchy):
```
ygg_41fd7ab6c5e843878612f4453bd28beb  score=1.0312  project=yggdrasil  type=project_status
  src=ygg-mcp  conf=0.90  used=4x
  P2 (производительность/масштаб) из docs/IMPROVEMENT-PLAN.md закрыт локальными коммитами…
```

After (content-first; badge, bar, relative time; query terms bolded in the preview):
```
1  project_status · yggdrasil · 1d ago · ▰▰▰▰▰ · used 4×
   P2 (производительность/масштаб) закрыт: эмбеддинги как float32 **BLOB**,
   **поиск** 10–29× быстрее, кэш unit-векторов…            ygg_41fd7ab6…

2  project · intothewildweb · 5d ago · ▰▰▰▰▱
   TODO: Реструктуризация секций сайта-портфолио…           ygg_149d6391…
```

**Interactive tail (TTY only):** turns search from a report into a workbench:
```
action? [N]=expand  pN=pin  sN=supersede  mN=materialize  Enter=done →
```
`2` prints hit 2 in full (no truncation, all metadata); `p1` pins; `m2` exports the
note. Piped/agent runs never see the prompt.

### `ygg remember` — today it dumps a 20-line JSON record

After:
```
✓ saved lesson → yggdrasil   ygg_a1b2c3d4…
⚠ similar existing (review for supersede):
  1  lesson · 12d ago  «webhook 401 → rotate the signing secret…»   ygg_9f8e7d…
```
(`--json` keeps the full record. The related-memories hint moves from stderr wall of
text to the same numbered, actionable format.)

### `ygg doctor` — already a checklist; make state legible at a glance

```
Yggdrasil doctor                                    engine 0.7.0 · 12ms

  ✓ engine        http://127.0.0.1:42069 · 68 memories · sqlite-fts5
  ✓ dense         paraphrase-multilingual (embeddings current)
  ✓ background    qwen2.5:3b
  ✓ token         ~/.yggdrasil/token (0600)
  ✓ Claude Code   MCP registered
  ✓ Codex         MCP registered

  All good.
```
Green `✓` / red `✗` / yellow `–`; response latency and engine version in the header;
every `✗` keeps its `→ fix:` line (now colored).

### `ygg stats` — numbers → shape

```
Yggdrasil memory · 52 live (3 archived) · 1.7 MB · dense: paraphrase-multilingual

by project                        by type
  content-factory  ████████ 16     lesson        ██████ 12
  monorepo         █████ 10        convention    ██████ 12
  yggdrasil        ████▌ 9         reference     ███▌ 7
  webdesk          █▌ 3            decision      ███ 6
  …                                …
```
Unicode bars scale to the max; two columns side-by-side when the terminal is wide
enough (fall back to stacked).

### `ygg seed` — a 2.5-hour job deserves a real progress line

TTY: one self-rewriting line per file (plus a persistent per-project summary):
```
seeding  ▍12/302 files · 4% · ETA 2h 08m · +37 lessons · 2 dup · 1 err
  now: content-factory/rollout-2026-06-30.jsonl (qwen2.5:3b)
```
Piped/CI: today's plain per-project lines stay. Finish with a box summary:
```
✓ seed done in 2h 12m — 302 files → +214 lessons, 41 dups skipped, 3 errors (retry: ygg seed)
```

### `ygg review` — color the stakes

- `high` issues red, `medium` yellow, `low` dim.
- Duplicate groups render as keep/drop diff: kept line green `✓ keep`, archived dim
  strikethrough-ish (`archive` prefix red).
- Summary line colored by outcome.

### `ygg config list` — align + show what's overridden

Non-default values bold + source colored (`config`=cyan, `env`=yellow, `flag`=magenta);
description stays dim; one blank line between entries.

### Errors — one style everywhere

```
ygg: ✗ Refusing to reset without a filter.
     → narrow with --project/--source/--type, or pass --all
```
Red `✗`, dim hint arrow. All `YggError` messages get an optional `hint=` field.

### `ygg help` — group with colored section headers, bold command names, dim
argument placeholders. Content unchanged.

## Implementation plan

1. `yggdrasil/ygg_ui.py` — palette (TTY+NO_COLOR aware), `badge` `bar` `ago` `table`
   `progress` `ok/fail/hint` `confirm`. Pure functions → unit-testable.
2. Wire in, one commit per surface: (a) search/recall/bootstrap + remember,
   (b) doctor + stats + config, (c) seed progress, (d) review colors + errors + help.
3. Interactive search tail last (own commit, `--no-input` escape hatch).
4. Tests: ui functions (pure); a non-TTY snapshot test asserting agent-visible output
   is unchanged; gates stay green (they run piped — that IS the regression test).

Estimated: ~M total, each commit small and independently shippable.
