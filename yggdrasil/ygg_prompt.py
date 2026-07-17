#!/usr/bin/env python3
"""Interactive prompts for the setup wizard — arrow keys, stdlib only.

Why not a prompt library: the pretty part is ~100 lines of ANSI, while the part
we actually needed — stepping BACK through a wizard — is a state machine no
prompt library hands you anyway (clack, the usual reference, doesn't). Paying
for that with the "zero dependencies" line in the README, which is a row we win
on in the comparison table, was a bad trade.

Degrades instead of breaking. `ygg install` runs through `uvx`, `npx` and Docker
where stdin often isn't a terminal; there a raw-mode TUI can't work at all, so
these fall back to a numbered list on plain input(), and to the default when
even that is impossible (EOF). The wizard's contract is identical either way.

Keys: ↑↓ (or k/j) move · enter picks · ← (or b) goes back · ctrl-c quits.
"""

from __future__ import annotations

import os
import sys

try:  # package context
    from . import ygg_ui
except ImportError:  # flat deploy
    import ygg_ui  # type: ignore

BACK = "\x00ygg-back"      # sentinel: user asked for the previous step
_ESC = "\x1b"


def interactive(inp=None, out=None) -> bool:
    """True only when a raw-mode TUI can actually work: BOTH ends are a terminal.

    stdout alone isn't enough — `ygg install < /dev/null` and piped installers
    have a tty stdout and a dead stdin, and reading keys there blocks forever.
    """
    if os.environ.get("YGG_NO_TUI"):
        return False
    inp = inp if inp is not None else sys.stdin
    try:
        return bool(inp.isatty()) and ygg_ui.enabled(out if out is not None else sys.stdout)
    except (ValueError, AttributeError):
        return False


# --------------------------------------------------------------------------- #
# key reading
# --------------------------------------------------------------------------- #

def _read_key_posix() -> str:
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch != _ESC:
            return ch
        # An escape sequence (arrows) arrives as ESC [ A. A LONE esc (quit) has
        # nothing behind it — peek with a zero timeout instead of blocking.
        import select as _select
        if not _select.select([sys.stdin], [], [], 0.05)[0]:
            return _ESC
        rest = sys.stdin.read(1)
        if rest != "[":
            return _ESC
        return _ESC + "[" + sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_key_windows() -> str:
    import msvcrt
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):        # arrow prefix
        return {"H": _ESC + "[A", "P": _ESC + "[B",
                "K": _ESC + "[D", "M": _ESC + "[C"}.get(msvcrt.getwch(), "")
    return ch


def read_key() -> str:
    return _read_key_windows() if os.name == "nt" else _read_key_posix()


UP, DOWN, LEFT, RIGHT = _ESC + "[A", _ESC + "[B", _ESC + "[D", _ESC + "[C"


# --------------------------------------------------------------------------- #
# select
# --------------------------------------------------------------------------- #

class Option:
    """One choice. `note` is the trade-off — the reason a user picks this one."""

    def __init__(self, value: str, label: str, note: str = ""):
        self.value, self.label, self.note = value, label, note


def _render(title: str, options: list[Option], cursor: int, p, allow_back: bool) -> int:
    """Draw the menu; return how many lines were printed (to erase next pass)."""
    lines = [f"{p.bold('◆')}  {p.bold(title)}"]
    for i, o in enumerate(options):
        if i == cursor:
            mark, label = p.green("●"), p.bold(o.label)
        else:
            mark, label = p.dim("○"), o.label
        note = f"  {p.dim(o.note)}" if o.note else ""
        lines.append(f"{p.dim('│')}  {mark} {label:<22}{note}")
    hint = "↑↓ move · enter select" + (" · ← back" if allow_back else "") + " · ctrl-c quit"
    lines.append(f"{p.dim('└')}  {p.dim(hint)}")
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()
    return len(lines)


def _erase(n: int) -> None:
    sys.stdout.write(f"\033[{n}F\033[J")   # up n lines, clear to end of screen
    sys.stdout.flush()


def select(title: str, options: list[Option], default: str = "",
           allow_back: bool = False) -> str:
    """Pick one option's value. Returns BACK if the user steps back.

    Falls back to a numbered list when there's no terminal to drive.
    """
    idx = next((i for i, o in enumerate(options) if o.value == default), 0)
    if not interactive():
        return _select_plain(title, options, idx, allow_back)

    p = ygg_ui.palette()
    n = _render(title, options, idx, p, allow_back)
    try:
        while True:
            key = read_key()
            if key in ("\r", "\n"):
                _erase(n)
                _render_done(title, options[idx], p)
                return options[idx].value
            if key in (UP, "k"):
                idx = (idx - 1) % len(options)
            elif key in (DOWN, "j"):
                idx = (idx + 1) % len(options)
            elif allow_back and key in (LEFT, "b"):
                _erase(n)
                return BACK
            elif key in ("\x03", _ESC):     # ctrl-c / esc
                _erase(n)
                raise KeyboardInterrupt
            else:
                continue
            _erase(n)
            n = _render(title, options, idx, p, allow_back)
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        raise


def _render_done(title: str, chosen: Option, p) -> None:
    sys.stdout.write(f"{p.green('✓')}  {title}  {p.bold(chosen.label)}\n")
    sys.stdout.flush()


def _select_plain(title: str, options: list[Option], idx: int, allow_back: bool) -> str:
    """No terminal: a numbered list on plain input(). Same contract."""
    print(f"\n{title}")
    for i, o in enumerate(options, 1):
        note = f"  — {o.note}" if o.note else ""
        print(f"  {i}) {o.label}{note}")
    suffix = "  (b = back)" if allow_back else ""
    while True:
        try:
            raw = input(f"Choice [{idx + 1}]{suffix}: ").strip()
        except EOFError:                    # piped/no stdin -> take the default
            return options[idx].value
        if not raw:
            return options[idx].value
        if allow_back and raw.lower() == "b":
            return BACK
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1].value
        print(f"  pick 1-{len(options)}")


# --------------------------------------------------------------------------- #
# free text
# --------------------------------------------------------------------------- #

def text(prompt: str, default: str = "", secret: bool = False,
         allow_back: bool = False) -> str:
    """A line of text, `default` shown as the placeholder. `b` steps back.

    Secrets are read with getpass so a pasted key never lands in the scrollback
    (or in a screen recording of the install).
    """
    shown = f" [{default}]" if default and not secret else ""
    hint = "  (b = back)" if allow_back else ""
    while True:
        try:
            if secret:
                import getpass
                raw = getpass.getpass(f"{prompt}{hint}: ").strip()
            else:
                raw = input(f"{prompt}{shown}{hint}: ").strip()
        except EOFError:
            return default
        if allow_back and raw.lower() == "b":
            return BACK
        if raw or default:
            return raw or default
        print("  required")


def confirm(prompt: str, default: bool = True, allow_back: bool = False):
    """Yes/no. Returns BACK if the user steps back."""
    d = "Y/n" if default else "y/N"
    while True:
        try:
            raw = input(f"{prompt} ({d}): ").strip().lower()
        except EOFError:
            return default
        if not raw:
            return default
        if allow_back and raw == "b":
            return BACK
        if raw[0] in "yn":
            return raw[0] == "y"


def banner(title: str) -> None:
    p = ygg_ui.palette()
    print(f"\n{p.green('┌')}  🌳 {p.bold(title)}\n{p.dim('│')}")
