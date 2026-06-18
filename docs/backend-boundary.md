# Yggdrasil Backend Boundary

Yggdrasil is a workflow/governance layer. The durable memory engine sits behind
a small, explicit, testable contract.

- **Default engine:** Yggdrasil's own `yggdrasil/ygg_memory_server.py` (stdlib
  SQLite + FTS5, zero heavy dependencies). Shipped, no external service.
- **Optional engine:** any external engine that satisfies the contract.
  Reached through the same REST client; selected via `YGG_ENGINE_URL`.

The point of the boundary is that nothing in the workflow layer is
engine-specific: the same gates pass against either engine.

## Contract

The engine must support (`MemoryBackend` protocol in `yggdrasil/ygg_core.py`):

- `health`
- `add`
- `search`
- `get_all`
- `update_memory`
- `archive_memory`

`archive_memory` is non-destructive. It must preserve the memory record and set both:

- top-level `archived=true`, when the backend supports it;
- `metadata.status=archived`.

Archive metadata must also include:

- `archived_by`
- `archived_at`
- `archive_reason`
- `canonical_memory_id`
- `review_action_id`

## Adapter

The engine-agnostic REST client and the `MemoryBackend` protocol live in:

```text
yggdrasil/ygg_core.py        # MemoryBackend protocol + RestMemoryBackend (alias: RestMemoryBackend)
yggdrasil/ygg_memory_server.py  # the default engine implementing the contract
```

Review queue, review actions, and the gates use the client instead of building
raw REST requests directly. The default engine satisfies the full contract,
including `metadata_patch` / `archived` on `PUT /update`.

## Capability Failure

If a configured engine does not accept `metadata_patch` or `archived` through
`PUT /update`, Yggdrasil must fail at the adapter boundary with
`BackendCapabilityError`.

Do not silently fall back to delete, direct SQLite mutation, or partial archive
state.

## Optional: external engine backend

Yggdrasil ships its own engine, but the workflow layer is engine-agnostic: any
REST service satisfying the `MemoryBackend` contract is a drop-in. Point
`YGG_ENGINE_URL` at a running instance to use it instead. An external engine
must expose the metadata-update contract — `PUT /update` accepting optional
`metadata_patch` / `archived` (a metadata-only update without re-embedding).
Without it, archive/merge/verify actions raise `BackendCapabilityError` — by
design, not a silent fallback.

