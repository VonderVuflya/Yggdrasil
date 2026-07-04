"""Relation graph: typed edges (SOLVES / SUPERSEDES / CONTRADICTS) between
memories — creation, idempotency, validation, SUPERSEDES archiving, cascade."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
from ygg_memory_server import MemoryStore  # noqa: E402


class RelationsTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(db_path=tempfile.mktemp(suffix=".sqlite"))
        self.a = self._add("follow_up: flaky websocket reconnect in prod")
        self.b = self._add("fix: refresh token BEFORE opening the socket, capped backoff")
        self.c = self._add("lesson: reconnect loops came from an expired token")

    def _add(self, content):
        return self.store.add(content=content, user_id="u", namespace="n",
                              scope="project", metadata={"project": "p", "type": "lesson"})["id"]

    def _mem(self, mid):
        row = self.store._conn.execute("SELECT archived FROM memories WHERE id=?", (mid,)).fetchone()
        return dict(row)

    def test_relate_and_read_back_both_directions(self):
        r = self.store.relate(from_id=self.b, to_id=self.a, rel_type="solves", user_id="u")
        self.assertTrue(r["created"])
        self.assertEqual(r["rel_type"], "SOLVES")           # case-normalised
        rels_b = self.store.relations_for(self.b)
        self.assertEqual(rels_b["outgoing"][0]["other_id"], self.a)
        self.assertIn("flaky websocket", rels_b["outgoing"][0]["other_content"])
        rels_a = self.store.relations_for(self.a)
        self.assertEqual(rels_a["incoming"][0]["other_id"], self.b)

    def test_idempotent(self):
        self.store.relate(from_id=self.b, to_id=self.a, rel_type="SOLVES", user_id="u")
        r2 = self.store.relate(from_id=self.b, to_id=self.a, rel_type="SOLVES", user_id="u")
        self.assertFalse(r2["created"])
        self.assertEqual(len(self.store.relations_for(self.b)["outgoing"]), 1)

    def test_supersedes_archives_the_target(self):
        self.assertEqual(self._mem(self.c)["archived"], 0)
        self.store.relate(from_id=self.b, to_id=self.c, rel_type="SUPERSEDES", user_id="u")
        self.assertEqual(self._mem(self.c)["archived"], 1)
        # and the edge explains why it's archived
        inc = self.store.relations_for(self.c)["incoming"]
        self.assertEqual((inc[0]["rel_type"], inc[0]["other_id"]), ("SUPERSEDES", self.b))

    def test_validation(self):
        with self.assertRaises(ValueError):   # unknown type
            self.store.relate(from_id=self.a, to_id=self.b, rel_type="LIKES", user_id="u")
        with self.assertRaises(ValueError):   # self-loop
            self.store.relate(from_id=self.a, to_id=self.a, rel_type="SOLVES", user_id="u")
        with self.assertRaises(ValueError):   # missing endpoint
            self.store.relate(from_id=self.a, to_id="ygg_nope", rel_type="SOLVES", user_id="u")

    def test_unrelate(self):
        self.store.relate(from_id=self.b, to_id=self.a, rel_type="CONTRADICTS", user_id="u")
        self.assertTrue(self.store.unrelate(from_id=self.b, to_id=self.a, rel_type="contradicts"))
        self.assertFalse(self.store.unrelate(from_id=self.b, to_id=self.a, rel_type="contradicts"))
        self.assertEqual(self.store.relations_for(self.a), {"outgoing": [], "incoming": []})

    def test_delete_cascades_edges(self):
        self.store.relate(from_id=self.b, to_id=self.a, rel_type="SOLVES", user_id="u")
        self.store.delete_by_id(self.a)
        self.assertEqual(self.store.relations_for(self.b), {"outgoing": [], "incoming": []})

    def test_purge_cascades_edges(self):
        self.store.relate(from_id=self.b, to_id=self.a, rel_type="SOLVES", user_id="u")
        self.store.purge(user_id="u", namespace="n")
        left = self.store._conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        self.assertEqual(left, 0)


if __name__ == "__main__":
    unittest.main()
