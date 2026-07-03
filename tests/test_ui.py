"""ygg_ui pure helpers + the agent-safety guarantee (non-TTY output unchanged)."""

import io
import sys
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg_ui  # noqa: E402
import ygg  # noqa: E402


class PaletteTest(unittest.TestCase):
    def test_off_palette_is_identity(self):
        p = ygg_ui.Palette(False)
        self.assertEqual(p.green("x"), "x")
        self.assertEqual(ygg_ui.badge("fix", p), "fix")

    def test_on_palette_wraps_ansi(self):
        p = ygg_ui.Palette(True)
        self.assertEqual(p.green("x"), "\033[32mx\033[0m")

    def test_bar_fills_by_fraction(self):
        p = ygg_ui.Palette(False)  # no colour -> just the glyphs
        self.assertEqual(ygg_ui.bar(1.0, p, width=5), "▰▰▰▰▰")
        self.assertEqual(ygg_ui.bar(0.0, p, width=5), "▱▱▱▱▱")
        self.assertEqual(ygg_ui.bar(0.6, p, width=5), "▰▰▰▱▱")
        self.assertEqual(ygg_ui.bar(5.0, p, width=5), "▰▰▰▰▰")   # clamped

    def test_ago(self):
        now = time.time()
        self.assertEqual(ygg_ui.ago(now), "just now")
        self.assertEqual(ygg_ui.ago(now - 3 * 3600), "3h ago")
        self.assertEqual(ygg_ui.ago(now - 2 * 86400), "2d ago")
        self.assertEqual(ygg_ui.ago(None), "")

    def test_short_id(self):
        self.assertEqual(ygg_ui.short_id("ygg_1234567890abcdef"), "ygg_123456…")
        self.assertEqual(ygg_ui.short_id("short"), "short")

    def test_enabled_respects_no_color(self, ):
        import os
        old = os.environ.get("NO_COLOR")
        os.environ["NO_COLOR"] = "1"
        try:
            self.assertFalse(ygg_ui.enabled(io.StringIO()))
        finally:
            if old is None:
                os.environ.pop("NO_COLOR", None)
            else:
                os.environ["NO_COLOR"] = old


class NonTtyStableTest(unittest.TestCase):
    """The exact bytes agents/gates/pipes see must not change."""

    HIT = {
        "id": "ygg_abc123def456", "memory": "webhook 401 → rotate the signing secret",
        "score": 1.3, "access_count": 2, "created_at": time.time(),
        "metadata": {"type": "fix", "project": "checkout", "source": "seed:claude",
                     "tags": ["seed"]},
    }

    def test_non_tty_hit_is_id_first_and_stable(self):
        p = ygg_ui.Palette(False)  # not a TTY
        out = io.StringIO()
        with redirect_stdout(out):
            ygg._print_hit(self.HIT, rank=1, max_score=1.3, p=p)
        text = out.getvalue()
        # stable format: id first, score, project/type, provenance, indented preview
        self.assertTrue(text.startswith("ygg_abc123def456  score=1.3000"))
        self.assertIn("project=checkout  type=fix", text)
        self.assertIn("src=seed:claude  conf=?  used=2x  tags=seed", text)
        self.assertIn("  webhook 401", text)
        # no ANSI escapes leak into non-TTY output
        self.assertNotIn("\033[", text)

    def test_tty_hit_is_content_first_and_coloured(self):
        p = ygg_ui.Palette(True)  # pretend TTY
        out = io.StringIO()
        with redirect_stdout(out):
            ygg._print_hit(self.HIT, rank=1, max_score=1.3, p=p)
        text = out.getvalue()
        self.assertIn("\033[", text)          # coloured
        self.assertIn("1. ", text)            # numbered handle
        self.assertIn("▰", text)              # relevance bar
        self.assertIn("webhook 401", text)    # content present
        self.assertNotIn("score=1.3000", text)  # the raw float is gone from the pretty view


if __name__ == "__main__":
    unittest.main()
