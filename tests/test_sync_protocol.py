"""Wire format and reconcile planning — pure, no sockets.

The plan is what makes reconcile cheap: nodes trade fingerprints, not records,
and only diverging bodies move.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg_sync_protocol as proto  # noqa: E402


def _rec(mid="ygg_a", **kw):
    base = {"id": mid, "user_id": "local", "namespace": "personal", "scope": "project",
            "project": "p", "type": "lesson", "content": "a fact", "content_hash": "h",
            "source": "s", "confidence": 0.5, "importance": 0.5, "created_at": 100.0,
            "updated_at": 100.0, "archived": 0, "metadata_json": "{}"}
    base.update(kw)
    return base


class StateHashTest(unittest.TestCase):
    def test_identical_records_hash_identically(self):
        self.assertEqual(proto.state_hash(_rec()), proto.state_hash(_rec()))

    def test_access_bookkeeping_is_not_part_of_the_state(self):
        """access_count and vectors are per-machine — if they entered the hash,
        merely reading a memory here would look like an edit over there."""
        noisy = _rec(access_count=99, last_accessed_at=5.0, embedding_blob=b"xx", embed_model="m")
        self.assertEqual(proto.state_hash(_rec()), proto.state_hash(noisy))

    def test_metadata_only_edit_changes_the_hash(self):
        """The reason updated_at/state_hash exist at all: content is untouched, so
        content_hash alone would call these two records identical."""
        self.assertNotEqual(proto.state_hash(_rec()), proto.state_hash(_rec(importance=0.9)))
        self.assertNotEqual(proto.state_hash(_rec()), proto.state_hash(_rec(metadata_json='{"a":1}')))

    def test_archive_changes_the_hash(self):
        self.assertNotEqual(proto.state_hash(_rec()), proto.state_hash(_rec(archived=1)))

    def test_missing_content_hash_falls_back_to_the_content(self):
        a = proto.state_hash(_rec(content_hash=None, content="one"))
        b = proto.state_hash(_rec(content_hash=None, content="two"))
        self.assertNotEqual(a, b)

    def test_touching_a_record_without_changing_it_is_not_a_divergence(self):
        """updated_at is carried for merge tie-breaks, never compared — otherwise
        two nodes that imported the same record at different moments would fetch
        and re-merge it on every single reconcile, forever."""
        self.assertEqual(proto.state_hash(_rec(updated_at=1.0)), proto.state_hash(_rec(updated_at=9.0)))


class DigestTest(unittest.TestCase):
    def test_digest_carries_version_and_both_maps(self):
        d = proto.build_digest([_rec()], {"ygg_dead": 12.0}, node_id="n1")
        self.assertEqual(d["proto"], proto.PROTOCOL_VERSION)
        self.assertEqual(d["node"], "n1")
        self.assertIn("ygg_a", d["memories"])
        self.assertEqual(d["tombstones"], {"ygg_dead": 12.0})

    def test_compatibility_gate(self):
        self.assertTrue(proto.compatible(proto.PROTOCOL_VERSION))
        self.assertFalse(proto.compatible(proto.PROTOCOL_VERSION + 1))
        self.assertFalse(proto.compatible(None))


class PlanTest(unittest.TestCase):
    def _plan(self, local_recs, remote_recs, local_tombs=None, remote_tombs=None):
        return proto.plan(
            proto.build_digest(local_recs, local_tombs or {}, node_id="l"),
            proto.build_digest(remote_recs, remote_tombs or {}, node_id="r"))

    def test_nothing_to_do_when_stores_agree(self):
        p = self._plan([_rec()], [_rec()])
        self.assertEqual((p.fetch, p.push, p.delete_local, p.push_tombstones), ([], [], [], []))

    def test_remote_only_record_is_fetched(self):
        self.assertEqual(self._plan([], [_rec()]).fetch, ["ygg_a"])

    def test_local_only_record_is_pushed(self):
        self.assertEqual(self._plan([_rec()], []).push, ["ygg_a"])

    def test_divergence_is_fetched_not_blindly_pushed(self):
        """Fetch their body, merge, then send the merged result — pushing our
        pre-merge version would just make them redo the same merge."""
        p = self._plan([_rec(importance=0.1)], [_rec(importance=0.9)])
        self.assertEqual(p.fetch, ["ygg_a"])
        self.assertEqual(p.push, [])

    def test_their_tombstone_deletes_our_copy(self):
        p = self._plan([_rec()], [], remote_tombs={"ygg_a": 50.0})
        self.assertEqual(p.delete_local, ["ygg_a"])
        self.assertEqual(p.push, [])

    def test_our_tombstone_is_pushed_and_blocks_the_refetch(self):
        """Without the block, the peer's live copy would come straight back in the
        same round trip that carries our deletion."""
        p = self._plan([], [_rec()], local_tombs={"ygg_a": 50.0})
        self.assertEqual(p.fetch, [])
        self.assertEqual(p.push_tombstones, ["ygg_a"])

    def test_a_tombstone_both_sides_know_is_not_resent(self):
        p = self._plan([], [], local_tombs={"ygg_a": 5.0}, remote_tombs={"ygg_a": 5.0})
        self.assertEqual(p.push_tombstones, [])

    def test_plan_is_ordered_for_stable_batching(self):
        p = self._plan([_rec("ygg_c"), _rec("ygg_a"), _rec("ygg_b")], [])
        self.assertEqual(p.push, ["ygg_a", "ygg_b", "ygg_c"])

    def test_empty_plan_is_falsy_so_callers_can_skip_the_round_trip(self):
        self.assertFalse(self._plan([_rec()], [_rec()]))
        self.assertTrue(self._plan([], [_rec()]))


if __name__ == "__main__":
    unittest.main()
