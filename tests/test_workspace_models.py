from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from yggdrasil.ygg_workspace_chat import ChatService
from yggdrasil import ygg_config as config
from yggdrasil import ygg_workspace_models as models


class CatalogServer:
    def __init__(self, routes):
        self.requests = []
        self.routes = routes
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                owner.requests.append((self.path, self.headers.get("Authorization")))
                status, body, headers = owner.routes.get(self.path, (404, {}, {}))
                if callable(body):
                    body = body()
                raw = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def ok(body):
    return 200, body, {}


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.service = ChatService(self.home, lambda body: {}, "user", "personal")
        self.addCleanup(self.service._db.close)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        for name, value in (("YGG_HOME", self.home), ("CONFIG", self.home / "config.json"),
                            ("SECRET_FILES", {"embed_api_key": self.home / "embed_api_key",
                                              "distill_api_key": self.home / "distill_api_key"})):
            patcher = patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def server(self, routes):
        server = CatalogServer(routes)
        self.addCleanup(server.close)
        return server

    def discover(self, server, provider="openai", **kwargs):
        return models.discover_models({"provider": provider, "url": server.url, **kwargs}, self.service)

    def test_ollama_lists_only_returned_models_and_filters_embedding_family(self):
        server = self.server({"/api/tags": ok({"models": [
            {"name": "qwen3:4b", "size": 1073741824, "details": {"family": "qwen3"}},
            {"name": "custom-vector", "details": {"family": "bert"}},
        ]})})
        result = self.discover(server, "ollama")
        self.assertTrue(result["reachable"])
        self.assertEqual(result["models"], [{"id": "qwen3:4b", "kind": "llm", "size": "1.0 GB"}])
        embedded = self.discover(server, "ollama", purpose="embed")
        self.assertEqual(embedded["models"], [{"id": "custom-vector", "kind": "embed"}])
        self.assertEqual(server.requests, [("/api/tags", None), ("/api/tags", None)])

    def test_lmstudio_returns_installed_unloaded_model_and_respects_explicit_type(self):
        server = self.server({"/api/v0/models": ok({"data": [
            {"id": "qwen3.5-9b", "type": "llm", "state": "not-loaded", "quantization": "Q4_K_M"},
            {"id": "custom-vector", "type": "embeddings", "state": "loaded"},
            {"id": "embed-in-name-but-vision", "type": "vlm"},
        ]})})
        result = self.discover(server, url=server.url + "/v1/", purpose="bg")
        self.assertEqual(result, {"reachable": True, "models": [
            {"id": "qwen3.5-9b", "kind": "llm", "note": "Q4_K_M"},
            {"id": "embed-in-name-but-vision", "kind": "llm"},
        ]})
        self.assertEqual(server.requests, [("/api/v0/models", None)])

    def test_openai_fallback_preserves_unknown_kind_for_either_purpose(self):
        server = self.server({"/v1/models": ok({"data": [
            {"id": "private-model"}, {"id": "nomic-embed-text"},
        ]})})
        chat = self.discover(server)
        self.assertEqual([m["id"] for m in chat["models"]], ["private-model"])
        self.assertEqual(chat["models"][0]["kind"], "unknown")
        self.assertTrue(chat["models"][0]["note"])
        embed = self.discover(server, purpose="embed")
        self.assertEqual([m["id"] for m in embed["models"]], ["private-model", "nomic-embed-text"])
        self.assertEqual(server.requests[:2], [("/api/v0/models", None), ("/v1/models", None)])

    def test_openai_falls_back_when_native_api_is_not_implemented(self):
        server = self.server({"/api/v0/models": (501, {}, {}),
                              "/v1/models": ok({"data": [{"id": "installed"}]})})
        result = self.discover(server)
        self.assertTrue(result["reachable"])
        self.assertEqual([m["id"] for m in result["models"]], ["installed"])

    def test_empty_catalog_is_reachable_without_fallback_or_recommendations(self):
        server = self.server({"/api/v0/models": ok({"data": []})})
        self.assertEqual(self.discover(server), {"models": [], "reachable": True})
        self.assertEqual(server.requests, [("/api/v0/models", None)])

    def test_closed_server_returns_safe_unavailable_result(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        result = models.discover_models({"provider": "ollama", "url": f"http://127.0.0.1:{port}"}, self.service)
        self.assertFalse(result["reachable"])
        self.assertEqual(result["models"], [])
        self.assertTrue(result["error"])
        self.assertNotIn(str(port), result["error"])

    def test_explicit_key_is_transient_and_empty_key_disables_saved_key(self):
        server = self.server({"/api/v0/models": ok({"data": []})})
        self.service.save_settings({"provider": "openai", "url": server.url, "model": "m", "api_key": "saved"})
        self.discover(server, api_key="transient")
        self.discover(server, api_key="")
        self.assertEqual(server.requests, [("/api/v0/models", "Bearer transient"), ("/api/v0/models", None)])
        self.assertEqual(self.service._key(), "saved")

    def test_saved_chat_key_requires_same_endpoint_and_provider(self):
        server = self.server({"/api/v0/models": ok({"data": []}), "/api/tags": ok({"models": []}),
                              "/different/api/v0/models": ok({"data": []})})
        other = self.server({"/api/v0/models": ok({"data": []})})
        self.service.save_settings({"provider": "openai", "url": server.url + "/v1", "model": "m", "api_key": "saved"})
        self.discover(server)
        self.discover(server, "ollama")
        self.discover(server, url=server.url + "/different")
        self.discover(other)
        self.assertEqual(server.requests, [("/api/v0/models", "Bearer saved"), ("/api/tags", None),
                                           ("/different/api/v0/models", None)])
        self.assertEqual(other.requests, [("/api/v0/models", None)])

    def test_concurrent_chat_settings_save_cannot_send_new_key_to_old_endpoint(self):
        server = self.server({"/api/v0/models": ok({"data": []})})
        self.service.save_settings({"provider": "openai", "url": server.url, "model": "m", "api_key": "old-key"})
        read_settings = self.service.settings
        reading = threading.Event()
        updated = threading.Event()
        reader = threading.current_thread()

        def pause_after_read():
            saved = read_settings()
            if threading.current_thread() is reader:
                reading.set()
                updated.wait(0.2)
            return saved

        def change_endpoint():
            if reading.wait(1):
                self.service.save_settings({"provider": "openai", "url": server.url + "/different",
                                            "model": "m", "api_key": "new-endpoint-secret"})
                updated.set()

        writer = threading.Thread(target=change_endpoint, daemon=True)
        with patch.object(self.service, "settings", pause_after_read):
            writer.start()
            result = self.discover(server)
            writer.join(1)
        self.assertTrue(result["reachable"])
        self.assertTrue(updated.is_set())
        self.assertEqual(server.requests, [("/api/v0/models", "Bearer old-key")])

    def test_background_and_embed_keys_are_scoped_to_their_configured_endpoint(self):
        server = self.server({"/api/v0/models": ok({"data": []})})
        other = self.server({"/api/v0/models": ok({"data": []})})
        config.set_value("distill_url", server.url)
        config.set_value("distill_api_key", "background-key")
        config.set_value("embed_url", server.url + "/v1")
        config.set_value("embed_backend", "openai")
        config.set_value("embed_api_key", "embed-key")
        self.discover(server, purpose="bg")
        self.discover(server, purpose="embed")
        self.discover(server, purpose="chat")
        self.discover(other, purpose="bg")
        self.discover(other, purpose="embed")
        self.assertEqual(server.requests, [("/api/v0/models", "Bearer background-key"),
                                           ("/api/v0/models", "Bearer embed-key"), ("/api/v0/models", None)])
        self.assertEqual(other.requests, [("/api/v0/models", None), ("/api/v0/models", None)])

    def test_redirect_is_never_followed_and_never_leaks_key(self):
        target = self.server({"/stolen": ok({"data": []})})
        server = self.server({"/api/v0/models": (302, {}, {"Location": target.url + "/stolen"}),
                              "/v1/models": (307, {}, {"Location": target.url + "/stolen"})})
        result = self.discover(server, api_key="redirect-secret")
        self.assertFalse(result["reachable"])
        self.assertEqual(target.requests, [])
        self.assertNotIn("redirect-secret", json.dumps(result))
        self.assertNotIn(target.url, json.dumps(result))

    def test_provider_error_body_is_never_exposed(self):
        server = self.server({"/api/v0/models": (401, {"error": "secret-body-secret-key"}, {})})
        result = self.discover(server, api_key="secret-key")
        self.assertFalse(result["reachable"])
        self.assertNotIn("secret", json.dumps(result))
        self.assertIn("key", result["error"].lower())

    def test_invalid_requests_do_not_contact_server(self):
        server = self.server({})
        invalid = [None, [], {}, {"provider": "bogus", "url": server.url},
                   {"provider": "openai", "url": server.url, "purpose": "anything"},
                   {"provider": "openai", "url": server.url, "api_key": "bad\r\nkey"},
                   {"provider": "openai", "url": server.url, "api_key": 123}]
        for url in ("", "file:///tmp/models", "ftp://localhost", "http://user:password@localhost",
                    "http://localhost/?key=secret", "http://localhost/#fragment", "http://localhost:99999",
                    "http://local host", "http://localhost\n", "http://[broken", "http://localhost/" + "a" * 2048):
            invalid.append({"provider": "openai", "url": url})
        for body in invalid:
            with self.subTest(body=body), self.assertRaises(ValueError):
                models.discover_models(body, self.service)
        self.assertEqual(server.requests, [])

    def test_malformed_entries_are_skipped_and_duplicate_models_are_collapsed(self):
        server = self.server({"/api/tags": ok({"models": [None, [], {}, {"name": 123},
            {"name": "good", "details": "invalid"}, {"name": "good"},
            {"name": "vector", "details": {"family": 4}}, {"name": "a" * 2001},
        ]})})
        result = self.discover(server, "ollama")
        self.assertTrue(result["reachable"])
        self.assertEqual([m["id"] for m in result["models"]], ["good", "vector"])

    def test_oversized_or_malformed_catalog_returns_safe_error(self):
        for payload in (b"x" * 1048577, b"not-json-secret", {"models": "bad"},
                        {"models": [{"name": str(i)} for i in range(1001)]}):
            with self.subTest(payload_type=type(payload)):
                server = self.server({"/api/tags": ok(payload)})
                result = self.discover(server, "ollama")
                self.assertFalse(result["reachable"])
                self.assertEqual(result["models"], [])
                self.assertNotIn("secret", json.dumps(result))

    def test_invalid_numeric_metadata_does_not_break_a_valid_catalog(self):
        server = self.server({"/api/tags": ok({"models": [
            {"name": "huge", "size": 10 ** 1000},
            {"name": "infinite", "size": float("inf")},
            {"name": "negative", "size": -1},
        ]})})
        result = self.discover(server, "ollama")
        self.assertTrue(result["reachable"])
        self.assertEqual([m["id"] for m in result["models"]], ["huge", "infinite", "negative"])
        self.assertTrue(all("size" not in m for m in result["models"]))

    def test_slow_provider_times_out(self):
        def slow():
            time.sleep(0.2)
            return {"models": []}
        server = self.server({"/api/tags": ok(slow)})
        with patch.object(models, "REQUEST_TIMEOUT", 0.03):
            result = self.discover(server, "ollama")
        self.assertFalse(result["reachable"])


if __name__ == "__main__":
    unittest.main()
