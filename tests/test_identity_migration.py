"""Tests for the demo->default identity migration (roadmap #16).

Covers the pure mapping, the one-time version-guarded SQL relabel (idempotent,
custom-identity-safe, backup + config-pin), and the config accessors. Each test
uses a fresh temp DB and redirects ygg_config.CONFIG so the pin never touches the
real ~/.yggdrasil.
"""

import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from yggdrasil import ygg_memory_server as S
from yggdrasil import ygg_config as _cfg


class RebrandMappingTest(unittest.TestCase):
    def test_only_the_exact_demo_pair_maps(self):
        self.assertEqual(S.rebrand_legacy_identity("demo-user", "yggdrasil-demo"),
                         (_cfg.DEFAULT_USER_ID, _cfg.DEFAULT_NAMESPACE))
        # a custom identity, or a half-match, is passed through untouched
        self.assertEqual(S.rebrand_legacy_identity("alice", "work"), ("alice", "work"))
        self.assertEqual(S.rebrand_legacy_identity("demo-user", "work"), ("demo-user", "work"))


class IdentityMigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "memory.sqlite")
        self._orig_config = _cfg.CONFIG
        _cfg.CONFIG = Path(self.tmp) / "config.json"  # isolate the pin
        # MemoryStore builds the schema (and marks a fresh DB v1 with no rows).
        S.MemoryStore(self.db)._conn.close()
        self.conn = sqlite3.connect(self.db)

    def tearDown(self):
        self.conn.close()
        _cfg.CONFIG = self._orig_config
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _insert(self, mid, user_id, namespace):
        self.conn.execute(
            "INSERT INTO memories (id,user_id,namespace,type,content,content_hash,source,"
            "confidence,importance,created_at,archived) VALUES (?,?,?,?,?,?,?,?,?,?,0)",
            (mid, user_id, namespace, "fix", "x", mid, "seed", 0.6, 0.5, 1.0))

    def _pre_migration(self):
        self.conn.execute("PRAGMA user_version=0")
        self.conn.commit()

    def test_rebrands_demo_rows_and_pins_config(self):
        self._insert("ygg_a", "demo-user", "yggdrasil-demo")
        self.conn.execute("INSERT INTO relations (from_id,to_id,rel_type,user_id,created_at) "
                          "VALUES ('ygg_a','ygg_b','SOLVES','demo-user',1.0)")
        self._pre_migration()
        res = S.migrate_identity(self.conn, backup_path=self.db + ".bak")
        self.assertEqual(res["migrated"], 1)
        row = self.conn.execute("SELECT user_id,namespace FROM memories WHERE id='ygg_a'").fetchone()
        self.assertEqual(tuple(row), (_cfg.DEFAULT_USER_ID, _cfg.DEFAULT_NAMESPACE))
        self.assertEqual(self.conn.execute("SELECT user_id FROM relations").fetchone()[0],
                         _cfg.DEFAULT_USER_ID)
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0],
                         S.IDENTITY_MIGRATION_VERSION)
        self.assertTrue(os.path.exists(self.db + ".bak"))
        self.assertEqual(_cfg.load().get("user_id"), _cfg.DEFAULT_USER_ID)

    def test_leaves_custom_identity_untouched(self):
        self._insert("ygg_c", "alice", "work")
        self._pre_migration()
        res = S.migrate_identity(self.conn, backup_path=self.db + ".bak")
        self.assertEqual(res["migrated"], 0)
        self.assertEqual(tuple(self.conn.execute(
            "SELECT user_id,namespace FROM memories WHERE id='ygg_c'").fetchone()), ("alice", "work"))
        # a no-op migration still marks the version and writes NO backup
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0],
                         S.IDENTITY_MIGRATION_VERSION)
        self.assertFalse(os.path.exists(self.db + ".bak"))

    def test_idempotent(self):
        self._insert("ygg_a", "demo-user", "yggdrasil-demo")
        self._pre_migration()
        S.migrate_identity(self.conn, backup_path=self.db + ".bak")
        again = S.migrate_identity(self.conn, backup_path=self.db + ".bak2")
        self.assertTrue(again["already"])
        self.assertEqual(again["migrated"], 0)
        self.assertFalse(os.path.exists(self.db + ".bak2"))

    def test_dry_run_changes_nothing(self):
        self._insert("ygg_a", "demo-user", "yggdrasil-demo")
        self._pre_migration()
        res = S.migrate_identity(self.conn, dry_run=True)
        self.assertEqual(res["migrated"], 1)
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], 0)  # untouched
        self.assertEqual(self.conn.execute(
            "SELECT user_id FROM memories WHERE id='ygg_a'").fetchone()[0], "demo-user")


class ConfigIdentityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_config = _cfg.CONFIG
        _cfg.CONFIG = Path(self.tmp) / "config.json"

    def tearDown(self):
        _cfg.CONFIG = self._orig_config
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pin_writes_defaults_then_no_ops(self):
        _cfg.pin_default_identity()
        self.assertEqual(_cfg.load().get("user_id"), _cfg.DEFAULT_USER_ID)
        self.assertEqual(_cfg.load().get("namespace"), _cfg.DEFAULT_NAMESPACE)
        # a user-set value is never overwritten
        _cfg.save({"user_id": "alice", "namespace": "work"})
        _cfg.pin_default_identity()
        self.assertEqual(_cfg.load().get("user_id"), "alice")

    def test_defaults_are_not_demo(self):
        self.assertNotEqual(_cfg.DEFAULT_USER_ID, _cfg.DEMO_USER_ID)
        self.assertNotEqual(_cfg.DEFAULT_NAMESPACE, _cfg.DEMO_NAMESPACE)


if __name__ == "__main__":
    unittest.main()
