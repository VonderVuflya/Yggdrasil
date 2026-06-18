from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "yggdrasil"))

from ygg_core import record_is_archived  # noqa: E402
from ygg_review_actions import build_actions  # noqa: E402


class YggCoreTests(unittest.TestCase):
    def test_record_is_archived_checks_top_level_flag(self) -> None:
        self.assertTrue(record_is_archived({"archived": True, "metadata": {}}))

    def test_record_is_archived_checks_metadata_status(self) -> None:
        self.assertTrue(record_is_archived({"metadata": {"status": "archived"}}))

    def test_record_is_archived_allows_active_record(self) -> None:
        self.assertFalse(record_is_archived({"archived": False, "metadata": {"status": "active"}}))

    def test_build_actions_prefers_oldest_exact_duplicate_as_canonical(self) -> None:
        report = {
            "issues": [
                {
                    "kind": "exact_duplicate",
                    "project": "demo",
                    "type": "debugging_lesson",
                    "records": [
                        {"id": "older-record", "created_at": 1},
                        {"id": "newer-record", "created_at": 2},
                    ],
                }
            ]
        }

        actions = build_actions(report)

        self.assertEqual(actions[0]["action"], "keep")
        self.assertEqual(actions[0]["memory_id"], "older-record")
        self.assertEqual(actions[1]["action"], "archive")
        self.assertEqual(actions[1]["memory_id"], "newer-record")
        self.assertEqual(actions[1]["canonical_memory_id"], "older-record")


if __name__ == "__main__":
    unittest.main()
