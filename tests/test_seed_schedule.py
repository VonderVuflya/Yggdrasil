"""Scheduled seed: the pure pieces (time parsing, plist rendering) — the
launchctl glue is exercised manually, these pin the contract."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg_seed  # noqa: E402


class ParseHhmmTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(ygg_seed.parse_hhmm("03:30"), (3, 30))
        self.assertEqual(ygg_seed.parse_hhmm("7:05"), (7, 5))
        self.assertEqual(ygg_seed.parse_hhmm("23:59"), (23, 59))
        self.assertEqual(ygg_seed.parse_hhmm("on"), (3, 30))   # bare 'on' -> default

    def test_invalid(self):
        for bad in ("24:00", "12:60", "330", "3:3", "", "midnight", "12:345"):
            self.assertIsNone(ygg_seed.parse_hhmm(bad), bad)


class SeedPlistTest(unittest.TestCase):
    def render(self):
        return ygg_seed.seed_schedule_plist(
            ["/usr/bin/python3", "/home/u/.yggdrasil/scripts/cli.py", "seed", "--yes"],
            3, 30, "/home/u/.yggdrasil/logs/seed-scheduled.log")

    def test_calendar_fired_not_kept_alive(self):
        text = self.render()
        self.assertIn("<key>StartCalendarInterval</key>", text)
        self.assertIn("<key>Hour</key><integer>3</integer>", text)
        self.assertIn("<key>Minute</key><integer>30</integer>", text)
        self.assertIn("<key>RunAtLoad</key><false/>", text)
        self.assertNotIn("KeepAlive", text)   # a nightly job, not a daemon

    def test_argv_and_log_paths_present(self):
        text = self.render()
        for part in ("cli.py", "<string>seed</string>", "<string>--yes</string>",
                     "seed-scheduled.log"):
            self.assertIn(part, text)
        self.assertIn(ygg_seed.SEED_LABEL, text)


if __name__ == "__main__":
    unittest.main()
