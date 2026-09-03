"""Pairing, the peer registry, and the pinned certificate.

The engine has no authorization levels: whoever authenticates can /purge. So
the LAN listener gets its own per-peer keys instead of reusing the local token,
which sits in every agent config on the machine.
"""

import os
import sys
import tempfile
import unittest

# POSIX file modes are the mechanism; on Windows os.chmod only toggles a
# read-only bit, so asserting them there tests the platform, not the code.
POSIX_MODES = os.name == "posix"
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg_sync_peers as peers  # noqa: E402


class CodeTest(unittest.TestCase):
    def test_code_round_trips(self):
        code = peers.make_code("192.168.3.150", 42070, "pid", "s3cret")
        parsed = peers.parse_code(code)
        self.assertEqual((parsed["host"], parsed["port"]), ("192.168.3.150", 42070))
        self.assertEqual((parsed["pairing_id"], parsed["secret"]), ("pid", "s3cret"))

    def test_garbage_is_rejected_not_guessed(self):
        for bad in ("", "http://host/x#y", "ygg://host/x", "ygg://host:notaport/x#y"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                peers.parse_code(bad)

    def test_secrets_are_not_predictable(self):
        self.assertNotEqual(peers.new_secret(), peers.new_secret())
        self.assertGreaterEqual(len(peers.new_secret()), 32)


class PendingPairingTest(unittest.TestCase):
    def setUp(self):
        self.pending = peers.PendingPairings()

    def test_a_code_can_be_redeemed_once(self):
        code = self.pending.issue("h", 1, now=0.0)
        parsed = peers.parse_code(code)
        self.assertTrue(self.pending.redeem(parsed["pairing_id"], parsed["secret"], now=1.0))
        self.assertFalse(self.pending.redeem(parsed["pairing_id"], parsed["secret"], now=2.0))

    def test_a_code_expires(self):
        parsed = peers.parse_code(self.pending.issue("h", 1, now=0.0))
        self.assertFalse(self.pending.redeem(parsed["pairing_id"], parsed["secret"],
                                             now=peers.CODE_TTL + 1))

    def test_a_wrong_secret_is_refused_and_does_not_burn_the_code(self):
        parsed = peers.parse_code(self.pending.issue("h", 1, now=0.0))
        self.assertFalse(self.pending.redeem(parsed["pairing_id"], "wrong", now=1.0))
        self.assertTrue(self.pending.redeem(parsed["pairing_id"], parsed["secret"], now=1.0))

    def test_unknown_pairing_id_is_refused(self):
        self.assertFalse(self.pending.redeem("nope", "s", now=1.0))


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "peers.json"

    def _peer(self, name="box", **kw):
        base = dict(node_id="n-" + name, name=name, url="https://h:42070",
                    key_out="out-" + name, key_in="in-" + name,
                    fingerprint="ff", embed_model="m")
        base.update(kw)
        return base

    def test_state_round_trips_through_disk(self):
        state = peers.blank_state()
        peers.add_peer(state, **self._peer())
        peers.save(state, self.path)
        self.assertEqual(peers.load(self.path)["peers"]["n-box"]["name"], "box")

    @unittest.skipUnless(POSIX_MODES, "file modes are POSIX-only")
    def test_the_file_is_not_world_readable(self):
        """It holds the keys to the whole store."""
        peers.save(peers.blank_state(), self.path)
        self.assertEqual(os.stat(self.path).st_mode & 0o077, 0)

    def test_a_missing_file_is_an_empty_registry_not_an_error(self):
        state = peers.load(self.path)
        self.assertEqual(state["peers"], {})
        self.assertTrue(state["node_id"])

    def test_corrupt_file_does_not_take_the_engine_down(self):
        self.path.write_text("{not json")
        self.assertEqual(peers.load(self.path)["peers"], {})

    def test_node_id_is_stable_across_loads(self):
        first = peers.load(self.path)
        peers.save(first, self.path)
        self.assertEqual(peers.load(self.path)["node_id"], first["node_id"])

    def test_a_presented_key_identifies_exactly_one_peer(self):
        state = peers.blank_state()
        peers.add_peer(state, **self._peer("a"))
        peers.add_peer(state, **self._peer("b"))
        self.assertEqual(peers.authorized(state, "in-a")["name"], "a")
        self.assertIsNone(peers.authorized(state, "in-c"))
        self.assertIsNone(peers.authorized(state, ""))

    def test_revoking_one_peer_leaves_the_others(self):
        state = peers.blank_state()
        peers.add_peer(state, **self._peer("a"))
        peers.add_peer(state, **self._peer("b"))
        self.assertTrue(peers.remove_peer(state, "a"))
        self.assertFalse(peers.remove_peer(state, "a"))
        self.assertEqual(list(state["peers"]), ["n-b"])

    def test_a_peer_can_be_revoked_by_node_id_too(self):
        state = peers.blank_state()
        peers.add_peer(state, **self._peer("a"))
        self.assertTrue(peers.remove_peer(state, "n-a"))


@unittest.skipUnless(peers.openssl_available(), "openssl not on PATH")
class CertificateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)

    def test_a_certificate_is_minted_once_and_reused(self):
        cert, key = peers.ensure_cert(self.home)
        self.assertTrue(cert.exists() and key.exists())
        again = peers.ensure_cert(self.home)
        self.assertEqual((cert, key), again)
        self.assertEqual(peers.cert_fingerprint(cert), peers.cert_fingerprint(cert))

    @unittest.skipUnless(POSIX_MODES, "file modes are POSIX-only")
    def test_the_private_key_is_not_world_readable(self):
        _, key = peers.ensure_cert(self.home)
        self.assertEqual(os.stat(key).st_mode & 0o077, 0)

    def test_fingerprints_differ_between_machines(self):
        first = peers.cert_fingerprint(peers.ensure_cert(self.home)[0])
        other = Path(self._tmp.name) / "second"
        other.mkdir()
        self.assertNotEqual(first, peers.cert_fingerprint(peers.ensure_cert(other)[0]))


if __name__ == "__main__":
    unittest.main()
