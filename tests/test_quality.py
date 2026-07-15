"""Tests for the store quality report (docs/TODO §6): distributions, exact +
near-duplicate detection, cross-project leakage, and truncated-record flagging."""

import os
import shutil
import tempfile
import unittest

from yggdrasil import ygg_memory_server as S


class QualityReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = S.MemoryStore(os.path.join(self.tmp, "m.sqlite"))  # lexical, no embedder

    def tearDown(self):
        self.store._conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ins(self, mid, project, mtype, content, content_hash, blob=None):
        self.store._conn.execute(
            "INSERT INTO memories (id,user_id,namespace,project,type,content,content_hash,"
            "source,confidence,importance,created_at,archived,embedding_blob) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?)",
            (mid, "local", "personal", project, mtype, content, content_hash,
             "seed", 0.6, 0.5, 1.0, blob))

    def test_distributions_and_exact_and_truncated(self):
        self._ins("a", "P1", "fix", "Fixed the parser bug.", "h1")
        self._ins("b", "P1", "fix", "Fixed the parser bug.", "h1")   # exact dup (same hash)
        self._ins("c", "P2", "lesson", "Сделайте следующее:", "h2")   # truncated (trailing colon)
        self.store._conn.commit()
        r = self.store.quality_report(user_id="local")
        self.assertEqual(r["total"], 3)
        self.assertEqual(r["by_type"], {"fix": 2, "lesson": 1})
        self.assertEqual(r["by_project"], {"P1": 2, "P2": 1})
        self.assertEqual(r["exact_duplicate_pairs"], 1)
        self.assertEqual(r["truncated_count"], 1)
        self.assertEqual(r["truncated_ids"], ["c"])

    def test_near_duplicate_and_cross_project_leakage(self):
        near_a = S._vec_to_blob([0.1] * 768)
        near_b = S._vec_to_blob([0.1001] * 768)   # ~identical direction -> cosine ~1
        self._ins("x", "P1", "decision", "Use qwen2.5:3b for RU.", "h3", near_a)
        self._ins("y", "P2", "decision", "Prefer qwen2.5:3b for Russian.", "h4", near_b)
        self.store._conn.commit()
        r = self.store.quality_report(user_id="local", near_dup_threshold=0.95)
        self.assertEqual(r["embedded"], 2)
        self.assertEqual(r["near_duplicate_pairs"], 1)
        self.assertEqual(r["cross_project_leakage_pairs"], 1)   # different projects
        self.assertFalse(r["near_duplicates"][0]["same_project"])

    def test_threshold_excludes_dissimilar(self):
        self._ins("x", "P1", "decision", "a", "h3", S._vec_to_blob([1.0] + [0.0] * 767))
        self._ins("y", "P1", "decision", "b", "h4", S._vec_to_blob([0.0, 1.0] + [0.0] * 766))
        self.store._conn.commit()
        r = self.store.quality_report(user_id="local", near_dup_threshold=0.95)
        self.assertEqual(r["near_duplicate_pairs"], 0)   # orthogonal vectors -> cosine 0


if __name__ == "__main__":
    unittest.main()
