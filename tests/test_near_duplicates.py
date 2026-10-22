"""Semantic near-duplicate review: the engine's whole-store scan and `ygg review`.

`ygg review` used to judge "duplicate" by the first 32 words only and looked at
just the first 1000 records, so a store full of reworded copies came back
"clean". These tests pin the replacement: an embedding-cosine scan grouped per
(user, project, type, embed_model), wired into review with conservative
auto-archiving. Vectors are hand-set, so no embedding model is needed.
"""

import argparse
import contextlib
import io
import json
import math
import random
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg  # noqa: E402
import ygg_memory_server as engine  # noqa: E402
from ygg_core import RestMemoryBackend, YggConfig  # noqa: E402


class _FakeEmbedder:
    """Marks dense as on. Rows get their vectors injected directly, so embed()
    is never relied on."""
    model = "test-model"

    def embed(self, text):
        return None


def _pair(cos):
    """Two 2-d unit vectors whose cosine is `cos`."""
    return [1.0, 0.0], [cos, math.sqrt(1.0 - cos * cos)]


def _insert(store, vec, *, project="p", mtype="lesson", user="u", ns="n",
            archived=False, model="test-model", created=None, content=None):
    mid = "ygg_" + uuid.uuid4().hex
    with store._lock:
        store._conn.execute(
            "INSERT INTO memories (id,user_id,namespace,scope,project,type,content,"
            "content_hash,source,confidence,importance,created_at,access_count,archived,"
            "metadata_json,embedding_blob,embed_model) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?,?)",
            (mid, user, ns, "project", project, mtype, content or f"memory {mid}",
             uuid.uuid4().hex, "t", None, 0.5, time.time() if created is None else created,
             1 if archived else 0,
             json.dumps({"project": project, "type": mtype, "source": "t"}),
             engine._vec_to_blob(vec) if vec is not None else None, model),
        )
        store._conn.commit()
    return mid


def _ids(group):
    return {r["id"] for r in group["records"]}


class NearDuplicatesEngineTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = engine.MemoryStore(str(Path(self._tmp.name) / "m.sqlite"))
        self.addCleanup(self.store.close)

    def test_same_bucket_pair_is_grouped_oldest_first(self):
        a, b = _pair(0.99)
        new = _insert(self.store, b, created=200.0)
        old = _insert(self.store, a, created=100.0)
        _insert(self.store, [0.0, 1.0], created=300.0)  # unrelated
        groups = self.store.near_duplicates(user_id="u", threshold=0.95)
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual([r["id"] for r in g["records"]], [old, new])
        self.assertAlmostEqual(g["similarity"], 0.99, places=3)
        self.assertEqual((g["project"], g["type"]), ("p", "lesson"))
        self.assertAlmostEqual(g["records"][1]["similarity"], 0.99, places=3)

    def test_different_project_or_type_never_grouped(self):
        v = [1.0, 0.0]
        _insert(self.store, v, project="A")
        _insert(self.store, v, project="B")
        _insert(self.store, v, project="A", mtype="decision")
        _insert(self.store, v, project="A", user="someone-else")
        self.assertEqual(self.store.near_duplicates(user_id="u"), [])

    def test_archived_records_excluded(self):
        v = [1.0, 0.0]
        _insert(self.store, v)
        _insert(self.store, v, archived=True)
        self.assertEqual(self.store.near_duplicates(user_id="u"), [])

    def test_different_embed_model_not_compared(self):
        v = [1.0, 0.0]
        _insert(self.store, v, model="model-a")
        _insert(self.store, v, model="model-b")
        self.assertEqual(self.store.near_duplicates(user_id="u"), [])

    def test_threshold_respected(self):
        a, b = _pair(0.93)
        _insert(self.store, a)
        _insert(self.store, b)
        self.assertEqual(self.store.near_duplicates(user_id="u", threshold=0.95), [])
        self.assertEqual(len(self.store.near_duplicates(user_id="u", threshold=0.92)), 1)

    def test_chained_similarity_forms_one_cluster(self):
        # A~B and B~C clear the bar; A~C does not. One group, honest min similarity.
        ang = math.acos(0.96)
        vecs = [[math.cos(k * ang), math.sin(k * ang)] for k in range(3)]
        ids = [_insert(self.store, v, created=float(i)) for i, v in enumerate(vecs)]
        groups = self.store.near_duplicates(user_id="u", threshold=0.95)
        self.assertEqual(len(groups), 1)
        self.assertEqual([r["id"] for r in groups[0]["records"]], ids)
        self.assertLess(groups[0]["similarity"], 0.95)        # min pair is A~C
        self.assertGreaterEqual(groups[0]["max_similarity"], 0.95)

    def test_project_and_namespace_filters(self):
        v = [1.0, 0.0]
        _insert(self.store, v, project="A")
        _insert(self.store, v, project="A")
        _insert(self.store, v, project="B", ns="other")
        _insert(self.store, v, project="B", ns="other")
        self.assertEqual(len(self.store.near_duplicates(user_id="u")), 2)
        self.assertEqual([g["project"] for g in self.store.near_duplicates(user_id="u", project="A")], ["A"])
        self.assertEqual([g["project"] for g in self.store.near_duplicates(user_id="u", namespace="other")], ["B"])

    def test_across_types_groups_within_project_and_names_the_types(self):
        a, b = _pair(0.99)
        fix = _insert(self.store, a, mtype="fix", created=1.0)
        lesson = _insert(self.store, b, mtype="lesson", created=2.0)
        _insert(self.store, a, project="other", mtype="fix", created=3.0)  # other project: never
        self.assertEqual(self.store.near_duplicates(user_id="u"), [])  # default stays per-type
        groups = self.store.near_duplicates(user_id="u", across_types=True)
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual([r["id"] for r in g["records"]], [fix, lesson])
        self.assertEqual(g["types"], ["fix", "lesson"])
        self.assertEqual([r["type"] for r in g["records"]], ["fix", "lesson"])

    def test_single_type_group_reports_its_type(self):
        _insert(self.store, [1.0, 0.0])
        _insert(self.store, [1.0, 0.0])
        g = self.store.near_duplicates(user_id="u", across_types=True)[0]
        self.assertEqual((g["type"], g["types"]), ("lesson", ["lesson"]))

    def test_perf_sanity_hundreds_of_1024_dim_vectors(self):
        rng = random.Random(7)
        base = [rng.gauss(0, 1) for _ in range(1024)]
        planted = [x + rng.gauss(0, 0.05) for x in base]
        _insert(self.store, base, created=0.0)
        _insert(self.store, planted, created=1.0)
        for i in range(398):
            _insert(self.store, [rng.gauss(0, 1) for _ in range(1024)], created=2.0 + i)
        t0 = time.perf_counter()
        groups = self.store.near_duplicates(user_id="u", threshold=0.95)
        elapsed = time.perf_counter() - t0
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["records"]), 2)
        self.assertLess(elapsed, 10.0, f"400x1024 scan took {elapsed:.2f}s")


class PairPrefilterRecallTest(unittest.TestCase):
    """The prefilter may only skip work, never pairs: on embedding-like data
    (a strong shared direction plus per-memory noise, with planted rewordings
    spanning the threshold) it must return exactly the brute-force pair set."""

    def test_matches_brute_force_at_and_around_the_threshold(self):
        rng = random.Random(11)
        dim = 256
        mean = [rng.gauss(0, 1) for _ in range(dim)]
        scale = [rng.uniform(0.05, 1.0) for _ in range(dim)]  # uneven variance, like real models

        def unit(v):
            n = math.sqrt(sum(x * x for x in v))
            return [x / n for x in v]

        vecs = [unit([m + rng.gauss(0, 1.2) * s for m, s in zip(mean, scale)]) for _ in range(150)]
        for k, noise in enumerate([0.02, 0.05, 0.08, 0.1, 0.12, 0.15, 0.2, 0.25] * 3):
            src = vecs[k * 5]
            vecs.append(unit([x + rng.gauss(0, noise) * s for x, s in zip(src, scale)]))
        for threshold in (0.92, 0.95):
            brute = {(i, j) for i in range(len(vecs)) for j in range(i + 1, len(vecs))
                     if sum(a * b for a, b in zip(vecs[i], vecs[j])) >= threshold}
            got = engine._pairs_at_least(vecs, threshold)
            self.assertEqual(set(got), brute, f"threshold {threshold}")
            self.assertTrue(brute, "fixture should plant pairs above the threshold")
            for (i, j), sim in got.items():
                self.assertAlmostEqual(sim, sum(a * b for a, b in zip(vecs[i], vecs[j])), places=9)


class _EngineServer:
    def __init__(self, testcase, embedder):
        tmp = tempfile.TemporaryDirectory()
        testcase.addCleanup(tmp.cleanup)
        self.store = engine.MemoryStore(str(Path(tmp.name) / "m.sqlite"), embedder=embedder)
        testcase.addCleanup(self.store.close)
        handler = type("H", (engine.Handler,), {"store": self.store, "token": "t"})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        testcase.addCleanup(self.httpd.server_close)
        testcase.addCleanup(self.httpd.shutdown)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def post(self, path, body):
        req = urllib.request.Request(
            self.url + path, data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": "Bearer t", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())["data"]


class NearDuplicatesRouteTest(unittest.TestCase):
    def test_dense_off_returns_empty_with_flag(self):
        srv = _EngineServer(self, embedder=None)
        _insert(srv.store, [1.0, 0.0])
        _insert(srv.store, [1.0, 0.0])
        data = srv.post("/near_duplicates", {"user_id": "u"})
        self.assertFalse(data["dense"])
        self.assertEqual(data["groups"], [])

    def test_dense_on_returns_groups(self):
        srv = _EngineServer(self, embedder=_FakeEmbedder())
        _insert(srv.store, [1.0, 0.0])
        _insert(srv.store, [1.0, 0.0])
        data = srv.post("/near_duplicates", {"user_id": "u", "threshold": 0.95})
        self.assertTrue(data["dense"])
        self.assertEqual(len(data["groups"]), 1)


class ReviewSemanticTest(unittest.TestCase):
    def setUp(self):
        self.srv = _EngineServer(self, embedder=_FakeEmbedder())
        old = ygg._BACKEND
        ygg._BACKEND = RestMemoryBackend(YggConfig(url=self.srv.url, token="t"))
        self.addCleanup(setattr, ygg, "_BACKEND", old)

    def _review(self, **kw):
        args = argparse.Namespace(user_id="u", namespace="n", project=None, apply=False,
                                  yes=False, limit=None, threshold=0.95)
        for k, v in kw.items():
            setattr(args, k, v)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ygg.review(args)
        return out.getvalue()

    def _archived(self, mid):
        return self.srv.store.get_by_id(mid)["archived"]

    def test_review_finds_semantic_group_beyond_first_1000_records(self):
        # 1200 fillers, each alone in its own project so nothing pairs up; the
        # duplicate pair is created LAST, i.e. past the old 1000-record window.
        for i in range(1200):
            _insert(self.srv.store, [1.0, 0.0], project=f"filler{i}", created=float(i))
        a, b = _pair(0.99)
        x = _insert(self.srv.store, a, project="late", created=5000.0, content="use user_roles table")
        y = _insert(self.srv.store, b, project="late", created=5001.0, content="user_roles lets one user hold roles")
        out = self._review()
        self.assertIn(x, out)
        self.assertIn(y, out)
        self.assertIn("0.99", out)                 # similarity is shown
        self.assertNotIn("memory is clean", out)

    def test_apply_yes_archives_only_high_similarity_groups(self):
        lo_a, lo_b = _pair(0.955)
        hi_a, hi_b = _pair(0.98)
        lo_keep = _insert(self.srv.store, lo_a, project="lo", created=1.0, content="lo one")
        lo_dup = _insert(self.srv.store, lo_b, project="lo", created=2.0, content="lo two")
        hi_keep = _insert(self.srv.store, hi_a, project="hi", created=1.0, content="hi one")
        hi_dup = _insert(self.srv.store, hi_b, project="hi", created=2.0, content="hi two")
        self._review(apply=True, yes=True)
        self.assertFalse(self._archived(lo_keep))
        self.assertFalse(self._archived(lo_dup))     # 0.955 < 0.97: listed, never auto-archived
        self.assertFalse(self._archived(hi_keep))    # oldest kept
        self.assertTrue(self._archived(hi_dup))      # 0.98: consolidated
        rels = self.srv.store.relations_for(hi_dup)
        self.assertIn(hi_keep, json.dumps(rels))     # SUPERSEDES edge recorded

    def test_review_groups_across_types_and_prints_each_type(self):
        a, b = _pair(0.99)
        x = _insert(self.srv.store, a, project="m", mtype="fix", created=1.0, content="add getOptions test")
        y = _insert(self.srv.store, b, project="m", mtype="decision", created=2.0, content="getOptions test added")
        out = self._review()
        self.assertIn(x, out)
        self.assertIn(y, out)
        self.assertIn("(fix)", out)
        self.assertIn("(decision)", out)

    def test_apply_yes_never_archives_a_mixed_type_group(self):
        a, b = _pair(0.99)
        keep = _insert(self.srv.store, a, project="m", mtype="fix", created=1.0, content="mixed one")
        dup = _insert(self.srv.store, b, project="m", mtype="lesson", created=2.0, content="mixed two")
        out = self._review(apply=True, yes=True)
        self.assertIn(dup, out)                      # found and listed...
        self.assertIn("mixed types", out)
        self.assertFalse(self._archived(keep))
        self.assertFalse(self._archived(dup))       # ...but which type survives is a human call

    def test_semantic_group_not_listed_twice_with_exact_duplicate(self):
        v = [1.0, 0.0]
        text = "identical text " * 10   # long enough for the text-signature finder too
        a = _insert(self.srv.store, v, project="e", created=1.0, content=text)
        b = _insert(self.srv.store, v, project="e", created=2.0, content=text)
        with self.srv.store._lock:
            self.srv.store._conn.execute("UPDATE memories SET content_hash='H' WHERE id IN (?,?)", (a, b))
            self.srv.store._conn.execute(
                "UPDATE memories SET metadata_json=? WHERE id IN (?,?)",
                (json.dumps({"project": "e", "type": "lesson", "content_hash": "H"}), a, b))
            self.srv.store._conn.commit()
        out = self._review()
        self.assertIn("1 issue(s)", out)


if __name__ == "__main__":
    unittest.main()
