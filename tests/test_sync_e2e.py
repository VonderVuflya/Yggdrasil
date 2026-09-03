"""Two engines, two nodes, one loopback — the whole uplink end to end.

The invariant this file is built around: after a reconcile, both stores export
byte-identical state. One assertion that catches almost any mistake in merging,
digesting, or ordering.
"""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg_sync_peers as peers  # noqa: E402
from ygg_memory_server import MemoryStore  # noqa: E402
from ygg_sync_node import SyncNode  # noqa: E402


def _export(store):
    return json.dumps(store.sync_export(), sort_keys=True, ensure_ascii=False)


class Pair(unittest.TestCase):
    """Two paired nodes, `self.a` and `self.b`, talking over loopback."""

    insecure = True

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.a_store = MemoryStore(str(root / "a" / "m.sqlite"))
        self.b_store = MemoryStore(str(root / "b" / "m.sqlite"))
        self.a = SyncNode(self.a_store, home=root / "a", name="alpha", insecure=self.insecure)
        self.b = SyncNode(self.b_store, home=root / "b", name="beta", insecure=self.insecure)
        for node in (self.a, self.b):
            node.start()
            self.addCleanup(node.stop)
        self.b.pair_with(self.a.issue_pairing_code(), name="alpha")

    def add(self, store, content, **meta):
        return store.add(content=content, user_id="local", namespace="personal",
                         scope="project", metadata={"project": "p", "type": "lesson", **meta})

    def assertConverged(self):
        self.a.reconcile(force=True)
        self.b.reconcile(force=True)
        self.assertEqual(_export(self.a_store), _export(self.b_store))


class PairingTest(Pair):
    def test_both_sides_know_each_other_after_one_code(self):
        self.assertEqual(len(peers.load(self.a.peers_path)["peers"]), 1)
        self.assertEqual(len(peers.load(self.b.peers_path)["peers"]), 1)

    def test_the_keys_are_per_pair_not_shared(self):
        a_peer = list(peers.load(self.a.peers_path)["peers"].values())[0]
        b_peer = list(peers.load(self.b.peers_path)["peers"].values())[0]
        self.assertEqual(a_peer["key_in"], b_peer["key_out"])
        self.assertEqual(a_peer["key_out"], b_peer["key_in"])
        self.assertNotEqual(a_peer["key_in"], a_peer["key_out"])

    def test_an_unpaired_caller_gets_nothing(self):
        self.assertEqual(self.a.probe(self.b.url, key="not-a-real-key")["status"], 401)

    def test_a_second_use_of_the_same_code_is_refused(self):
        code = self.a.issue_pairing_code()
        self.b.pair_with(code, name="alpha-again")
        with self.assertRaises(RuntimeError):
            self.b.pair_with(code, name="alpha-third")

    def test_no_cors_headers_are_ever_emitted(self):
        headers = self.a.probe(self.b.url, key="whatever")["headers"]
        self.assertFalse([h for h in headers if h.lower().startswith("access-control")])


class PushTest(Pair):
    def test_a_write_reaches_the_peer(self):
        rec = self.add(self.a_store, "the deploy needs the migration first")
        self.a.flush_outbox()
        self.assertEqual(self.b_store.records_by_ids([rec["id"]])[0]["content"],
                         "the deploy needs the migration first")

    def test_a_delete_reaches_the_peer(self):
        rec = self.add(self.a_store, "a leaked token")
        self.a.flush_outbox()
        self.a_store.delete_by_id(rec["id"])
        self.a.flush_outbox()
        self.assertEqual(self.b_store.records_by_ids([rec["id"]]), [])
        self.assertIn(rec["id"], self.b_store.tombstones())

    def test_the_queue_drains_only_on_success(self):
        self.add(self.a_store, "written while the peer is down")
        self.b.stop()
        self.a.flush_outbox()
        self.assertEqual(self.a_store.outbox_count(), 1)

    def test_an_arrival_is_not_queued_back_towards_its_sender(self):
        """The ping-pong guard. Without it these two would trade one record forever."""
        self.add(self.a_store, "one fact")
        self.a.flush_outbox()
        self.assertEqual(self.b_store.outbox_count(), 0)


class ReconcileTest(Pair):
    def test_a_peer_that_was_offline_catches_up(self):
        self.b.stop()
        self.add(self.a_store, "written during the outage")
        self.a.flush_outbox()
        self.b.start()
        self.assertConverged()

    def test_writes_on_both_sides_converge(self):
        self.add(self.a_store, "from the laptop")
        self.add(self.b_store, "from the compute box")
        self.assertConverged()

    def test_a_diverged_record_converges_to_the_same_merge(self):
        rec = self.add(self.a_store, "short")
        self.a.flush_outbox()
        self.a_store.update(rec["id"], data="a considerably longer version",
                            metadata_patch=None, archived=None)
        self.b_store.update(rec["id"], data="edited over here",
                            metadata_patch={"importance": 0.9}, archived=None)
        self.assertConverged()

    def test_an_archive_on_one_side_holds_on_both(self):
        rec = self.add(self.a_store, "obsolete advice")
        self.a.flush_outbox()
        self.a_store.update(rec["id"], data=None, metadata_patch=None, archived=True)
        self.assertConverged()
        self.assertEqual(self.b_store.records_by_ids([rec["id"]])[0]["archived"], 1)

    def test_a_deletion_is_not_undone_by_the_peer_that_still_has_it(self):
        rec = self.add(self.a_store, "a leaked token")
        self.a.flush_outbox()
        self.a_store.delete_by_id(rec["id"])
        self.assertConverged()
        self.assertEqual(self.b_store.records_by_ids([rec["id"]]), [])

    def test_reconcile_is_idempotent(self):
        self.add(self.a_store, "from the laptop")
        self.add(self.b_store, "from the compute box")
        self.assertConverged()
        before = _export(self.a_store)
        self.assertConverged()
        self.assertEqual(before, _export(self.a_store))

    def test_reconcile_is_skipped_while_still_fresh(self):
        """Yggdrasil is called a few times a day — a reconcile per recall would be
        pure waste, so a recent success short-circuits without touching the network."""
        self.a.reconcile(force=True)
        self.assertFalse(self.a.reconcile()["ran"])

    def test_overflow_still_converges_through_reconcile(self):
        self.a_store.OUTBOX_MAX = 2
        for i in range(6):
            self.add(self.a_store, f"fact number {i}")
        self.assertTrue(self.a_store.needs_reconcile)
        self.assertConverged()


class ReadTriggerTest(Pair):
    def test_a_read_starts_a_reconcile_without_waiting_for_it(self):
        self.add(self.b_store, "written on the other box")
        self.assertTrue(self.a.maybe_reconcile_async())
        for _ in range(100):
            if self.a_store.count():
                break
            time.sleep(0.05)
        self.assertEqual(self.a_store.count(), 1)

    def test_a_fresh_node_does_not_start_one(self):
        self.a.reconcile(force=True)
        self.assertFalse(self.a.maybe_reconcile_async())

    def test_a_node_with_no_peers_never_starts_one(self):
        state = peers.load(self.a.peers_path)
        state["peers"] = {}
        peers.save(state, self.a.peers_path)
        self.a.reload_peers()
        self.assertFalse(self.a.maybe_reconcile_async())


@unittest.skipUnless(peers.openssl_available(), "openssl not on PATH")
class TlsTest(Pair):
    insecure = False

    def test_traffic_is_encrypted_and_the_certificate_is_pinned(self):
        a_peer = list(peers.load(self.b.peers_path)["peers"].values())[0]
        self.assertTrue(a_peer["url"].startswith("https://"))
        self.assertEqual(a_peer["fingerprint"],
                         peers.cert_fingerprint(peers.ensure_cert(self.a.home)[0]))

    def test_a_swapped_certificate_is_refused(self):
        state = peers.load(self.b.peers_path)
        for peer in state["peers"].values():
            peer["fingerprint"] = "0" * 64
        peers.save(state, self.b.peers_path)
        self.b.reload_peers()
        self.add(self.b_store, "must not leave this machine")
        self.b.flush_outbox()
        self.assertEqual(self.b_store.outbox_count(), 1)

    def test_paired_nodes_still_converge_over_tls(self):
        self.add(self.a_store, "from the laptop")
        self.add(self.b_store, "from the compute box")
        self.assertConverged()


if __name__ == "__main__":
    unittest.main()
