"""Two engines, two nodes, one loopback — the whole uplink end to end.

The invariant this file is built around: after a reconcile, both stores export
byte-identical state. One assertion that catches almost any mistake in merging,
digesting, or ordering.
"""

import http.client
import json
import os
import socket
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg_sync_peers as peers  # noqa: E402
from ygg_memory_server import MemoryStore, _Uplink  # noqa: E402
from ygg_sync_node import SyncNode  # noqa: E402


def _export(store):
    return json.dumps(store.sync_export(), sort_keys=True, ensure_ascii=False)


class UplinkRetryTest(unittest.TestCase):
    def test_a_port_busy_at_boot_is_retried_until_it_frees(self):
        """Seen live: the release gates held 42070 while launchd restarted the
        daemon, and the machine stayed unreachable until the next restart."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = Path(tmp.name)
        store = MemoryStore(str(home / "m.sqlite"))
        self.addCleanup(store.close)
        peers.save({"node_id": "me", "peers": {"x": {"name": "x", "url": "http://127.0.0.1:9"}}},
                   home / "peers.json")
        squatter = socket.socket()
        squatter.bind(("127.0.0.1", 0))
        squatter.listen()
        port = squatter.getsockname()[1]
        env = {"YGG_HOME": str(home), "YGG_SYNC_HOST": "127.0.0.1",
               "YGG_SYNC_PORT": str(port), "YGG_SYNC_INSECURE": "1"}
        with mock.patch.dict(os.environ, env):
            uplink = _Uplink()
            uplink.RETRY_SECONDS = 0.05
            uplink.start_if_paired(store)
            self.assertIsNone(uplink.node)
            self.assertIn(f"port {port} is already in use", uplink.error)
            self.assertIn("retrying", uplink.error)
            squatter.close()
            deadline = time.time() + 5
            while uplink.node is None and time.time() < deadline:
                time.sleep(0.05)
        self.assertIsNotNone(uplink.node)
        self.addCleanup(uplink.node.stop)
        self.assertIsNone(uplink.error)


class Pair(unittest.TestCase):
    """Two paired nodes, `self.a` and `self.b`, talking over loopback."""

    insecure = True

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.a_store = MemoryStore(str(root / "a" / "m.sqlite"))
        self.b_store = MemoryStore(str(root / "b" / "m.sqlite"))
        # Cleanups run LIFO, so these close before the temp tree is removed —
        # Windows will not delete a directory holding an open SQLite file.
        self.addCleanup(self.b_store.close)
        self.addCleanup(self.a_store.close)
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

    def test_a_pairing_without_a_node_id_is_refused(self):
        parsed = peers.parse_code(self.a.issue_pairing_code())
        with self.assertRaises(PermissionError):
            self.a.accept_pairing({"pairing_id": parsed["pairing_id"], "secret": parsed["secret"],
                                   "node_id": "", "name": "x", "url": "http://h:1", "key": "k"})
        self.assertEqual(len(peers.load(self.a.peers_path)["peers"]), 1)

    def test_a_pairing_claiming_our_own_node_id_is_refused(self):
        parsed = peers.parse_code(self.a.issue_pairing_code())
        with self.assertRaises(PermissionError):
            self.a.accept_pairing({"pairing_id": parsed["pairing_id"], "secret": parsed["secret"],
                                   "node_id": self.a.node_id, "name": "x", "url": "http://h:1",
                                   "key": "k"})

    def test_an_oversized_body_is_refused_unread(self):
        """/sync/pair is unauthenticated; trusting Content-Length there lets
        anyone on the LAN make the engine allocate whatever they claim."""
        conn = http.client.HTTPConnection(self.a.host, self.a.port, timeout=5)
        self.addCleanup(conn.close)
        conn.putrequest("POST", "/sync/pair")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(10 ** 10))
        conn.endheaders()
        conn.send(b"{}")
        self.assertEqual(conn.getresponse().status, 413)

    def test_no_cors_headers_are_ever_emitted(self):
        headers = self.a.probe(self.b.url, key="whatever")["headers"]
        self.assertFalse([h for h in headers if h.lower().startswith("access-control")])


class AddressTest(Pair):
    def test_redeeming_moves_the_listener_to_the_interface_that_reaches_the_issuer(self):
        """A guessed address (a VPN, a Docker bridge) used to be what the other
        side stored, so it could never push back. The route the pairing took
        is the one address both machines provably share."""
        root = Path(self._tmp.name)
        c_store = MemoryStore(str(root / "c" / "m.sqlite"))
        self.addCleanup(c_store.close)
        c = SyncNode(c_store, home=root / "c", name="gamma", host="localhost",
                     insecure=self.insecure, host_pinned=False)
        c.start()
        self.addCleanup(c.stop)
        c.pair_with(self.a.issue_pairing_code(), name="alpha")
        self.assertEqual(c.host, "127.0.0.1")
        stored = [p for p in self.a.peers_state["peers"].values() if p["name"] == "gamma"][0]
        self.assertEqual(stored["url"], c.url)
        rec = self.add(self.a_store, "reaches gamma at the address it advertised")
        self.a.flush_outbox()
        self.assertEqual(len(c_store.records_by_ids([rec["id"]])), 1)

    def test_a_pinned_host_is_left_alone(self):
        root = Path(self._tmp.name)
        c_store = MemoryStore(str(root / "c" / "m.sqlite"))
        self.addCleanup(c_store.close)
        c = SyncNode(c_store, home=root / "c", name="gamma", host="localhost",
                     insecure=self.insecure)
        c.start()
        self.addCleanup(c.stop)
        c.pair_with(self.a.issue_pairing_code(), name="alpha")
        self.assertEqual(c.host, "localhost")

    def test_the_redeemer_keeps_the_address_it_actually_reached(self):
        stored = [p for p in self.b.peers_state["peers"].values() if p["name"] == "alpha"][0]
        self.assertEqual(stored["url"], self.a.url)


def _lan_address_or_none():
    """A non-loopback address this machine can bind, for tests that need two
    distinct interfaces. None on a box with only loopback (CI containers)."""
    import ygg_memory_server as engine
    for addr in engine._private_addresses():
        try:
            with socket.socket() as probe:
                probe.bind((addr, 0))
        except OSError:
            continue
        return addr
    return None


class NetworkTest(Pair):
    def _conn(self, node):
        if self.insecure:
            return http.client.HTTPConnection(node.host, node.port, timeout=5)
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        return http.client.HTTPSConnection(node.host, node.port, timeout=5, context=ctx)

    def _node(self, name, **kw):
        root = Path(self._tmp.name)
        store = MemoryStore(str(root / name / "m.sqlite"))
        self.addCleanup(store.close)
        node = SyncNode(store, home=root / name, name=name, insecure=self.insecure, **kw)
        node.start()
        self.addCleanup(node.stop)
        return node, store

    # -- the issuer calls back --------------------------------------------

    def test_pairing_reports_that_the_issuer_can_reach_us(self):
        c, _ = self._node("gamma")
        peer = c.pair_with(self.a.issue_pairing_code(), name="alpha")
        self.assertTrue(peer["reachable_back"])

    def test_pairing_reports_a_redeemer_the_issuer_cannot_reach(self):
        """The ufw case: the link was made, but writes from the issuer would
        never arrive. Said at pairing time, not discovered weeks later."""
        c, _ = self._node("gamma")
        c._close_listener()  # as good as a firewall dropping the port
        peer = c.pair_with(self.a.issue_pairing_code(), name="alpha")
        self.assertFalse(peer["reachable_back"])
        self.assertTrue(peer["back_error"])
        self.assertNotIn("reachable_back", list(peers.load(c.peers_path)["peers"].values())[0])

    # -- health -----------------------------------------------------------

    def test_a_delivered_push_is_recorded_as_healthy(self):
        self.add(self.a_store, "fine")
        self.a.flush_outbox()
        health = self.a.peer_health()[self.b.node_id]
        self.assertIsNotNone(health["ok_at"])
        self.assertIsNone(health["error"])
        self.assertEqual(health["backlog"], 0)

    def test_a_failing_peer_shows_its_error_and_backlog(self):
        self.b.stop()
        self.add(self.a_store, "stuck")
        self.a.flush_outbox()
        health = self.a.peer_health()[self.b.node_id]
        self.assertTrue(health["error"])
        self.assertEqual(health["backlog"], 1)

    def test_a_successful_reconcile_wakes_the_sender(self):
        """Seen live: the record arrived through reconcile, yet the list said
        "1 waiting" until the sender's backoff (up to five minutes) ran out."""
        self.b.stop()
        self.add(self.a_store, "queued while beta was off")
        self.a.flush_outbox()
        self.b.start()
        self.a_store.outbox_signal.clear()
        self.a.reconcile(force=True)
        self.assertTrue(self.a_store.outbox_signal.is_set())

    def test_being_contacted_is_recorded(self):
        self.add(self.a_store, "hello b")
        self.a.flush_outbox()
        self.assertIsNotNone(self.b.peer_health()[self.a.node_id]["heard_at"])

    # -- addresses move ---------------------------------------------------

    def test_a_peer_that_moved_is_found_at_its_new_address(self):
        """DHCP hands out a new address; the peer says so on its next request."""
        a_peer_in_b = lambda: self.b.peers_state["peers"][self.a.node_id]["url"]  # noqa: E731
        self.a._rebind("localhost")
        self.assertNotEqual(a_peer_in_b(), self.a.url)
        self.add(self.a_store, "from the new address")
        self.a.flush_outbox()
        self.assertEqual(a_peer_in_b(), self.a.url)
        self.assertEqual(peers.load(self.b.peers_path)["peers"][self.a.node_id]["url"], self.a.url)

    def test_a_malformed_advertised_address_is_ignored(self):
        key = self.a.peers_state["peers"][self.b.node_id]["key_out"]
        before = self.b.peers_state["peers"][self.a.node_id]["url"]
        for bogus in ("ftp://x:1", "http://:1", "http://h:notaport", "garbage"):
            conn = self._conn(self.b)
            conn.request("GET", "/sync/hello", headers={
                "Authorization": f"Bearer {key}", "X-Ygg-Url": bogus})
            self.assertEqual(conn.getresponse().status, 200)
            conn.close()
        self.assertEqual(self.b.peers_state["peers"][self.a.node_id]["url"], before)

    def test_an_unauthenticated_caller_cannot_move_a_peer(self):
        before = self.b.peers_state["peers"][self.a.node_id]["url"]
        conn = self._conn(self.b)
        conn.request("GET", "/sync/hello", headers={
            "Authorization": "Bearer nope", "X-Ygg-Url": "http://10.9.9.9:1"})
        self.assertEqual(conn.getresponse().status, 401)
        conn.close()
        self.assertEqual(self.b.peers_state["peers"][self.a.node_id]["url"], before)

    # -- more than one interface -------------------------------------------

    def test_a_second_peer_on_another_interface_adds_a_listener(self):
        """Moving the one listener to reach a new peer used to cut off the
        peers already reached through the old interface."""
        lan = _lan_address_or_none()
        if lan is None:
            self.skipTest("needs a non-loopback interface")
        c, c_store = self._node("gamma", host_pinned=False)
        c.pair_with(self.a.issue_pairing_code(), name="alpha")  # over loopback
        d, d_store = self._node("delta", host=lan)
        c.pair_with(d.issue_pairing_code(), name="delta")       # over the LAN
        self.assertEqual(c.host, "127.0.0.1")
        self.assertIn(lan, c.hosts)
        rec = self.add(c_store, "reaches both")
        c.flush_outbox()
        self.assertEqual(len(self.a_store.records_by_ids([rec["id"]])), 1)
        self.assertEqual(len(d_store.records_by_ids([rec["id"]])), 1)
        rec2 = self.add(d_store, "and back over the LAN")
        d.flush_outbox()
        self.assertEqual(len(c_store.records_by_ids([rec2["id"]])), 1)

    def test_a_code_can_name_a_chosen_address(self):
        """`ygg link --tailscale`: the code carries that interface, and the
        node listens there too."""
        lan = _lan_address_or_none()
        if lan is None:
            self.skipTest("needs a non-loopback interface")
        code = self.a.issue_pairing_code(host=lan)
        self.assertEqual(peers.parse_code(code)["host"], lan)
        self.assertIn(lan, self.a.hosts)
        c, _ = self._node("gamma")
        self.assertTrue(c.pair_with(code, name="alpha")["reachable_back"])

    def test_a_code_for_an_address_we_do_not_have_is_refused(self):
        with self.assertRaises(ValueError):
            self.a.issue_pairing_code(host="203.0.113.7")


class TlsNetworkTest(NetworkTest):
    insecure = False


class ArchiveTest(Pair):
    def test_an_unarchive_reaches_the_peer_and_stays(self):
        rec = self.add(self.a_store, "archived by mistake")
        self.a_store.update(rec["id"], data=None, metadata_patch=None, archived=True)
        self.a.flush_outbox()
        self.assertTrue(self.b_store.records_by_ids([rec["id"]])[0]["archived"])
        self.a_store.update(rec["id"], data=None, metadata_patch=None, archived=False)
        self.a.flush_outbox()
        self.assertConverged()
        for store in (self.a_store, self.b_store):
            row = store.records_by_ids([rec["id"]])[0]
            self.assertFalse(row["archived"])
            self.assertEqual(json.loads(row["metadata_json"])["status"], "active")


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

    def test_one_offline_peer_does_not_hold_back_the_others(self):
        """Acks used to require EVERY peer, so one sleeping machine made the
        healthy ones re-receive the same first batch on every backoff tick."""
        root = Path(self._tmp.name)
        c_store = MemoryStore(str(root / "c" / "m.sqlite"))
        self.addCleanup(c_store.close)
        c = SyncNode(c_store, home=root / "c", name="gamma", insecure=self.insecure)
        c.start()
        self.addCleanup(c.stop)
        c.pair_with(self.a.issue_pairing_code(), name="alpha")
        self.a.reload_peers()
        c.stop()

        first = self.add(self.a_store, "first while gamma sleeps")
        self.assertTrue(self.a.flush_outbox()["errors"])
        self.assertEqual(len(self.b_store.records_by_ids([first["id"]])), 1)
        # beta already has it: a second flush must not count it as sent again
        self.assertEqual(self.a.flush_outbox()["sent"], 0)
        self.assertEqual(self.a_store.outbox_count(), 1)  # still owed to gamma

        c.start()
        self.assertEqual(self.a.flush_outbox()["errors"], [])
        self.assertEqual(len(c_store.records_by_ids([first["id"]])), 1)
        self.assertEqual(self.a_store.outbox_count(), 0)

    def test_a_large_backlog_drains_in_one_flush(self):
        import ygg_sync_node as node_mod
        old = node_mod.PUSH_BATCH
        node_mod.PUSH_BATCH = 2
        self.addCleanup(setattr, node_mod, "PUSH_BATCH", old)
        for i in range(5):
            self.add(self.a_store, f"backlog fact {i}")
        self.a.flush_outbox()
        self.assertEqual(self.b_store.count(), 5)
        self.assertEqual(self.a_store.outbox_count(), 0)

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

    def _code_parts(self):
        code = self.a.issue_pairing_code()
        head, _, fp = code.rpartition(".")
        return code, head, fp

    def test_a_code_whose_fingerprint_does_not_match_is_refused_before_the_secret_leaves(self):
        """The man-in-the-middle case: whoever answers the connection must hold
        the certificate named in the code, or the secret is never sent."""
        code, head, fp = self._code_parts()
        with self.assertRaises(RuntimeError):
            self.b.pair_with(f"{head}.{'0' * len(fp)}", name="impostor")
        # had the secret gone out, alpha would have burned the code
        self.b.pair_with(code, name="alpha-again")

    def test_a_code_without_a_fingerprint_is_refused_over_tls(self):
        _, head, _ = self._code_parts()
        with self.assertRaises(RuntimeError):
            self.b.pair_with(head, name="unpinned")

    def test_a_peer_with_no_pin_is_refused_not_trusted(self):
        state = peers.load(self.b.peers_path)
        for peer in state["peers"].values():
            peer["fingerprint"] = ""
        peers.save(state, self.b.peers_path)
        self.b.reload_peers()
        self.add(self.b_store, "must not leave this machine")
        self.assertTrue(self.b.flush_outbox()["errors"])
        self.assertEqual(self.b_store.outbox_count(), 1)

    def test_an_offline_peer_is_an_error_not_an_exception(self):
        self.b.stop()
        self.add(self.a_store, "written while beta sleeps")
        self.assertTrue(self.a.flush_outbox()["errors"])
        self.assertFalse(self.a.reconcile(force=True)["errors"] == [])

    def test_the_sender_survives_an_offline_peer(self):
        """A refused TLS connect used to escape as a raw OSError and kill the
        sender thread — live push then stayed dead until the daemon restarted."""
        self.a.start_sender()
        self.b.stop()
        self.add(self.a_store, "written while beta sleeps")
        time.sleep(0.5)
        self.assertTrue(self.a._sender.is_alive())
        self.b.start()
        later = self.add(self.a_store, "written after beta woke")
        for _ in range(100):
            if self.b_store.records_by_ids([later["id"]]):
                break
            time.sleep(0.05)
        self.assertEqual(self.b_store.count(), 2)

    def test_a_silent_connection_does_not_block_the_listener(self):
        """The handshake used to run in the accept loop, so one idle TCP
        connection froze the listener for everyone."""
        idle = socket.create_connection((self.a.host, self.a.port))
        self.addCleanup(idle.close)
        time.sleep(0.2)
        self.add(self.b_store, "still gets through")
        self.assertEqual(self.b.flush_outbox()["errors"], [])

    def test_paired_nodes_still_converge_over_tls(self):
        self.add(self.a_store, "from the laptop")
        self.add(self.b_store, "from the compute box")
        self.assertConverged()


if __name__ == "__main__":
    unittest.main()
