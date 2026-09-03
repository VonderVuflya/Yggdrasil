"""Engine-side uplink plumbing: updated_at, tombstones, and the outbox.

The outbox is what makes "push on write" cost the agent nothing: a mutation
records that something changed and returns; a background sender deals with the
network. Two invariants matter more than the rest and are tested directly —
enqueueing happens inside the mutation's own transaction, and anything that
arrived FROM a peer never enqueues (or two nodes ping-pong one record forever).
"""

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg_sync_merge as merge  # noqa: E402
from ygg_memory_server import MemoryStore  # noqa: E402


def _store():
    tmp = tempfile.TemporaryDirectory()
    store = MemoryStore(str(Path(tmp.name) / "m.sqlite"))
    return store, tmp


def _add(store, content="a fact", **meta):
    return store.add(content=content, user_id="local", namespace="personal",
                     scope="project", metadata={"project": "p", "type": "lesson", **meta})


class UpdatedAtTest(unittest.TestCase):
    def setUp(self):
        self.store, self._tmp = _store()
        self.addCleanup(self._tmp.cleanup)

    def test_add_stamps_updated_at(self):
        rec = _add(self.store)
        row = self.store.records_by_ids([rec["id"]])[0]
        self.assertEqual(row["updated_at"], row["created_at"])

    def test_update_advances_updated_at(self):
        rec = _add(self.store)
        before = self.store.records_by_ids([rec["id"]])[0]["updated_at"]
        time.sleep(0.01)
        self.store.update(rec["id"], data="edited", metadata_patch=None, archived=None)
        after = self.store.records_by_ids([rec["id"]])[0]["updated_at"]
        self.assertGreater(after, before)

    def test_metadata_only_edit_also_advances_it(self):
        """The case content_hash cannot see."""
        rec = _add(self.store)
        before = self.store.records_by_ids([rec["id"]])[0]["updated_at"]
        time.sleep(0.01)
        self.store.update(rec["id"], data=None, metadata_patch={"importance": 0.9}, archived=None)
        self.assertGreater(self.store.records_by_ids([rec["id"]])[0]["updated_at"], before)

    def test_export_carries_updated_at(self):
        _add(self.store)
        self.assertIn("updated_at", self.store.sync_export()["memories"][0])


class OutboxTest(unittest.TestCase):
    def setUp(self):
        self.store, self._tmp = _store()
        self.addCleanup(self._tmp.cleanup)

    def _kinds(self):
        return [(r["kind"], r["ref_id"]) for r in self.store.outbox_pending()]

    def test_add_enqueues_the_memory(self):
        rec = _add(self.store)
        self.assertEqual(self._kinds(), [("memory", rec["id"])])

    def test_update_enqueues(self):
        rec = _add(self.store)
        self.store.outbox_ack([r["seq"] for r in self.store.outbox_pending()])
        self.store.update(rec["id"], data="edited", metadata_patch=None, archived=None)
        self.assertEqual(self._kinds(), [("memory", rec["id"])])

    def test_repeated_edits_collapse_to_one_entry(self):
        """The queue holds references, not bodies — the sender reads current state,
        so two quick edits ship one final version instead of two stale ones."""
        rec = _add(self.store)
        for text in ("one", "two", "three"):
            self.store.update(rec["id"], data=text, metadata_patch=None, archived=None)
        self.assertEqual(self._kinds(), [("memory", rec["id"])])

    def test_delete_enqueues_a_tombstone(self):
        rec = _add(self.store)
        self.store.outbox_ack([r["seq"] for r in self.store.outbox_pending()])
        self.store.delete_by_id(rec["id"])
        self.assertEqual(self._kinds(), [("tombstone", rec["id"])])

    def test_ack_clears_only_what_was_sent(self):
        """A write that lands mid-flight must survive the ack for the batch before it."""
        _add(self.store, content="first")
        in_flight = self.store.outbox_pending()
        second = _add(self.store, content="second")
        self.store.outbox_ack([r["seq"] for r in in_flight])
        self.assertEqual([r["ref_id"] for r in self.store.outbox_pending()], [second["id"]])

    def test_imports_from_a_peer_never_enqueue(self):
        """Without this two nodes bounce the same record between them forever."""
        self.store.apply_remote(memories=[{
            "id": "ygg_remote", "user_id": "local", "namespace": "personal",
            "scope": "project", "project": "p", "type": "lesson", "content": "from the peer",
            "content_hash": "h", "source": "s", "confidence": 0.5, "importance": 0.5,
            "created_at": 1.0, "updated_at": 1.0, "archived": 0, "metadata_json": "{}"}])
        self.assertEqual(self.store.outbox_pending(), [])

    def test_git_sync_import_does_not_enqueue_either(self):
        self.store.sync_upsert([{
            "id": "ygg_git", "user_id": "local", "namespace": "personal", "scope": "project",
            "project": "p", "type": "lesson", "content": "via git", "content_hash": "h",
            "source": "s", "confidence": 0.5, "importance": 0.5, "created_at": 1.0,
            "archived": 0, "metadata_json": "{}"}])
        self.assertEqual(self.store.outbox_pending(), [])

    def test_overflow_bounds_the_queue_and_asks_for_a_full_reconcile(self):
        """A peer that was off for a week must not cost unbounded disk. The queue
        is expendable because reconcile catches up regardless — but writes that
        land after the drop still queue normally, so the assertion is the bound,
        not emptiness."""
        self.store.OUTBOX_MAX = 3
        for i in range(12):
            _add(self.store, content=f"fact number {i}")
        self.assertLessEqual(self.store.outbox_count(), self.store.OUTBOX_MAX)
        self.assertTrue(self.store.needs_reconcile)


class TombstoneTest(unittest.TestCase):
    def setUp(self):
        self.store, self._tmp = _store()
        self.addCleanup(self._tmp.cleanup)

    def test_delete_records_a_tombstone(self):
        rec = _add(self.store)
        self.store.delete_by_id(rec["id"])
        self.assertIn(rec["id"], self.store.tombstones())

    def test_purge_records_tombstones_for_everything_it_removed(self):
        ids = [_add(self.store, content=f"fact {i}")["id"] for i in range(3)]
        self.store.purge(user_id="local", project="p")
        self.assertEqual(sorted(self.store.tombstones()), sorted(ids))

    def test_a_tombstoned_record_cannot_be_reimported(self):
        """The point of the whole mechanism: a deleted secret must not come back
        from the machine that still has it."""
        rec = _add(self.store, content="leaked token")
        self.store.delete_by_id(rec["id"])
        self.store.apply_remote(memories=[dict(rec, content="leaked token",
                                               content_hash="h", updated_at=time.time() + 60,
                                               metadata_json="{}")])
        self.assertEqual(self.store.records_by_ids([rec["id"]]), [])

    def test_expired_tombstones_are_collected(self):
        rec = _add(self.store)
        self.store.delete_by_id(rec["id"])
        self.assertEqual(self.store.gc_tombstones(now=time.time() + merge.TOMBSTONE_TTL + 1), 1)
        self.assertEqual(self.store.tombstones(), {})

    def test_live_tombstones_survive_gc(self):
        rec = _add(self.store)
        self.store.delete_by_id(rec["id"])
        self.assertEqual(self.store.gc_tombstones(now=time.time()), 0)


class ApplyRemoteTest(unittest.TestCase):
    def setUp(self):
        self.store, self._tmp = _store()
        self.addCleanup(self._tmp.cleanup)

    def test_a_diverged_record_is_merged_not_overwritten(self):
        rec = _add(self.store, content="short")
        remote = dict(self.store.records_by_ids([rec["id"]])[0],
                      content="a considerably longer version", content_hash="hl",
                      importance=0.9, updated_at=time.time() + 5)
        self.store.apply_remote(memories=[remote])
        got = self.store.records_by_ids([rec["id"]])[0]
        self.assertEqual(got["content"], "a considerably longer version")
        self.assertEqual(got["importance"], 0.9)

    def test_a_remote_delete_removes_the_local_record(self):
        rec = _add(self.store)
        self.store.apply_remote(tombstones={rec["id"]: time.time()})
        self.assertEqual(self.store.records_by_ids([rec["id"]]), [])
        self.assertIn(rec["id"], self.store.tombstones())

    def test_counters_report_what_happened(self):
        rec = _add(self.store)
        out = self.store.apply_remote(tombstones={rec["id"]: time.time()})
        self.assertEqual(out["deleted"], 1)


if __name__ == "__main__":
    unittest.main()
