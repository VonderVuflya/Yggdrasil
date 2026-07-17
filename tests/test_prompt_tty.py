"""The raw-mode path, driven by real keypresses through a real pty.

This is the test that should have existed first. test_prompt.py covers the
non-TTY fallback thoroughly and never touched the arrow-key path — so the TUI
shipped with every arrow decoding as a lone ESC and killing the wizard, and the
suite stayed green throughout.

The bug it now pins: sys.stdin is a TextIOWrapper, so read(1) pulls a whole
os.read(fd, 8192) into ITS buffer. An arrow is three bytes (ESC [ A) — all three
land in that buffer, and the select() looking for the rest polls the descriptor,
which is empty. Only reading the fd directly keeps them where select can see it.
"""

import os
import pty
import select
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

UP, DOWN, LEFT, ENTER = b"\x1b[A", b"\x1b[B", b"\x1b[D", b"\r"

DRIVER = r"""
import sys
sys.path.insert(0, {root!r})
from yggdrasil import ygg_prompt as P
opts = [P.Option("ollama", "Ollama, local", "private"),
        P.Option("llamacpp", "llama.cpp, local", "no ollama"),
        P.Option("openrouter", "OpenRouter, hosted", "free tier")]
try:
    r = P.select("Where?", opts, allow_back={allow_back!r})
except KeyboardInterrupt:
    r = "INTERRUPTED"
sys.stderr.write("\nRESULT=" + str(r) + "\n")
sys.stderr.flush()
"""


def _pump(fd: bytearray, out: bytearray, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        if select.select([fd], [], [], 0.05)[0]:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                return
            if not chunk:
                return
            out += chunk


def drive(keys: list[bytes] | bytes, allow_back: bool = False, timeout: float = 8.0) -> str:
    """Run select() under a pty, press `keys`, return what it chose.

    Keys go in ONE AT A TIME with a gap. read_key() flips the tty into raw mode
    per call and restores it after, so between keypresses the line discipline is
    canonical again — a burst written into that window is held pending a newline
    that never comes, and the child blocks forever on a key it was already sent.
    """
    if isinstance(keys, bytes):
        keys = [keys]
    pid, fd = pty.fork()
    if pid == 0:                                     # child: the real prompt
        os.environ.pop("YGG_NO_TUI", None)
        os.environ.pop("NO_COLOR", None)
        code = DRIVER.format(root=ROOT, allow_back=allow_back)
        os.execv(sys.executable, [sys.executable, "-c", code])
    out = bytearray()
    try:
        _pump(fd, out, 0.8)                          # let the menu render + setraw
        for key in keys:
            os.write(fd, key)
            _pump(fd, out, 0.45)                     # let it redraw + re-enter raw
            if b"RESULT=" in out:
                break
        deadline = time.time() + timeout
        while b"RESULT=" not in out and time.time() < deadline:
            _pump(fd, out, 0.2)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.waitpid(pid, 0)
        except (ChildProcessError, OSError):
            pass
    text = bytes(out).decode("utf-8", "replace")
    for line in text.splitlines():
        if "RESULT=" in line:
            return line.split("RESULT=")[1].strip()
    return f"NO RESULT (got {text[-160:]!r})"


@unittest.skipUnless(hasattr(os, "fork"), "pty requires fork")
class ArrowKeyTest(unittest.TestCase):
    def test_enter_takes_the_highlighted_option(self):
        self.assertEqual(drive([ENTER]), "ollama")

    def test_down_moves_the_cursor(self):
        """The regression: this used to decode as a lone ESC and abort."""
        self.assertEqual(drive([DOWN, ENTER]), "llamacpp")

    def test_down_twice(self):
        self.assertEqual(drive([DOWN, DOWN, ENTER]), "openrouter")

    def test_up_wraps_to_the_end(self):
        self.assertEqual(drive([UP, ENTER]), "openrouter")

    def test_vim_keys(self):
        self.assertEqual(drive([b"j", ENTER]), "llamacpp")
        self.assertEqual(drive([b"j", b"k", ENTER]), "ollama")

    def test_left_steps_back_when_allowed(self):
        self.assertEqual(drive([LEFT], allow_back=True), P_BACK())

    def test_left_is_ignored_when_back_is_not_allowed(self):
        """On the first step there's nowhere back to — ← must not abort."""
        self.assertEqual(drive([LEFT, DOWN, ENTER], allow_back=False), "llamacpp")

    def test_ctrl_c_interrupts(self):
        self.assertEqual(drive([b"\x03"]), "INTERRUPTED")

    def test_unknown_escape_sequence_is_ignored(self):
        """Terminals emit focus events (ESC [ I) unprompted; one must not quit."""
        self.assertEqual(drive([b"\x1b[I", DOWN, ENTER]), "llamacpp")


def P_BACK():
    sys.path.insert(0, ROOT)
    from yggdrasil import ygg_prompt
    return ygg_prompt.BACK


if __name__ == "__main__":
    unittest.main()
