"""Tests for ygg_setup: the acceleration-tier / GPU-warning classifier (§1) and
the multilingual-aware model catalog + recommendation (§3).

These are pure/deterministic given a hardware dict, so no Ollama or engine is
touched — we feed synthetic `hw()` dicts and assert the recommendation and the
rendered catalog."""

import builtins
import importlib
import io
import json
import os
import pathlib
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

from yggdrasil import ygg_setup as s


def _hw(**over):
    base = {"cpu": "test", "cores": 8, "ram_gb": 16, "arch": "x86_64",
            "apple_silicon": False, "accel": "CPU", "accel_tier": "cpu",
            "accel_warn": "", "gpus": []}
    base.update(over)
    return base


class RecommendTest(unittest.TestCase):
    def test_never_recommends_llama_for_the_upgrade(self):
        # Llama 3.2 has no Russian/Chinese — it must never be the default pick.
        for h in (_hw(apple_silicon=True, accel_tier="metal", ram_gb=32),
                  _hw(accel_tier="cuda", ram_gb=64),
                  _hw(accel_tier="rocm/vulkan", ram_gb=32),
                  _hw(ram_gb=8), _hw(ram_gb=32)):  # CPU-only, big + small RAM
            _, bg = s.recommend(h)
            self.assertNotEqual(bg, "llama3.2:3b")
            self.assertTrue(bg.startswith("qwen2.5"))

    def test_accelerated_16gb_gets_the_3b_upgrade(self):
        self.assertEqual(s.recommend(_hw(apple_silicon=True, accel_tier="metal", ram_gb=16))[1],
                         "qwen2.5:3b")

    def test_cpu_only_stays_on_the_1_5b_sweet_spot(self):
        self.assertEqual(s.recommend(_hw(accel_tier="cpu", ram_gb=32))[1], "qwen2.5:1.5b")


class CatalogTest(unittest.TestCase):
    def _render(self, h):
        buf = io.StringIO()
        with redirect_stdout(buf):
            s.print_catalog(h)
        return buf.getvalue()

    def test_warns_when_gpu_will_not_accelerate(self):
        out = self._render(_hw(accel_warn="You have a GPU (AMD Radeon RX 580) but it will NOT accelerate ..."))
        self.assertIn("⚠", out)
        self.assertIn("RX 580", out)

    def test_llama_entry_flags_no_russian(self):
        out = self._render(_hw())
        # the language column makes the gap explicit right on the llama line
        line = next(l for l in out.splitlines() if "llama3.2:3b" in l)
        self.assertIn("NO Russian", line)

    def test_every_bg_model_carries_a_language_tag(self):
        # the 5th tuple field must be present and rendered for real models
        for name, _size, _desc, _tier, lang in s.BG_MODELS:
            if name != "none":
                self.assertTrue(lang and lang != "—", name)


class WizardConfigMergeTest(unittest.TestCase):
    """Re-running `ygg install` must not eat settings the wizard never asks about.

    It used to write config.json from scratch, silently dropping the pinned
    user_id/namespace (which strands existing memory — the exact failure the
    0.11.0 identity migration exists to prevent), plus embed_backend/embed_url,
    distill_url and sync_repo."""

    # Settings the wizard never asks about, so it must never touch them.
    # embed_backend/embed_url are deliberately NOT here: the wizard owns those
    # now (it asks where embeddings run), and picking Ollama clears them on
    # purpose — see WizardBackendStepTest.
    PRESET = {
        "user_id": "local", "namespace": "personal",
        "distill_url": "http://192.168.3.124:11434",
        "sync_repo": "git@github.com:me/mem.git",
    }

    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp())
        os.environ["YGG_HOME"] = str(self.home)
        importlib.reload(s)
        self.cfg = self.home / "config.json"
        # backend (1 = Ollama), embed model, bg model, hooks, autosave,
        # write_path, consolidation
        self._answers = iter(["1", "all-minilm", "qwen2.5:1.5b", "n", "n", "n", "n"])
        self._real_input = builtins.input
        builtins.input = lambda *a, **k: next(self._answers, "")
        self._real_install = None

    def tearDown(self):
        builtins.input = self._real_input
        os.environ.pop("YGG_HOME", None)
        shutil.rmtree(self.home, ignore_errors=True)
        importlib.reload(s)

    def _run_wizard(self):
        # stub the service install — we only care about what lands in config.json
        import yggdrasil.service as service
        real = service.install
        service.install = lambda *a, **k: 0
        try:
            with redirect_stdout(io.StringIO()):
                s.wizard()
        finally:
            service.install = real

    def test_wizard_preserves_settings_it_never_asks_about(self):
        self.cfg.write_text(json.dumps(self.PRESET))
        self._run_wizard()
        after = json.loads(self.cfg.read_text())
        for key, value in self.PRESET.items():
            self.assertEqual(after.get(key), value, f"wizard dropped {key}")

    def test_wizard_still_writes_its_own_answers(self):
        self.cfg.write_text(json.dumps(self.PRESET))
        self._run_wizard()
        after = json.loads(self.cfg.read_text())
        self.assertEqual(after["embed_model"], "all-minilm")
        self.assertEqual(after["bg_model"], "qwen2.5:1.5b")
        self.assertIn("features", after)

    def test_wizard_survives_a_corrupt_config(self):
        self.cfg.write_text("{ not json")
        self._run_wizard()
        after = json.loads(self.cfg.read_text())  # rebuilt, not crashed
        self.assertEqual(after["embed_model"], "all-minilm")

    def test_wizard_works_with_no_config_yet(self):
        self._run_wizard()
        after = json.loads(self.cfg.read_text())
        self.assertEqual(after["bg_model"], "qwen2.5:1.5b")


class WizardBackendStepTest(unittest.TestCase):
    """The wizard asks WHERE embeddings run, and you can walk back to change it.

    Driven through the non-TTY fallback (numbered list + input()) — the same path
    a real `uvx ... ygg install` takes when stdin isn't a terminal.
    """

    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp())
        os.environ["YGG_HOME"] = str(self.home)
        import yggdrasil.ygg_config as C
        self.C = importlib.reload(C)
        importlib.reload(s)
        self.cfg = self.home / "config.json"
        self._real_input = builtins.input

    def tearDown(self):
        builtins.input = self._real_input
        os.environ.pop("YGG_HOME", None)
        shutil.rmtree(self.home, ignore_errors=True)
        importlib.reload(s)

    def _run(self, *answers, key=None):
        it = iter(answers)
        builtins.input = lambda *a, **k: next(it)
        if key is not None:
            import getpass
            self._real_getpass = getpass.getpass
            getpass.getpass = lambda prompt="": key
        import yggdrasil.service as service
        real = service.install
        service.install = lambda *a, **k: 0
        try:
            with redirect_stdout(io.StringIO()):
                s.wizard()
        finally:
            service.install = real
            if key is not None:
                import getpass
                getpass.getpass = self._real_getpass
        return json.loads(self.cfg.read_text())

    def test_ollama_path_writes_no_backend_keys(self):
        cfg = self._run("1", "all-minilm", "qwen2.5:1.5b", "n", "n", "n", "n")
        self.assertEqual(cfg["embed_model"], "all-minilm")
        self.assertNotIn("embed_backend", cfg)   # ollama is the default; don't pin it
        self.assertNotIn("embed_url", cfg)

    def test_openrouter_path_sets_backend_url_and_keyfile(self):
        cfg = self._run("3", "nvidia/llama-nemotron-embed-vl-1b-v2:free",
                        "https://openrouter.ai/api/v1",
                        "qwen2.5:1.5b", "n", "n", "n", "n",
                        key="sk-or-v1-TESTKEY")
        self.assertEqual(cfg["embed_backend"], "openai")
        self.assertEqual(cfg["embed_url"], "https://openrouter.ai/api/v1")
        self.assertNotIn("embed_api_key", cfg)            # never in config.json
        self.assertEqual(self.C.read_secret(self.C.EMBED_KEY_FILE), "sk-or-v1-TESTKEY")

    def test_llamacpp_path_needs_no_key(self):
        cfg = self._run("2", "bge-small-en-v1.5", "http://127.0.0.1:8080/v1",
                        "qwen2.5:1.5b", "n", "n", "n", "n")
        self.assertEqual(cfg["embed_backend"], "openai")
        self.assertEqual(cfg["embed_url"], "http://127.0.0.1:8080/v1")
        self.assertFalse(self.C.EMBED_KEY_FILE.exists())

    def test_walking_back_to_ollama_clears_the_hosted_keys(self):
        """Otherwise a stale openrouter URL keeps aiming the daemon at a host
        the user just walked away from."""
        cfg = self._run("3", "nvidia/some-model", "b", "b",      # openrouter -> back -> back
                        "1", "all-minilm",                        # ...pick ollama instead
                        "qwen2.5:1.5b", "n", "n", "n", "n")
        self.assertEqual(cfg["embed_model"], "all-minilm")
        self.assertNotIn("embed_backend", cfg)
        self.assertNotIn("embed_url", cfg)

    def test_none_skips_straight_past_model_url_and_key(self):
        cfg = self._run("4", "qwen2.5:1.5b", "n", "n", "n", "n")
        self.assertEqual(cfg["embed_model"], "")
        self.assertFalse(cfg["features"]["dense"])
        self.assertNotIn("embed_url", cfg)


class HwClassifierTest(unittest.TestCase):
    def test_hw_reports_tier_and_warn_fields(self):
        h = s.hw()  # real machine — we only assert the shape/contract
        self.assertIn(h["accel_tier"], ("cpu", "metal", "cuda", "rocm/vulkan"))
        self.assertIsInstance(h["accel_warn"], str)
        # An Intel Mac must always explain why inference is CPU-only.
        if h["os"] == "Darwin" and not h["apple_silicon"]:
            self.assertTrue(h["accel_warn"])


if __name__ == "__main__":
    unittest.main()
