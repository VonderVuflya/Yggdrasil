#!/usr/bin/env python3
"""Seed the demo backend with the test-a / test-b fixtures the quality gate expects.

The quality gate (ygg_quality_gate.py) assumes the backend already contains a
project-scoped `test-a` debugging lesson and an unrelated `test-b` memory. That
seeding used to happen ad-hoc; this script makes it reproducible and
backend-agnostic (it talks the same REST contract, so it works against
ygg_memory_server.py or any compatible engine).

Idempotent: skips a fixture if a non-archived record with the same
project+type+content_hash already exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os

try:
    from .ygg_core import RestMemoryBackend, YggConfig, metadata_of, record_is_archived
    from . import ygg_config as _cfg
except ImportError:  # flat layout (deployed scripts dir / tests / direct run)
    from ygg_core import RestMemoryBackend, YggConfig, metadata_of, record_is_archived
    import ygg_config as _cfg


# test-a: a debugging lesson that must be findable by the gate's bootstrap query
# ("mobile overflow chips") and search ("scrollWidth clientWidth chips overflow").
TEST_A_LESSON = (
    "type: debugging_lesson\n"
    "project: test-a\n"
    "marker: YGG_A_ALPHA\n"
    "problem: Mobile hero causes horizontal overflow on narrow phones\n"
    "symptoms:\n"
    "- page is wider than the viewport on a 390px mobile screen\n"
    "- filter chips overflow past the right edge of the screen\n"
    "- document scrollWidth exceeds clientWidth\n"
    "failed_approaches:\n"
    "- only shrinking text\n"
    "- hiding overflow on the body\n"
    "working_solution:\n"
    "- constrain the chip row container and let chips wrap onto multiple lines\n"
    "- verify with browser viewport measurements and a screenshot\n"
    "recognition_signals:\n"
    "- scrollWidth greater than clientWidth\n"
    "- chip bounding rectangles extend beyond the viewport\n"
)

# test-b: an UNRELATED, non-debugging_lesson memory. Must not contain the
# strings the gate uses to detect cross-project leakage ("debugging_lesson",
# "YGG_A_ALPHA", "test-a").
TEST_B_NOTE = (
    "type: note\n"
    "project: test-b\n"
    "marker: YGG_B_BETA\n"
    "summary: Payment webhook verification rotates the signing secret quarterly.\n"
    "detail: keep the webhook secret in the environment, never in memory.\n"
)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def fixture(project: str, mem_type: str, content: str, namespace: str, user_id: str) -> dict:
    digest = content_hash(content)
    return {
        "content": content,
        "user_id": user_id,
        "namespace": namespace,
        "scope": "project",
        "metadata": {
            "project": project,
            "scope": "project",
            "type": mem_type,
            "source": "ygg-seed-demo",
            "confidence": 0.85,
            "content_hash": digest,
            "skip_extraction": True,
        },
    }


def already_present(records: list[dict], project: str, mem_type: str, digest: str) -> dict | None:
    for record in records:
        meta = metadata_of(record)
        if (
            not record_is_archived(record)
            and meta.get("project") == project
            and meta.get("type") == mem_type
            and meta.get("content_hash") == digest
        ):
            return record
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Yggdrasil demo fixtures (test-a / test-b).")
    # This is the DEMO fixture seeder: it pins the demo identity EXPLICITLY (never
    # inherits the user-facing default) so it stays greppable and immune to the
    # identity migration. It only ever runs against an isolated gate DB.
    parser.add_argument("--namespace", default=_cfg.DEMO_NAMESPACE)
    parser.add_argument("--user-id", default=_cfg.DEMO_USER_ID)
    args = parser.parse_args()

    backend = RestMemoryBackend(YggConfig(
        url=os.environ.get("YGG_ENGINE_URL", "http://127.0.0.1:42069").rstrip("/"),
        token=os.environ.get("YGG_ENGINE_TOKEN") or _cfg.DEMO_TOKEN,
        namespace=args.namespace,
        user_id=args.user_id,
    ))

    existing = backend.get_all(user_id=args.user_id, limit=1000, namespace=args.namespace)
    fixtures = [
        fixture("test-a", "debugging_lesson", TEST_A_LESSON, args.namespace, args.user_id),
        fixture("test-b", "note", TEST_B_NOTE, args.namespace, args.user_id),
    ]

    results = []
    for fx in fixtures:
        meta = fx["metadata"]
        present = already_present(existing, meta["project"], meta["type"], meta["content_hash"])
        if present:
            results.append({"project": meta["project"], "status": "exists", "id": present.get("id")})
            continue
        data = backend.add(fx).get("data", {})
        results.append({"project": meta["project"], "status": "added", "id": data.get("id")})

    print(json.dumps({"namespace": args.namespace, "user_id": args.user_id, "fixtures": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
