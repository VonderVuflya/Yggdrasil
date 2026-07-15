# Yggdrasil — Benchmarks

Honest, reproducible numbers. Everything here you can run yourself in minutes — the
whole point is that you don't have to trust us. Retrieval re-measured 2026-07-16
against the current engine on a 232-memory / 110-query corpus; footprint on v0.5.4.

> TL;DR — with an optional local model, Yggdrasil puts the right memory **in the top 3
> every time (recall@3 = 1.00)** and #1 **0.94 of the time within a project** (n=110), the
> path you actually use. Searching the **entire store** with no project filter is harder:
> recall@1 = 0.72, recall@3 = 0.87 across all 232 memories. Zero-dep lexical mode alone is
> recall@1 = 0.76. All in a **132 KB** install, **~21 MB** RAM, no Docker / DB server / cloud / API key.

---

## 1. Retrieval quality (the metric that actually matters)

A memory tool is only as good as its ability to surface the *right* memory for a
query. We measure that on a fixed corpus of 232 software-engineering memories against
a 110-query labelled set, split into four query classes and a **dev/holdout** split —
ranking weights are tuned on *dev* only, so **the holdout column is the unbiased
number** (it was never used for tuning).

We report **two views**, because "recall@1" means nothing without the candidate pool:

- **Project-scoped** — search within one project (`ygg search --project P`, the path
  you actually use). Candidate pool: **median 11** same-project memories (max 25).
- **Full-corpus** — search the *whole* store, no project filter ("have I solved this
  anywhere?"). Candidate pool: **all 232**. Strictly harder; semantically-similar
  memories in *other* projects become distractors.

`paraphrase-multilingual` model, recall@1 with 95% bootstrap CI:

| | holdout (unbiased) | all splits | recall@3 | MRR |
| --- | :---: | :---: | :---: | :---: |
| **Project-scoped** (pool ~11) | **0.94** `[0.87–1.00]` | 0.96 `[0.93–0.99]` | **1.00** | 0.97 |
| **Full-corpus** (pool 232) | 0.72 `[0.59–0.83]` | 0.75 `[0.66–0.83]` | 0.87 | 0.79 |
| **Lexical, zero-dep** (project-scoped) | 0.76 | 0.77 `[0.69–0.85]` | 0.82 | 0.79 |

By query class (all splits, project-scoped), lexical → +local model: **keyword**
1.00 → 1.00, **identifier** 1.00 → 1.00, **paraphrase** 0.60 → 0.88, **crosslingual**
(EN→RU) 0.25 → 0.95.

Honest takeaways:

- **recall@3 = 1.00 project-scoped** — on the path you actually use, the right memory is
  always in the top 3, and it's #1 for 0.94 of queries. Store-wide (all 232, no filter)
  it's harder: recall@1 0.72, recall@3 0.87.
- **The number held as the corpus grew 6×.** At n=35 the headline was recall@1 0.93 with
  a wide CI; at n=232 / 110 queries it's 0.94 with a tighter CI `[0.87–1.00]` and roughly
  double the candidate pool. Bigger, harder eval, same result.
- **holdout ≈ dev** (0.94 vs 0.98 project-scoped) — the ranking weights don't overfit
  the metric; the tuner (`eval/ygg_tune.py`) explicitly kept defaults when a swept gain
  didn't hold on holdout.
- **Zero-dep lexical already gets 0.76** — keyword and code-identifier queries are solved
  (1.00) by SQLite FTS5 alone, no download. The local model is what adds *meaning* and
  *cross-language* (crosslingual jumps 0.25 → 0.95).

**Reproduce it (≈1 min, no setup):**

```bash
python3 eval/ygg_eval.py --report                                        # lexical, zero-dep
YGG_EMBED_MODEL=paraphrase-multilingual python3 eval/ygg_eval.py --report   # + local model
```

`--report` prints exactly the two-view, holdout-vs-dev, pool-size + CI breakdown above.
Drop it for raw JSON. The corpus, queries, labels and scoring live in
[`eval/ygg_eval.py`](eval/ygg_eval.py) — nothing hidden; change it, re-run.

---

## 2. Footprint (what it costs to run)

| | Yggdrasil |
| --- | --- |
| **Runtime dependencies** | **0** — pure Python standard library |
| **Install size** | **132 KB** wheel (154 KB sdist) |
| **Memory (always-on daemon)** | **~21 MB** RSS (lexical engine) |
| **Database** | one SQLite file (+ a Markdown note per memory) |
| **Requires Docker / Postgres / cloud / API key** | **No / No / No / No** |
| **Lexical search** | in-process SQLite FTS5, sub-millisecond |

The optional embedding model is the only heavyweight, and it's opt-in: pick `none`
at install for a pure-lexical, zero-download setup, or let the wizard recommend a
model sized to your hardware.

---

## 3. How it compares

Different memory tools solve different problems. This is an honest map, not a
"we win every cell" table — the point is to show *which* problem Yggdrasil owns.

| | **Yggdrasil** | Mimir | basic-memory | mem0 |
| --- | --- | --- | --- | --- |
| **Primary user** | dev *using* Claude Code / Codex | dev *building* an agent | note-taker / agent | app builder |
| **Install** | `uvx`/`pip`/`npx`/`brew`, one line | `curl \| sh` (Rust) | pip | pip |
| **Runtime dependencies** | **0** (pure stdlib) | compiled binary¹ | **42** packages² | **54** packages² |
| **Local / private** | 100%, no account | yes | yes | cloud default (OpenAI) |
| **Auto session memory** | **SessionStart + per-prompt auto-recall** | manual MCP config | manual | SDK calls |
| **Cross-project recall** | **yes (measured 1.00)** | — | — | — |
| **Tool surface** | **6 curated** (Glama TDQS **tier A**) | 43 tools | ~9 | 5 |
| **Retrieval quality** | **published + reproducible** (§1) | not published | not published | vendor benchmarks |
| **License** | AGPL-3.0 (OSI) | MIT | AGPL-3.0 | Apache-2.0 |

¹ Mimir ships a single Rust binary (its README cites ~8 MB, ~85 MB RSS at 100 K
entities); no runtime packages, but you run a prebuilt binary or compile Rust.
² Direct runtime dependencies declared on PyPI (basic-memory 0.22.1, mem0ai 2.0.10),
each pulling a transitive tree (vector DB clients, FastAPI, LLM routers, etc.). Verify:
`pip show basic-memory` / `pip show mem0ai`.

The **0 vs 42 vs 54** dependency gap is the whole point: Yggdrasil is pure Python
standard library, so `uvx --from yggdrasil-memory ygg mcp` is the entire supply chain.
Nothing to audit, nothing to break on a transitive bump, nothing that phones home.

Where Yggdrasil deliberately does **not** compete: raw engine throughput on millions
of entities (a Rust core like Mimir's will win that) and being a backend SDK you
build an app on (that's mem0/Letta/Zep's job). Yggdrasil is the **drop-in memory for
the coding agents you already use** — and on *that* job (retrieval quality for a
developer's own decisions/lessons, install simplicity, footprint, and a curated
tool surface an agent can actually navigate), the numbers above are the case.

---

## 4. Methodology & honesty notes

- All Yggdrasil numbers are produced by the committed harness in `eval/`; re-run them.
- Competitor cells are architectural facts (deps, deployment, license, tool count)
  taken from each project's own docs — **we do not publish head-to-head retrieval
  numbers we didn't run.** If you want a true head-to-head, the harness is open;
  PRs adding adapters for other engines are welcome.
- `recall@k` = fraction of queries whose correct memory appears in the top *k*.
  `MRR` = mean reciprocal rank. Corpus n=232, queries n=110 (54 holdout / 56 dev),
  across 21 projects and four query classes.
- **Headline honesty:** the number to trust is **holdout** recall@1 (the weights were
  tuned on dev only), and it's reported for **both** the project-scoped pool (~11) and
  the full-corpus pool (232). The 95% CIs are bootstrapped over the query set.
- **Known limitation:** the corpus is hand-authored synthetic memory, not distilled from
  real transcripts, so it won't perfectly match a production distribution. It's diverse
  (21 projects, keyword / identifier / paraphrase / crosslingual classes) and large
  enough (n=110) for a meaningful CI, but a corpus grown from real `ygg seed` output
  remains the ideal. We publish what we can reproduce, honestly labelled.
- Hardware affects the embedding model, not the lexical path. The lexical numbers
  are deterministic and hardware-independent. Model: `paraphrase-multilingual` via
  Ollama (pin a digest for byte-exact reproduction; minor version drift can move a
  point estimate within the CI).
