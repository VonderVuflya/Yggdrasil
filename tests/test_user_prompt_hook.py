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


def _run(hits, prompt="how do I configure the embedding backend for openrouter?"):
    """Run the hook against a stubbed engine; return its stdout."""
    payload = json.dumps({"data": hits}).encode()
    resp = mock.MagicMock()
    resp.__enter__.return_value = io.BytesIO(payload)
    resp.__exit__.return_value = False
    buf = io.StringIO()
    with mock.patch.object(h.urllib.request, "urlopen", lambda *a, **k: resp), \
         mock.patch.object(h.sys, "stdin", io.StringIO(json.dumps({"prompt": prompt}))), \
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
