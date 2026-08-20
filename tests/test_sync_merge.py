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

    def test_confidence_and_importance_take_the_stronger_signal(self):
        m = merge.merge_memory(_rec(confidence=0.2, importance=0.1),
                               _rec(confidence=0.9, importance=0.8))
        self.assertEqual(m["confidence"], 0.9)
        self.assertEqual(m["importance"], 0.8)

    def test_longer_content_wins_and_carries_its_own_hash(self):
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
