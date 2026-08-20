#!/usr/bin/env python3
"""Conflict resolution — the ONE policy every sync transport shares.

Both `ygg sync` (git repo) and the peer uplink import from here. Two nodes
reconcile independently and never agree on an order, so every rule below has to
be **commutative**: merge(a, b) must equal merge(b, a). Otherwise the machines
don't converge, they take turns overwriting each other and the digests disagree
forever.

That requirement is why this module exists instead of the rules living inline.
It is pure — no I/O, no clock, no database — so the properties are cheap to
test exhaustively (see tests/test_sync_merge.py).

Field rules, in the spirit of archive-never-delete:
  - archived            OR   — an archive decision made anywhere holds everywhere
  - confidence/importance max  — trust the stronger signal
  - content             longer wins (an edit adds information)
  - created_at          min  — the earliest creation is the true one
  - updated_at          max
  - metadata_json       union of keys; `pinned` is OR'd
  - everything else     the value from the more recently updated record

Ties are broken by value, not by side: picking "local" on a tie is exactly the
asymmetry that keeps two machines apart.
"""

from __future__ import annotations

import json
from typing import Any

# How long a deletion keeps blocking the record's return. Long enough to outlive
# a machine that was off for a holiday; not forever, because tombstones are dead
# weight in every digest.
TOMBSTONE_TTL = 90 * 24 * 3600.0

# Fields with no semantic ordering of their own — resolved by recency.
_BY_RECENCY = ("user_id", "namespace", "scope", "project", "type", "source")


def _ts(rec: dict[str, Any]) -> float:
    """Best available 'last touched' stamp. Records written before the
    updated_at migration only carry created_at."""
    for field in ("updated_at", "created_at"):
        value = rec.get(field)
        if value is not None:
            return float(value)
    return 0.0


def _pick(lv: Any, rv: Any, lts: float, rts: float) -> Any:
    """Symmetric choice between two values: newer wins; on an equal stamp the
    larger string form wins. Symmetric because the tie-break looks only at the
    values, never at which argument they arrived in."""
    if lv == rv:
        return lv
    if lts != rts:
        return lv if lts > rts else rv
    return max((lv, rv), key=lambda v: "" if v is None else str(v))


def _loads(raw: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def merge_memory(local: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
    """Deterministic union of two versions of the SAME memory (same id)."""
    lts, rts = _ts(local), _ts(remote)
    merged = dict(remote)
    merged.update({k: v for k, v in local.items() if k not in merged})

    merged["archived"] = 1 if (local.get("archived") or remote.get("archived")) else 0

    for field in ("confidence", "importance"):
        vals = [v for v in (local.get(field), remote.get(field)) if v is not None]
        merged[field] = max(vals) if vals else None

    # Content and its hash move together — a record carrying the other version's
    # hash breaks dedup in both directions.
    lc, rc = local.get("content") or "", remote.get("content") or ""
    if lc == rc:
        merged["content"] = lc
        merged["content_hash"] = _pick(local.get("content_hash"), remote.get("content_hash"), lts, rts)
    else:
        winner = local if (len(lc), lc) > (len(rc), rc) else remote
        merged["content"] = winner.get("content")
        merged["content_hash"] = winner.get("content_hash")

    stamps = [v for v in (local.get("created_at"), remote.get("created_at")) if v is not None]
    if stamps:
        merged["created_at"] = min(stamps)
    merged["updated_at"] = max(lts, rts)

    for field in _BY_RECENCY:
        merged[field] = _pick(local.get(field), remote.get(field), lts, rts)

    lmd, rmd = _loads(local.get("metadata_json")), _loads(remote.get("metadata_json"))
    md = dict(rmd)
    for key, lval in lmd.items():
        md[key] = _pick(lval, rmd[key], lts, rts) if key in rmd else lval
    if lmd.get("pinned") or rmd.get("pinned"):
        md["pinned"] = True
    merged["metadata_json"] = json.dumps(md, sort_keys=True)

    return merged


def tombstone_wins(*, deleted_at: float, record: dict[str, Any], now: float) -> bool:
    """Should a live tombstone suppress this record?

    A live one ALWAYS does — deliberately, without comparing deleted_at to the
    record's updated_at. Two machines' clocks drift, and "I deleted the leaked
    token" must hold regardless of what the other box thinks the time is. The
    cost is documented: a delete racing a remote edit discards the edit. Users
    who mean "changed my mind" have `archive`, which merges without losing
    anything.
    """
    del record  # deliberately unused: see docstring
    return (now - float(deleted_at)) < TOMBSTONE_TTL


def expired_tombstones(tombstones: dict[str, float], *, now: float) -> list[str]:
    """Ids whose deletion is old enough to forget. Sorted, so callers (and
    tests) get a stable order."""
    return sorted(mid for mid, deleted_at in tombstones.items()
                  if (now - float(deleted_at)) >= TOMBSTONE_TTL)
