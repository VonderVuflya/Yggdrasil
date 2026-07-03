"""ygg import: migrate FROM other memory tools' stores (parsers only, no engine)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "yggdrasil"))
import ygg  # noqa: E402


class McpMemoryImportTest(unittest.TestCase):
    # The reference MCP memory server's on-disk format (newline-delimited JSON).
    FIXTURE = (
        '{"type":"entity","name":"John_Smith","entityType":"person",'
        '"observations":["Speaks fluent Spanish","Joined in 2019"]}\n'
        '{"type":"entity","name":"checkout_api","entityType":"service",'
        '"observations":["Idempotency keys added to refunds"]}\n'
        '{"type":"relation","from":"John_Smith","to":"checkout_api","relationType":"maintains"}\n'
        '{"type":"entity","name":"empty_one","entityType":"note","observations":[]}\n'
        'garbage line that is not json\n'
    )

    def _write(self, text):
        p = Path(tempfile.mktemp(suffix=".json"))
        p.write_text(text, encoding="utf-8")
        return p

    def test_entities_become_memories_with_relations_folded_in(self):
        items = ygg._import_mcp_memory(self._write(self.FIXTURE), "acme")
        contents = [c for c, _ in items]
        # entity with observations + a relation
        john = next(c for c in contents if c.startswith("John Smith"))
        self.assertIn("Speaks fluent Spanish", john)
        self.assertIn("maintains checkout_api", john)   # relation folded in
        # entity with no observations is still imported (has a label)
        self.assertTrue(any(c.startswith("checkout api") for c in contents))
        # empty entity with no observations and no relations -> still a label line
        self.assertTrue(any("empty one" in c for c in contents))
        # every item is a reference type
        self.assertTrue(all(t == "reference" for _, t in items))
        # garbage line ignored, no crash
        self.assertEqual(len(items), 3)


class BasicMemoryImportTest(unittest.TestCase):
    def test_markdown_notes_imported_verbatim(self):
        d = Path(tempfile.mkdtemp())
        (d / "auth.md").write_text("Rotate refresh tokens on every use.", encoding="utf-8")
        (d / "sub").mkdir()
        (d / "sub" / "db.md").write_text("Add a composite index for the WHERE+ORDER BY.", encoding="utf-8")
        (d / "empty.md").write_text("   ", encoding="utf-8")
        items = ygg._import_basic_memory(d, "acme")
        contents = [c for c, _ in items]
        self.assertTrue(any("Rotate refresh tokens" in c for c in contents))
        self.assertTrue(any("composite index" in c for c in contents))  # nested dir too
        self.assertEqual(len(items), 2)  # empty note skipped


if __name__ == "__main__":
    unittest.main()
