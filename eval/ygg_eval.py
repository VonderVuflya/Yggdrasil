#!/usr/bin/env python3
"""Retrieval-quality eval for the Yggdrasil engine (NOT a code unit test).

Measures how good the memory ENGINE is at retrieving the right memory for a
query — the behavioural metric we optimise. Seeds a fixed, realistic corpus into
an in-process MemoryStore (temp DB, deterministic, no network) and scores a
labelled set of queries with recall@1, recall@3 and MRR, broken down by query
class:

  - keyword     : query shares words with the target (lexical should handle)
  - identifier  : target uses code identifiers (scrollWidth, useEffect) the
                  query spells as separate words (motivates identifier split)
  - paraphrase  : query shares MEANING but few/no words (motivates dense search)
  - crosslingual: English query, Russian-content target (needs a multilingual model)

Every case carries a **split**: "dev" (used to tune ranking params) or "holdout"
(kept untouched for final, unbiased validation). Pass `splits={"dev"}` to
`evaluate()` to score only the tuning set; the self-tuning loop optimises on dev
and reports on holdout so it cannot overfit the metric.

Run:  python3 eval/ygg_eval.py            # all splits
      YGG_EMBED_MODEL=paraphrase-multilingual python3 eval/ygg_eval.py   # dense
Exit code is 0 always; this is a measurement, not a pass/fail gate.
"""

from __future__ import annotations

import json
import os
import random
import statistics
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
from ygg_memory_server import MemoryStore  # noqa: E402
from ygg_embeddings import get_embedder  # noqa: E402

NS = "yggdrasil-eval"
USER = "eval-user"


def bootstrap_ci(hits: list[int], n_resamples: int = 5000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float]:
    """95% bootstrap confidence interval for the mean of 0/1 hits. Honest about
    small n — with 15 holdout cases the interval is wide, and it should be."""
    if not hits:
        return (0.0, 0.0)
    rng = random.Random(seed)
    k = len(hits)
    means = sorted(sum(hits[rng.randrange(k)] for _ in range(k)) / k for _ in range(n_resamples))
    lo = means[int((alpha / 2) * n_resamples)]
    hi = means[min(int((1 - alpha / 2) * n_resamples), n_resamples - 1)]
    return (round(lo, 3), round(hi, 3))

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
    ("W5", "webapp", "debugging_lesson",
     "getBoundingClientRect returns zero height inside a display none parent; measure after the element is visible."),
    ("W6", "webapp", "debugging_lesson",
     "querySelectorAll returns a static NodeList, not an array; convert with Array.from before calling map."),
    ("W7", "webapp", "debugging_lesson",
     "Stale closure inside setInterval captures the initial value; read from a ref or use the functional "
     "updater form of setState instead."),
    ("W8", "webapp", "decision",
     "Initial bundle was huge; adopt code-splitting with React.lazy and Suspense to load routes on demand."),
    ("W9", "webapp", "debugging_lesson",
     "useMemo recomputes every render because the dependency object is recreated; memoize the dependency too."),
    ("P1", "payments", "debugging_lesson",
     "Recurring subscription charge fails with an insufficient-funds decline code; retry after three days per the dunning schedule."),
    ("P2", "payments", "debugging_lesson",
     "Payment webhook returns 401 because the signing secret was rotated; update the environment variable and redeploy."),
    ("P3", "payments", "decision",
     "Refund idempotency: always pass an idempotency key, otherwise a retried request issues duplicate refunds."),
    ("P4", "payments", "debugging_lesson",
     "Stripe webhook events arrive out of order; treat handlers as idempotent and reconcile by the event created timestamp."),
    ("P5", "payments", "decision",
     "Store monetary amounts in integer minor units (cents); floating point causes rounding drift when summing totals."),
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
    ("O5", "ops", "debugging_lesson",
     "Kubernetes pod was OOMKilled because the container memory limit sat below the JVM heap; set -Xmx under the limit."),
    ("O6", "ops", "debugging_lesson",
     "TLS handshake fails after certificate renewal because the intermediate chain was missing; bundle the full chain in the pem."),
    ("O7", "ops", "command",
     "Mirror a directory with rsync using --archive and --delete, and preview first with --dry-run."),
    ("A1", "auth", "debugging_lesson",
     "JWT validation fails intermittently due to clock skew between services; allow a small leeway when checking the exp claim."),
    ("A2", "auth", "debugging_lesson",
     "OAuth redirect loop because the registered callback URL had a trailing-slash mismatch; register the exact redirect URI."),
    ("A3", "auth", "decision",
     "Rotate refresh tokens on every use and revoke the whole family on reuse detection to limit token-theft blast radius."),
    ("D1", "data", "debugging_lesson",
     "Pandas merge silently drops rows because the join keys had mismatched dtypes; cast both columns to the same type first."),
    ("D2", "data", "debugging_lesson",
     "Slow query from a missing index on the foreign key; add a composite index matching the WHERE and ORDER BY clauses."),
    ("M1", "mobile", "debugging_lesson",
     "iOS keyboard covers the text input because the view does not inset for the safe area; observe the keyboard frame and pad the bottom."),
    ("M2", "mobile", "debugging_lesson",
     "Android release build crashes because ProGuard stripped a reflection-only class; add a keep rule for it."),
    # Russian-language memories (synthetic): real memory is often bilingual.
    ("RU1", "ru", "debugging_lesson",
     "Локальный сервер разработки случайно подключается к боевой базе данных вместо тестовой; "
     "проверяйте переменные окружения перед запуском."),
    ("RU2", "ru", "debugging_lesson",
     "Платёж по подписке отклонён из-за недостатка средств на карте; "
     "повторить попытку через несколько дней по расписанию."),
    ("RU3", "ru", "debugging_lesson",
     "Сборка докер-образа каждый раз пересобирается с нуля, потому что зависимости копируются после исходников; "
     "сначала копируйте файл блокировки зависимостей."),
    ("RU4", "ru", "debugging_lesson",
     "Утечка памяти из-за незакрытых соединений с базой данных; используйте контекстный менеджер или пул с авто-возвратом соединений."),
    ("RU5", "ru", "decision",
     "Храните денежные суммы в целых копейках; числа с плавающей точкой дают ошибки округления при суммировании."),
    # English lexical distractors: share keywords with a crosslingual query's
    # words but are a different topic — expose lexical dominance over a better
    # vector hit.
    ("RUD", "ru", "note",
     "Set the production build flag to minify and fingerprint assets before the release."),
    ("DD1", "data", "note",
     "Document the database backup retention policy and the restore runbook for the on-call rotation."),
]

# --- labelled queries: (query, expected_label, project, klass, split) -----
# identifier/paraphrase queries are deliberately ISOLATED: their only signal is
# the camelCase identifier (spelled as words) or the meaning — they share no
# other content words with the target, so they expose the real weakness.
CASES = [
    # keyword — lexical should already handle these
    ("recurring charge insufficient funds retry", "P1", "payments", "keyword", "dev"),
    ("gpu pod venv numpy broken after base image upgrade", "O1", "ops", "keyword", "dev"),
    ("docker build cache miss copy lockfile first", "O3", "ops", "keyword", "holdout"),
    ("webhook 401 signing secret rotated redeploy", "P2", "payments", "keyword", "dev"),
    ("preload hero image fetchpriority", "W4", "webapp", "keyword", "holdout"),
    ("postgres connection pool exhausted pgbouncer", "O2", "ops", "keyword", "dev"),
    ("kubernetes pod oomkilled memory limit jvm heap", "O5", "ops", "keyword", "dev"),
    ("tls handshake fails intermediate chain certificate", "O6", "ops", "keyword", "holdout"),
    ("jwt validation clock skew leeway exp claim", "A1", "auth", "keyword", "dev"),
    ("oauth redirect loop callback url trailing slash", "A2", "auth", "keyword", "holdout"),
    ("pandas merge drops rows mismatched dtypes", "D1", "data", "keyword", "dev"),
    ("stripe webhook events out of order idempotent", "P4", "payments", "keyword", "holdout"),
    ("ios keyboard covers text input safe area", "M1", "mobile", "keyword", "dev"),
    ("android release proguard stripped reflection keep rule", "M2", "mobile", "keyword", "holdout"),
    ("missing index foreign key slow query composite", "D2", "data", "keyword", "dev"),
    # identifier — ONLY the camelCase identifier (as words) overlaps the target
    ("scroll width and client width", "W1", "webapp", "identifier", "dev"),
    ("use effect and use callback", "W2", "webapp", "identifier", "holdout"),
    ("get bounding client rect", "W5", "webapp", "identifier", "dev"),
    ("fetch priority", "W4", "webapp", "identifier", "holdout"),
    ("query selector all", "W6", "webapp", "identifier", "dev"),
    ("set interval and set state", "W7", "webapp", "identifier", "holdout"),
    ("use memo", "W9", "webapp", "identifier", "dev"),
    # paraphrase — shares meaning, not words (the dense ceiling)
    ("the page is too wide on small phones", "W1", "webapp", "paraphrase", "dev"),
    ("client got billed two times on a repeated call", "P3", "payments", "paraphrase", "holdout"),
    ("too many open database links during traffic spikes", "O2", "ops", "paraphrase", "dev"),
    ("a service keeps getting killed for using too much memory", "O5", "ops", "paraphrase", "holdout"),
    ("logins are randomly rejected when server clocks disagree", "A1", "auth", "paraphrase", "dev"),
    ("totals are slightly off because of decimal rounding", "P5", "payments", "paraphrase", "holdout"),
    ("rows disappear after combining two datasets", "D1", "data", "paraphrase", "dev"),
    ("the first download is huge so split it into pieces", "W8", "webapp", "paraphrase", "holdout"),
    # crosslingual — English query, Russian-content target (needs a multilingual model)
    ("dev server accidentally connects to the production database", "RU1", "ru", "crosslingual", "dev"),
    ("subscription payment was declined due to insufficient funds", "RU2", "ru", "crosslingual", "holdout"),
    ("docker image rebuilds from scratch every time", "RU3", "ru", "crosslingual", "dev"),
    ("memory leak from database connections that are never closed", "RU4", "ru", "crosslingual", "holdout"),
    ("store money as whole cents to avoid rounding errors", "RU5", "ru", "crosslingual", "dev"),
]


# Cross-project recall: query the FULL corpus (no project filter) and expect the
# right memory to surface regardless of which project it lives in — the
# "have I solved this anywhere before?" path.
CROSS_PROJECT_CASES = [
    ("horizontal overflow on a narrow phone screen", "W1"),
    ("retry a declined recurring subscription charge", "P1"),
    ("docker layer cache keeps invalidating on every build", "O3"),
    ("dev environment pointing at the production database", "RU1"),
    ("container killed for exceeding its memory limit", "O5"),
    ("token check fails when clocks are out of sync", "A1"),
]

# Expanded 200+ corpus for a statistically meaningful benchmark (docs/TODO #26).
# Overrides the compact inline set above; set YGG_EVAL_SMALL=1 to fall back to it
# for a quick check. corpus_large.py lives next to this file.
if not os.environ.get("YGG_EVAL_SMALL"):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from corpus_large import CORPUS, CASES, CROSS_PROJECT_CASES  # noqa: E402,F811


def seed(store: MemoryStore, verbose: bool = False) -> dict[str, str]:
    label_to_id: dict[str, str] = {}
    total = len(CORPUS)
    for i, (label, project, mtype, content) in enumerate(CORPUS, 1):
        rec = store.add(
            content=content, user_id=USER, namespace=NS, scope="project",
            metadata={"project": project, "scope": "project", "type": mtype, "source": "eval"},
        )
        label_to_id[label] = rec["id"]
        if verbose and (i % 25 == 0 or i == total):
            # heartbeat: embedding over a remote endpoint is network-bound and
            # otherwise silent, so show that it's alive.
            print(f"  seeding + embedding {i}/{total} memories…", flush=True)
    return label_to_id


_UNSET = object()

# How many corpus memories share each project — the candidate pool a
# project-scoped query is actually choosing between. Disclosed in the report so
# a reader knows whether recall@1 means "picked 1 of ~6" or "1 of the whole store".
_POOL = Counter(project for _, project, _, _ in CORPUS)


def evaluate(splits: set[str] | None = None, embedder=_UNSET, project_filter: bool = True,
             store: MemoryStore | None = None, label_to_id: dict[str, str] | None = None) -> dict:
    """Score the labelled queries.

    project_filter=True  -> search WITHIN each query's project (the real
        `ygg search --project P` path; candidate pool = same-project memories).
    project_filter=False -> search the WHOLE corpus (the hard "have I solved this
        anywhere?" path; candidate pool = every memory). The honest upper-bound
        on difficulty; report both so the headline isn't read as harder than it is.

    Pass a pre-seeded `store` + `label_to_id` to reuse one embedded corpus across
    many evaluate() calls — the seed embeddings are the expensive part over a
    remote endpoint, and splits/project_filter don't change what's stored.
    """
    own = store is None
    db_path = None
    if own:
        fd, db_path = tempfile.mkstemp(suffix=".sqlite", prefix="ygg-eval-")
        os.close(fd)
    try:
        if own:
            emb = get_embedder() if embedder is _UNSET else embedder
            store = MemoryStore(db_path, embedder=emb)
            label_to_id = seed(store)
        cases = [c for c in CASES if splits is None or c[4] in splits]
        per_class: dict[str, dict] = {}
        per_split: dict[str, dict] = {}
        details = []
        hits1: list[int] = []          # per-query recall@1, for the bootstrap CI
        rr_sum = 0.0
        r1 = r3 = 0
        pools: list[int] = []
        for query, label, project, klass, split in cases:
            expected = label_to_id[label]
            filters = {"project": project, "scope": "project"} if project_filter else {}
            pools.append(_POOL[project] if project_filter else len(CORPUS))
            results = store.search(query=query, user_id=USER, limit=5, filters=filters, namespaces=[NS])
            ids = [r["id"] for r in results]
            rank = ids.index(expected) + 1 if expected in ids else 0
            hit1 = 1 if rank == 1 else 0
            hit3 = 1 if 0 < rank <= 3 else 0
            rr = 1.0 / rank if rank else 0.0
            r1 += hit1; r3 += hit3; rr_sum += rr
            hits1.append(hit1)
            for bucket, key in ((per_class, klass), (per_split, split)):
                pc = bucket.setdefault(key, {"n": 0, "r1": 0, "r3": 0, "rr": 0.0})
                pc["n"] += 1; pc["r1"] += hit1; pc["r3"] += hit3; pc["rr"] += rr
            details.append({"query": query, "expected": label, "class": klass, "split": split, "rank": rank})
        # cross-project recall@3 over the full corpus (no project filter)
        cp_hits = 0
        for query, label in CROSS_PROJECT_CASES:
            res = store.search(query=query, user_id=USER, limit=3, filters={}, namespaces=[NS])
            if label_to_id[label] in [r["id"] for r in res]:
                cp_hits += 1
        cross_project = round(cp_hits / len(CROSS_PROJECT_CASES), 4) if CROSS_PROJECT_CASES else None

        n = len(cases)

        def _summ(bucket: dict[str, dict]) -> dict:
            return {
                k: {"n": v["n"], "recall@1": round(v["r1"] / v["n"], 4),
                    "recall@3": round(v["r3"] / v["n"], 4), "mrr": round(v["rr"] / v["n"], 4)}
                for k, v in sorted(bucket.items())
            }

        return {
            "cross_project_recall@3": cross_project,
            "n_cases": n,
            "splits": sorted(splits) if splits else "all",
            "project_filter": project_filter,
            "candidate_pool": ({"min": min(pools), "median": statistics.median(pools), "max": max(pools)}
                               if pools else None),
            "recall@1": round(r1 / n, 4) if n else 0.0,
            "recall@1_ci95": bootstrap_ci(hits1),
            "recall@3": round(r3 / n, 4) if n else 0.0,
            "mrr": round(rr_sum / n, 4) if n else 0.0,
            "by_class": _summ(per_class),
            "by_split": _summ(per_split),
            "misses": [d for d in details if d["rank"] != 1],
        }
    finally:
        if own and db_path:
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.remove(db_path + suffix)
                except FileNotFoundError:
                    pass


def _mode_name() -> str:
    return os.environ.get("YGG_EMBED_MODEL") or "lexical"


def honest_report() -> None:
    """Print the credibility-first view: holdout-only headline (the split NOT
    used for tuning), the hard full-corpus number, disclosed pool sizes, and a
    95% CI that's honest about the small corpus."""
    mode = _mode_name()
    print(f"# Yggdrasil retrieval eval — mode: {mode}\n", flush=True)
    # Seed + embed the corpus ONCE, then reuse it for every split × scope — over a
    # remote embedding endpoint the seed is by far the slowest part.
    fd, db_path = tempfile.mkstemp(suffix=".sqlite", prefix="ygg-eval-")
    os.close(fd)
    store = MemoryStore(db_path, embedder=get_embedder())
    label_to_id = seed(store, verbose=True)
    # Guard: if a model was requested but nothing actually got embedded (endpoint
    # unreachable / model not pulled), these numbers are LEXICAL, not dense — say
    # so loudly instead of printing a lexical result under a dense label.
    emb_model = os.environ.get("YGG_EMBED_MODEL")
    if emb_model:
        missing = store.missing_embeddings()
        if missing:
            scope = "ALL" if missing >= len(CORPUS) else str(missing)
            print(f"\n⚠ WARNING: YGG_EMBED_MODEL={emb_model} but {scope} memories have NO embedding — "
                  f"the endpoint returned nothing, so these results are effectively LEXICAL.\n"
                  f"  Fix: on the box run `ollama pull {emb_model}`, and check YGG_EMBED_URL is reachable\n"
                  f"  (test: curl $YGG_EMBED_URL/api/embed -d '{{\"model\":\"{emb_model}\",\"input\":\"hi\"}}').\n",
                  flush=True)
    print(flush=True)
    try:
        for pf, scope_label in ((True, "project-scoped (real `ygg search --project P` path)"),
                                (False, "full-corpus (hard: 1 of the whole store)")):
            print(f"## {scope_label}", flush=True)
            allr = evaluate(project_filter=pf, store=store, label_to_id=label_to_id)
            hold = evaluate(splits={"holdout"}, project_filter=pf, store=store, label_to_id=label_to_id)
            dev = evaluate(splits={"dev"}, project_filter=pf, store=store, label_to_id=label_to_id)
            pool = allr["candidate_pool"]
            print(f"  candidate pool per query: min {pool['min']} · median {pool['median']} · max {pool['max']}")
            for name, r in (("HOLDOUT (untouched by tuning)", hold), ("dev (tuning split)", dev), ("all", allr)):
                lo, hi = r["recall@1_ci95"]
                print(f"  {name:<30} n={r['n_cases']:<3} recall@1={r['recall@1']:.3f} "
                      f"[95% CI {lo:.2f}–{hi:.2f}]  recall@3={r['recall@3']:.3f}  mrr={r['mrr']:.3f}", flush=True)
            # per-class (all splits): shows WHERE dense wins over lexical —
            # paraphrase and crosslingual are the classes that need embeddings.
            print("  by query class (all):")
            for k, v in allr["by_class"].items():
                print(f"    {k:<13} n={v['n']:<3} recall@1={v['recall@1']:.3f}  recall@3={v['recall@3']:.3f}")
            print(flush=True)
        print("Headline should be read as HOLDOUT recall@1 (the split the fusion weights were NOT tuned on).")
    finally:
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(db_path + suffix)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    if "--report" in sys.argv or os.environ.get("YGG_EVAL_REPORT"):
        honest_report()
    else:
        print(json.dumps(evaluate(), indent=2, ensure_ascii=False))
