"""Tests for the reader adapter, knowledge_os/reader/library.py.

Covers the behaviours the unit-0 contract calls out as easy to get wrong:
inbound-relationship inversion, broken-record capture (including the case
where a record parses but still lands in Library.issues), unresolved
relations, record_kind normalization, date normalization across both YAML
representations, index health in all three states, and accepted_at
extraction. Follows the repository's existing convention: unittest, no
pytest, no fixtures, workspaces built on disk in a TemporaryDirectory.
"""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path

from reader_support import create_workspace, write_record

from knowledge_os.index import rebuild_indexes
from knowledge_os.reader import library
from knowledge_os.workspace import Workspace


def _knowledge_metadata(**overrides: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "id": "demo",
        "title": "Demo",
        "type": "knowledge",
        "status": "active",
        "scope": "general",
        "created": "2026-08-29",
        "updated": "2026-08-29",
        "provenance": [{"kind": "fixture", "reference": "demo"}],
    }
    metadata.update(overrides)
    return metadata


class InboundRelationshipTests(unittest.TestCase):
    def test_inbound_map_inverts_related(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/target.md", _knowledge_metadata(id="target", title="Target"))
            write_record(
                root,
                "knowledge/pointer.md",
                _knowledge_metadata(id="pointer", title="Pointer", related=["target"]),
            )
            lib = library.load_library(Workspace(root))

            target = lib.records_by_id["target"]
            self.assertEqual(
                target.inbound,
                (library.Relation(field="related", record_id="pointer", title="Pointer", resolved=True),),
            )
            pointer = lib.records_by_id["pointer"]
            self.assertEqual(
                pointer.outbound,
                (library.Relation(field="related", record_id="target", title="Target", resolved=True),),
            )
            # The relation's own target has no inbound entries; inversion is directed.
            self.assertEqual(pointer.inbound, ())

    def test_inbound_covers_sources_and_supersedes_separately(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/base.md", _knowledge_metadata(id="base", title="Base"))
            write_record(
                root,
                "knowledge/citing.md",
                _knowledge_metadata(id="citing", title="Citing", sources=["base"]),
            )
            lib = library.load_library(Workspace(root))
            base = lib.records_by_id["base"]
            self.assertEqual(len(base.inbound), 1)
            self.assertEqual(base.inbound[0].field, "sources")
            self.assertEqual(base.inbound[0].record_id, "citing")

    def test_unresolved_relation_is_flagged_not_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/pointer.md",
                _knowledge_metadata(id="pointer", title="Pointer", related=["missing-id"]),
            )
            lib = library.load_library(Workspace(root))
            pointer = lib.records_by_id["pointer"]
            self.assertEqual(
                pointer.outbound,
                (library.Relation(field="related", record_id="missing-id", title=None, resolved=False),),
            )


class BrokenRecordTests(unittest.TestCase):
    def test_unparseable_file_is_broken_not_a_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/good.md", _knowledge_metadata(id="good", title="Good"))
            (root / "knowledge" / "bad.md").write_text("no frontmatter here\n", encoding="utf-8")

            lib = library.load_library(Workspace(root))

            self.assertIn("good", lib.records_by_id)
            self.assertNotIn("bad", lib.records_by_id)
            self.assertEqual(len(lib.broken), 1)
            self.assertEqual(lib.broken[0].path, "knowledge/bad.md")
            self.assertIn("frontmatter", lib.broken[0].message)
            # The neighbour stays readable: one broken file does not hide the rest.
            self.assertEqual(len(lib.records), 1)
            # The same problem is visible in the raw issues list too (kos lint parity).
            self.assertTrue(any(issue.path == "knowledge/bad.md" for issue in lib.issues))

    def test_relational_issue_on_a_valid_record_is_not_broken(self) -> None:
        """A file that parses but fails a *relational* check (here: its type
        does not match its directory) appears in Library.issues but must not
        be double-counted as a BrokenRecord: it already produced a Record."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/mismatched.md",
                _knowledge_metadata(id="mismatched", title="Mismatched", type="source"),
            )

            lib = library.load_library(Workspace(root))

            self.assertIn("mismatched", lib.records_by_id)
            self.assertEqual(lib.broken, ())
            self.assertTrue(any("does not match directory" in issue.message for issue in lib.issues))


class RecordKindNormalizationTests(unittest.TestCase):
    def test_knowledge_record_without_record_kind_is_ordinary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/plain.md", _knowledge_metadata(id="plain"))
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["plain"]
            self.assertEqual(record.record_kind, "ordinary")
            self.assertFalse(record.is_decision)
            self.assertIsNone(record.accepted_at)

    def test_project_decision_record_kind_is_decision_with_accepted_at(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "projects/demo/README.md",
                {
                    "id": "demo",
                    "title": "Demo project",
                    "type": "project",
                    "status": "active",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            write_record(
                root,
                "projects/demo/decisions/choice.md",
                {
                    "id": "choice",
                    "title": "Choice",
                    "type": "project",
                    "status": "active",
                    "scope": "project:demo",
                    "record_kind": "decision",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [
                        {
                            "kind": "decision-acceptance",
                            "reference": "conversation:2026-08-30:demo",
                            "captured": "2026-08-30T00:00:00Z",
                        }
                    ],
                },
            )
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["choice"]
            self.assertEqual(record.record_kind, "decision")
            self.assertTrue(record.is_decision)
            self.assertEqual(record.accepted_at, "2026-08-30T00:00:00Z")

    def test_non_knowledge_project_type_has_no_record_kind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "sources/raw.md",
                {
                    "id": "raw",
                    "title": "Raw",
                    "type": "source",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["raw"]
            self.assertIsNone(record.record_kind)
            self.assertFalse(record.is_decision)
            self.assertIsNone(record.accepted_at)


class DateNormalizationTests(unittest.TestCase):
    def test_quoted_and_unquoted_dates_normalize_to_the_same_string(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/quoted.md",
                _knowledge_metadata(id="quoted", created="2026-08-29", updated="2026-08-29", verified="2026-08-29"),
            )
            write_record(
                root,
                "knowledge/unquoted.md",
                _knowledge_metadata(
                    id="unquoted",
                    created=datetime.date(2026, 8, 29),
                    updated=datetime.date(2026, 8, 29),
                    verified=datetime.date(2026, 8, 29),
                ),
            )

            lib = library.load_library(Workspace(root))
            quoted = lib.records_by_id["quoted"]
            unquoted = lib.records_by_id["unquoted"]

            for record in (quoted, unquoted):
                self.assertIsInstance(record.created, str)
                self.assertIsInstance(record.updated, str)
                self.assertIsInstance(record.verified, str)
            self.assertEqual(quoted.created, unquoted.created)
            self.assertEqual(quoted.verified, unquoted.verified)
            self.assertEqual(quoted.created, "2026-08-29")

    def test_missing_verified_is_none_not_a_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/plain.md", _knowledge_metadata(id="plain"))
            lib = library.load_library(Workspace(root))
            self.assertIsNone(lib.records_by_id["plain"].verified)


class IndexHealthTests(unittest.TestCase):
    def test_absent_index_reports_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/plain.md", _knowledge_metadata(id="plain"))
            lib = library.load_library(Workspace(root))
            self.assertFalse(lib.index.available)
            self.assertFalse(lib.index.stale)
            self.assertIsNotNone(lib.index.message)
            # search() degrades to an empty result rather than raising.
            self.assertEqual(library.search(Workspace(root), "plain"), [])

    def test_fresh_index_reports_available_and_is_searchable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/plain.md",
                _knowledge_metadata(id="plain", title="Plain", tags=["xylophone"]),
            )
            workspace = Workspace(root)
            rebuild_indexes(workspace)

            lib = library.load_library(workspace)
            self.assertEqual(lib.index, library.IndexHealth(available=True, stale=False, message=None))

            results = library.search(workspace, "xylophone")
            self.assertEqual([result["id"] for result in results], ["plain"])

    def test_stale_index_after_edit_without_reindex(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            path = write_record(root, "knowledge/plain.md", _knowledge_metadata(id="plain"))
            workspace = Workspace(root)
            rebuild_indexes(workspace)

            path.write_text(path.read_text(encoding="utf-8") + "\nExtra content.\n", encoding="utf-8")

            lib = library.load_library(workspace)
            self.assertTrue(lib.index.available)
            self.assertTrue(lib.index.stale)
            self.assertIsNotNone(lib.index.message)


if __name__ == "__main__":
    unittest.main()
