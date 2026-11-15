"""Merge policy — the single resolver both transports share.

`ygg sync` (git) and the peer uplink call the SAME functions, and two nodes
reconcile independently, without agreeing on an order. So the rules have to be
commutative: if merge(a,b) != merge(b,a) the machines never converge, they just
take turns overwriting each other.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg_sync_merge as merge  # noqa: E402


def _rec(**kw):
    base = {"id": "ygg_x", "user_id": "local", "namespace": "personal", "scope": "project",
            "project": "p", "type": "lesson", "content": "a fact", "content_hash": "h",
            "source": "s", "confidence": 0.5, "importance": 0.5, "created_at": 100.0,
            "updated_at": 100.0, "archived": 0, "metadata_json": "{}"}
    base.update(kw)
    return base


class ConvergenceTest(unittest.TestCase):
    """The two properties that make independent reconcile safe. Everything else
    in this file is a detail of the rules; these are the contract."""

    CASES = (
        (_rec(), _rec(content="a much longer fact with detail", content_hash="h2")),
        (_rec(archived=1), _rec(confidence=0.9)),
        (_rec(importance=0.2, updated_at=100.0), _rec(importance=0.8, updated_at=300.0)),
        (_rec(metadata_json='{"pinned": true}'), _rec(metadata_json='{"tag": "x"}')),
        (_rec(confidence=None), _rec(confidence=0.4)),
        (_rec(content="a long original version", updated_at=100.0),
         _rec(content="short fix", content_hash="h3", updated_at=200.0)),
        (_rec(metadata_json='{"k": 1}'), _rec(metadata_json='{"k": "1"}')),
        (_rec(archived=1, metadata_json='{"status": "archived"}'),
         _rec(archived=0, updated_at=50.0,
              metadata_json='{"archived_changed_at": 400.0, "status": "active"}')),
        (_rec(archived=1, metadata_json='{"archived_changed_at": 300.0, "status": "archived"}'),
         _rec(archived=0, updated_at=900.0, content="edited", content_hash="he")),
        (_rec(archived=1, metadata_json='{"archived_changed_at": 300.0}'),
         _rec(archived=0, metadata_json='{"archived_changed_at": 300.0}')),
    )

    def test_merge_is_commutative(self):
        for a, b in self.CASES:
            with self.subTest(a=a["content"], b=b["content"]):
                self.assertEqual(merge.merge_memory(dict(a), dict(b)),
                                 merge.merge_memory(dict(b), dict(a)))

    def test_merge_is_idempotent(self):
        for a, b in self.CASES:
            with self.subTest(a=a["content"]):
                once = merge.merge_memory(dict(a), dict(b))
                self.assertEqual(once, merge.merge_memory(dict(once), dict(once)))


class FieldRulesTest(unittest.TestCase):
    def test_archive_decision_holds_everywhere(self):
        self.assertEqual(merge.merge_memory(_rec(archived=0), _rec(archived=1))["archived"], 1)
        self.assertEqual(merge.merge_memory(_rec(archived=1), _rec(archived=0))["archived"], 1)

    def _both(self, a, b):
        return [merge.merge_memory(dict(x), dict(y)) for x, y in ((a, b), (b, a))]

    def test_a_later_unarchive_beats_an_archive(self):
        """Archive merged by OR, so restoring a memory on one machine was undone
        by the next reconcile with the other: "reversible" was not true."""
        archived = _rec(archived=1, metadata_json='{"archived_changed_at": 300.0, "status": "archived"}')
        restored = _rec(archived=0, metadata_json='{"archived_changed_at": 400.0, "status": "active"}')
        for m in self._both(archived, restored):
            self.assertEqual(m["archived"], 0)
            self.assertEqual(json.loads(m["metadata_json"])["status"], "active")
            self.assertEqual(json.loads(m["metadata_json"])["archived_changed_at"], 400.0)

    def test_an_unarchive_beats_an_archive_from_before_the_stamp_existed(self):
        legacy = _rec(archived=1, updated_at=900.0, metadata_json='{"status": "archived"}')
        restored = _rec(archived=0, updated_at=100.0,
                        metadata_json='{"archived_changed_at": 400.0, "status": "active"}')
        for m in self._both(legacy, restored):
            self.assertEqual(m["archived"], 0)

    def test_an_edit_elsewhere_does_not_unarchive(self):
        """The archive decision has its own clock: a newer CONTENT edit on a
        machine that never saw the archive must not bring the memory back."""
        archived = _rec(archived=1, metadata_json='{"archived_changed_at": 300.0, "status": "archived"}')
        edited = _rec(archived=0, updated_at=900.0, content="edited later", content_hash="he")
        for m in self._both(archived, edited):
            self.assertEqual(m["archived"], 1)
            self.assertEqual(m["content"], "edited later")
            self.assertEqual(json.loads(m["metadata_json"])["status"], "archived")

    def test_an_equal_archive_stamp_still_archives(self):
        a = _rec(archived=1, metadata_json='{"archived_changed_at": 300.0}')
        b = _rec(archived=0, metadata_json='{"archived_changed_at": 300.0}')
        for m in self._both(a, b):
            self.assertEqual(m["archived"], 1)

    def test_confidence_and_importance_take_the_stronger_signal(self):
        m = merge.merge_memory(_rec(confidence=0.2, importance=0.1),
                               _rec(confidence=0.9, importance=0.8))
        self.assertEqual(m["confidence"], 0.9)
        self.assertEqual(m["importance"], 0.8)

    def test_a_newer_edit_wins_even_when_it_is_shorter(self):
        """Corrections shrink text. Under "longer wins" a fix that tightened a
        memory was reverted by every peer that still had the wordier copy."""
        old = _rec(content="a long, wordy and partly wrong version", content_hash="ho", updated_at=100.0)
        new = _rec(content="the fix", content_hash="hn", updated_at=200.0)
        for a, b in ((old, new), (new, old)):
            m = merge.merge_memory(dict(a), dict(b))
            self.assertEqual((m["content"], m["content_hash"]), ("the fix", "hn"))

    def test_on_equal_stamps_longer_content_wins_and_carries_its_own_hash(self):
        m = merge.merge_memory(_rec(content="short", content_hash="hs"),
                               _rec(content="a longer text", content_hash="hl"))
        self.assertEqual((m["content"], m["content_hash"]), ("a longer text", "hl"))

    def test_equal_length_content_is_broken_by_value_not_by_side(self):
        """The old rule was "tie goes to local" — which is precisely the asymmetry
        that keeps two machines from converging: each side would keep its own text
        forever and the digests would never agree. The tie-break now looks only at
        the values, so both nodes land on the same one."""
        a, b = _rec(content="local", content_hash="hl"), _rec(content="remot", content_hash="hr")
        self.assertEqual(merge.merge_memory(dict(a), dict(b)),
                         merge.merge_memory(dict(b), dict(a)))
        self.assertEqual(merge.merge_memory(dict(a), dict(b))["content"], "remot")

    def test_a_tie_between_values_of_different_types_is_symmetric(self):
        """str() makes 1 and "1" look identical, so the old tie-break returned
        whichever argument came first."""
        a, b = _rec(metadata_json='{"k": 1}'), _rec(metadata_json='{"k": "1"}')
        self.assertEqual(merge.merge_memory(dict(a), dict(b))["metadata_json"],
                         merge.merge_memory(dict(b), dict(a))["metadata_json"])

    def test_a_value_beats_a_missing_one_on_a_tie(self):
        self.assertEqual(merge.merge_memory(_rec(source=None), _rec(source="agent"))["source"], "agent")
        self.assertEqual(merge.merge_memory(_rec(source="agent"), _rec(source=None))["source"], "agent")

    def test_metadata_unions_and_pinned_is_sticky(self):
        m = merge.merge_memory(_rec(metadata_json='{"a": 1, "pinned": true}'),
                               _rec(metadata_json='{"b": 2}'))
        self.assertEqual(json.loads(m["metadata_json"]), {"a": 1, "b": 2, "pinned": True})

    def test_updated_at_takes_the_latest(self):
        self.assertEqual(merge.merge_memory(_rec(updated_at=100.0), _rec(updated_at=500.0))["updated_at"], 500.0)

    def test_missing_updated_at_falls_back_to_created_at(self):
        a = _rec(created_at=7.0); a.pop("updated_at")
        b = _rec(created_at=7.0); b.pop("updated_at")
        self.assertEqual(merge.merge_memory(a, b)["updated_at"], 7.0)

    def test_corrupt_metadata_json_does_not_stop_a_reconcile(self):
        m = merge.merge_memory(_rec(metadata_json="{not json"), _rec(metadata_json='{"b": 2}'))
        self.assertEqual(m["id"], "ygg_x")


class ClockSkewTest(unittest.TestCase):
    def test_a_stamp_from_the_future_is_clamped(self):
        """A peer whose clock runs a year ahead would otherwise win every
        recency-resolved field forever."""
        self.assertEqual(merge.clamp_stamp(10_000.0, now=100.0), 100.0 + merge.MAX_CLOCK_SKEW)

    def test_a_plausible_stamp_is_left_alone(self):
        self.assertEqual(merge.clamp_stamp(90.0, now=100.0), 90.0)
        self.assertEqual(merge.clamp_stamp(100.0 + merge.MAX_CLOCK_SKEW - 1, now=100.0),
                         100.0 + merge.MAX_CLOCK_SKEW - 1)


class TombstoneTest(unittest.TestCase):
    def test_tombstone_beats_even_a_newer_edit(self):
        """Deliberate. Comparing deleted_at with updated_at would let clock skew on
        the other machine resurrect something the user deleted — and 'I deleted the
        leaked token' has to hold unconditionally. `archive` is the reversible verb."""
        self.assertTrue(merge.tombstone_wins(deleted_at=1.0, record=_rec(updated_at=9999.0), now=2.0))

    def test_expired_tombstone_stops_blocking_the_record(self):
        self.assertFalse(merge.tombstone_wins(deleted_at=0.0, record=_rec(),
                                              now=merge.TOMBSTONE_TTL + 10.0))

    def test_expired_tombstones_are_collectable(self):
        now = merge.TOMBSTONE_TTL + 100.0
        self.assertEqual(merge.expired_tombstones({"a": 0.0, "b": now - 5.0}, now=now), ["a"])

    def test_live_tombstones_are_kept(self):
        self.assertEqual(merge.expired_tombstones({"a": 10.0}, now=20.0), [])


if __name__ == "__main__":
    unittest.main()


class EdgeRuleTest(unittest.TestCase):
    def test_an_unlink_beats_the_link_it_saw(self):
        self.assertFalse(merge.edge_survives(100.0, 150.0))

    def test_a_link_made_after_the_unlink_wins(self):
        self.assertTrue(merge.edge_survives(200.0, 150.0))

    def test_a_tie_goes_to_the_unlink(self):
        self.assertFalse(merge.edge_survives(150.0, 150.0))

    def test_an_unstamped_link_never_beats_an_unlink(self):
        self.assertFalse(merge.edge_survives(None, 1.0))

    def test_no_unlink_means_the_edge_stands(self):
        self.assertTrue(merge.edge_survives(None, None))
