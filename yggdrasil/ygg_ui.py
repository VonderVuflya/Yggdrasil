#!/usr/bin/env python3
"""Tiny stdlib-only terminal UI for the `ygg` CLI — one visual language.

Colour and fancy rendering turn on ONLY for a real TTY with colour allowed, so
piped / agent / gate output stays plain and byte-stable, and `--json` is never
touched. No dependencies — pure ANSI. Everything a command needs to look good
lives here: palette, type badges, a relevance bar, relative time, short ids.
"""

from __future__ import annotations

import os
import sys
import time

# Canonical memory type -> ANSI colour code. Keeps every command's badges
# consistent (a `fix` is always yellow, a `decision` always cyan).
_TYPE_COLOR = {
    "decision": "36", "lesson": "32", "fix": "33", "convention": "34",
    "project_status": "35", "follow_up": "31", "reference": "2",
    # legacy / free-form types still get a sensible colour
    "project": "35", "todo": "33", "note": "2", "memory": "2",
}


class Palette:
    """ANSI colouriser, gated once on construction."""

    def __init__(self, on: bool):
        self.on = on

    def paint(self, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.on else s

    def cyan(self, s): return self.paint("36", s)
    def green(self, s): return self.paint("32", s)
    def red(self, s): return self.paint("31", s)
    def yellow(self, s): return self.paint("33", s)
    def magenta(self, s): return self.paint("35", s)
    def blue(self, s): return self.paint("34", s)
    def dim(self, s): return self.paint("2", s)
    def bold(self, s): return self.paint("1", s)


def enabled(stream=None) -> bool:
    """True when it's safe to emit colour/animation: a real TTY, colour not
    disabled. NO_COLOR (any value) and YGG_NO_COLOR both force plain."""
    if os.environ.get("NO_COLOR") is not None or os.environ.get("YGG_NO_COLOR"):
        return False
    stream = stream if stream is not None else sys.stdout
    try:
        return bool(stream.isatty())
    except (ValueError, AttributeError):
        return False


def palette(stream=None) -> Palette:
    return Palette(enabled(stream))


def badge(mtype: str | None, p: Palette) -> str:
    """A colour-coded memory-type tag."""
    return p.paint(_TYPE_COLOR.get(mtype or "", "2"), mtype or "memory")


def bar(frac: float, p: Palette, width: int = 5) -> str:
    """A relevance meter `▰▰▰▱▱` — filled cells coloured, empty dim."""
    try:
        frac = max(0.0, min(1.0, float(frac)))
    except (TypeError, ValueError):
        frac = 0.0
    full = round(frac * width)
    return p.green("▰" * full) + p.dim("▱" * (width - full))


def ago(ts) -> str:
    """Relative time like `2d ago` / `3h ago` / `just now` from a unix ts."""
    try:
        delta = time.time() - float(ts)
    except (TypeError, ValueError):
        return ""
    if delta < 90:
        return "just now"
    for unit, n in (("d", 86400), ("h", 3600), ("m", 60)):
        if delta >= n:
            return f"{int(delta // n)}{unit} ago"
    return "just now"


def short_id(mid: str | None, keep: int = 10) -> str:
    mid = mid or ""
    return mid[:keep] + "…" if len(mid) > keep else mid


def mark_ok(p: Palette) -> str: return p.green("✓")
def mark_warn(p: Palette) -> str: return p.yellow("–")
def mark_fail(p: Palette) -> str: return p.red("✗")
