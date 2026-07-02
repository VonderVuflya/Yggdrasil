from __future__ import annotations

import os
import sys, pathlib
import tempfile
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "yggdrasil"))

from ygg_memory_server import MemoryStore, tokenize  # noqa: E402


class MemoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(prefix="ygg-memory-", suffix=".sqlite", delete=False)
        self.db_path = handle.name
        handle.close()
        self.store = MemoryStore(self.db_path)

    def tearDown(self) -> None:
        self.store._conn.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self.db_path + suffix)
            except FileNotFoundError:
                pass

    def add_memory(
        self,
        content: str,
        *,
        user_id: str = "user-1",
        namespace: str = "default",
        scope: str = "global",
        metadata: dict | None = None,
    ) -> dict:
        return self.store.add(
            content=content,
            user_id=user_id,
            namespace=namespace,
            scope=scope,
            metadata=metadata or {},
        )

    def test_add_returns_record_with_id_and_add_event(self) -> None:
        record = self.add_memory("Remember the bridge design", metadata={"importance": 0.8})

        self.assertIsInstance(record["id"], str)
        self.assertTrue(record["id"])
        self.assertEqual(record["event"], "ADD")
        self.assertEqual(record["memory"], "Remember the bridge design")
        self.assertEqual(record["content"], "Remember the bridge design")
        self.assertIsInstance(record["metadata"], dict)
        self.assertIs(record["archived"], False)
        self.assertIn("created_at", record)
        self.assertEqual(record["importance"], 0.8)

    def test_add_does_not_dedupe_identical_content(self) -> None:
        first = self.add_memory("Identical memory")
        second = self.add_memory("Identical memory")

        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(self.store.count(), 2)

    def test_get_all_filters_namespace_limits_and_includes_archived(self) -> None:
        first = self.add_memory("First n1 memory", namespace="n1")
        second = self.add_memory("Second n1 memory", namespace="n1")
        self.add_memory("Other namespace memory", namespace="n2")
        self.store.update(second["id"], data=None, metadata_patch=None, archived=True)

        limited = self.store.get_all(user_id="user-1", limit=1, namespace=None)
        self.assertEqual([record["id"] for record in limited], [first["id"]])

        n1_records = self.store.get_all(user_id="user-1", limit=10, namespace="n1")
        self.assertEqual([record["id"] for record in n1_records], [first["id"], second["id"]])
        self.assertTrue(n1_records[1]["archived"])

    def test_search_finds_overlapping_terms_and_returns_positive_score(self) -> None:
        record = self.add_memory("Apollo search index keeps useful lexical memories")

        results = self.store.search(
            query="lexical memories",
            user_id="user-1",
            limit=5,
            filters={},
            namespaces=None,
        )

        self.assertEqual(results[0]["id"], record["id"])
        self.assertIsInstance(results[0]["score"], float)
        self.assertGreater(results[0]["score"], 0.0)

    def test_search_project_filter_isolates_records(self) -> None:
        self.add_memory("Project alpha stores launch notes", metadata={"project": "a"})

        results = self.store.search(
            query="launch notes",
            user_id="user-1",
            limit=5,
            filters={"project": "b"},
            namespaces=None,
        )

        self.assertEqual(results, [])

    def test_search_namespace_filter_isolates_records(self) -> None:
        self.add_memory("Namespace one stores deploy notes", namespace="n1")

        results = self.store.search(
            query="deploy notes",
            user_id="user-1",
            limit=5,
            filters={},
            namespaces=["n2"],
        )

        self.assertEqual(results, [])

    def test_search_excludes_archived_records(self) -> None:
        record = self.add_memory("Archived memories should not be searchable")
        self.store.update(record["id"], data=None, metadata_patch=None, archived=True)

        results = self.store.search(
            query="archived searchable",
            user_id="user-1",
            limit=5,
            filters={},
            namespaces=None,
        )

        self.assertEqual(results, [])

    def test_update_replaces_content_and_merges_metadata_patch(self) -> None:
        record = self.add_memory(
            "Old searchable content",
            metadata={"project": "alpha", "source": "seed"},
        )

        updated = self.store.update(
            record["id"],
            data="New searchable content",
            metadata_patch={"type": "lesson"},
            archived=None,
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated["content"], "New searchable content")
        self.assertEqual(updated["memory"], "New searchable content")
        self.assertEqual(updated["metadata"]["project"], "alpha")
        self.assertEqual(updated["metadata"]["source"], "seed")
        self.assertEqual(updated["metadata"]["type"], "lesson")

        stored = self.store.get_all(user_id="user-1", limit=10, namespace=None)
        self.assertEqual(stored[0]["content"], "New searchable content")

    def test_update_archived_sets_top_level_flag_and_metadata_status(self) -> None:
        record = self.add_memory("Archive status override", metadata={"status": "active"})

        updated = self.store.update(record["id"], data=None, metadata_patch=None, archived=True)

        self.assertIsNotNone(updated)
        self.assertIs(updated["archived"], True)
        self.assertEqual(updated["metadata"]["status"], "archived")

    def test_search_empty_query_returns_empty_list(self) -> None:
        self.add_memory("Empty query should not match anything")

        self.assertEqual(
            self.store.search(query="", user_id="user-1", limit=5, filters={}, namespaces=None),
            [],
        )
        self.assertEqual(
            self.store.search(query="   ", user_id="user-1", limit=5, filters={}, namespaces=None),
            [],
        )

    def test_record_access_increments_count_and_timestamp(self) -> None:
        rec = self.add_memory("Usage logging target memory")
        before = self.store.get_all(user_id="user-1", limit=10, namespace=None)[0]
        self.assertEqual(before["access_count"], 0)
        self.assertIsNone(before["last_accessed_at"])

        self.store.record_access([rec["id"]])
        self.store.record_access([rec["id"]])

        after = self.store.get_all(user_id="user-1", limit=10, namespace=None)[0]
        self.assertEqual(after["access_count"], 2)
        self.assertIsNotNone(after["last_accessed_at"])

    def test_usage_boost_ranks_frequently_accessed_higher(self) -> None:
        a = self.add_memory("alpha beta gamma delta")
        b = self.add_memory("alpha epsilon zeta eta")

        # Frequently recall b — the usage signal should lift it above the tie.
        for _ in range(10):
            self.store.record_access([b["id"]])

        results = self.store.search(
            query="alpha", user_id="user-1", limit=5, filters={}, namespaces=None
        )
        self.assertEqual({r["id"] for r in results}, {a["id"], b["id"]})
        self.assertEqual(results[0]["id"], b["id"])

    def test_search_is_side_effect_free(self) -> None:
        # search() must not log access (keeps the eval harness deterministic);
        # only record_access — called by the HTTP layer — bumps the counter.
        self.add_memory("side effect free search memory")
        self.store.search(query="search memory", user_id="user-1", limit=5, filters={}, namespaces=None)
        stored = self.store.get_all(user_id="user-1", limit=10, namespace=None)[0]
        self.assertEqual(stored["access_count"], 0)
        self.assertIsNone(stored["last_accessed_at"])

    def test_pinned_memory_ranks_above_equal_unpinned(self) -> None:
        a = self.add_memory("alpha beta gamma delta")
        b = self.add_memory("alpha epsilon zeta eta")
        self.store.update(b["id"], data=None, metadata_patch={"pinned": True}, archived=None)

        results = self.store.search(
            query="alpha", user_id="user-1", limit=5, filters={}, namespaces=None
        )
        self.assertEqual({r["id"] for r in results}, {a["id"], b["id"]})
        self.assertEqual(results[0]["id"], b["id"])
        self.assertTrue(results[0]["pinned"])

    def test_search_filters_by_tag(self) -> None:
        self.add_memory("alpha tagged memory", metadata={"tags": ["urgent", "db"]})
        self.add_memory("alpha untagged memory")

        tagged = self.store.search(
            query="alpha", user_id="user-1", limit=5, filters={"tag": "urgent"}, namespaces=None
        )
        self.assertEqual(len(tagged), 1)
        self.assertIn("urgent", tagged[0]["metadata"].get("tags", []))

        none = self.store.search(
            query="alpha", user_id="user-1", limit=5, filters={"tag": "missing"}, namespaces=None
        )
        self.assertEqual(none, [])

    def test_tokenize_lowercases_and_drops_stopwords_and_one_char_tokens(self) -> None:
        self.assertEqual(tokenize("The A QUICK x fox"), ["quick", "fox"])

    def test_secret_guard_flags_structured_tokens_only(self) -> None:
        from ygg_memory_server import looks_like_secret
        # real credentials -> flagged
        self.assertIsNotNone(looks_like_secret("aws key AKIAIOSFODNN7EXAMPLE in config"))
        self.assertIsNotNone(looks_like_secret("token ghp_1234567890abcdefghijklmnopqrstuv"))
        self.assertIsNotNone(looks_like_secret("glpat-abcdef1234567890XYZ_"))
        self.assertIsNotNone(looks_like_secret("Authorization: Bearer eyJhbGciOiJIUzI1Niedd.eyJzdWIiOiIxMjM0NTY.abcdef"))
        self.assertIsNotNone(looks_like_secret("-----BEGIN OPENSSH PRIVATE KEY-----"))
        # legitimate memory content that merely MENTIONS secrets -> NOT flagged
        self.assertIsNone(looks_like_secret("the fix was to rotate the signing secret and redeploy"))
        self.assertIsNone(looks_like_secret("store the password hash, never the plaintext password"))

    def test_tokenize_handles_cyrillic(self) -> None:
        # The FTS index uses unicode61 (indexes Cyrillic fine); the query-side
        # tokenizer must not silently drop non-Latin words.
        self.assertEqual(tokenize("исправил Баг в парсере"), ["исправил", "баг", "парсере"])

    def test_tokenize_splits_snake_case(self) -> None:
        self.assertEqual(tokenize("retry_backoff limit"), ["retry", "backoff", "limit"])

    def test_search_finds_cyrillic_content_lexically(self) -> None:
        record = self.add_memory("исправил баг в парсере вакансий — дедупликация по хэшу")

        results = self.store.search(
            query="баг парсере",
            user_id="user-1",
            limit=5,
            filters={},
            namespaces=None,
        )

        self.assertEqual([r["id"] for r in results], [record["id"]])
        self.assertGreater(results[0]["score"], 0.0)

    def test_get_by_id_returns_record_or_none(self) -> None:
        record = self.add_memory("Lookup me directly by id")

        found = self.store.get_by_id(record["id"])
        self.assertIsNotNone(found)
        self.assertEqual(found["content"], "Lookup me directly by id")
        self.assertIsNone(self.store.get_by_id("ygg_does_not_exist"))

    def test_delete_by_id_removes_row_and_fts_entry(self) -> None:
        record = self.add_memory("deletable secret leaked accidentally")

        self.assertTrue(self.store.delete_by_id(record["id"]))
        self.assertFalse(self.store.delete_by_id(record["id"]))  # already gone
        self.assertEqual(self.store.count(), 0)
        self.assertEqual(
            self.store.search(query="deletable secret", user_id="user-1", limit=5, filters={}, namespaces=None),
            [],
        )

    def test_purge_filters_dry_run_and_deletes(self) -> None:
        self.add_memory("seed lesson one", metadata={"project": "p", "source": "seed-claude"})
        self.add_memory("seed lesson two", metadata={"project": "p", "source": "seed-claude"})
        keeper = self.add_memory("hand-written keeper", metadata={"project": "p", "source": "ygg-cli"})

        preview = self.store.purge(user_id="user-1", source="seed-claude", dry_run=True)
        self.assertEqual(preview, 2)
        self.assertEqual(self.store.count(), 3)  # dry run deletes nothing

        deleted = self.store.purge(user_id="user-1", source="seed-claude")
        self.assertEqual(deleted, 2)
        self.assertEqual(self.store.count(), 1)
        remaining = self.store.get_all(user_id="user-1", limit=10, namespace=None)
        self.assertEqual([r["id"] for r in remaining], [keeper["id"]])
        # FTS agrees: purged rows are unsearchable, the keeper still matches.
        self.assertEqual(
            self.store.search(query="seed lesson", user_id="user-1", limit=5, filters={}, namespaces=None),
            [],
        )

    def test_update_content_refreshes_content_hash(self) -> None:
        import hashlib

        old_hash = hashlib.sha256(b"old content for hashing").hexdigest()
        record = self.add_memory(
            "old content for hashing",
            metadata={"project": "p", "type": "lesson", "content_hash": old_hash},
        )

        self.store.update(record["id"], data="new content after edit", metadata_patch=None, archived=None)

        new_hash = hashlib.sha256(b"new content after edit").hexdigest()
        # The dedup index must see the NEW hash (and the old one must be free again).
        self.assertIsNotNone(
            self.store.find_by_hash(user_id="user-1", project="p", memory_type="lesson", content_hash=new_hash)
        )
        self.assertIsNone(
            self.store.find_by_hash(user_id="user-1", project="p", memory_type="lesson", content_hash=old_hash)
        )


if __name__ == "__main__":
    unittest.main()
