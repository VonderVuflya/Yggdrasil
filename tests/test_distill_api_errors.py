"""API failures must not be reported as malformed model output."""

import contextlib
import io
import json
import unittest
import urllib.error
from unittest import mock

from yggdrasil import ygg_seed as s


class DistillApiErrorsTest(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(s, "_ENDPOINT_CACHE", {}))
        self.stack.enter_context(mock.patch.object(s, "OLLAMA_URL", "http://studio:1234"))
        self.stack.enter_context(mock.patch.object(s, "DISTILL_REASONING", "off"))

    def test_http_200_unsupported_routes_fall_back_to_openai(self):
        seen = []

        def respond(req, **kwargs):
            seen.append(req.full_url)
            if "/api/" in req.full_url:
                return io.BytesIO(json.dumps({
                    "error": "Unexpected endpoint or method. (POST /api/generate)"
                }).encode())
            return io.BytesIO(
                b'data: {"choices":[{"delta":{"content":"{\\"lessons\\":[]}"},'
                b'"finish_reason":"stop"}]}\n\ndata: [DONE]\n')

        with mock.patch.object(s.urllib.request, "urlopen", respond):
            self.assertEqual(s._ollama_generate("m", "p"), '{"lessons":[]}')
        self.assertEqual(len(seen), 3)
        self.assertEqual(s._ENDPOINT_CACHE[s.OLLAMA_URL], ("openai", True))

    def test_streamed_api_error_is_not_empty_model_output(self):
        for mode, body in (
            ("ollama_generate", b'{"error":"model not found"}\n'),
            ("openai", b'data: {"error":{"message":"model not found"}}\n'),
            ("openai", b'{"error":{"message":"model not found"}}\n'),
        ):
            with self.subTest(mode=mode, body=body), mock.patch.object(
                    s.urllib.request, "urlopen", return_value=io.BytesIO(body)):
                with self.assertRaisesRegex(ValueError, "model not found"):
                    s._stream_collect("http://studio", {}, mode, 1, 5)

    def test_nonstream_api_error_is_not_empty_model_output(self):
        s._ENDPOINT_CACHE[s.OLLAMA_URL] = ("openai", False)
        with mock.patch.object(s, "_post_json", return_value={
                "error": {"message": "No models loaded"}}):
            with self.assertRaisesRegex(ValueError, "No models loaded"):
                s._ollama_generate("m", "p")

    def test_http_error_after_optional_field_retry_preserves_cause(self):
        s._ENDPOINT_CACHE[s.OLLAMA_URL] = ("openai", True)
        seen = []

        def fail(url, body, *args):
            seen.append(body)
            raise urllib.error.HTTPError(url, 400, "Bad Request", {}, io.BytesIO(
                b'{"error":{"message":"No models loaded. Please load a model."}}'))

        with mock.patch.object(s, "_stream_collect", fail):
            with self.assertRaisesRegex(ValueError, "No models loaded"):
                s._ollama_generate("m", "p")
        self.assertEqual(len(seen), 2)
        self.assertIn("reasoning_effort", seen[0])
        self.assertNotIn("reasoning_effort", seen[1])

    def test_distill_reports_api_failure_without_writing_memory(self):
        with mock.patch.object(s, "_ollama_generate", side_effect=ValueError(
                "distill endpoint: No models loaded")) as generate, \
             mock.patch.object(s._ygg, "write_memory") as write, \
             mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            result = s.distill_text("log", project="t", source="seed",
                                   model="m", user_id="u", namespace="n")
        self.assertEqual(result["errors"], 1)
        self.assertIn("No models loaded", err.getvalue())
        self.assertNotIn("malformed JSON", err.getvalue())
        generate.assert_called_once()
        write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
