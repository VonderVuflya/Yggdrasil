# Yggdrasil — Benchmarks

Honest, reproducible numbers. Everything here you can run yourself in minutes — the
whole point is that you don't have to trust us. Measured on 2026-06-29, Yggdrasil
v0.5.4.

> TL;DR — Yggdrasil retrieves the right memory **recall@1 = 0.94 / recall@3 = 1.00 /
> MRR = 0.97** with an optional local model (0.77 with **zero** dependencies and no
> model at all), in a **132 KB** install with **~21 MB** RAM and **no Docker, no
> database server, no cloud, no API key**.

---

## 1. Retrieval quality (the metric that actually matters)

A memory tool is only as good as its ability to surface the *right* memory for a
query. We measure that on a fixed, realistic corpus of 35 software-engineering
memories (web / payments / ops) against a labelled query set, split into four
classes and a dev/holdout split so the ranking params can't overfit the metric.

| Query class | what it stresses | Lexical (zero-dep) | + local model |
| --- | --- | :---: | :---: |
| **keyword** | shares words with the target | 1.00 | 1.00 |
| **identifier** | `scrollWidth`, `useEffect` spelled as words | 1.00 | 1.00 |
| **paraphrase** | same meaning, few shared words | 0.63 | 0.88 |
| **crosslingual** | English query → Russian memory | 0.00 | 0.80 |
| **cross-project recall@3** | "solved this in another project?" | 0.83 | **1.00** |
| **Overall recall@1** | | **0.77** | **0.94** |
| **Overall recall@3** | | 0.77 | **1.00** |
| **Overall MRR** | | 0.77 | **0.97** |

Two honest takeaways:

- **Out of the box, with zero dependencies and no model, Yggdrasil already gets
  recall@1 = 0.77** — keyword and code-identifier queries are essentially solved
  (1.00) by SQLite FTS5 alone. That's the default everyone gets, instantly, with no
  download.
- The optional local embedding model (via [Ollama](https://ollama.com),
  `paraphrase-multilingual`) is what unlocks **meaning** and **cross-language** recall:
  paraphrase 0.63 → 0.88, crosslingual 0.00 → 0.80, and **cross-project recall hits
  1.00**. It runs entirely on your machine — still no cloud, no API key.

**Reproduce it (≈1 min, no setup):**

```bash
python3 eval/ygg_eval.py                                   # lexical, zero-dep
YGG_EMBED_MODEL=paraphrase-multilingual python3 eval/ygg_eval.py   # + local model
```

The corpus, queries, labels and scoring live in [`eval/ygg_eval.py`](eval/ygg_eval.py).
Nothing is hidden; change the corpus, add your own queries, re-run.

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

| | **Yggdrasil** | Mimir | mem0 | Letta / Zep |
| --- | --- | --- | --- | --- |
| **Primary user** | dev *using* Claude Code / Codex | dev *building* an agent | app builder | app builder |
| **Install** | `uvx`/`pip`/`npx`/`brew`, one line | Rust binary (`curl \| sh`) | pip + vector DB | Docker + Postgres |
| **Runtime deps** | **zero (stdlib)** | single binary | Python + vector DB | Postgres + runtime |
| **Local / private** | 100%, no account | yes | cloud default | Docker needed |
| **Auto session memory** | **SessionStart + per-prompt auto-recall** | manual MCP config | SDK calls | SDK calls |
| **Cross-project recall** | **yes (measured 1.00)** | — | — | — |
| **Tool surface** | **6 curated** (Glama TDQS **tier A**) | 43 tools | 5 | 8 / 0 |
| **Retrieval quality** | **published + reproducible** (above) | not published | vendor benchmarks | vendor benchmarks |
| **License** | AGPL-3.0 (OSI) | MIT | Apache-2.0 | Apache-2.0 |

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
  `MRR` = mean reciprocal rank. Corpus n=35, queries n=35, dev/holdout split.
- Hardware affects the embedding model, not the lexical path. The lexical numbers
  are deterministic and hardware-independent.
