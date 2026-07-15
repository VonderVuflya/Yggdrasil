"""Tests for ygg_setup: the acceleration-tier / GPU-warning classifier (§1) and
the multilingual-aware model catalog + recommendation (§3).

These are pure/deterministic given a hardware dict, so no Ollama or engine is
touched — we feed synthetic `hw()` dicts and assert the recommendation and the
rendered catalog."""

import io
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
