"""Engine-side uplink plumbing: updated_at, tombstones, and the outbox.

The outbox is what makes "push on write" cost the agent nothing: a mutation
records that something changed and returns; a background sender deals with the
network. Two invariants matter more than the rest and are tested directly —
enqueueing happens inside the mutation's own transaction, and anything that
arrived FROM a peer never enqueues (or two nodes ping-pong one record forever).
"""

import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg_sync_merge as merge  # noqa: E402
import ygg_memory_server as engine  # noqa: E402
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
        # LIFO: the directory is registered first so it is removed LAST, after the
        # database handle is closed. Windows refuses to delete a directory that
        # still holds an open SQLite file.
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self.store.close)

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
        # LIFO: the directory is registered first so it is removed LAST, after the
        # database handle is closed. Windows refuses to delete a directory that
        # still holds an open SQLite file.
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self.store.close)

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

    def test_an_edit_to_the_same_memory_mid_flight_survives_the_ack(self):
        """Coalescing by (kind, ref_id) used to keep the OLD seq, so the ack for
        the batch that carried the previous version swallowed the new edit."""
        rec = _add(self.store, content="first version")
        in_flight = self.store.outbox_pending()
        self.store.update(rec["id"], data="second version", metadata_patch=None, archived=None)
        self.store.outbox_ack([r["seq"] for r in in_flight])
        self.assertEqual([r["ref_id"] for r in self.store.outbox_pending()], [rec["id"]])

    def test_pending_can_resume_after_a_given_seq(self):
        first = _add(self.store, content="first")
        second = _add(self.store, content="second")
        seq = self.store.outbox_pending()[0]["seq"]
        self.assertEqual([r["ref_id"] for r in self.store.outbox_pending(after=seq)], [second["id"]])
        self.assertNotEqual(first["id"], second["id"])

    def test_ack_through_drops_everything_up_to_a_seq(self):
        _add(self.store, content="first")
        second = _add(self.store, content="second")
        seq = self.store.outbox_pending()[0]["seq"]
        self.store.outbox_ack_through(seq)
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
        # LIFO: the directory is registered first so it is removed LAST, after the
        # database handle is closed. Windows refuses to delete a directory that
        # still holds an open SQLite file.
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self.store.close)

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
        # LIFO: the directory is registered first so it is removed LAST, after the
        # database handle is closed. Windows refuses to delete a directory that
        # still holds an open SQLite file.
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self.store.close)

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

    def test_a_stamp_from_the_future_is_clamped_on_arrival(self):
        rec = _add(self.store, content="short")
        remote = dict(self.store.records_by_ids([rec["id"]])[0],
                      content="pushed by a box whose clock is a year ahead", content_hash="hf",
                      updated_at=time.time() + 365 * 24 * 3600)
        self.store.apply_remote(memories=[remote])
        got = self.store.records_by_ids([rec["id"]])[0]
        self.assertLessEqual(got["updated_at"], time.time() + merge.MAX_CLOCK_SKEW)

    def test_an_archive_stamp_from_the_future_is_clamped_on_arrival(self):
        rec = _add(self.store)
        remote = dict(self.store.records_by_ids([rec["id"]])[0], archived=1,
                      metadata_json=json.dumps({merge.ARCHIVE_STAMP: time.time() + 365 * 24 * 3600}))
        self.store.apply_remote(memories=[remote])
        md = json.loads(self.store.records_by_ids([rec["id"]])[0]["metadata_json"])
        self.assertLessEqual(md[merge.ARCHIVE_STAMP], time.time() + merge.MAX_CLOCK_SKEW)

    def test_unarchiving_clears_the_status_that_would_still_hide_it(self):
        rec = _add(self.store)
        self.store.update(rec["id"], data=None, metadata_patch=None, archived=True)
        self.store.update(rec["id"], data=None, metadata_patch=None, archived=False)
        md = json.loads(self.store.records_by_ids([rec["id"]])[0]["metadata_json"])
        self.assertEqual(md["status"], "active")
        self.assertIn(merge.ARCHIVE_STAMP, md)

    def test_a_tombstone_from_the_future_is_clamped_so_it_can_expire(self):
        rec = _add(self.store)
        self.store.apply_remote(tombstones={rec["id"]: time.time() + 10 * merge.TOMBSTONE_TTL})
        self.assertLessEqual(self.store.tombstones()[rec["id"]], time.time() + merge.MAX_CLOCK_SKEW)

    def test_a_namespace_change_from_a_peer_is_written(self):
        """merge resolves user_id/namespace and the digest hashes them — a writer
        that skipped them left the record "different" on every reconcile, forever."""
        rec = _add(self.store)
        remote = dict(self.store.records_by_ids([rec["id"]])[0],
                      namespace="work", updated_at=time.time() + 5)
        self.store.apply_remote(memories=[remote])
        self.assertEqual(self.store.records_by_ids([rec["id"]])[0]["namespace"], "work")
        self.assertEqual(self.store.apply_remote(memories=[remote])["updated"], 0)

    def test_the_writer_never_resurrects_a_tombstoned_id(self):
        """apply_remote checks tombstones before it takes the write lock; a local
        delete that lands in between must still hold."""
        rec = _add(self.store, content="leaked token")
        row = self.store.records_by_ids([rec["id"]])[0]
        self.store.delete_by_id(rec["id"])
        self.store.sync_upsert([dict(row)])
        self.assertEqual(self.store.records_by_ids([rec["id"]]), [])

    def test_counters_report_what_happened(self):
        rec = _add(self.store)
        out = self.store.apply_remote(tombstones={rec["id"]: time.time()})
        self.assertEqual(out["deleted"], 1)


class GitTransportRouteTest(unittest.TestCase):
    """The routes `ygg sync` (git) talks to. They used to carry memories and
    relations only, so the git transport could neither learn about a delete nor
    pass one on — and re-imported deleted memories on every run."""

    def setUp(self):
        self.store, self._tmp = _store()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self.store.close)
        handler = type("H", (engine.Handler,), {"store": self.store, "token": "t"})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def post(self, path, body):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.httpd.server_address[1]}{path}",
            data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": "Bearer t", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())["data"]

    def test_export_carries_the_tombstones(self):
        rec = _add(self.store)
        self.store.delete_by_id(rec["id"])
        self.assertIn(rec["id"], self.post("/sync_export", {})["tombstones"])

    def test_upsert_applies_tombstones_before_records(self):
        rec = _add(self.store, content="leaked token")
        row = self.store.records_by_ids([rec["id"]])[0]
        self.post("/sync_upsert", {"memories": [row], "relations": [],
                                   "tombstones": {rec["id"]: time.time()}})
        self.assertEqual(self.store.records_by_ids([rec["id"]]), [])
        self.assertIn(rec["id"], self.store.tombstones())


if __name__ == "__main__":
    unittest.main()
