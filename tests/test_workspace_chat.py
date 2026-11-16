from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from yggdrasil.ygg_workspace_chat import ChatService


def memory(mid="a1", project="alpha", content="Решение: использовать SQLite"):
    return {"id": mid, "project": project, "content": content, "type": "decision",
            "source": "notes.md", "created_at": 1700000000, "archived": False, "metadata": {}}


class Engine:
    def __init__(self):
        self.items = [memory(), memory("b1", "beta")]
        self.requests = []

    def __call__(self, body):
        self.requests.append(body.copy())
        items = [m for m in self.items if body["project"] is None or m["project"] == body["project"]]
        if body["op"] == "memory":
            found = next((m for m in items if m["id"] == body["id"]), None)
            if not found:
                raise KeyError("Запись не найдена")
            return {"memory": found, "relations": []}
        return {"items": [m for m in items if not m["archived"]]}


class Provider:
    def __init__(self, protocol="ollama", failure=False, partial=False):
        self.requests = []
        self.failure = failure
        self.partial = partial
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append((self.path, body, self.headers.get("Authorization")))
                if owner.failure:
                    self.send_error(503, "secret-provider-error")
                    return
                self.send_response(200)
                self.end_headers()
                if protocol == "ollama":
                    events = [{"message": {"content": "По памяти "}, "done": False},
                              {"message": {"content": "используется SQLite [1]."}, "done": False}]
                    if not owner.partial:
                        events.append({"done": True})
                    payload = "\n".join(json.dumps(e) for e in events) + "\n"
                else:
                    payload = 'data: ' + json.dumps({"choices": [{"delta": {"content": "SQLite [1]."}}]}) + '\n\n'
                    if not owner.partial:
                        payload += 'data: [DONE]\n\n'
                self.wfile.write(payload.encode())

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.engine = Engine()
        self.service = ChatService(self.home, self.engine, "user", "personal")

    def tearDown(self):
        self.service._db.close()

    def test_new_chat_title_is_locale_neutral(self):
        self.assertEqual(self.service.create_chat("alpha")["title"], "")

    def provider(self, **kwargs):
        provider = Provider(**kwargs)
        self.addCleanup(provider.close)
        self.service.save_settings({"provider": kwargs.get("protocol", "ollama"),
                                    "url": provider.url, "model": "local-model"})
        return provider

    def test_persist_chat_and_sources_across_restart(self):
        chat = self.service.create_chat("alpha")
        result = list(self.service.stream(chat["id"], "Какую базу выбрали?"))
        self.assertEqual(result[-1]["message"]["status"], "search_only")
        other = ChatService(self.home, self.engine, "user", "personal")
        self.addCleanup(other._db.close)
        restored = other.get_chat(chat["id"])
        self.assertEqual(restored["chat"]["project"], "alpha")
        self.assertEqual(restored["messages"][0]["content"], "Какую базу выбрали?")
        self.assertEqual([m["id"] for m in restored["messages"][1]["sources"]], ["a1"])

    def test_identity_cannot_read_or_delete_another_users_chat(self):
        chat = self.service.create_chat("alpha")
        other = ChatService(self.home, self.engine, "someone-else", "personal")
        self.addCleanup(other._db.close)
        self.assertEqual(other.list_chats("alpha"), {"chats": []})
        with self.assertRaises(KeyError):
            other.get_chat(chat["id"])
        with self.assertRaises(KeyError):
            other.delete_chat(chat["id"])
        self.assertEqual(self.service.get_chat(chat["id"])["chat"]["id"], chat["id"])

    def test_namespace_isolation(self):
        chat = self.service.create_chat("alpha")
        other = ChatService(self.home, self.engine, "user", "work")
        self.addCleanup(other._db.close)
        with self.assertRaises(KeyError):
            other.get_chat(chat["id"])

    def test_project_and_global_dialogs_have_separate_lists(self):
        alpha = self.service.create_chat("alpha")
        global_chat = self.service.create_chat(None)
        no_project = self.service.create_chat("")
        self.assertEqual([c["id"] for c in self.service.list_chats("alpha")["chats"]], [alpha["id"]])
        self.assertEqual([c["id"] for c in self.service.list_chats(None)["chats"]], [global_chat["id"]])
        self.assertEqual([c["id"] for c in self.service.list_chats("")["chats"]], [no_project["id"]])

    def test_global_chat_retrieves_multiple_projects(self):
        chat = self.service.create_chat(None)
        events = list(self.service.stream(chat["id"], "Сравни решения"))
        self.assertEqual({s["project"] for s in events[0]["sources"]}, {"alpha", "beta"})

    def test_empty_search_never_calls_provider(self):
        provider = self.provider()
        self.engine.items = []
        chat = self.service.create_chat("alpha")
        events = list(self.service.stream(chat["id"], "Что выбрано?"))
        self.assertEqual(provider.requests, [])
        self.assertIn("не найдено", events[-1]["message"]["content"])
        self.assertEqual(events[-1]["message"]["sources"], [])

    def test_attachment_rejects_other_project_or_archived_memory(self):
        with self.assertRaises((KeyError, ValueError)):
            self.service.create_chat("alpha", "b1")
        self.engine.items[0]["archived"] = True
        with self.assertRaises((KeyError, ValueError)):
            self.service.create_chat("alpha", "a1")

    def test_attachment_survives_search_miss_but_not_deletion(self):
        chat = self.service.create_chat("alpha", "a1")
        events = list(self.service.stream(chat["id"], "Объясни это решение"))
        self.assertEqual(events[0]["sources"][0]["id"], "a1")
        self.engine.items = []
        events = list(self.service.stream(chat["id"], "Что ещё?"))
        self.assertEqual(events[-1]["message"]["sources"], [])

    def test_server_drops_out_of_scope_search_results(self):
        chat = self.service.create_chat("alpha")
        self.service.query = lambda body: {"items": [memory(), memory("b1", "beta")]}
        events = list(self.service.stream(chat["id"], "База"))
        self.assertEqual([m["id"] for m in events[0]["sources"]], ["a1"])

    def test_ollama_stream_uses_saved_scope_and_sources(self):
        provider = self.provider()
        chat = self.service.create_chat("alpha")
        events = list(self.service.stream(chat["id"], "Какую базу выбрали?"))
        self.assertEqual(events[-1]["message"]["status"], "complete")
        self.assertEqual(events[-1]["message"]["content"], "По памяти используется SQLite [1].")
        path, body, _ = provider.requests[0]
        self.assertEqual(path, "/api/chat")
        self.assertTrue(body["stream"])
        prompt = json.dumps(body["messages"], ensure_ascii=False)
        self.assertIn("SQLite", prompt)
        self.assertNotIn('"beta"', prompt)
        self.assertTrue(all(r["project"] == "alpha" for r in self.engine.requests))

    def test_openai_stream_normalizes_v1_base_and_private_key(self):
        provider = self.provider(protocol="openai")
        public = self.service.save_settings({"provider": "openai", "url": provider.url + "/v1/",
                                             "model": "model", "api_key": "secret-test-key"})
        chat = self.service.create_chat("alpha")
        events = list(self.service.stream(chat["id"], "База?"))
        self.assertEqual(events[-1]["message"]["status"], "complete")
        self.assertEqual(provider.requests[0][0], "/v1/chat/completions")
        self.assertEqual(provider.requests[0][2], "Bearer secret-test-key")
        self.assertNotIn("secret-test-key", json.dumps(public))
        self.assertTrue(public["has_key"])

    def test_provider_failure_retains_sources_and_redacts_error(self):
        self.provider(failure=True)
        chat = self.service.create_chat("alpha")
        events = list(self.service.stream(chat["id"], "База?"))
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(events[-1]["message"]["status"], "error")
        self.assertEqual(len(events[-1]["message"]["sources"]), 1)
        self.assertNotIn("secret-provider-error", json.dumps(events))

    def test_incomplete_provider_stream_is_not_success(self):
        self.provider(partial=True)
        chat = self.service.create_chat("alpha")
        events = list(self.service.stream(chat["id"], "База?"))
        self.assertEqual(events[-1]["message"]["status"], "error")
        self.assertIn("SQLite", events[-1]["message"]["content"])

    def test_stop_preserves_partial_answer(self):
        self.provider()
        chat = self.service.create_chat("alpha")
        stream = self.service.stream(chat["id"], "База?")
        self.assertEqual(next(stream)["type"], "sources")
        delta = next(stream)
        self.assertEqual(delta["type"], "delta")
        self.service.stop(chat["id"])
        final = list(stream)[-1]
        self.assertEqual(final["message"]["status"], "stopped")
        self.assertEqual(final["message"]["content"], delta["text"])

    def test_disconnect_keeps_partial_and_allows_next_request(self):
        self.provider()
        chat = self.service.create_chat("alpha")
        stream = self.service.stream(chat["id"], "База?")
        next(stream)
        next(stream)
        stream.close()
        saved = self.service.get_chat(chat["id"])["messages"][-1]
        self.assertEqual(saved["status"], "stopped")
        self.assertEqual(saved["content"], "По памяти ")
        events = list(self.service.stream(chat["id"], "Повтори"))
        self.assertEqual(events[-1]["message"]["status"], "complete")

    def test_same_chat_rejects_overlapping_generation(self):
        self.provider()
        chat = self.service.create_chat("alpha")
        first = self.service.stream(chat["id"], "Первый вопрос")
        next(first)
        with self.assertRaises(RuntimeError):
            next(self.service.stream(chat["id"], "Второй вопрос"))
        first.close()
        self.assertEqual(len(self.service.get_chat(chat["id"])["messages"]), 2)

    def test_delete_removes_history(self):
        chat = self.service.create_chat("alpha")
        list(self.service.stream(chat["id"], "База?"))
        self.assertEqual(self.service.delete_chat(chat["id"]), {"ok": True})
        with self.assertRaises(KeyError):
            self.service.get_chat(chat["id"])
        self.assertEqual(self.service.list_chats("alpha"), {"chats": []})

    def test_followup_uses_bounded_previous_questions(self):
        provider = self.provider()
        chat = self.service.create_chat("alpha")
        list(self.service.stream(chat["id"], "Какую базу выбрали?"))
        list(self.service.stream(chat["id"], "Почему?"))
        self.assertIn("Какую базу выбрали?", self.engine.requests[-1]["query"])
        self.assertIn("Почему?", provider.requests[-1][1]["messages"][-1]["content"])

    def test_context_is_bounded_and_truncation_reported(self):
        provider = self.provider()
        self.engine.items = [memory(str(i), "alpha", "данные " * 5000) for i in range(20)]
        chat = self.service.create_chat("alpha")
        events = list(self.service.stream(chat["id"], "Что известно?"))
        self.assertTrue(events[0]["truncated"])
        self.assertTrue(events[-1]["message"]["truncated"])
        self.assertLess(len(json.dumps(provider.requests[0][1]["messages"], ensure_ascii=False)), 25000)

    def test_settings_are_opt_in_and_secrets_remain_separate(self):
        self.assertFalse(self.service.settings()["configured"])
        self.service.save_settings({"provider": "ollama", "url": "http://localhost:11434", "model": "qwen", "api_key": "private-key"})
        self.service.save_settings({"provider": "ollama", "url": "http://localhost:11434", "model": "qwen-new"})
        self.assertTrue(self.service.settings()["has_key"])
        for file in self.home.glob("*.json"):
            self.assertNotIn("private-key", file.read_text())
        secret = self.home / "workspace_chat_key"
        self.assertEqual(secret.read_text(), "private-key")
        if os.name != "nt":
            self.assertEqual(secret.stat().st_mode & 0o777, 0o600)
        self.service.save_settings({"provider": "ollama", "url": "http://localhost:11434", "model": "qwen", "api_key": ""})
        self.assertFalse(self.service.settings()["has_key"])

    def test_changing_provider_endpoint_does_not_reuse_another_servers_key(self):
        self.service.save_settings({"provider":"openai", "url":"http://localhost:1234", "model":"a", "api_key":"only-server-a"})
        self.service.save_settings({"provider":"openai", "url":"http://localhost:1235", "model":"b"})
        self.assertFalse(self.service.settings()["has_key"])
        self.service.save_settings({"provider":"openai", "url":"http://localhost:1236", "model":"c", "api_key":"server-c"})
        self.assertEqual(self.service._key(), "server-c")

    def test_error_explanation_survives_reload(self):
        self.provider(failure=True)
        chat = self.service.create_chat("alpha")
        events = list(self.service.stream(chat["id"], "База?"))
        saved = self.service.get_chat(chat["id"])["messages"][-1]
        self.assertEqual(saved["content"], events[-1]["error"])
        self.assertEqual(saved["status"], "error")

    def test_stop_before_generation_does_not_contact_model(self):
        provider = self.provider()
        chat = self.service.create_chat("alpha")
        stream = self.service.stream(chat["id"], "База?")
        next(stream)
        self.service.stop(chat["id"])
        self.assertEqual(list(stream)[-1]["message"]["status"], "stopped")
        self.assertEqual(provider.requests, [])

    def test_invalid_settings_and_messages_do_not_persist(self):
        for url in ["file:///etc/passwd", "http://user:password@host", "https://host/?key=secret", "https://host/#key"]:
            with self.assertRaises(ValueError):
                self.service.save_settings({"provider": "ollama", "url": url, "model": "qwen"})
        chat = self.service.create_chat("alpha")
        for content in ["", "   ", None, "x" * 8001]:
            with self.assertRaises(ValueError):
                list(self.service.stream(chat["id"], content))
        self.assertEqual(self.service.get_chat(chat["id"])["messages"], [])


if __name__ == "__main__":
    unittest.main()
