"""Hardening of the HTTP MCP facade (CSRF / DNS rebinding / token compare) and
required-argument validation in the shared tool dispatcher."""

import http.client
import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from yggdrasil import ygg_http_mcp as http_mcp  # noqa: E402
from yggdrasil import ygg_mcp_server as mcp  # noqa: E402

PING = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})


class HttpFacadeHardeningTests(unittest.TestCase):
    token = "s3cret"

    def setUp(self):
        patches = [mock.patch.object(http_mcp, "TOKEN", self.token),
                   mock.patch.dict("os.environ", {"YGG_MCP_ALLOWED_HOSTS": "ygg.example.com"})]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), http_mcp.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def post(self, headers=None, body=PING):
        h = {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
        h.update(headers or {})
        h = {k: v for k, v in h.items() if v is not None}
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1])
        conn.putrequest("POST", "/mcp", skip_host="Host" in h)
        for k, v in h.items():
            conn.putheader(k, v)
        conn.putheader("Content-Length", str(len(body)))
        conn.endheaders(body.encode())
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, data

    def test_happy_path(self):
        status, _ = self.post()
        self.assertEqual(status, 200)

    def test_bad_token_rejected(self):
        self.assertEqual(self.post({"Authorization": "Bearer nope"})[0], 401)

    def test_a_rejection_is_readable_even_with_a_large_body(self):
        """Rejecting before reading the body closed the socket with data still
        unread, so the kernel answered with a reset and the client saw
        ConnectionResetError instead of the 401 (seen on CI, macOS)."""
        big = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping",
                          "params": {"pad": "x" * 512_000}})
        for headers, code in (({"Authorization": "Bearer nope"}, 401),
                              ({"Origin": "https://evil.example"}, 403),
                              ({"Content-Type": "text/plain"}, 415)):
            with self.subTest(code=code):
                self.assertEqual(self.post(headers, body=big)[0], code)

    def test_text_plain_rejected_415(self):
        status, data = self.post({"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        self.assertIn("error", json.loads(data))

    def test_json_content_type_with_charset_ok(self):
        self.assertEqual(self.post({"Content-Type": "application/json; charset=utf-8"})[0], 200)

    def test_foreign_origin_rejected_403(self):
        status, data = self.post({"Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        self.assertIn("error", json.loads(data))

    def test_loopback_origin_ok(self):
        for origin in ("http://localhost:3000", "http://127.0.0.1", "https://[::1]:8443"):
            self.assertEqual(self.post({"Origin": origin})[0], 200, origin)

    def test_foreign_host_rejected_403(self):
        self.assertEqual(self.post({"Host": "attacker.com:42071"})[0], 403)

    def test_configured_public_host_allowed(self):
        self.assertEqual(self.post({"Host": "ygg.example.com"})[0], 200)
        self.assertEqual(self.post({"Host": "ygg.example.com",
                                    "Origin": "https://ygg.example.com"})[0], 200)

    def test_token_compared_in_constant_time(self):
        with mock.patch.object(http_mcp.hmac, "compare_digest", return_value=True) as cd:
            self.assertEqual(self.post({"Authorization": "Bearer anything"})[0], 200)
        cd.assert_called()


class RequiredArgumentTests(unittest.TestCase):
    def test_every_tool_reports_missing_required(self):
        for tool in mcp.tool_schema():
            for req in tool["inputSchema"].get("required", []):
                with mock.patch.object(mcp, "run_ygg") as run:
                    resp = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                       "params": {"name": tool["name"], "arguments": {}}})
                run.assert_not_called()
                result = resp["result"]
                self.assertTrue(result["isError"], tool["name"])
                self.assertIn(f"missing required argument: {req}",
                              result["content"][0]["text"])
                break

    def test_bootstrap_without_project(self):
        resp = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": "ygg_bootstrap", "arguments": {}}})
        self.assertEqual(resp["result"]["content"][0]["text"],
                         "missing required argument: project")


if __name__ == "__main__":
    unittest.main()
