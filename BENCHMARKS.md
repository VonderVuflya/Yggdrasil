# Yggdrasil — Benchmarks

Honest, reproducible numbers. Everything here you can run yourself in minutes — the
whole point is that you don't have to trust us. Retrieval re-measured 2026-07-02
against the current engine (float32-blob vector store); footprint on v0.5.4.

> TL;DR — with an optional local model, Yggdrasil puts the right memory **in the top 3
> every time (recall@3 = 1.00)** and #1 **0.93–0.94 of the time within a project**, the
> path you actually use. Even searching the **entire store** with no project filter it's
> still recall@3 = 1.00 (recall@1 = 0.80). Zero-dep lexical mode alone is recall@1 = 0.77.
> All in a **132 KB** install, **~21 MB** RAM, no Docker / DB server / cloud / API key.

---

## 1. Retrieval quality (the metric that actually matters)

A memory tool is only as good as its ability to surface the *right* memory for a
query. We measure that on a fixed corpus of 35 software-engineering memories against
a 35-query labelled set, split into four query classes and a **dev/holdout** split —
ranking weights are tuned on *dev* only, so **the holdout column is the unbiased
number** (it was never used for tuning).

We report **two views**, because "recall@1" means nothing without the candidate pool:

- **Project-scoped** — search within one project (`ygg search --project P`, the path
  you actually use). Candidate pool: **median 6** same-project memories.
- **Full-corpus** — search the *whole* store, no project filter ("have I solved this
  anywhere?"). Candidate pool: **all 35**. Strictly harder; semantically-similar
  memories in *other* projects become distractors.

`paraphrase-multilingual` model, recall@1 with 95% bootstrap CI (n is small — the CIs
are wide on purpose):

| | holdout (unbiased) | all splits | recall@3 | MRR |
| --- | :---: | :---: | :---: | :---: |
| **Project-scoped** (pool ~6) | **0.93** `[0.80–1.00]` | 0.94 `[0.86–1.00]` | **1.00** | 0.97 |
| **Full-corpus** (pool 35) | 0.80 `[0.60–1.00]` | 0.80 `[0.66–0.91]` | **1.00** | 0.89 |
| **Lexical, zero-dep** (either view) | 0.80 | 0.77 `[0.63–0.91]` | 0.77 | 0.77 |

By query class (all splits, project-scoped), lexical → +local model: **keyword**
1.00 → 1.00, **identifier** 1.00 → 1.00, **paraphrase** 0.63 → 0.88, **crosslingual**
(EN→RU) 0.00 → 0.80.

Honest takeaways:

- **recall@3 = 1.00 in both views** — with the local model, the right memory is *always*
  in the top 3, even against the entire store. recall@1 (is it #1?) is 0.93 within a
  project, 0.80 store-wide.
- **holdout ≈ dev** (0.93 vs 0.95 project-scoped) — the ranking weights don't overfit
  the metric; the tuner (`eval/ygg_tune.py`) explicitly kept defaults when a swept gain
  didn't hold on holdout.
- **Zero-dep lexical already gets 0.77** — keyword and code-identifier queries are solved
  (1.00) by SQLite FTS5 alone, no download. The local model is what adds *meaning* and
  *cross-language*.
- **n = 35 is small** (hence the wide CIs) and the corpus is author-written, not distilled
  from real transcripts — see §4. Take the point estimates as directional, the *shape*
  (recall@3 saturates, holdout ≈ dev, lexical solves keyword/identifier) as the finding.

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
  `MRR` = mean reciprocal rank. Corpus n=35, queries n=35, 20 dev / 15 holdout.
- **Headline honesty:** the number to trust is **holdout** recall@1 (the weights were
  tuned on dev only), and it's reported for **both** the project-scoped pool (~6) and
  the full-corpus pool (35). The 95% CIs are bootstrapped over the query set and are
  wide because n is small — we show them rather than hide behind a point estimate.
- **Known limitation:** the corpus is author-written synthetic memory, not distilled
  from real transcripts, and n=35 is small. A larger corpus (200+) built from real
  `ygg seed` output would tighten the CIs and better reflect production distribution —
  tracked as future work. We publish what we can currently reproduce, honestly labelled.
- Hardware affects the embedding model, not the lexical path. The lexical numbers
  are deterministic and hardware-independent. Model: `paraphrase-multilingual` via
  Ollama (pin a digest for byte-exact reproduction; minor version drift can move a
  point estimate within the CI).
