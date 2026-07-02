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

    def test_add_populates_vector_cache(self):
        store = self._store()
        rec = store.add(content="cache me", user_id="u", namespace="n",
                        scope="global", metadata={})
        # add() with a live embedder must warm the in-process cache so the next
        # search doesn't re-parse the blob.
        seq = store._conn.execute("SELECT seq FROM memories WHERE id=?", (rec["id"],)).fetchone()[0]
        self.assertIn(seq, store._vec_cache)

    def test_reindex_reembeds_on_model_change(self):
        store = self._store()
        store.add(content="written by model A", user_id="u", namespace="n", scope="global", metadata={})
        self.assertEqual(store.missing_embeddings(), 0)   # current model, up to date
        # Simulate switching the embedding model: the old row is now stale.
        store._embed_model = "fake-v2"
        store.embedder.model = "fake-v2"
        self.assertEqual(store.missing_embeddings(), 1)   # model mismatch = needs reindex
        self.assertEqual(store.reindex_embeddings(), 1)
        self.assertEqual(store.missing_embeddings(), 0)


class VectorPathRankingParityTest(unittest.TestCase):
    """A pinned memory found only by meaning (no keyword overlap) must still get
    its pin boost — parity with the lexical path."""

    class ConstEmbedder:
        model = "toy"
        def embed(self, text):  # noqa: ARG002 — same vector for all: pure vector tie
            return [1.0, 0.0, 0.0]

    def test_pin_boost_applies_on_vector_only_hits(self):
        store = eng.MemoryStore(tempfile.mktemp(suffix=".sqlite"), embedder=self.ConstEmbedder())
        a = store.add(content="alpha note", user_id="u", namespace="n", scope="global",
                      metadata={"project": "p", "type": "lesson"})
        b = store.add(content="beta note", user_id="u", namespace="n", scope="global",
                      metadata={"project": "p", "type": "lesson"})
        store.update(b["id"], data=None, metadata_patch={"pinned": True}, archived=None)
        # Query shares no tokens with either memory -> retrieved by vector only.
        res = store.search(query="zzz", user_id="u", limit=2,
                           filters={"project": "p"}, namespaces=["n"])
        self.assertEqual({r["id"] for r in res}, {a["id"], b["id"]})
        self.assertEqual(res[0]["id"], b["id"])  # pinned first, despite the vector tie


class LegacyMigrationTest(unittest.TestCase):
    def test_json_embedding_migrates_to_blob_on_open(self):
        import json
        path = tempfile.mktemp(suffix=".sqlite")
        # First open: write a legacy JSON-text embedding directly (pre-blob format).
        store = eng.MemoryStore(path, embedder=None)
        with store._lock:
            store._conn.execute(
                "INSERT INTO memories (id,user_id,namespace,scope,project,type,content,"
                "content_hash,source,confidence,importance,created_at,access_count,archived,"
                "metadata_json,embedding) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,0,?,?)",
                ("ygg_legacy", "u", "n", "project", "p", "lesson", "x", None, "t", None,
                 0.5, time.time(), "{}", json.dumps([1.0, 0.0, 0.0])),
            )
            store._conn.commit()
        store._conn.close()

        # Reopen: _init_schema must backfill the blob from the JSON text.
        store2 = eng.MemoryStore(path, embedder=None)
        row = store2._conn.execute("SELECT embedding_blob, embed_model FROM memories WHERE id='ygg_legacy'").fetchone()
        self.assertIsNotNone(row["embedding_blob"])
        self.assertEqual(row["embed_model"], "(legacy)")
        # And it's usable for semantic dedup.
        hit = store2.find_similar(user_id="u", project="p", mem_type="lesson",
                                  vec=[1.0, 0.0, 0.0], threshold=0.9)
        self.assertIsNotNone(hit)


if __name__ == "__main__":
    unittest.main()
