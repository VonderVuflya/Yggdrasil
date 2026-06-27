"""find_similar: semantic near-dup lookup (cosine + threshold + scope isolation).

Tests the cosine/threshold logic directly with hand-set embeddings, so no
embedding model is needed.
"""

import json
import tempfile
import time
import unittest
import uuid

from yggdrasil import ygg_memory_server as eng


class FindSimilarTest(unittest.TestCase):
    def _store(self):
        return eng.MemoryStore(tempfile.mktemp(suffix=".sqlite"), embedder=None)

    def _insert(self, store, vec, *, project="p", mtype="lesson", user="u"):
        with store._lock:
            store._conn.execute(
                "INSERT INTO memories (id,user_id,namespace,scope,project,type,content,"
                "content_hash,source,confidence,importance,created_at,access_count,archived,"
                "metadata_json,embedding) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,0,?,?)",
                ("ygg_" + uuid.uuid4().hex, user, "n", "project", project, mtype, "x",
                 None, "t", None, 0.5, time.time(), "{}", json.dumps(vec)),
            )
            store._conn.commit()

    def test_near_identical_is_found(self):
        store = self._store()
        self._insert(store, [1.0, 0.0, 0.0])
        r = store.find_similar(user_id="u", project="p", mem_type="lesson",
                               vec=[1.0, 0.001, 0.0], threshold=0.92)
        self.assertIsNotNone(r)
        self.assertGreaterEqual(r["similarity"], 0.92)

    def test_distinct_not_matched(self):
        store = self._store()
        self._insert(store, [1.0, 0.0, 0.0])
        r = store.find_similar(user_id="u", project="p", mem_type="lesson",
                               vec=[0.0, 1.0, 0.0], threshold=0.92)  # orthogonal -> cosine 0
        self.assertIsNone(r)

    def test_scope_isolation(self):
        store = self._store()
        self._insert(store, [1.0, 0.0, 0.0], project="A")
        # same vector but a different project -> not a dup
        self.assertIsNone(store.find_similar(user_id="u", project="B", mem_type="lesson",
                                             vec=[1.0, 0.0, 0.0], threshold=0.92))
        # different type -> not a dup
        self.assertIsNone(store.find_similar(user_id="u", project="A", mem_type="decision",
                                             vec=[1.0, 0.0, 0.0], threshold=0.92))


if __name__ == "__main__":
    unittest.main()
