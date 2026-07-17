"""The stdlib prompt primitives: the non-TTY fallback and the BACK sentinel.

Raw mode needs a real terminal to drive, so what's pinned here is the fallback —
the path `ygg install` actually takes under uvx, npx, Docker and CI, and the one
that breaks silently if it ever regresses.

These must pass identically from a shell and from a pipe, which is the whole
trick: the environment differs, so nothing may assert on the ambient terminal
(`interactive()` gets explicit streams) and nothing may reach the fallback by
luck (`_ForcePlain` sets YGG_NO_TUI, instead of relying on redirect_stdout to
happen to hide the tty — that version passed piped and hung on a real one).
"""

import builtins
import io
import os
import unittest
from contextlib import redirect_stdout

from yggdrasil import ygg_prompt as p

OPTS = [p.Option("ollama", "Ollama, local", "private"),
        p.Option("openrouter", "OpenRouter, hosted", "free tier"),
        p.Option("none", "none", "lexical only")]


class _Answers:
    """Feed scripted answers to input()/getpass()."""

    def __init__(self, *answers):
        self.it = iter(answers)

    def __enter__(self):
        self._real = builtins.input
        builtins.input = lambda *a, **k: next(self.it)
        return self

    def __exit__(self, *a):
        builtins.input = self._real
        return False


def _quiet(fn, *a, **k):
    with redirect_stdout(io.StringIO()):
        return fn(*a, **k)


class _Tty(io.StringIO):
    def isatty(self):
        return True


class _Pipe(io.StringIO):
    def isatty(self):
        return False


class InteractiveDetectionTest(unittest.TestCase):
    """Assert on the streams we pass in, never on the ambient terminal: these
    run both from a real shell (tty) and from CI (pipe), and a test that reads
    the environment passes in one and fails in the other."""

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("NO_COLOR", "YGG_NO_COLOR", "YGG_NO_TUI")}
        for k in self._env:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_both_ends_a_terminal_can_drive_raw_mode(self):
        self.assertTrue(p.interactive(inp=_Tty(), out=_Tty()))

    def test_piped_stdin_cannot(self):
        """`ygg install < /dev/null` has a tty stdout and a dead stdin — reading
        keys there blocks forever."""
        self.assertFalse(p.interactive(inp=_Pipe(), out=_Tty()))

    def test_piped_stdout_cannot(self):
        self.assertFalse(p.interactive(inp=_Tty(), out=_Pipe()))

    def test_no_color_forces_the_plain_path(self):
        os.environ["NO_COLOR"] = "1"
        self.assertFalse(p.interactive(inp=_Tty(), out=_Tty()))

    def test_env_kill_switch(self):
        os.environ["YGG_NO_TUI"] = "1"
        self.assertFalse(p.interactive(inp=_Tty(), out=_Tty()))


class _ForcePlain(unittest.TestCase):
    """Pin the fallback path explicitly. Without this these tests only took it
    because redirect_stdout happened to hide the tty — run them from a real
    terminal and they'd enter raw mode and hang waiting for a keypress."""

    def setUp(self):
        self._prev = os.environ.get("YGG_NO_TUI")
        os.environ["YGG_NO_TUI"] = "1"

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("YGG_NO_TUI", None)
        else:
            os.environ["YGG_NO_TUI"] = self._prev


class SelectFallbackTest(_ForcePlain):
    def test_number_picks_the_option(self):
        with _Answers("2"):
            self.assertEqual(_quiet(p.select, "Where?", OPTS), "openrouter")

    def test_empty_takes_the_default(self):
        with _Answers(""):
            self.assertEqual(_quiet(p.select, "Where?", OPTS, default="none"), "none")

    def test_default_is_the_first_option_when_unset(self):
        with _Answers(""):
            self.assertEqual(_quiet(p.select, "Where?", OPTS), "ollama")

    def test_b_returns_back_when_allowed(self):
        with _Answers("b"):
            self.assertEqual(_quiet(p.select, "Where?", OPTS, allow_back=True), p.BACK)

    def test_b_is_not_back_when_not_allowed(self):
        """On the first step `b` is just a bad answer — reprompt, don't escape."""
        with _Answers("b", "3"):
            self.assertEqual(_quiet(p.select, "Where?", OPTS, allow_back=False), "none")

    def test_reprompts_on_garbage(self):
        with _Answers("9", "banana", "1"):
            self.assertEqual(_quiet(p.select, "Where?", OPTS), "ollama")

    def test_eof_takes_the_default_instead_of_crashing(self):
        """`ygg install < /dev/null` must not traceback."""
        def eof(*a, **k):
            raise EOFError
        real, builtins.input = builtins.input, eof
        try:
            self.assertEqual(_quiet(p.select, "Where?", OPTS, default="openrouter"), "openrouter")
        finally:
            builtins.input = real


class TextTest(_ForcePlain):
    def test_empty_takes_the_default(self):
        with _Answers(""):
            self.assertEqual(p.text("Model", "all-minilm"), "all-minilm")

    def test_value_overrides_the_default(self):
        with _Answers("bge-m3"):
            self.assertEqual(p.text("Model", "all-minilm"), "bge-m3")

    def test_back(self):
        with _Answers("b"):
            self.assertEqual(p.text("Model", "x", allow_back=True), p.BACK)

    def test_eof_takes_the_default(self):
        def eof(*a, **k):
            raise EOFError
        real, builtins.input = builtins.input, eof
        try:
            self.assertEqual(p.text("Model", "all-minilm"), "all-minilm")
        finally:
            builtins.input = real


class ConfirmTest(_ForcePlain):
    def test_yes_no_and_default(self):
        with _Answers("y"):
            self.assertTrue(p.confirm("ok?", False))
        with _Answers("n"):
            self.assertFalse(p.confirm("ok?", True))
        with _Answers(""):
            self.assertTrue(p.confirm("ok?", True))

    def test_back(self):
        with _Answers("b"):
            self.assertEqual(p.confirm("ok?", True, allow_back=True), p.BACK)


class HostedEndpointDetectionTest(unittest.TestCase):
    """`ygg doctor` warns about a hosted endpoint with no key. Anything on your
    own machine or LAN authenticates nothing and must stay quiet."""

    def test_local_and_lan_are_not_hosted(self):
        from yggdrasil.cli import _is_hosted
        for url in ("http://127.0.0.1:11434", "http://localhost:8080/v1",
                    "http://192.168.3.124:11434", "http://10.0.0.5:11434",
                    "http://172.16.0.9:11434", "http://macbook.local:11434", ""):
            self.assertFalse(_is_hosted(url), url)

    def test_real_hostnames_are_hosted(self):
        from yggdrasil.cli import _is_hosted
        for url in ("https://openrouter.ai/api/v1",
                    "https://kom8s3dc7y2i3n-11434.proxy.runpod.net",
                    "https://api.openai.com/v1"):
            self.assertTrue(_is_hosted(url), url)


if __name__ == "__main__":
    unittest.main()
