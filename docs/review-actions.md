# Memory Review Actions

`yggdrasil/ygg_review_actions.py` turns review queue issues into explicit proposed actions.

It creates action proposals, records user-approved decisions, and can apply approved archive actions through an explicit audited flow.

## Generate Proposals

```bash
yggdrasil/ygg_review_actions.py propose --review-report reports/review-queue-1779823862.json
```

Outputs:

- `reports/review-actions-*.json`
- `vault/99-review/memory-review-actions.md`

## Record A Decision

```bash
yggdrasil/ygg_review_actions.py record \
  --action-id archive-3-42285633 \
  --decision approve \
  --reason "Exact duplicate of canonical memory"
```

Decisions append to:

- `reports/review-action-audit.jsonl`

## Apply Approved Archive Actions

Dry-run is the default. It reads the action bundle and audit log, then previews only approved `archive` actions:

```bash
yggdrasil/ygg_review_actions.py apply \
  --actions-report reports/review-actions-1780001070.json \
  --dry-run \
  --user-id dense-user
```

Execute requires an explicit flag:

```bash
yggdrasil/ygg_review_actions.py apply \
  --actions-report reports/review-actions-1780001070.json \
  --execute \
  --user-id dense-user
```

The apply flow:

- only applies actions whose latest audit decision is `approve`;
- only supports `archive`;
- does not delete memories;
- calls the engine `/update` with `metadata_patch` and `archived=true`;
- appends each planned, applied, failed, missing, or already-archived attempt to `reports/review-action-audit.jsonl`.

Archive metadata includes:

```json
{
  "status": "archived",
  "archived_by": "ygg_review_actions",
  "archived_at": "...",
  "archive_reason": "...",
  "canonical_memory_id": "...",
  "review_action_id": "..."
}
```

## Policy

- `keep`: mark a memory as canonical in the human review process.
- `archive`: approved archive action, applied only through explicit `apply --execute`.
- `merge_proposal`: ask a human/agent to draft a consolidated memory.
- `verify_or_archive`: check stale/conflict candidates against repository reality.

The review queue ignores memories already marked archived via either top-level `archived=true` or `metadata.status=archived`.

## Repeatable Gate

```bash
yggdrasil/ygg_review_apply_gate.py
```

This creates an isolated duplicate pair, runs queue/propose/approve/dry-run/execute, and writes `reports/review-apply-gate-*.json`.
