"""What `ygg link` tells the user — the part that used to say ✓ while nothing
arrived on the other machine."""

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg_link  # noqa: E402


class FirewallHintTest(unittest.TestCase):
    def test_ufw_gets_a_rule_scoped_to_the_peer(self):
        hint = ygg_link.firewall_hint(42070, "192.168.3.151", firewall="ufw")
        self.assertIn("sudo ufw allow from 192.168.3.151 to any port 42070 proto tcp", hint)

    def test_firewalld_gets_a_rich_rule(self):
        hint = ygg_link.firewall_hint(42070, "192.168.3.151", firewall="firewalld")
        self.assertIn("firewall-cmd", hint)
        self.assertIn("192.168.3.151", hint)

    def test_windows_gets_netsh(self):
        hint = ygg_link.firewall_hint(42070, "10.0.0.2", firewall="windows")
        self.assertIn("netsh advfirewall", hint)
        self.assertIn("localport=42070", hint)

    def test_macos_points_at_the_settings(self):
        self.assertIn("Firewall", ygg_link.firewall_hint(42070, "10.0.0.2", firewall="macos"))

    def test_unknown_still_names_port_and_peer(self):
        hint = ygg_link.firewall_hint(42070, "10.0.0.2", firewall=None)
        self.assertIn("42070", hint)
        self.assertIn("10.0.0.2", hint)


class FailureAdviceTest(unittest.TestCase):
    def test_a_timeout_looks_like_a_firewall(self):
        self.assertEqual(ygg_link.failure_cause("https://h:42070: timed out"), "firewall")

    def test_refused_means_nothing_listens_there(self):
        """Seen live: the daemon on the other box was stopped and the old hint
        told the user to open a firewall that was not the problem."""
        self.assertEqual(ygg_link.failure_cause("[Errno 61] Connection refused"), "down")

    def test_no_route_is_the_network(self):
        self.assertEqual(ygg_link.failure_cause("[Errno 65] No route to host"), "network")

    def test_anything_else_gets_no_guess(self):
        self.assertIsNone(ygg_link.failure_cause("/sync/push -> HTTP 401: unpaired"))


class PeerStateTest(unittest.TestCase):
    def test_never_contacted(self):
        self.assertEqual(ygg_link.peer_state(None)[0], "idle")

    def test_delivered(self):
        kind, text = ygg_link.peer_state({"ok_at": time.time(), "error": None, "backlog": 0})
        self.assertEqual(kind, "ok")
        self.assertIn("delivered", text)

    def test_an_error_after_the_last_success_is_a_failure(self):
        now = time.time()
        kind, text = ygg_link.peer_state({"ok_at": now - 600, "error": "timed out",
                                          "error_at": now, "backlog": 3})
        self.assertEqual(kind, "fail")
        self.assertIn("timed out", text)
        self.assertIn("3 waiting", text)

    def test_a_success_after_an_old_error_is_healthy(self):
        now = time.time()
        kind, _ = ygg_link.peer_state({"ok_at": now, "error": None, "error_at": now - 600,
                                       "backlog": 0})
        self.assertEqual(kind, "ok")

    def test_waiting_changes_are_never_shown_as_healthy(self):
        """The ufw night: ✓ on the list, three writes queued and going nowhere."""
        kind, text = ygg_link.peer_state({"ok_at": None, "error": None, "heard_at": time.time(),
                                          "backlog": 3})
        self.assertNotEqual(kind, "ok")
        self.assertIn("3 waiting", text)


if __name__ == "__main__":
    unittest.main()
