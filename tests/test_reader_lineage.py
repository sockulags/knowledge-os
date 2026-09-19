"""Tests for the lineage/compare view, knowledge_os/reader/views/lineage.py.

Nothing in the real workspace this repository ships uses ``supersedes``, so
every behaviour here is driven from a synthetic two-decision fixture built
with ``reader_support.write_record`` (an "active" original superseded by an
"active" replacement) plus small variations for the degradation cases: a
decision with no lineage at all, a non-decision record, a supersession
target id that does not exist, and one that exists but is not a decision.

Follows the repository's existing test convention: unittest, no pytest, no
fixtures, workspaces built on disk inside a TemporaryDirectory. The
comparison-building unit tests call ``lineage._build_comparisons`` and
``lineage._status_text`` directly against a loaded ``library.Library``
(mirroring how tests/test_reader_library.py tests the adapter); the
end-to-end tests drive the real HTTP route through ``reader_support.serve``.
"""

from __future__ import annotations

import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from reader_support import REPOSITORY, create_workspace, serve, write_record

from knowledge_os.reader import library, strings
from knowledge_os.reader.views import lineage
from knowledge_os.workspace import Workspace

#: This unit's assigned end-to-end port (see the batch worker instructions):
#: ten sibling agents each run their own server in parallel on their own port.
PORT = 8821

ORIGINAL_ACCEPTED = "2026-08-01T00:00:00Z"
REPLACEMENT_ACCEPTED = "2026-08-30T00:00:00Z"


def _decision_metadata(**overrides: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "id": "original",
        "title": "Original decision",
        "type": "project",
        "status": "active",
        "scope": "project:demo",
        "record_kind": "decision",
        "created": "2026-08-01",
        "updated": "2026-08-01",
        "provenance": [
            {
                "kind": "decision-acceptance",
                "reference": "conversation:2026-08-01:demo",
                "captured": ORIGINAL_ACCEPTED,
            }
        ],
    }
    metadata.update(overrides)
    return metadata


def _build_lineage_workspace(root: Path) -> None:
    """A minimal, valid two-decision supersession chain: original -> replacement."""

    create_workspace(root, name="lineage-fixture")
    write_record(
        root,
        "projects/demo/README.md",
        {
            "id": "demo",
            "title": "Demo project",
            "type": "project",
            "status": "active",
            "scope": "project:demo",
            "created": "2026-08-01",
            "updated": "2026-08-01",
            "provenance": [{"kind": "fixture", "reference": "demo"}],
        },
    )
    write_record(
        root,
        "projects/demo/decisions/original.md",
        _decision_metadata(
            id="original",
            title="Original decision",
            status="superseded",
            provenance=[
                {
                    "kind": "decision-acceptance",
                    "reference": "conversation:2026-08-01:demo",
                    "captured": ORIGINAL_ACCEPTED,
                }
            ],
        ),
        body="We will do it the original way.\n\nThis paragraph never changes.\n",
    )
    write_record(
        root,
        "projects/demo/decisions/replacement.md",
        _decision_metadata(
            id="replacement",
            title="Replacement decision",
            status="active",
            supersedes=["original"],
            provenance=[
                {
                    "kind": "decision-acceptance",
                    "reference": "conversation:2026-08-30:demo",
                    "captured": REPLACEMENT_ACCEPTED,
                }
            ],
        ),
        body="We will do it the replacement way instead.\n\nThis paragraph never changes.\n",
    )


class ComparisonBuildingTests(unittest.TestCase):
    def test_outbound_supersedes_pairs_older_left_newer_right(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_lineage_workspace(root)
            lib = library.load_library(Workspace(root))
            replacement = lib.records_by_id["replacement"]

            comparisons = lineage._build_comparisons(replacement, lib)

            self.assertEqual(len(comparisons), 1)
            comparison = comparisons[0]
            self.assertEqual(comparison.heading, strings.LINEAGE_SUPERSEDES)
            self.assertEqual(comparison.state, "ok")
            self.assertEqual(comparison.left.record.id, "original")
            self.assertEqual(comparison.right.record.id, "replacement")
            self.assertNotEqual(comparison.summary, strings.LINEAGE_SUMMARY_UNCHANGED)
            kinds = {block.kind for block in comparison.blocks}
            # One paragraph was reworded, one is untouched: both show up.
            self.assertIn("changed", kinds)
            self.assertIn("equal", kinds)

    def test_inbound_supersedes_pairs_subject_left_replacement_right(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_lineage_workspace(root)
            lib = library.load_library(Workspace(root))
            original = lib.records_by_id["original"]

            comparisons = lineage._build_comparisons(original, lib)

            self.assertEqual(len(comparisons), 1)
            comparison = comparisons[0]
            self.assertEqual(comparison.heading, strings.LINEAGE_SUPERSEDED_BY)
            self.assertEqual(comparison.state, "ok")
            self.assertEqual(comparison.left.record.id, "original")
            self.assertEqual(comparison.right.record.id, "replacement")

    def test_status_text_active_decision_shows_acceptance_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_lineage_workspace(root)
            lib = library.load_library(Workspace(root))
            replacement = lib.records_by_id["replacement"]
            self.assertEqual(
                lineage._status_text(replacement, lib),
                strings.DECISION_STATUS["active"].format(date="30 August 2026"),
            )

    def test_status_text_superseded_decision_names_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_lineage_workspace(root)
            lib = library.load_library(Workspace(root))
            original = lib.records_by_id["original"]
            self.assertEqual(
                lineage._status_text(original, lib),
                strings.DECISION_STATUS["superseded"].format(title="Replacement decision", date="30 August 2026"),
            )

    def test_decision_with_no_lineage_has_no_comparisons(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "projects/solo/README.md",
                {
                    "id": "solo",
                    "title": "Solo project",
                    "type": "project",
                    "status": "active",
                    "scope": "project:solo",
                    "created": "2026-08-01",
                    "updated": "2026-08-01",
                    "provenance": [{"kind": "fixture", "reference": "solo"}],
                },
            )
            write_record(
                root,
                "projects/solo/decisions/lone.md",
                _decision_metadata(
                    id="lone",
                    title="Lone decision",
                    scope="project:solo",
                    status="active",
                    provenance=[
                        {
                            "kind": "decision-acceptance",
                            "reference": "conversation:2026-08-01:solo",
                            "captured": ORIGINAL_ACCEPTED,
                        }
                    ],
                ),
            )
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["lone"]

            self.assertEqual(lineage._build_comparisons(record, lib), ())

    def test_non_decision_record_has_no_comparisons(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/plain.md",
                {
                    "id": "plain",
                    "title": "Plain",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-01",
                    "updated": "2026-08-01",
                    "provenance": [{"kind": "fixture", "reference": "plain"}],
                },
            )
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["plain"]

            self.assertFalse(record.is_decision)
            self.assertEqual(lineage._build_comparisons(record, lib), ())


class DegradedLineageTests(unittest.TestCase):
    """Corpus states validate_workspace flags with an Issue but still serves
    (a corpus that fails ``kos lint`` is still browsable): these must render
    an explaining comparison entry, never a raised exception or a silently
    dropped relation."""

    def test_missing_supersession_target_is_shown_not_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "projects/demo/decisions/replacement.md",
                _decision_metadata(
                    id="replacement",
                    title="Replacement decision",
                    scope="project:demo",
                    status="active",
                    supersedes=["ghost"],
                ),
            )
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["replacement"]

            comparisons = lineage._build_comparisons(record, lib)

            self.assertEqual(len(comparisons), 1)
            self.assertEqual(comparisons[0].heading, strings.LINEAGE_SUPERSEDES)
            self.assertEqual(comparisons[0].state, "missing")
            self.assertIn("ghost", comparisons[0].detail)
            self.assertIsNone(comparisons[0].left)
            self.assertIsNone(comparisons[0].right)

    def test_non_decision_supersession_target_is_shown_not_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "projects/demo/not-a-decision.md",
                {
                    "id": "not-a-decision",
                    "title": "Not a decision",
                    "type": "project",
                    "status": "active",
                    "scope": "project:demo",
                    "created": "2026-08-01",
                    "updated": "2026-08-01",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            write_record(
                root,
                "projects/demo/decisions/replacement.md",
                _decision_metadata(
                    id="replacement",
                    title="Replacement decision",
                    scope="project:demo",
                    status="active",
                    supersedes=["not-a-decision"],
                ),
            )
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["replacement"]
            target = lib.records_by_id["not-a-decision"]
            self.assertFalse(target.is_decision)

            comparisons = lineage._build_comparisons(record, lib)

            self.assertEqual(len(comparisons), 1)
            self.assertEqual(comparisons[0].state, "not_decision")
            self.assertIn("Not a decision", comparisons[0].detail)


class EndToEndSyntheticFixtureTests(unittest.TestCase):
    def test_compare_pages_render_both_directions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_lineage_workspace(root)
            with serve(root, PORT) as base_url:
                with urllib.request.urlopen(f"{base_url}/r/replacement/compare") as response:
                    self.assertEqual(response.status, 200)
                    body = response.read().decode("utf-8")
                self.assertIn("Replacement decision", body)
                self.assertIn("Original decision", body)
                self.assertIn(strings.LINEAGE_SUPERSEDES, body)
                self.assertIn("30 August 2026", body)

                with urllib.request.urlopen(f"{base_url}/r/original/compare") as response:
                    self.assertEqual(response.status, 200)
                    body = response.read().decode("utf-8")
                self.assertIn("Replacement decision", body)
                self.assertIn("Original decision", body)
                self.assertIn(strings.LINEAGE_SUPERSEDED_BY, body)

    def test_unknown_record_id_renders_explaining_page_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_lineage_workspace(root)
            with serve(root, PORT) as base_url:
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(f"{base_url}/r/does-not-exist/compare")
                self.assertEqual(caught.exception.code, 404)
                body = caught.exception.read().decode("utf-8")
                self.assertIn("does-not-exist", body)


class EndToEndRealWorkspaceTests(unittest.TestCase):
    def test_reader_decision_has_no_lineage_and_workspace_is_untouched(self) -> None:
        catalog = REPOSITORY / "indexes" / "catalog.md"
        before_mtime = catalog.stat().st_mtime_ns
        before_text = catalog.read_text(encoding="utf-8")

        with serve(REPOSITORY, PORT) as base_url:
            with urllib.request.urlopen(f"{base_url}/r/knowledge-os-reader/compare") as response:
                self.assertEqual(response.status, 200)
                body = response.read().decode("utf-8")
            self.assertIn(strings.LINEAGE_NO_COMPARISON, body)
            self.assertNotIn("Traceback", body)

        self.assertEqual(catalog.stat().st_mtime_ns, before_mtime)
        self.assertEqual(catalog.read_text(encoding="utf-8"), before_text)


if __name__ == "__main__":
    unittest.main()
