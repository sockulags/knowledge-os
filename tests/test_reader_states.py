"""Tests for knowledge_os/reader/states.py: degradation and health states.

Follows the repository's existing test convention exactly (see
tests/test_vertical_slice.py and tests/test_reader_library.py): unittest
only, no pytest, no fixtures, no conftest.py. Every workspace is built fresh
on disk inside a tempfile.TemporaryDirectory() and never touches the real
workspace this repository ships (a sibling agent is reading it while this
suite runs).

Covers docs/plans/reader-v1.md Sec.6 acceptance criteria 6, 7, and 8 at the
states.py layer (states.py is pure and has no server dependency, per the
unit-9 contract), plus every helper's own edge cases: broken records,
broken relations, the health line's lint/issue accounting (and its
dedup rule against Library.broken), and all three IndexHealth states.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reader_support import create_workspace, write_record

from knowledge_os.index import rebuild_indexes
from knowledge_os.reader import library, states, strings
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


class DiagnosticForBrokenTests(unittest.TestCase):
    """Acceptance criterion 6: a corrupted frontmatter file renders as
    broken with its exact lint message, while its neighbour stays a normal
    record and is unaffected."""

    def test_corrupted_frontmatter_becomes_a_diagnostic_with_the_exact_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/good.md", _knowledge_metadata(id="good", title="Good"))
            (root / "knowledge" / "corrupt.md").write_text(
                "---\nid: [unterminated\n---\n\nBody.\n", encoding="utf-8"
            )

            lib = library.load_library(Workspace(root))

            self.assertIn("good", lib.records_by_id)
            self.assertEqual(len(lib.broken), 1)
            diagnostics = states.broken_entries(lib)
            self.assertEqual(len(diagnostics), 1)
            diagnostic = diagnostics[0]
            self.assertEqual(diagnostic.label, strings.BROKEN_RECORD_LABEL)
            self.assertEqual(diagnostic.path, "knowledge/corrupt.md")
            # The exact lint message from BrokenRecord.message must survive,
            # framed but not replaced, inside the pre-formatted detail.
            self.assertIn(lib.broken[0].message, diagnostic.detail)
            self.assertEqual(diagnostic.detail, strings.BROKEN_RECORD_DETAIL.format(message=lib.broken[0].message))
            # The neighbour is untouched: still a normal, readable record.
            self.assertEqual(lib.records_by_id["good"].title, "Good")

    def test_broken_entries_are_sorted_by_path_and_do_not_include_readable_issues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            (root / "knowledge" / "z-broken.md").write_text("no frontmatter\n", encoding="utf-8")
            (root / "knowledge" / "a-broken.md").write_text("no frontmatter\n", encoding="utf-8")
            # Parses fine but fails a relational check: must not show up here.
            write_record(
                root,
                "knowledge/mismatched.md",
                _knowledge_metadata(id="mismatched", title="Mismatched", type="source"),
            )

            lib = library.load_library(Workspace(root))
            diagnostics = states.broken_entries(lib)

            self.assertEqual([d.path for d in diagnostics], ["knowledge/a-broken.md", "knowledge/z-broken.md"])


class DiagnosticForUnreadableTests(unittest.TestCase):
    """Sec.6 "Unreadable content": non-UTF-8, deleted mid-session, or
    rejected by path safety. Exercised directly against LibraryError, since
    read_repo_document's own I/O is library.py's concern, not states.py's."""

    def test_wraps_a_library_error_with_its_own_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            (root / "docs").mkdir()
            (root / "docs" / "binary.md").write_bytes(b"\xff\xfe not utf-8")
            workspace = Workspace(root)

            with self.assertRaises(library.LibraryError) as caught:
                library.read_repo_document(workspace, "docs/binary.md")

            diagnostic = states.diagnostic_for_unreadable("docs/binary.md", caught.exception)
            self.assertEqual(diagnostic.label, strings.UNREADABLE_CONTENT_LABEL)
            self.assertEqual(diagnostic.path, "docs/binary.md")
            self.assertEqual(diagnostic.detail, str(caught.exception))
            self.assertIn("not valid UTF-8", diagnostic.detail)

    def test_missing_file_also_produces_a_diagnostic_not_a_crash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            workspace = Workspace(root)

            with self.assertRaises(library.LibraryError) as caught:
                library.read_repo_document(workspace, "docs/gone.md")

            diagnostic = states.diagnostic_for_unreadable("docs/gone.md", caught.exception)
            self.assertIn("no longer exists", diagnostic.detail)


class RelationLabelTests(unittest.TestCase):
    """Sec.6 "Broken relation": shown as "points at unknown id X", flagged,
    never silently dropped; a resolved relation is unaffected."""

    def test_unresolved_relation_reports_the_unknown_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/pointer.md",
                _knowledge_metadata(id="pointer", title="Pointer", related=["missing-id"]),
            )
            lib = library.load_library(Workspace(root))
            relation = lib.records_by_id["pointer"].outbound[0]

            self.assertFalse(relation.resolved)
            self.assertTrue(states.is_relation_broken(relation))
            self.assertEqual(states.relation_label(relation), strings.BROKEN_RELATION.format(record_id="missing-id"))

    def test_resolved_relation_shows_the_target_title(self) -> None:
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
            relation = lib.records_by_id["pointer"].outbound[0]

            self.assertTrue(relation.resolved)
            self.assertFalse(states.is_relation_broken(relation))
            self.assertEqual(states.relation_label(relation), "Target")


class IssueEntriesTests(unittest.TestCase):
    """Sec.6 "Lint failing globally": the health line must not double-count
    a file that appears in both Library.broken and Library.issues, and must
    link an issue back to its record when the file still parsed."""

    def test_unparsed_issue_has_no_record_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            (root / "knowledge" / "bad.md").write_text("no frontmatter\n", encoding="utf-8")
            lib = library.load_library(Workspace(root))

            entries = states.issue_entries(lib)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].path, "knowledge/bad.md")
            self.assertIsNone(entries[0].record_id)

    def test_parsed_but_relationally_invalid_issue_links_to_its_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/mismatched.md",
                _knowledge_metadata(id="mismatched", title="Mismatched", type="source"),
            )
            lib = library.load_library(Workspace(root))

            entries = states.issue_entries(lib)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].record_id, "mismatched")
            self.assertEqual(lib.broken, ())


class HealthSummaryTests(unittest.TestCase):
    def test_clean_workspace_reports_lint_ok(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/plain.md", _knowledge_metadata(id="plain"))
            workspace = Workspace(root)
            rebuild_indexes(workspace)
            lib = library.load_library(workspace)

            summary = states.build_health_summary(lib)
            self.assertTrue(summary.lint_ok)
            self.assertEqual(summary.lint_message, strings.LINT_OK)
            self.assertEqual(summary.issue_count, 0)
            self.assertEqual(summary.issues, ())
            self.assertFalse(summary.search_disabled)
            self.assertIsNone(summary.search_disabled_reason)

    def test_lint_message_pluralizes_a_single_issue_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            (root / "knowledge" / "bad.md").write_text("no frontmatter\n", encoding="utf-8")
            lib = library.load_library(Workspace(root))
            summary = states.build_health_summary(lib)
            self.assertEqual(summary.issue_count, 1)
            self.assertEqual(summary.lint_message, strings.LINT_ISSUES_SINGULAR)
            self.assertNotIn("(s)", summary.lint_message)

    def test_broken_and_relational_issues_are_counted_once_each(self) -> None:
        """A workspace with one unparseable file and one parsed-but-invalid
        file must report exactly 2 issues, never adding Library.broken's
        count again on top of Library.issues."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            (root / "knowledge" / "bad.md").write_text("no frontmatter\n", encoding="utf-8")
            write_record(
                root,
                "knowledge/mismatched.md",
                _knowledge_metadata(id="mismatched", title="Mismatched", type="source"),
            )
            lib = library.load_library(Workspace(root))
            self.assertEqual(len(lib.broken), 1)
            self.assertEqual(len(lib.issues), 2)

            summary = states.build_health_summary(lib)
            self.assertFalse(summary.lint_ok)
            self.assertEqual(summary.issue_count, 2)
            self.assertEqual(summary.lint_message, strings.LINT_ISSUES_PLURAL.format(count=2))
            self.assertEqual(len(summary.issues), 2)

    def test_absent_index_disables_search_with_the_absent_message(self) -> None:
        """Acceptance criterion 7: with the index missing, browsing still
        works (Library.records loads normally) and the health summary
        reports search as unavailable with the rebuild instruction."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/plain.md", _knowledge_metadata(id="plain"))
            lib = library.load_library(Workspace(root))

            self.assertEqual(len(lib.records), 1)
            summary = states.build_health_summary(lib)
            self.assertFalse(summary.index_available)
            self.assertTrue(summary.search_disabled)
            self.assertEqual(summary.search_disabled_reason, strings.INDEX_HEALTH["absent"])
            self.assertIn("kos index", summary.search_disabled_reason)

    def test_stale_index_after_edit_reports_stale_and_disables_search(self) -> None:
        """Acceptance criterion 8: after editing a record without
        re-running `kos index`, the health line reports the index as
        stale."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            path = write_record(root, "knowledge/plain.md", _knowledge_metadata(id="plain"))
            workspace = Workspace(root)
            rebuild_indexes(workspace)

            path.write_text(path.read_text(encoding="utf-8") + "\nExtra content.\n", encoding="utf-8")

            lib = library.load_library(workspace)
            summary = states.build_health_summary(lib)
            self.assertTrue(summary.index_available)
            self.assertTrue(summary.index_stale)
            self.assertTrue(summary.search_disabled)
            self.assertEqual(summary.search_disabled_reason, strings.INDEX_HEALTH["stale"])

    def test_lint_summary_line_matches_build_health_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/plain.md", _knowledge_metadata(id="plain"))
            lib = library.load_library(Workspace(root))
            self.assertEqual(states.lint_summary_line(lib), states.build_health_summary(lib).lint_message)


if __name__ == "__main__":
    unittest.main()
