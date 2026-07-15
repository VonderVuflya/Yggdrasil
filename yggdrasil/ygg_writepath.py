#!/usr/bin/env python3
"""Smart write-path: background semantic consolidation using a local LLM.

The lexical review queue only catches exact / same-opening duplicates. This
processor catches SEMANTIC duplicates and contradictions (same lesson in
different words; a corrected version superseding an old one) that lexical rules
miss. For each unprocessed memory it finds the most similar peer (dense search)
and asks a small LOCAL model (Ollama, e.g. qwen2.5:1.5b) to classify the
relationship, then applies only NON-DESTRUCTIVE actions (archive), high-confidence
only — everything else is left for human review. Runs in the background; costs
the main agent zero tokens.

  python3 ygg_writepath.py [--apply] [--limit N]   # dry-run by default (scheduled via `ygg consolidate`)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path

try:
    from .ygg_core import RestMemoryBackend, YggConfig, metadata_of, record_is_archived
    from . import ygg_config as _cfg
except ImportError:  # flat layout (deployed scripts dir / tests / direct run)
    from ygg_core import RestMemoryBackend, YggConfig, metadata_of, record_is_archived
    import ygg_config as _cfg

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
AUDIT = REPORTS / "writepath-audit.jsonl"
# Distillation endpoint — same resolution as `ygg seed` (flag > env > config).
# main() re-resolves with --ollama-url before running.
OLLAMA = _cfg.distill_url()
CONF_THRESHOLD = 0.7
# Only compare genuinely-similar peers (raw cosine). This is the key safety gate:
# a small local model hallucinates a "supersedes" relation when forced to compare
# unrelated notes, so we never even ask unless the vectors are close.
SIM_THRESHOLD = 0.6


def load_bg_model() -> str:
    # bg_model may be unset (default qwen) — but here we want "" if truly unset so
    # the caller can skip; resolve returns the default, so check config/env first.
    if os.environ.get("YGG_BG_MODEL"):
        return os.environ["YGG_BG_MODEL"]
    return _cfg.load().get("bg_model", "")


def classify(bg_model: str, a: str, b: str) -> dict | None:
    """Ask the local model how note A relates to note B. Returns parsed JSON."""
    prompt = (
        "You compare two short engineering memory notes and classify their relationship.\n"
        f"NOTE A:\n{a[:800]}\n\nNOTE B:\n{b[:800]}\n\n"
        "Reply with ONLY a JSON object: "
        '{"relation": "<R>", "confidence": <0..1>, "reason": "<short>"}\n'
        "R is one of: DUPLICATE (same lesson/fact, just different wording), "
        "SUPERSEDES_A (A is a newer/corrected version that makes B obsolete), "
        "SUPERSEDES_B (B makes A obsolete), RELATED (same topic, distinct content), "
        "UNRELATED (different topics)."
    )
    body = json.dumps({
        "model": bg_model,
        "messages": [{"role": "user", "content": prompt}],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0},
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA + "/api/chat", data=body,
                                headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            content = json.loads(resp.read())["message"]["content"]
        out = json.loads(content)
        if isinstance(out, dict) and "relation" in out:
            return out
    except Exception:
        return None
    return None


def audit(entry: dict) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    entry["at"] = dt.datetime.now(tz=dt.timezone.utc).isoformat()
    with AUDIT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Background semantic write-path consolidation.")
    parser.add_argument("--user-id", default=_cfg.user_id())
    parser.add_argument("--namespace", default=_cfg.namespace())
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--apply", action="store_true", help="Apply archives. Default: dry-run.")
    parser.add_argument("--ollama-url", default="", dest="ollama_url",
                        help="Ollama endpoint for the classifier (default: config distill_url, else local)")
    parser.add_argument("--model", default="", help="classifier model (default: config bg_model)")
    args = parser.parse_args()

    global OLLAMA
    OLLAMA = _cfg.distill_url(args.ollama_url or None)
    bg_model = args.model or load_bg_model()
    if not bg_model:
        print(json.dumps({"status": "skipped", "reason": "no bg_model configured"}))
        return 0

    backend = RestMemoryBackend(YggConfig.from_env())
    records = backend.get_all(user_id=args.user_id, limit=args.limit, namespace=args.namespace)
    active = {r["id"]: r for r in records if not record_is_archived(r)}
    archived_now: set[str] = set()
    results = []

    for mid, rec in list(active.items()):
        if mid in archived_now or metadata_of(rec).get("writepath_seen"):
            continue
        content = rec.get("memory") or rec.get("content") or ""
        project = metadata_of(rec).get("project")
        # most similar peer in the same project (dense search via the engine)
        hits = backend.search({
            "query": content, "user_id": args.user_id, "limit": 4,
            "filters": {"project": project, "scope": "project"}, "namespaces": [args.namespace],
        }).get("data", [])
        peer = next((h for h in hits if h["id"] != mid and h["id"] in active
                     and h["id"] not in archived_now
                     and (h.get("vector_score") or 0) >= SIM_THRESHOLD), None)

        # mark processed in both modes so scheduled runs are idempotent (only
        # new memories are re-evaluated next time)
        backend.update_memory(mid, metadata_patch={"writepath_seen": True})

        if not peer:
            continue
        verdict = classify(bg_model, content, peer.get("memory") or "")
        if not verdict:
            continue
        rel, conf = verdict.get("relation"), float(verdict.get("confidence") or 0)
        entry = {"memory_id": mid, "peer_id": peer["id"], "relation": rel,
                 "confidence": conf, "reason": verdict.get("reason", ""), "project": project,
                 "mode": "apply" if args.apply else "dry-run"}

        # decide which (if any) to archive — non-destructive, high-confidence only
        victim = None
        if conf >= CONF_THRESHOLD:
            if rel == "DUPLICATE":
                # keep the older (canonical); archive the newer
                victim, keep = ((mid, peer["id"]) if (rec.get("created_at") or 0) >= (peer.get("created_at") or 0)
                                else (peer["id"], mid))
                patch = {"status": "archived", "merged_into": keep, "archived_by": "ygg_writepath",
                         "writepath_relation": "DUPLICATE", "writepath_seen": True}
            elif rel == "SUPERSEDES_A":   # A=mid supersedes B=peer -> archive peer
                victim, patch = peer["id"], {"status": "archived", "superseded_by": mid,
                                             "archived_by": "ygg_writepath", "writepath_relation": "SUPERSEDED", "writepath_seen": True}
            elif rel == "SUPERSEDES_B":   # B=peer supersedes A=mid -> archive mid
                victim, patch = mid, {"status": "archived", "superseded_by": peer["id"],
                                      "archived_by": "ygg_writepath", "writepath_relation": "SUPERSEDED", "writepath_seen": True}
        entry["action"] = f"archive {victim}" if victim else "none (low-confidence or RELATED/UNRELATED)"
        if victim and args.apply:
            backend.archive_memory(victim, patch)
            archived_now.add(victim)
        audit(entry)
        results.append(entry)

    summary = {"status": "ok", "mode": "apply" if args.apply else "dry-run",
               "processed": len(active), "actions": [r for r in results if r.get("action", "").startswith("archive")],
               "archived": len(archived_now)}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
