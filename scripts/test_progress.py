#!/usr/bin/env python3
"""Run the unittest suite with a live progress line instead of a wall of dots.

    python3 scripts/test_progress.py [tests_dir]

On a terminal: one redrawn line — bar, done/total, elapsed, the test running
right now and how long it has been running (yellow past SLOW seconds, so a hang
names itself). Failures print above the bar as they happen; what a test prints
is captured and shown only if it fails. Without a terminal (CI, a log file): a
plain line every 10%. Ctrl-C reports which test it stopped in. Exit code is 0
only if everything passed.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import time
import unittest

SLOW = 10.0  # seconds before the running test is shown as suspicious
TICK = 0.25
_ANSI = re.compile(r"\033\[[0-9;]*[A-Za-z]")

TTY = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
B, D, R = ("\033[1m", "\033[2m", "\033[0m") if TTY else ("", "", "")
RED, GRN, YLW, CYN = ("\033[31m", "\033[32m", "\033[33m", "\033[36m") if TTY else ("",) * 4


def _clock(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def _short(test) -> str:
    """`module.Class.test_name` — what you would pass to `-m unittest` to rerun it."""
    return test.id()


def _visible(text: str) -> int:
    return len(_ANSI.sub("", text))


class ProgressResult(unittest.TestResult):
    def __init__(self, total: int, out) -> None:
        super().__init__()
        self.buffer = True  # the suite's own prints stay out of the way unless a test fails
        self.total = total
        self.out = out
        self.done = 0
        self.started = time.monotonic()
        self.current: str | None = None
        self.last: str | None = None  # survives stopTest, so Ctrl-C can name the hang
        self.current_at = 0.0
        self.timings: list[tuple[float, str]] = []
        self._lock = threading.Lock()
        self._last_pct = -1

    # ── drawing ──────────────────────────────────────────────────────────────
    def _line(self) -> str:
        width = shutil.get_terminal_size((100, 20)).columns
        frac = self.done / self.total if self.total else 1.0
        bar_w = 24
        fill = int(frac * bar_w)
        bad = len(self.failures) + len(self.errors)
        bar = (RED if bad else GRN) + "█" * fill + D + "░" * (bar_w - fill) + R
        head = (f"  {bar} {B}{self.done}/{self.total}{R} {int(frac * 100):3d}%"
                f"  {D}{_clock(time.monotonic() - self.started)}{R}")
        if bad:
            head += f"  {RED}✗ {bad}{R}"
        if not self.current:
            return head
        running = time.monotonic() - self.current_at
        name = self.current
        tag = f" {running:.0f}s" if running >= 1 else ""
        room = width - _visible(head) - len(tag) - 5
        if room < 12:
            return head
        if len(name) > room:
            name = "…" + name[-(room - 1):]
        col = YLW if running >= SLOW else D
        return f"{head}  {col}▸ {name}{tag}{R}"

    def draw(self) -> None:
        with self._lock:
            if TTY:
                self.out.write("\r\033[K" + self._line())
                self.out.flush()
                return
            pct = (self.done * 10 // self.total * 10) if self.total else 100
            if pct != self._last_pct:
                self._last_pct = pct
                self.out.write(f"  {self.done}/{self.total} ({pct}%) {_clock(time.monotonic() - self.started)}\n")
                self.out.flush()

    def above(self, text: str) -> None:
        """Print a permanent line above the live bar."""
        with self._lock:
            self.out.write(("\r\033[K" if TTY else "") + text + "\n")
            self.out.flush()
        self.draw()

    # ── unittest hooks ───────────────────────────────────────────────────────
    def startTest(self, test) -> None:
        super().startTest(test)
        self.current, self.current_at = _short(test), time.monotonic()
        self.last = self.current
        self.draw()

    def stopTest(self, test) -> None:
        super().stopTest(test)
        self.timings.append((time.monotonic() - self.current_at, _short(test)))
        self.done += 1
        self.current = None
        self.draw()

    def addFailure(self, test, err) -> None:
        super().addFailure(test, err)
        self._mirrorOutput = False  # captured output is already in the traceback below
        self.above(f"  {RED}✗ FAIL{R}  {_short(test)}")

    def addError(self, test, err) -> None:
        super().addError(test, err)
        self._mirrorOutput = False
        self.above(f"  {RED}✗ ERROR{R} {_short(test)}")

    def addUnexpectedSuccess(self, test) -> None:
        super().addUnexpectedSuccess(test)
        self.above(f"  {YLW}⚠ unexpected success{R} {_short(test)}")


def main(argv: list[str]) -> int:
    start_dir = argv[1] if len(argv) > 1 else "tests"
    out = sys.stdout
    # run as a script, sys.path[0] is scripts/ — tests that import the package
    # expect the repo root there, exactly as `python -m unittest` puts it
    sys.path.insert(0, os.getcwd())
    suite = unittest.defaultTestLoader.discover(start_dir)
    result = ProgressResult(suite.countTestCases(), out)

    stop = threading.Event()

    def ticker() -> None:  # keeps the clock and "running for Ns" moving during a slow test
        while not stop.wait(TICK if TTY else 30):
            if TTY:
                result.draw()
                continue
            name, since = result.current, result.current_at
            if name and time.monotonic() - since >= SLOW:  # a log has no live line: say it
                result.above(f"  … still in {name} ({time.monotonic() - since:.0f}s)")

    threading.Thread(target=ticker, daemon=True).start()
    interrupted = False
    try:
        suite.run(result)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        stop.set()
    if TTY:
        out.write("\r\033[K")

    for kind, items in (("FAIL", result.failures), ("ERROR", result.errors)):
        for test, tb in items:
            out.write(f"\n{RED}{'━' * 60}{R}\n{RED}{B}{kind}{R} {_short(test)}\n{tb}")

    took = _clock(time.monotonic() - result.started)
    slow = sorted(result.timings, reverse=True)[:3]
    if interrupted:
        where = result.last or "before the first test"
        out.write(f"  {YLW}⚠ interrupted after {took} in {B}{where}{R}\n")
        return 130
    bad = len(result.failures) + len(result.errors)
    skipped = f" · {len(result.skipped)} skipped" if result.skipped else ""
    if bad:
        out.write(f"\n  {RED}✗ {bad} failed{R} · {result.testsRun - bad} passed{skipped} · {took}\n")
    else:
        out.write(f"  {GRN}✓{R} {B}{result.testsRun} passed{R}{skipped} {D}· {took}{R}\n")
    if slow:
        out.write(f"  {D}slowest: " + ", ".join(f"{n.split('.')[-1]} {t:.1f}s" for t, n in slow) + f"{R}\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
