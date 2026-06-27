"""missing_embeddings + reindex_embeddings: dense-recall self-heal (no Ollama)."""

import tempfile
import time
import unittest
import uuid

from yggdrasil import ygg_memory_server as eng


class FakeEmbedder:
    model = "fake"

    def embed(self, text):  # noqa: ARG002
        return [0.1, 0.2, 0.3]


class ReindexTest(unittest.TestCase):
    def _store(self):
        return eng.MemoryStore(tempfile.mktemp(suffix=".sqlite"), embedder=FakeEmbedder())

    def _insert(self, store, *, archived=0):
        with store._lock:
            store._conn.execute(
                "INSERT INTO memories (id,user_id,namespace,scope,project,type,content,"
                "content_hash,source,confidence,importance,created_at,access_count,archived,"
                f"metadata_json,embedding) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,{archived},?,NULL)",
                ("ygg_" + uuid.uuid4().hex, "u", "n", "project", "p", "lesson", "hello world",
                 None, "t", None, 0.5, time.time(), "{}"),
            )
            store._conn.commit()

    def test_reindex_backfills_missing(self):
        store = self._store()
        self._insert(store)
        self._insert(store)
        self.assertEqual(store.missing_embeddings(), 2)
        self.assertEqual(store.reindex_embeddings(), 2)
        self.assertEqual(store.missing_embeddings(), 0)

    def test_archived_not_counted_missing(self):
        store = self._store()
        self._insert(store, archived=1)
        self.assertEqual(store.missing_embeddings(), 0)


if __name__ == "__main__":
    unittest.main()
