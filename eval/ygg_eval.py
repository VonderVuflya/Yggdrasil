#!/usr/bin/env python3
"""Retrieval-quality eval for the Yggdrasil engine (NOT a code unit test).

Measures how good the memory ENGINE is at retrieving the right memory for a
query — the behavioural metric we optimise. Seeds a fixed, realistic corpus
into an in-process MemoryStore (temp DB, deterministic, no network) and scores
a labelled set of queries with recall@1, recall@3 and MRR, broken down by
query class:

  - keyword     : query shares words with the target (lexical should handle)
  - identifier  : target uses code identifiers (scrollWidth, useEffect) the
                  query spells as separate words (motivates identifier split)
  - paraphrase  : query shares MEANING but few/no words (motivates dense search)

Run:  python3 eval/ygg_eval.py
Exit code is 0 always; this is a measurement, not a pass/fail gate.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ygg_memory_server import MemoryStore  # noqa: E402
from ygg_embeddings import get_embedder  # noqa: E402

NS = "yggdrasil-eval"
USER = "eval-user"

# --- fixed corpus: (label, project, type, content) ------------------------
CORPUS = [
    ("W1", "webapp", "debugging_lesson",
     "Mobile hero overflow: document scrollWidth exceeds clientWidth on a 390px viewport; "
     "constrain the chip row container and let the chips wrap onto multiple lines."),
    ("W2", "webapp", "debugging_lesson",
     "React useEffect infinite render loop caused by an unstable dependency array; "
     "wrap the handler in useCallback so the reference is stable."),
    ("W3", "webapp", "debugging_lesson",
     "Hydration mismatch from rendering a timestamp during SSR; move the dynamic value into useEffect "
     "so it only runs on the client."),
    ("W4", "webapp", "decision",
     "Largest Contentful Paint was slow; preload the hero image and set fetchPriority high to speed first paint."),
    ("P1", "payments", "debugging_lesson",
     "Recurring subscription charge fails with an insufficient-funds decline code; retry after three days per the dunning schedule."),
    ("P2", "payments", "debugging_lesson",
     "Payment webhook returns 401 because the signing secret was rotated; update the environment variable and redeploy."),
    ("P3", "payments", "decision",
     "Refund idempotency: always pass an idempotency key, otherwise a retried request issues duplicate refunds."),
    ("O1", "ops", "debugging_lesson",
     "GPU pod venv corruption after a docker base image upgrade breaks numpy and transformers; "
     "reinstall packages in the persistent venv using the fix script."),
    ("O2", "ops", "debugging_lesson",
     "Postgres connection pool exhausted under load; lower per-request connections and put pgbouncer in front."),
    ("O3", "ops", "debugging_lesson",
     "Docker build cache misses on every run because COPY . . precedes dependency install; "
     "copy the lockfile first, install, then copy the rest."),
    ("O4", "ops", "command",
     "To tail service logs use journalctl with the unit name and the follow flag; filter by priority for errors."),
    ("W5", "webapp", "debugging_lesson",
     "getBoundingClientRect returns zero height inside a display none parent; measure after the element is visible."),
]

# --- labelled queries: (query, expected_label, project, klass) ------------
# identifier/paraphrase queries are deliberately ISOLATED: their only signal is
# the camelCase identifier (spelled as words) or the meaning — they share no
# other content words with the target, so they expose the real weakness.
CASES = [
    # keyword — lexical should already handle these
    ("recurring charge insufficient funds retry", "P1", "payments", "keyword"),
    ("gpu pod venv numpy broken after base image upgrade", "O1", "ops", "keyword"),
    ("docker build cache miss copy lockfile first", "O3", "ops", "keyword"),
    ("webhook 401 signing secret rotated redeploy", "P2", "payments", "keyword"),
    ("preload hero image fetchpriority", "W4", "webapp", "keyword"),
    ("postgres connection pool exhausted pgbouncer", "O2", "ops", "keyword"),
    # identifier — ONLY the camelCase identifier (as words) overlaps the target
    ("scroll width and client width", "W1", "webapp", "identifier"),
    ("use effect and use callback", "W2", "webapp", "identifier"),
    ("get bounding client rect", "W5", "webapp", "identifier"),
    ("fetch priority", "W4", "webapp", "identifier"),
    # paraphrase — shares meaning, not words (the dense ceiling)
    ("the page is too wide on small phones", "W1", "webapp", "paraphrase"),
    ("client got billed two times on a repeated call", "P3", "payments", "paraphrase"),
    ("too many open database links during traffic spikes", "O2", "ops", "paraphrase"),
]


def seed(store: MemoryStore) -> dict[str, str]:
    label_to_id: dict[str, str] = {}
    for label, project, mtype, content in CORPUS:
        rec = store.add(
            content=content, user_id=USER, namespace=NS, scope="project",
            metadata={"project": project, "scope": "project", "type": mtype, "source": "eval"},
        )
        label_to_id[label] = rec["id"]
    return label_to_id


def evaluate() -> dict:
    fd, db_path = tempfile.mkstemp(suffix=".sqlite", prefix="ygg-eval-")
    os.close(fd)
    try:
        store = MemoryStore(db_path, embedder=get_embedder())
        label_to_id = seed(store)
        per_class: dict[str, dict] = {}
        details = []
        rr_sum = 0.0
        r1 = r3 = 0
        for query, label, project, klass in CASES:
            expected = label_to_id[label]
            results = store.search(query=query, user_id=USER, limit=5,
                                   filters={"project": project, "scope": "project"}, namespaces=[NS])
            ids = [r["id"] for r in results]
            rank = ids.index(expected) + 1 if expected in ids else 0
            hit1 = 1 if rank == 1 else 0
            hit3 = 1 if 0 < rank <= 3 else 0
            rr = 1.0 / rank if rank else 0.0
            r1 += hit1; r3 += hit3; rr_sum += rr
            pc = per_class.setdefault(klass, {"n": 0, "r1": 0, "r3": 0, "rr": 0.0})
            pc["n"] += 1; pc["r1"] += hit1; pc["r3"] += hit3; pc["rr"] += rr
            details.append({"query": query, "expected": label, "class": klass, "rank": rank})
        n = len(CASES)
        metrics = {
            "n_cases": n,
            "recall@1": round(r1 / n, 4),
            "recall@3": round(r3 / n, 4),
            "mrr": round(rr_sum / n, 4),
            "by_class": {
                k: {"n": v["n"], "recall@1": round(v["r1"] / v["n"], 4),
                    "recall@3": round(v["r3"] / v["n"], 4), "mrr": round(v["rr"] / v["n"], 4)}
                for k, v in sorted(per_class.items())
            },
            "misses": [d for d in details if d["rank"] != 1],
        }
        return metrics
    finally:
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(db_path + suffix)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2, ensure_ascii=False))
