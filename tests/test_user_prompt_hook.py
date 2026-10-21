"""The UserPromptSubmit hook's injected context — the only Yggdrasil copy an
end user reads on every single prompt, so it gets a test like any other output.

Covers the contract (valid hook JSON, fail-safe on a dead engine, nothing
injected when nothing is relevant) and the citation marker's wording, which is
what the user actually sees in the agent's prose.
"""

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

from yggdrasil.hooks import ygg_user_prompt as h


def _hit(text="Switched the bg model to qwen2.5:3b", project="yggdrasil-demo", mtype="decision"):
    return {"memory": text, "score": 9.9,
            "metadata": {"project": project, "type": mtype}}


def _run(hits, prompt="how do I configure the embedding backend for openrouter?", cwd=None):
    """Run the hook against a stubbed engine; return its stdout."""
    payload = json.dumps({"data": hits}).encode()
    resp = mock.MagicMock()
    resp.__enter__.return_value = io.BytesIO(payload)
    resp.__exit__.return_value = False
    buf = io.StringIO()
    with mock.patch.object(h.urllib.request, "urlopen", lambda *a, **k: resp), \
         mock.patch.object(h.sys, "stdin", io.StringIO(json.dumps({"prompt": prompt, "cwd": cwd}))), \
         redirect_stdout(buf):
        h.main()
    return buf.getvalue()


def _context(out):
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


class CitationMarkerTest(unittest.TestCase):
    def test_marker_is_from_memory_not_the_api_verb(self):
        """`recalled` was ygg_recall's verb leaking into human-facing copy — it
        named the machine's action instead of telling the reader the claim came
        from their own memory."""
        ctx = _context(_run([_hit()]))
        self.assertIn("🌳 from memory:", ctx)
        self.assertNotIn("recalled:", ctx)

    def test_marker_keeps_the_tree_brand(self):
        """🌳 marks every ygg surface (doctor, seed, sync) — it's the brand."""
        self.assertIn("🌳", _context(_run([_hit()])))

    def test_context_still_tells_the_agent_to_verify(self):
        """Memory can be stale; the injected copy must keep saying so."""
        self.assertIn("stale", _context(_run([_hit()])).lower())

    def test_no_jargon_leaks_into_user_facing_copy(self):
        ctx = _context(_run([_hit()])).lower()
        for jargon in ("auto-recall", "ygg_recall", "additionalcontext", "cosine"):
            self.assertNotIn(jargon, ctx)


class InjectionHardeningTest(unittest.TestCase):
    """Memories can come from untrusted places (a README-tricked agent, a paired
    peer), so they must reach the model as labelled data, never as user orders."""

    def test_block_says_notes_are_data_not_instructions(self):
        ctx = _context(_run([_hit()])).lower()
        self.assertIn("not instructions", ctx)
        self.assertIn("confirm", ctx)

    def test_provenance_source_is_shown(self):
        hit = _hit()
        hit["source"] = "peer"
        self.assertIn("peer", _context(_run([hit])))

    def test_source_falls_back_to_metadata(self):
        hit = _hit()
        hit["metadata"]["source"] = "import"
        self.assertIn("import", _context(_run([hit])))

    def test_foreign_project_is_marked(self):
        ctx = _context(_run([_hit(project="other-repo")], cwd="/tmp/not-a-repo/mine"))
        self.assertIn("other project: other-repo", ctx)

    def test_same_project_is_not_marked_foreign(self):
        ctx = _context(_run([_hit(project="mine")], cwd="/tmp/not-a-repo/mine"))
        self.assertNotIn("other project", ctx)

    def test_no_token_skips_quietly_without_demo_fallback(self):
        with mock.patch.dict(h.os.environ, {}, clear=False), \
             mock.patch.object(h.Path, "read_text", side_effect=OSError):
            h.os.environ.pop("YGG_ENGINE_TOKEN", None)
            self.assertEqual(h.token(), "")
            called = []
            buf = io.StringIO()
            with mock.patch.object(h.urllib.request, "urlopen", lambda *a, **k: called.append(1)), \
                 mock.patch.object(h.sys, "stdin", io.StringIO(json.dumps({"prompt": "a real question here?"}))), \
                 redirect_stdout(buf):
                rc = h.main()
        self.assertEqual((rc, buf.getvalue(), called), (0, "", []))


class ContractTest(unittest.TestCase):
    def test_emits_valid_hook_json_with_the_memory(self):
        out = _run([_hit(text="Switched the bg model to qwen2.5:3b")])
        payload = json.loads(out)
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        ctx = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("qwen2.5:3b", ctx)
        self.assertIn("yggdrasil-demo", ctx)   # provenance is on the memory line
        self.assertIn("decision", ctx)

    def test_injects_nothing_when_no_hits(self):
        self.assertEqual(_run([]), "")

    def test_dead_engine_is_silent_and_never_blocks_a_prompt(self):
        buf = io.StringIO()
        def boom(*a, **k):
            raise OSError("connection refused")
        with mock.patch.object(h.urllib.request, "urlopen", boom), \
             mock.patch.object(h.sys, "stdin", io.StringIO(json.dumps({"prompt": "a real question here?"}))), \
             redirect_stdout(buf):
            rc = h.main()
        self.assertEqual(rc, 0)      # never fail a prompt
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
