"""`ygg config` as a thing you READ: grouping, masking, help on demand.

The old listing printed twelve settings and twenty-four lines of help as one
wall, so finding the one you came for meant scanning all of it. What's pinned
here is the shape — every setting present, secrets never shown, help only when
asked — plus the edit menu's fallback path.
"""

import builtins
import importlib
import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

from yggdrasil import cli
from yggdrasil import ygg_config as C


def _run(*args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        cli._config_cmd(list(args))
    return buf.getvalue()


class GroupingTest(unittest.TestCase):
    def test_every_setting_appears_in_a_group(self):
        """A new key must never silently vanish from the listing."""
        grouped = {k for _, keys in C.grouped() for k in keys}
        self.assertEqual(grouped, set(C.SETTINGS))

    def test_no_key_is_listed_twice(self):
        keys = [k for _, keys in C.grouped() for k in keys]
        self.assertEqual(len(keys), len(set(keys)))

    def test_listing_shows_every_setting_under_a_heading(self):
        out = _run("list")
        for key in C.SETTINGS:
            self.assertIn(key, out)
        self.assertIn("Embeddings", out)
        self.assertIn("Distillation", out)
        self.assertIn("Identity", out)


class HelpOnDemandTest(unittest.TestCase):
    def test_plain_listing_omits_help_text(self):
        out = _run("list")
        self.assertNotIn("Bearer key for the openai backend", out)

    def test_verbose_includes_it(self):
        self.assertIn("Bearer key", _run("list", "-v"))

    def test_verbose_flag_is_not_mistaken_for_a_subcommand(self):
        """`ygg config -v` — no subcommand, just the flag."""
        out = _run("-v")
        self.assertIn("Bearer key", out)
        self.assertNotIn("unknown config subcommand", out)


class SecretMaskingTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        os.environ["YGG_HOME"] = self.home
        for e in ("YGG_EMBED_API_KEY", "OPENROUTER_API_KEY", "YGG_DISTILL_API_KEY"):
            os.environ.pop(e, None)
        importlib.reload(C)

    def tearDown(self):
        os.environ.pop("YGG_HOME", None)
        shutil.rmtree(self.home, ignore_errors=True)
        importlib.reload(C)

    def test_keys_are_masked_in_the_listing(self):
        C.set_value("embed_api_key", "sk-or-v1-SECRETVALUE0000")
        C.set_value("distill_api_key", "sk-or-v1-OTHERSECRET1111")
        out = _run("list")
        self.assertNotIn("SECRETVALUE", out)
        self.assertNotIn("OTHERSECRET", out)
        self.assertIn("sk-or-", out)      # enough to recognise which key it is

    def test_verbose_does_not_unmask(self):
        C.set_value("embed_api_key", "sk-or-v1-SECRETVALUE0000")
        self.assertNotIn("SECRETVALUE", _run("list", "-v"))


class BrokenCombinationTest(unittest.TestCase):
    """A missing key is only wrong relative to a backend chosen three rows
    earlier, so no row can be judged alone — and an un-set key renders dim,
    which made the one cell that mattered the quietest thing on screen."""

    def setUp(self):
        self.home = tempfile.mkdtemp()
        os.environ["YGG_HOME"] = self.home
        for e in ("YGG_EMBED_URL", "YGG_EMBED_BACKEND", "YGG_EMBED_API_KEY",
                  "YGG_DISTILL_URL", "YGG_DISTILL_API_KEY", "OPENROUTER_API_KEY"):
            os.environ.pop(e, None)
        importlib.reload(C)

    def tearDown(self):
        for e in ("YGG_HOME", "YGG_EMBED_URL", "YGG_EMBED_BACKEND",
                  "YGG_EMBED_API_KEY", "YGG_DISTILL_URL", "YGG_DISTILL_API_KEY"):
            os.environ.pop(e, None)
        shutil.rmtree(self.home, ignore_errors=True)
        importlib.reload(C)

    def test_hosted_embed_without_a_key_is_flagged(self):
        C.set_value("embed_url", "https://openrouter.ai/api/v1")
        self.assertIn("embed_api_key", cli._config_problems(C))
        self.assertIn("hosted", _run("list"))

    def test_hosted_distill_without_a_key_is_flagged(self):
        C.set_value("distill_url", "https://openrouter.ai/api/v1")
        self.assertIn("distill_api_key", cli._config_problems(C))

    def test_key_present_clears_the_flag(self):
        C.set_value("embed_url", "https://openrouter.ai/api/v1")
        C.set_value("embed_api_key", "sk-or-v1-x")
        self.assertNotIn("embed_api_key", cli._config_problems(C))

    def test_local_endpoint_needs_no_key(self):
        C.set_value("embed_url", "http://127.0.0.1:11434")
        self.assertEqual(cli._config_problems(C), {})

    def test_a_healthy_config_flags_nothing(self):
        self.assertEqual(cli._config_problems(C), {})
        self.assertNotIn("↑", _run("list"))


class EditMenuTest(unittest.TestCase):
    """Driven through the non-TTY fallback — same path as a piped install."""

    def setUp(self):
        self.home = tempfile.mkdtemp()
        os.environ["YGG_HOME"] = self.home
        os.environ["YGG_NO_TUI"] = "1"
        importlib.reload(C)
        self._real_input = builtins.input

    def tearDown(self):
        builtins.input = self._real_input
        for e in ("YGG_HOME", "YGG_NO_TUI"):
            os.environ.pop(e, None)
        importlib.reload(C)

    def _answer(self, *answers):
        it = iter(answers)
        builtins.input = lambda *a, **k: next(it)

    def _index_of(self, key):
        keys = [k for _, ks in C.grouped() for k in ks]
        return str(keys.index(key) + 1)

    def test_picking_a_setting_and_changing_it_writes_config(self):
        self._answer(self._index_of("bg_model"), "qwen2.5:7b")
        with redirect_stdout(io.StringIO()):
            cli._config_cmd(["edit"])
        self.assertEqual(C.resolve("bg_model"), "qwen2.5:7b")

    def test_empty_answer_leaves_the_value_alone(self):
        C.set_value("bg_model", "qwen2.5:3b")
        self._answer(self._index_of("bg_model"), "")
        out = io.StringIO()
        with redirect_stdout(out):
            cli._config_cmd(["edit"])
        self.assertEqual(C.resolve("bg_model"), "qwen2.5:3b")
        self.assertIn("unchanged", out.getvalue())

    def test_daemon_settings_say_to_redeploy(self):
        self._answer(self._index_of("embed_model"), "bge-m3")
        out = io.StringIO()
        with redirect_stdout(out):
            cli._config_cmd(["edit"])
        self.assertIn("redeploy", out.getvalue())

    def test_menu_shows_current_values(self):
        C.set_value("bg_model", "qwen2.5:3b")
        self._answer(self._index_of("bg_model"), "")
        out = io.StringIO()
        with redirect_stdout(out):
            cli._config_cmd(["edit"])
        self.assertIn("qwen2.5:3b", out.getvalue())


if __name__ == "__main__":
    unittest.main()
