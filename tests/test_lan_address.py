"""Which address a machine advertises to its peers.

Both samples are real: a Mac whose default route goes through a VPN and which
runs OrbStack, and a Linux box with a dozen Docker bridges. On each, the old
guess picked a bridge — an address the other machine cannot reach.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg_memory_server as engine  # noqa: E402
import ygg_sync_peers as peers  # noqa: E402

MAC_IFCONFIG = """\
lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
utun3: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1000
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tinet 192.168.3.151 netmask 0xffffff00 broadcast 192.168.3.255
bridge100: flags=8a63<UP,BROADCAST,SMART,RUNNING,ALLMULTI,SIMPLEX,MULTICAST> mtu 1500
\tinet 192.168.139.3 netmask 0xfffffe00 broadcast 192.168.139.255
bridge101: flags=8a63<UP,BROADCAST,SMART,RUNNING,ALLMULTI,SIMPLEX,MULTICAST> mtu 1500
\tinet 192.168.107.0 netmask 0xffffff00 broadcast 192.168.107.255
utun225: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1500
\tinet 169.254.10.2 --> 169.254.10.1 netmask 0xfffffffc
"""

LINUX_IP = """\
1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever preferred_lft forever
4: br-3eea6ac863cc    inet 192.168.48.1/20 brd 192.168.63.255 scope global br-3eea6ac863cc\\       valid_lft forever
2: enp15s0    inet 192.168.3.150/24 brd 192.168.3.255 scope global dynamic noprefixroute enp15s0\\       valid_lft 68065sec
16: docker0    inet 172.17.0.1/16 brd 172.17.255.255 scope global docker0\\       valid_lft forever
283: happ-xray    inet 172.19.0.1/30 brd 172.19.0.3 scope global happ-xray\\       valid_lft forever
"""


class ParseTest(unittest.TestCase):
    def test_ifconfig_pairs_each_address_with_its_interface(self):
        self.assertEqual(engine._parse_ifconfig(MAC_IFCONFIG), [
            ("lo0", "127.0.0.1"), ("en0", "192.168.3.151"), ("bridge100", "192.168.139.3"),
            ("bridge101", "192.168.107.0"), ("utun225", "169.254.10.2")])

    def test_ip_addr_pairs_each_address_with_its_interface(self):
        self.assertEqual(engine._parse_ip_addr(LINUX_IP), [
            ("lo", "127.0.0.1"), ("br-3eea6ac863cc", "192.168.48.1"),
            ("enp15s0", "192.168.3.150"), ("docker0", "172.17.0.1"),
            ("happ-xray", "172.19.0.1")])


class RankTest(unittest.TestCase):
    def _candidates(self, pairs, probed=()):
        with mock.patch.object(engine, "_interface_addresses", return_value=pairs), \
                mock.patch.object(engine, "_probed_addresses", return_value=list(probed)):
            return engine._private_addresses()

    def test_the_wifi_card_beats_orbstack_bridges_behind_a_vpn(self):
        # What the Mac reported: every route probe answers with the VPN's
        # link-local address, and the hostname resolves to the bridge first.
        got = self._candidates(engine._parse_ifconfig(MAC_IFCONFIG),
                               probed=["169.254.10.2", "192.168.107.0", "192.168.3.151"])
        self.assertEqual(got[0], "192.168.3.151")
        self.assertNotIn("169.254.10.2", got)

    def test_the_ethernet_port_beats_docker_bridges(self):
        got = self._candidates(engine._parse_ip_addr(LINUX_IP))
        self.assertEqual(got[0], "192.168.3.150")

    def test_an_unknown_interface_still_outranks_a_known_bridge(self):
        got = self._candidates([("docker0", "172.17.0.1"), ("happ-xray", "172.19.0.1")])
        self.assertEqual(got, ["172.19.0.1", "172.17.0.1"])

    def test_without_the_os_tools_the_probes_still_answer(self):
        self.assertEqual(self._candidates([], probed=["10.0.0.5"]), ["10.0.0.5"])


class TailscaleTest(unittest.TestCase):
    PAIRS = [("en0", "192.168.3.151"), ("utun4", "100.101.7.12"), ("bridge100", "192.168.139.3")]

    def test_a_tailnet_address_is_a_candidate_but_the_lan_comes_first(self):
        with mock.patch.object(engine, "_interface_addresses", return_value=self.PAIRS), \
                mock.patch.object(engine, "_probed_addresses", return_value=[]):
            got = engine._private_addresses()
        self.assertEqual(got[0], "192.168.3.151")
        self.assertIn("100.101.7.12", got)

    def test_the_tailnet_address_is_found(self):
        with mock.patch.object(engine, "_interface_addresses", return_value=self.PAIRS):
            self.assertEqual(engine._tailscale_address(), "100.101.7.12")

    def test_no_tailnet_no_address(self):
        with mock.patch.object(engine, "_interface_addresses", return_value=self.PAIRS[:1]):
            self.assertIsNone(engine._tailscale_address())

    def test_shared_address_space_outside_the_tailnet_block_is_not_tailscale(self):
        with mock.patch.object(engine, "_interface_addresses",
                               return_value=[("eth0", "100.128.0.1")]):
            self.assertIsNone(engine._tailscale_address())


class PeerRouteTest(unittest.TestCase):
    def test_every_route_to_a_peer_gets_a_listener(self):
        routes = {"192.168.3.150": "192.168.3.151", "100.90.1.2": "100.101.7.12",
                  "192.168.3.160": "192.168.3.151"}
        with mock.patch.object(peers, "route_source", side_effect=routes.get):
            self.assertEqual(engine._listen_addresses(list(routes)),
                             ["192.168.3.151", "100.101.7.12"])

    def test_no_peers_means_one_guessed_address(self):
        with mock.patch.object(engine, "_private_addresses", return_value=["192.168.3.151"]):
            self.assertEqual(engine._listen_addresses([]), ["192.168.3.151"])

    def test_a_known_peer_decides_the_address(self):
        # Guessing is for when there is nobody to ask. Once a peer exists, the
        # routing table already knows which interface reaches it.
        with mock.patch.object(peers, "route_source", return_value="192.168.3.151"), \
                mock.patch.object(engine, "_private_addresses", return_value=["192.168.107.0"]):
            self.assertEqual(engine._lan_address(["192.168.3.150"]), "192.168.3.151")

    def test_an_unroutable_peer_falls_back_to_the_guess(self):
        with mock.patch.object(peers, "route_source", return_value=None), \
                mock.patch.object(engine, "_private_addresses", return_value=["192.168.3.151"]):
            self.assertEqual(engine._lan_address(["192.168.3.150"]), "192.168.3.151")

    def test_route_source_names_the_local_end(self):
        self.assertEqual(peers.route_source("127.0.0.1"), "127.0.0.1")

    def test_route_source_of_garbage_is_none(self):
        self.assertIsNone(peers.route_source("not a host at all"))


if __name__ == "__main__":
    unittest.main()
