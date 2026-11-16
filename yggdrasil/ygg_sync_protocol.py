#!/usr/bin/env python3
"""Wire format and reconcile planning for the peer uplink.

Pure module: dictionaries in, dictionaries out, no sockets and no database. It
exists so the expensive question — "what actually differs between two stores?"
— is answered by comparing fingerprints instead of shipping records.

Digest shape (one JSON object, the whole store):

    {"proto": 1, "node": "<node id>",
     "memories":   {"<memory id>": ["<state hash>", <updated_at>], ...},
     "tombstones": {"<memory id>": <deleted_at>, ...}}

That is roughly 40 bytes per memory, so a 10k store fingerprints in ~400 KB and
a LAN round trip costs milliseconds. There is deliberately NO `since` parameter:
an incremental digest keyed on time would silently drop changes whenever two
machines' clocks disagree, and repairing exactly that kind of hole is the entire
job of reconcile.

`updated_at` rides along for merge tie-breaks but is never compared — see
state_hash().
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

# Bumped only for incompatible changes. Nodes exchange it in /sync/hello and
# refuse to sync rather than corrupt each other with a half-understood payload.
PROTOCOL_VERSION = 1

# Everything that defines a memory's synced state. Deliberately excludes
# access_count, last_accessed_at, embedding_blob and embed_model: those are
# per-machine, and including them would make merely *reading* a memory here look
# like an edit over there.
STATE_FIELDS = ("id", "user_id", "namespace", "scope", "project", "type",
                "source", "confidence", "importance", "archived", "metadata_json")


def state_hash(record: dict[str, Any]) -> str:
    """Fingerprint of a memory's synced state.

    `updated_at` is NOT part of it. If it were, two nodes that imported the same
    record at different moments would look divergent forever and re-fetch it on
    every reconcile. Content enters through content_hash, falling back to the
    text itself for rows written before content_hash was backfilled.
    """
    body = {k: record.get(k) for k in STATE_FIELDS}
    digest = record.get("content_hash")
    if not digest:
        digest = hashlib.sha256((record.get("content") or "").encode("utf-8")).hexdigest()
    body["content_hash"] = digest
    body["archived"] = 1 if record.get("archived") else 0
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_digest(records: list[dict[str, Any]], tombstones: dict[str, float],
                 *, node_id: str) -> dict[str, Any]:
    return {
        "proto": PROTOCOL_VERSION,
        "node": node_id,
        "memories": {r["id"]: [state_hash(r), r.get("updated_at") or r.get("created_at") or 0.0]
                     for r in records if r.get("id")},
        "tombstones": {str(k): float(v) for k, v in (tombstones or {}).items()},
    }


def compatible(remote_proto: Any) -> bool:
    return remote_proto == PROTOCOL_VERSION


@dataclass
class Plan:
    """What this node must do to converge with the peer it just fingerprinted."""

    fetch: list[str] = field(default_factory=list)            # pull their body, then merge
    push: list[str] = field(default_factory=list)             # they have never seen ours
    delete_local: list[str] = field(default_factory=list)     # they deleted it; so do we
    push_tombstones: list[str] = field(default_factory=list)  # we deleted it; tell them

    def __bool__(self) -> bool:
        return bool(self.fetch or self.push or self.delete_local or self.push_tombstones)

    def summary(self) -> str:
        return (f"fetch {len(self.fetch)} · push {len(self.push)} · "
                f"delete {len(self.delete_local)} · tombstones {len(self.push_tombstones)}")


def plan(local: dict[str, Any], remote: dict[str, Any]) -> Plan:
    """Diff two digests from the LOCAL node's point of view.

    Divergent records are fetched, not pushed: we pull their version, merge, and
    send the merged result. Pushing our pre-merge copy would only make the peer
    redo the identical merge and push it back.
    """
    lm: dict[str, Any] = local.get("memories") or {}
    rm: dict[str, Any] = remote.get("memories") or {}
    lt: dict[str, Any] = local.get("tombstones") or {}
    rt: dict[str, Any] = remote.get("tombstones") or {}
    out = Plan()

    for mid, entry in sorted(rm.items()):
        if mid in lt:
            # We deleted it. Do not pull it back in the same breath as we tell
            # them about the deletion.
            continue
        mine = lm.get(mid)
        if mine is None or mine[0] != entry[0]:
            out.fetch.append(mid)

    for mid, entry in sorted(lm.items()):
        if mid in rt:
            out.delete_local.append(mid)
        elif mid not in rm:
            out.push.append(mid)

    out.push_tombstones = sorted(set(lt) - set(rt))
    return out
