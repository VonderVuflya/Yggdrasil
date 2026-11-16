"""git-backed sync: the deterministic merge policy, file rendering, and the
engine's id-preserving upsert (the git glue is exercised end-to-end manually)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg_sync  # noqa: E402
import ygg_sync_merge  # noqa: E402
from ygg_memory_server import MemoryStore  # noqa: E402


def _rec(**kw):
    base = {"id": "ygg_x", "user_id": "u", "namespace": "n", "scope": "project",
            "project": "p", "type": "lesson", "content": "a fact",
            "content_hash": "h", "source": "s", "confidence": None,
            "importance": 0.5, "created_at": 1.0, "archived": 0,
            "metadata_json": "{}"}
    base.update(kw)
    return base


class MergeMemoryTest(unittest.TestCase):
    def test_archive_anywhere_holds_everywhere(self):
        self.assertEqual(ygg_sync.merge_memory(_rec(archived=1), _rec(archived=0))["archived"], 1)
        self.assertEqual(ygg_sync.merge_memory(_rec(archived=0), _rec(archived=1))["archived"], 1)

    def test_longer_content_wins_and_equal_lengths_tie_break_by_value(self):
        m = ygg_sync.merge_memory(_rec(content="short", content_hash="hl"),
                                  _rec(content="a much longer edited fact", content_hash="hr"))
        self.assertEqual(m["content"], "a much longer edited fact")
        self.assertEqual(m["content_hash"], "hr")
        # Equal lengths used to resolve to "local". That made the result depend on
        # which side was merging, so two machines each kept their own text and the
        # stores never converged — harmless while sync was a manual git command,
        # fatal for a live uplink. The tie-break now looks only at the values.
        a, b = _rec(content="local", content_hash="hl"), _rec(content="remot", content_hash="hr")
        self.assertEqual(ygg_sync.merge_memory(dict(a), dict(b)),
                         ygg_sync.merge_memory(dict(b), dict(a)))

    def test_confidence_max_and_pinned_or(self):
        m = ygg_sync.merge_memory(
            _rec(confidence=0.9, metadata_json=json.dumps({"pinned": True})),
            _rec(confidence=0.6, metadata_json=json.dumps({"tags": ["x"]})))
        self.assertEqual(m["confidence"], 0.9)
        md = json.loads(m["metadata_json"])
        self.assertTrue(md["pinned"])
        self.assertEqual(md["tags"], ["x"])   # union keeps remote-only keys


class RenderTest(unittest.TestCase):
    def test_memory_render_is_deterministic(self):
        a = ygg_sync.render_memory(_rec())
        b = ygg_sync.render_memory(dict(reversed(list(_rec().items()))))
        self.assertEqual(a, b)                # key order can't leak into bytes
        self.assertTrue(a.endswith("\n"))

    def test_relations_sorted_unique_and_conflict_tolerant(self):
        rels = [{"from_id": "b", "to_id": "a", "rel_type": "SOLVES"},
                {"from_id": "b", "to_id": "a", "rel_type": "SOLVES"},
                {"from_id": "a", "to_id": "c", "rel_type": "CONTRADICTS"}]
        body = ygg_sync.render_relations(rels)
        self.assertEqual(len(body.strip().splitlines()), 2)   # deduped
        parsed = ygg_sync.parse_relations("<<<<<<< ours\n" + body + ">>>>>>> theirs\n")
        self.assertEqual(len(parsed), 2)                      # markers tolerated


class TombstoneFileTest(unittest.TestCase):
    def test_merge_is_per_id_min_and_commutative(self):
        a, b = {"x": 5.0, "y": 9.0}, {"x": 3.0, "z": 1.0}
        self.assertEqual(ygg_sync.merge_tombstones(a, b), {"x": 3.0, "y": 9.0, "z": 1.0})
        self.assertEqual(ygg_sync.merge_tombstones(a, b), ygg_sync.merge_tombstones(b, a))

    def test_render_is_sorted_and_parse_tolerates_garbage(self):
        body = ygg_sync.render_tombstones({"b": 2.0, "a": 1.0})
        self.assertLess(body.index('"a"'), body.index('"b"'))
        self.assertEqual(ygg_sync.parse_tombstones(body), {"a": 1.0, "b": 2.0})
        self.assertEqual(ygg_sync.parse_tombstones("<<<<<<< nope"), {})
        self.assertEqual(ygg_sync.parse_tombstones('{"a": "bad", "b": 2}'), {"b": 2.0})


class ExportTombstoneTest(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())

    def _data(self, mems, tombs):
        return {"memories": mems, "relations": [], "tombstones": tombs}

    def test_export_writes_tombstones_and_removes_files(self):
        now = 1_000_000.0
        ygg_sync._export(self.repo, self._data([_rec(id="ygg_keep"), _rec(id="ygg_dead")], {}), now=now)
        self.assertTrue((self.repo / "memories" / "ygg_dead.json").exists())
        ygg_sync._export(self.repo, self._data([_rec(id="ygg_keep")], {"ygg_dead": now - 10}), now=now)
        self.assertFalse((self.repo / "memories" / "ygg_dead.json").exists())
        self.assertTrue((self.repo / "memories" / "ygg_keep.json").exists())
        got = ygg_sync.parse_tombstones((self.repo / "tombstones.json").read_text())
        self.assertEqual(got, {"ygg_dead": now - 10})

    def test_export_unions_repo_tombstones_and_removes_their_files(self):
        now = 1_000_000.0
        (self.repo / "tombstones.json").write_text(ygg_sync.render_tombstones({"ygg_theirs": now - 5}))
        (self.repo / "memories").mkdir()
        (self.repo / "memories" / "ygg_theirs.json").write_text("{}")
        ygg_sync._export(self.repo, self._data([], {"ygg_mine": now - 7}), now=now)
        got = ygg_sync.parse_tombstones((self.repo / "tombstones.json").read_text())
        self.assertEqual(set(got), {"ygg_theirs", "ygg_mine"})
        self.assertFalse((self.repo / "memories" / "ygg_theirs.json").exists())

    def test_expired_tombstones_are_dropped_from_file(self):
        now = 1_000_000_000.0
        old = now - ygg_sync_merge.TOMBSTONE_TTL - 1
        ygg_sync._export(self.repo, self._data([], {"ygg_old": old, "ygg_new": now - 1}), now=now)
        got = ygg_sync.parse_tombstones((self.repo / "tombstones.json").read_text())
        self.assertEqual(set(got), {"ygg_new"})


class GitTransportDeleteTest(unittest.TestCase):
    """Two machines + a bare repo, driven through the real sync() flow with the
    engine HTTP calls routed to in-process stores."""

    def _run(self, store, repo):
        def fake(method, path, body=None):
            if path == "/sync_export":
                exp = store.sync_export()
                exp["tombstones"] = store.tombstones()
                return {"data": exp}
            tombs = body.get("tombstones") or {}
            if tombs:
                got = store.apply_remote(memories=body["memories"], tombstones=tombs,
                                         relations=body.get("relations"))
            else:
                got = store.sync_upsert(body["memories"], body.get("relations"))
            return {"data": got}
        old = ygg_sync.request_json
        ygg_sync.request_json = fake
        try:
            import argparse, contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ygg_sync.sync(argparse.Namespace(repo=str(repo))), 0)
        finally:
            ygg_sync.request_json = old

    def test_delete_propagates_and_does_not_resurrect(self):
        import subprocess
        from unittest import mock
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        bare = root / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
        env = mock.patch.dict("os.environ", {
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
        env.start()
        self.addCleanup(env.stop)
        a_repo, b_repo = root / "a", root / "b"
        a = MemoryStore(db_path=str(root / "a.sqlite"))
        b = MemoryStore(db_path=str(root / "b.sqlite"))
        self.addCleanup(b.close)
        self.addCleanup(a.close)
        a.sync_upsert([_rec(id="ygg_leak", content="api key sk-123"),
                       _rec(id="ygg_ok", content="fine")], [])
        a_repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(a_repo)], check=True)
        subprocess.run(["git", "-C", str(a_repo), "remote", "add", "origin", str(bare)], check=True)
        self._run(a, a_repo)
        subprocess.run(["git", "clone", "-q", str(bare), str(b_repo)], check=True)
        self._run(b, b_repo)
        self.assertEqual({r["id"] for r in b.sync_export()["memories"]}, {"ygg_leak", "ygg_ok"})
        # B edits the leaked record (diverges from the repo), A hard-deletes it.
        b.sync_upsert([_rec(id="ygg_leak", content="api key sk-123 plus a much longer edit")], [])
        a.delete_by_id("ygg_leak")
        self._run(a, a_repo)
        self._run(b, b_repo)
        self._run(a, a_repo)
        for repo in (a_repo, b_repo):
            self.assertEqual(subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                                            capture_output=True, text=True).stdout.strip(), "")
            self.assertFalse((repo / ".git" / "MERGE_HEAD").exists())
        for store in (a, b):
            self.assertEqual({r["id"] for r in store.sync_export()["memories"]}, {"ygg_ok"})
            self.assertIn("ygg_leak", store.tombstones())
        self.assertFalse((a_repo / "memories" / "ygg_leak.json").exists())


class SyncUpsertTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(db_path=tempfile.mktemp(suffix=".sqlite"))

    def test_insert_update_unchanged(self):
        rec = _rec(id="ygg_s1", content="машина А выучила урок про ретраи")
        r1 = self.store.sync_upsert([rec], [])
        self.assertEqual((r1["added"], r1["updated"]), (1, 0))
        r2 = self.store.sync_upsert([rec], [])
        self.assertEqual((r2["added"], r2["unchanged"]), (0, 1))
        # imported content is lexically searchable (FTS row was written)
        hits = self.store.search(query="ретраи", user_id="u", limit=3,
                                 filters={}, namespaces=None)
        self.assertTrue(any(h["id"] == "ygg_s1" for h in hits))
        r3 = self.store.sync_upsert([{**rec, "archived": 1}], [])
        self.assertEqual(r3["updated"], 1)
        # ...and an archive decision synced in takes it OUT of search
        hits = self.store.search(query="ретраи", user_id="u", limit=3,
                                 filters={}, namespaces=None)
        self.assertFalse(any(h["id"] == "ygg_s1" for h in hits))

    def test_relations_import_skips_missing_endpoints(self):
        a = _rec(id="ygg_a", content="a")
        b = _rec(id="ygg_b", content="b")
        r = self.store.sync_upsert([a, b], [
            {"from_id": "ygg_a", "to_id": "ygg_b", "rel_type": "SOLVES", "user_id": "u"},
            {"from_id": "ygg_a", "to_id": "ygg_GONE", "rel_type": "SOLVES", "user_id": "u"}])
        self.assertEqual((r["relations_added"], r["relations_skipped"]), (1, 1))

    def test_export_roundtrip_is_stable(self):
        self.store.sync_upsert([_rec(id="ygg_r1"), _rec(id="ygg_r2", content="другое")], [])
        exp = self.store.sync_export()
        r = self.store.sync_upsert(exp["memories"], exp["relations"])
        self.assertEqual(r["unchanged"], 2)   # re-importing own export is a no-op


if __name__ == "__main__":
    unittest.main()
