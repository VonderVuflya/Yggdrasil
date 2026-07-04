"""git-backed sync: the deterministic merge policy, file rendering, and the
engine's id-preserving upsert (the git glue is exercised end-to-end manually)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg_sync  # noqa: E402
from ygg_memory_server import MemoryStore  # noqa: E402


def _rec(**kw):
    base = {"id": "ygg_x", "user_id": "u", "namespace": "n", "scope": "project",
            "project": "p", "type": "lesson", "content": "a fact",
            "content_hash": "h", "source": "s", "confidence": None,
            "importance": 0.5, "created_at": 1.0, "archived": 0,
            "metadata_json": "{}"}
    base.update(kw)
    return base


class MergeMemoryTest(unittest.TestCase):
    def test_archive_anywhere_holds_everywhere(self):
        self.assertEqual(ygg_sync.merge_memory(_rec(archived=1), _rec(archived=0))["archived"], 1)
        self.assertEqual(ygg_sync.merge_memory(_rec(archived=0), _rec(archived=1))["archived"], 1)

    def test_longer_content_wins_tie_goes_local(self):
        m = ygg_sync.merge_memory(_rec(content="short", content_hash="hl"),
                                  _rec(content="a much longer edited fact", content_hash="hr"))
        self.assertEqual(m["content"], "a much longer edited fact")
        self.assertEqual(m["content_hash"], "hr")
        m2 = ygg_sync.merge_memory(_rec(content="local", content_hash="hl"),
                                   _rec(content="remot", content_hash="hr"))
        self.assertEqual((m2["content"], m2["content_hash"]), ("local", "hl"))

    def test_confidence_max_and_pinned_or(self):
        m = ygg_sync.merge_memory(
            _rec(confidence=0.9, metadata_json=json.dumps({"pinned": True})),
            _rec(confidence=0.6, metadata_json=json.dumps({"tags": ["x"]})))
        self.assertEqual(m["confidence"], 0.9)
        md = json.loads(m["metadata_json"])
        self.assertTrue(md["pinned"])
        self.assertEqual(md["tags"], ["x"])   # union keeps remote-only keys


class RenderTest(unittest.TestCase):
    def test_memory_render_is_deterministic(self):
        a = ygg_sync.render_memory(_rec())
        b = ygg_sync.render_memory(dict(reversed(list(_rec().items()))))
        self.assertEqual(a, b)                # key order can't leak into bytes
        self.assertTrue(a.endswith("\n"))

    def test_relations_sorted_unique_and_conflict_tolerant(self):
        rels = [{"from_id": "b", "to_id": "a", "rel_type": "SOLVES"},
                {"from_id": "b", "to_id": "a", "rel_type": "SOLVES"},
                {"from_id": "a", "to_id": "c", "rel_type": "CONTRADICTS"}]
        body = ygg_sync.render_relations(rels)
        self.assertEqual(len(body.strip().splitlines()), 2)   # deduped
        parsed = ygg_sync.parse_relations("<<<<<<< ours\n" + body + ">>>>>>> theirs\n")
        self.assertEqual(len(parsed), 2)                      # markers tolerated


class SyncUpsertTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(db_path=tempfile.mktemp(suffix=".sqlite"))

    def test_insert_update_unchanged(self):
        rec = _rec(id="ygg_s1", content="машина А выучила урок про ретраи")
        r1 = self.store.sync_upsert([rec], [])
        self.assertEqual((r1["added"], r1["updated"]), (1, 0))
        r2 = self.store.sync_upsert([rec], [])
        self.assertEqual((r2["added"], r2["unchanged"]), (0, 1))
        # imported content is lexically searchable (FTS row was written)
        hits = self.store.search(query="ретраи", user_id="u", limit=3,
                                 filters={}, namespaces=None)
        self.assertTrue(any(h["id"] == "ygg_s1" for h in hits))
        r3 = self.store.sync_upsert([{**rec, "archived": 1}], [])
        self.assertEqual(r3["updated"], 1)
        # ...and an archive decision synced in takes it OUT of search
        hits = self.store.search(query="ретраи", user_id="u", limit=3,
                                 filters={}, namespaces=None)
        self.assertFalse(any(h["id"] == "ygg_s1" for h in hits))

    def test_relations_import_skips_missing_endpoints(self):
        a = _rec(id="ygg_a", content="a")
        b = _rec(id="ygg_b", content="b")
        r = self.store.sync_upsert([a, b], [
            {"from_id": "ygg_a", "to_id": "ygg_b", "rel_type": "SOLVES", "user_id": "u"},
            {"from_id": "ygg_a", "to_id": "ygg_GONE", "rel_type": "SOLVES", "user_id": "u"}])
        self.assertEqual((r["relations_added"], r["relations_skipped"]), (1, 1))

    def test_export_roundtrip_is_stable(self):
        self.store.sync_upsert([_rec(id="ygg_r1"), _rec(id="ygg_r2", content="другое")], [])
        exp = self.store.sync_export()
        r = self.store.sync_upsert(exp["memories"], exp["relations"])
        self.assertEqual(r["unchanged"], 2)   # re-importing own export is a no-op


if __name__ == "__main__":
    unittest.main()
