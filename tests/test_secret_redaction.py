"""Secrets must be redacted BEFORE text goes to the distill model, and the
widened pattern list must catch common credential formats without eating git SHAs."""

import json
import unittest

from yggdrasil import ygg, ygg_seed

SHA40 = "da39a3ee5e6b4b0d3255bfef95601890afd80709"
SECRETS = {
    "stripe_live": "sk_live_" + "a1B2c3D4e5F6g7H8i9J0k1L2",
    "stripe_restricted": "rk_live_" + "a1B2c3D4e5F6g7H8i9J0k1L2",
    "npm": "npm_" + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1dE3fG5",
    "hf": "hf_" + "aB3dE5gH7jK9mN1pQ3sT5vW7yZ9bC1dE3f",
    "bearer": "Bearer abcDEF123456.ghiJKL789_mno-pqr",
    "env": "STRIPE_WEBHOOK_SECRET=whsec_9f8e7d6c5b4a",
    "env_key": "MY_SERVICE_KEY=Zm9vYmFyYmF6",
    "hex": "0123456789abcdef" * 4 + "0123456789",
    "b64": "Qx7kP2mVn9Ls4TgRz8WcY1aBdE5fHj3Ku6NoXi0vUq2Aw",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N",
    "url": "postgres://admin:hunter2pass@db.internal/app",
}


# Shape-only heuristics: redacted from transcripts on the way to a model (losing
# a digest there costs nothing), but never grounds to REFUSE a write — every
# memory carries a sha256 content_hash, and digests are ordinary in dev notes.
HEURISTIC = {"hex", "b64"}


class RedactSecretsTest(unittest.TestCase):
    def test_each_format_redacted_and_detected(self):
        for name, secret in SECRETS.items():
            with self.subTest(name):
                text = f"before {secret} after"
                if name in HEURISTIC:
                    self.assertEqual(ygg.scan_for_secrets(text), [], name)
                else:
                    self.assertTrue(ygg.scan_for_secrets(text), name)
                out = ygg.redact_secrets(text)
                self.assertIn("[REDACTED]", out)
                self.assertNotIn(secret.split("=")[-1].split(" ")[-1], out)
                self.assertTrue(out.startswith("before ") and out.endswith(" after"))

    def test_pem_block_fully_removed(self):
        pem = ("-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXk\nAAAA\n"
               "-----END OPENSSH PRIVATE KEY-----")
        out = ygg.redact_secrets(f"x\n{pem}\ny")
        self.assertNotIn("b3BlbnNz", out)
        self.assertEqual(out, "x\n[REDACTED]\ny")
        self.assertTrue(ygg.scan_for_secrets("-----BEGIN PRIVATE KEY-----"))

    def test_git_sha_and_prose_survive(self):
        text = f"commit {SHA40} fixed the token refresh in /Users/me/Projects/some-long-directory-name"
        self.assertEqual(ygg.redact_secrets(text), text)
        self.assertEqual(ygg.scan_for_secrets(text), [])

    def test_idempotent_and_empty(self):
        self.assertEqual(ygg.redact_secrets(""), "")
        once = ygg.redact_secrets("k=" + SECRETS["npm"])
        self.assertEqual(ygg.redact_secrets(once), once)

    def test_a_sha256_digest_is_not_a_secret_to_the_write_guard(self):
        digest = "8ded4eda431fc815958b045ea08b4d95d4e7bbbacb73f0176b2fee34dea15c23"
        ygg.require_safe_memory(f"image pinned to sha256:{digest}", {"content_hash": digest})

    def test_require_safe_memory_uses_widened_patterns(self):
        with self.assertRaises(ygg.YggError):
            ygg.require_safe_memory("use " + SECRETS["stripe_live"], {})


class SeedRedactsBeforeModelTest(unittest.TestCase):
    def test_prompt_sent_to_model_has_no_secret(self):
        seen = []
        orig_gen, orig_write = ygg_seed._ollama_generate, ygg_seed._ygg.write_memory
        ygg_seed._ollama_generate = lambda model, prompt, *a, **k: (seen.append(prompt) or json.dumps(["a lesson"]))
        ygg_seed._ygg.write_memory = lambda **kw: ("added", {})
        try:
            ygg_seed.distill_text(
                f"we set {SECRETS['stripe_live']} and {SECRETS['bearer']}\n{SHA40}",
                project="p", source="s", model="m", user_id="u", namespace="n")
        finally:
            ygg_seed._ollama_generate, ygg_seed._ygg.write_memory = orig_gen, orig_write
        self.assertTrue(seen)
        for p in seen:
            self.assertNotIn(SECRETS["stripe_live"], p)
            self.assertNotIn("abcDEF123456", p)
            self.assertIn(SHA40, p)


if __name__ == "__main__":
    unittest.main()
