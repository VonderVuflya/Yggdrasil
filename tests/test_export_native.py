"""Native-memory bridge: rendering + idempotent managed-block upsert in AGENTS.md."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg  # noqa: E402


def _rec(mtype, content, pinned=False, used=0):
    return {"memory": content, "content": content, "access_count": used,
            "metadata": {"type": mtype, "project": "checkout", "pinned": pinned}}


class RenderBlockTest(unittest.TestCase):
    def test_block_groups_by_type_and_marks_pins(self):
        recs = [_rec("decision", "use idempotency keys"),
                _rec("project_status", "payments refactor in progress", pinned=True),
                _rec("lesson", "webhook 401 = rotated secret")]
        block = ygg._render_native_block("checkout", recs)
        self.assertTrue(block.startswith(ygg._YGG_BEGIN))
        self.assertTrue(block.rstrip().endswith(ygg._YGG_END))
        # status heading comes before decisions/lessons (priority order)
        self.assertLess(block.index("Current status"), block.index("Decisions"))
        self.assertIn("📌 payments refactor in progress", block)
        self.assertIn("- use idempotency keys", block)


class UpsertTest(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mktemp(suffix="-AGENTS.md"))

    def tearDown(self):
        if self.path.exists():
            self.path.unlink()

    def test_create_then_idempotent_then_update(self):
        block1 = ygg._render_native_block("checkout", [_rec("lesson", "first lesson")])
        self.assertEqual(ygg._upsert_managed_block(self.path, block1), "created")
        # re-running with the SAME block changes nothing
        self.assertEqual(ygg._upsert_managed_block(self.path, block1), "unchanged")
        # a different block updates in place
        block2 = ygg._render_native_block("checkout", [_rec("lesson", "second lesson")])
        self.assertEqual(ygg._upsert_managed_block(self.path, block2), "updated")
        self.assertIn("second lesson", self.path.read_text())
        self.assertNotIn("first lesson", self.path.read_text())

    def test_preserves_user_content_around_block(self):
        self.path.write_text("# My AGENTS.md\n\nHand-written rules I care about.\n")
        block = ygg._render_native_block("checkout", [_rec("decision", "ship small PRs")])
        ygg._upsert_managed_block(self.path, block)
        text = self.path.read_text()
        self.assertIn("Hand-written rules I care about.", text)   # user content kept
        self.assertIn("ship small PRs", text)                     # block added
        # updating again must NOT duplicate or eat the user's content
        block2 = ygg._render_native_block("checkout", [_rec("decision", "ship small PRs v2")])
        ygg._upsert_managed_block(self.path, block2)
        text2 = self.path.read_text()
        self.assertEqual(text2.count("Hand-written rules I care about."), 1)
        self.assertEqual(text2.count(ygg._YGG_BEGIN), 1)          # exactly one managed block
        self.assertIn("ship small PRs v2", text2)


if __name__ == "__main__":
    unittest.main()
