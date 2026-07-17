"""Distillation against a hosted endpoint: the Bearer header and the 401 message.

Distill has spoken the OpenAI dialect since 0.7.1 but never authenticated, so
`distill_url` pointed at OpenRouter raised a bare 401 that named neither the key
nor the cause. These pin the header and the error text — offline, mocked.
"""

import importlib
import os
import shutil
import tempfile
import unittest
import urllib.error
from unittest import mock

from yggdrasil import ygg_config as C
from yggdrasil import ygg_seed as s


class DistillAuthHeaderTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        os.environ["YGG_HOME"] = self.home
        for e in ("YGG_DISTILL_API_KEY", "OPENROUTER_API_KEY"):
            os.environ.pop(e, None)
        importlib.reload(C)
        s._cfg = C

    def tearDown(self):
        for e in ("YGG_HOME", "YGG_DISTILL_API_KEY", "OPENROUTER_API_KEY"):
            os.environ.pop(e, None)
        importlib.reload(C)
        s._cfg = C

    def test_no_key_means_no_auth_header(self):
        """A local Ollama must not be sent an Authorization header."""
        self.assertNotIn("Authorization", s._headers())

    def test_configured_key_becomes_a_bearer_header(self):
        C.set_value("distill_api_key", "sk-or-v1-abc")
        self.assertEqual(s._headers()["Authorization"], "Bearer sk-or-v1-abc")

    def test_env_key_works_without_config(self):
        os.environ["YGG_DISTILL_API_KEY"] = "sk-or-from-env"
        self.assertEqual(s._headers()["Authorization"], "Bearer sk-or-from-env")

    def test_openrouter_env_var_is_honoured(self):
        os.environ["OPENROUTER_API_KEY"] = "sk-or-vendor"
        self.assertEqual(s._headers()["Authorization"], "Bearer sk-or-vendor")

    def test_key_is_resolved_per_call_not_at_import(self):
        """`ygg config set` must take effect on the next run, not the next process."""
        self.assertNotIn("Authorization", s._headers())
        C.set_value("distill_api_key", "sk-later")
        self.assertIn("Authorization", s._headers())

    def test_secret_goes_to_its_own_0600_file_not_config_json(self):
        C.set_value("distill_api_key", "sk-or-SECRET")
        self.assertTrue(C.DISTILL_KEY_FILE.exists())
        self.assertNotIn("distill_api_key", C.load())
        self.assertEqual(C.display("distill_api_key", "sk-or-SECRETVALUE123"), "sk-or-…E123")

    def test_content_type_and_user_agent_survive(self):
        h = s._headers()
        self.assertEqual(h["Content-Type"], "application/json")
        self.assertIn("yggdrasil/", h["User-Agent"])


class UnauthorizedMessageTest(unittest.TestCase):
    """A bare 401 named neither the key nor the cause — and pointed at
    /v1/chat/completions, because the two dialects probed before it 404'd and
    were swallowed."""

    def _raise(self, code):
        def boom(url, *a, **k):
            raise urllib.error.HTTPError(url, code, "Unauthorized", {}, None)
        return boom

    def test_401_explains_the_missing_key(self):
        with mock.patch.object(s, "_post_json", self._raise(401)), \
             mock.patch.object(s, "_stream_collect", self._raise(401)):
            with self.assertRaises(RuntimeError) as ctx:
                s._ollama_generate("m", "summarise this", timeout=5)
        msg = str(ctx.exception)
        self.assertIn("401", msg)
        self.assertIn("ygg config set distill_api_key", msg)
        self.assertIn("no key", msg.lower())          # local endpoints are fine

    def test_403_gets_the_same_treatment(self):
        with mock.patch.object(s, "_post_json", self._raise(403)), \
             mock.patch.object(s, "_stream_collect", self._raise(403)):
            with self.assertRaises(RuntimeError) as ctx:
                s._ollama_generate("m", "summarise this", timeout=5)
        self.assertIn("distill_api_key", str(ctx.exception))

    def test_404_still_falls_through_dialects(self):
        """404 means 'this endpoint doesn't speak that dialect' — keep probing."""
        with mock.patch.object(s, "_post_json", self._raise(404)), \
             mock.patch.object(s, "_stream_collect", self._raise(404)):
            with self.assertRaises(urllib.error.HTTPError):   # not RuntimeError
                s._ollama_generate("m", "summarise this", timeout=5)


class OpenAIBaseUrlTest(unittest.TestCase):
    """`embed_url` takes the /v1 base, `distill_url` takes the host root — the
    same provider therefore needs two different URLs in two settings. Accept
    either here: a copied /v1 used to produce /v1/v1 and a 404 that reads like a
    broken endpoint rather than a typo."""

    def _openai_url(self, distill_url):
        seen = []

        def boom(url, *a, **k):
            seen.append(url)
            raise urllib.error.HTTPError(url, 404, "nope", {}, None)

        with mock.patch.object(s, "OLLAMA_URL", distill_url), \
             mock.patch.object(s, "_post_json", boom), \
             mock.patch.object(s, "_stream_collect", boom):
            try:
                s._ollama_generate("m", "p", timeout=2)
            except Exception:  # noqa: BLE001 — we only want the URLs it tried
                pass
        return next((u for u in seen if "chat/completions" in u), "")

    def test_host_root_builds_the_openai_path(self):
        self.assertEqual(self._openai_url("https://openrouter.ai/api"),
                         "https://openrouter.ai/api/v1/chat/completions")

    def test_v1_base_does_not_double_up(self):
        self.assertEqual(self._openai_url("https://openrouter.ai/api/v1"),
                         "https://openrouter.ai/api/v1/chat/completions")

    def test_trailing_slash_v1_is_handled(self):
        self.assertEqual(self._openai_url("https://openrouter.ai/api/v1/"),
                         "https://openrouter.ai/api/v1/chat/completions")

    def test_local_ollama_is_untouched(self):
        self.assertEqual(self._openai_url("http://127.0.0.1:11434"),
                         "http://127.0.0.1:11434/v1/chat/completions")


if __name__ == "__main__":
    unittest.main()
