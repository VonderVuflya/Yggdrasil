"""ygg review: queue building + duplicate keep/archive planning (pure logic)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg  # noqa: E402


def _rec(mid, content, *, project="p", mtype="lesson", created=0.0, chash=None, status=None):
    md = {"type": mtype, "project": project, "source": "t"}
    if chash:
        md["content_hash"] = chash
    if status:
        md["status"] = status
    return {"id": mid, "memory": content, "content": content, "created_at": created, "metadata": md}


class ReviewQueueTest(unittest.TestCase):
    def test_exact_duplicates_grouped_and_planned(self):
        recs = [
            _rec("a", "same text", created=1.0, chash="H"),
            _rec("b", "same text", created=2.0, chash="H"),
            _rec("c", "different", created=3.0, chash="H2"),
        ]
        issues = ygg._review_issues(recs)
        dups = [i for i in issues if i["kind"] == "exact_duplicate"]
        self.assertEqual(len(dups), 1)
        keep, archive = ygg._dup_keep_and_archive(dups[0])
        self.assertEqual(keep, "a")           # oldest kept
        self.assertEqual(archive, ["b"])      # the rest archived

    def test_stale_marker_detected_but_never_auto_archived_id(self):
        recs = [_rec("s", "this decision is now superseded by the new approach", created=1.0)]
        issues = ygg._review_issues(recs)
        stale = [i for i in issues if i["kind"] == "stale_or_conflict_marker"]
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["severity"], "high")

    def test_clean_store_has_no_issues(self):
        recs = [_rec("a", "unique lesson one", created=1.0, chash="H1"),
                _rec("b", "unique lesson two", created=2.0, chash="H2")]
        self.assertEqual(ygg._review_issues(recs), [])

    def test_issues_sorted_high_severity_first(self):
        recs = [
            _rec("a", "same dup text here", created=1.0, chash="H"),
            _rec("b", "same dup text here", created=2.0, chash="H"),
            _rec("s", "this approach was superseded by the new one", created=3.0),
        ]
        issues = ygg._review_issues(recs)
        self.assertEqual(issues[0]["severity"], "high")   # stale marker leads


if __name__ == "__main__":
    unittest.main()
