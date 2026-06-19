#!/usr/bin/env python3
"""Self-tuning for Yggdrasil retrieval ranking (propose-only).

An autoresearch-style loop over the eval metric: sweep the fusion knobs, score
each config on the eval **dev** split, keep the best, then validate the winner
on the untouched **holdout** split. It only PROPOSES env settings — it never
changes defaults. You apply `YGG_FUSION_*` yourself if the gain holds on holdout
(propose-safe, like background consolidation).

Only the lexical:vector ratio is swept (vector weight fixed at 1.0, since in
score-normalized fusion only the ratio changes ranking), plus classic RRF.
Embeddings are cached across configs, so only the first config pays the model
cost — the rest just re-fuse cached vectors.

Run:  YGG_EMBED_MODEL=paraphrase-multilingual python3 eval/ygg_tune.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg_memory_server as engine  # noqa: E402
from ygg_embeddings import get_embedder  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ygg_eval  # noqa: E402


class _CachingEmbedder:
    """Memoize embed(text) so repeated configs reuse vectors (embeddings don't
    depend on fusion weights). Proxies any other attribute to the real embedder."""

    def __init__(self, inner):
        self._inner = inner
        self._cache: dict[str, list[float]] = {}

    def embed(self, text: str):
        vec = self._cache.get(text)
        if vec is None:
            vec = self._inner.embed(text)
            self._cache[text] = vec
        return vec

    def __getattr__(self, name):  # delegate model-name etc.
        return getattr(self._inner, name)


def main() -> int:
    base = get_embedder()
    if base is None:
        print("No embedder available. Tuning needs dense fusion — run with "
              "YGG_EMBED_MODEL=paraphrase-multilingual (Ollama).", file=sys.stderr)
        return 1
    emb = _CachingEmbedder(base)

    # Candidate configs: score-fusion across lexical:vector ratios + classic RRF.
    configs = [("score", w, 1.0) for w in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0, 1.5)]
    configs.append(("rrf", engine.FUSION_W_LEX, engine.FUSION_W_VEC))
    default = ("score", 0.3, 1.0)

    orig = (engine.FUSION_MODE, engine.FUSION_W_LEX, engine.FUSION_W_VEC)
    ranked = []
    try:
        for mode, wl, wv in configs:
            engine.FUSION_MODE, engine.FUSION_W_LEX, engine.FUSION_W_VEC = mode, wl, wv
            dev = ygg_eval.evaluate(splits={"dev"}, embedder=emb)
            ranked.append({"mode": mode, "w_lex": wl, "w_vec": wv,
                           "dev_recall@1": dev["recall@1"], "dev_recall@3": dev["recall@3"],
                           "dev_mrr": dev["mrr"]})
        ranked.sort(key=lambda r: (r["dev_recall@1"], r["dev_mrr"], r["dev_recall@3"]), reverse=True)
        best = ranked[0]

        engine.FUSION_MODE, engine.FUSION_W_LEX, engine.FUSION_W_VEC = best["mode"], best["w_lex"], best["w_vec"]
        best_hold = ygg_eval.evaluate(splits={"holdout"}, embedder=emb)
        engine.FUSION_MODE, engine.FUSION_W_LEX, engine.FUSION_W_VEC = default
        def_dev = ygg_eval.evaluate(splits={"dev"}, embedder=emb)
        def_hold = ygg_eval.evaluate(splits={"holdout"}, embedder=emb)
    finally:
        engine.FUSION_MODE, engine.FUSION_W_LEX, engine.FUSION_W_VEC = orig

    print(json.dumps({
        "configs_ranked_by_dev": ranked,
        "best": best,
        "best_holdout": {"recall@1": best_hold["recall@1"], "recall@3": best_hold["recall@3"]},
        "default": {"mode": default[0], "w_lex": default[1], "w_vec": default[2],
                    "dev_recall@1": def_dev["recall@1"], "holdout_recall@1": def_hold["recall@1"]},
    }, indent=2, ensure_ascii=False))

    best_key = (best["dev_recall@1"], best["dev_mrr"], best["dev_recall@3"])
    def_key = (def_dev["recall@1"], def_dev["mrr"], def_dev["recall@3"])
    is_default = best["mode"] == default[0] and abs(best["w_lex"] - default[1]) < 1e-9
    if is_default or best_key <= def_key:
        print(f"\nDefaults already optimal — no swept config beats them on dev "
              f"(dev recall@1 {def_dev['recall@1']}, mrr {def_dev['mrr']}). Keep current settings.",
              file=sys.stderr)
    elif best_hold["recall@1"] >= def_hold["recall@1"]:
        print(f"\nRECOMMEND (gain holds on holdout): "
              f"YGG_FUSION={best['mode']} YGG_FUSION_W_LEX={best['w_lex']} YGG_FUSION_W_VEC={best['w_vec']}\n"
              f"  dev recall@1 {def_dev['recall@1']} -> {best['dev_recall@1']}; "
              f"holdout recall@1 {def_hold['recall@1']} -> {best_hold['recall@1']}", file=sys.stderr)
    else:
        print(f"\nBest dev config ({best['mode']} w_lex={best['w_lex']}) did NOT hold on holdout "
              f"(overfit) — keep defaults. holdout: default {def_hold['recall@1']} vs best {best_hold['recall@1']}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
