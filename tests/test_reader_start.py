"""End-to-end tests for the start view, ``GET /`` (knowledge_os/reader/views/start.py).

Follows the repository's existing convention: unittest only, no pytest, no
fixtures, workspaces built on disk in a ``tempfile.TemporaryDirectory()``.
Every populated-workspace test drives the real server through
``reader_support.serve`` and asserts on the rendered HTML, matching the
subprocess-and-assert style used elsewhere in this suite; the empty-workspace
case does the same, on a bare workspace with no records and no skills.
"""

from __future__ import annotations

import tempfile
import urllib.request
from pathlib import Path

from reader_support import create_workspace, serve, write_record

import unittest

#: Assigned to this unit; do not reuse across parallel test runs.
PORT = 8814


def _get(base_url: str, path: str = "/") -> tuple[int, str]:
    request = urllib.request.Request(base_url + path)
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


def _decision_metadata(**overrides: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "id": "demo-decision",
        "title": "Demo decision",
        "type": "project",
        "record_kind": "decision",
        "status": "draft",
        "scope": "project:demo",
        "created": "2026-08-30",
        "updated": "2026-08-30",
        "provenance": [{"kind": "user-approved-conversation", "reference": "conversation:2026-08-30:demo"}],
    }
    metadata.update(overrides)
    return metadata


class StartViewEmptyWorkspaceTests(unittest.TestCase):
    def test_empty_workspace_explains_what_a_record_is(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)

            with serve(root, PORT) as base_url:
                status, body = _get(base_url, "/")

            self.assertEqual(status, 200)
            self.assertIn("This workspace has no durable records yet", body)
            self.assertIn("kos capture", body)
            # The populated-workspace sections do not render at all.
            self.assertNotIn("Recently changed", body)
            self.assertNotIn("record-card", body)


class StartViewPopulatedWorkspaceTests(unittest.TestCase):
    def test_start_page_lists_records_skills_and_open_decision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "projects/demo/README.md",
                {
                    "id": "demo",
                    "title": "Demo project overview",
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
                "projects/demo/decisions/demo-decision.md",
                _decision_metadata(),
            )
            write_record(
                root,
                "projects/demo/decisions/accepted-decision.md",
                _decision_metadata(
                    id="accepted-decision",
                    title="Accepted decision",
                    status="active",
                    provenance=[
                        {
                            "kind": "decision-acceptance",
                            "reference": "conversation:2026-08-31:demo",
                            "captured": "2026-08-31T00:00:00Z",
                        }
                    ],
                ),
            )
            (root / "skills" / "demo-skill").mkdir(parents=True)
            (root / "skills" / "demo-skill" / "SKILL.md").write_text(
                "---\nname: demo-skill\ndescription: A demo skill.\n---\n\nBody.\n",
                encoding="utf-8",
            )

            with serve(root, PORT) as base_url:
                status, body = _get(base_url, "/")

            self.assertEqual(status, 200)
            # Every record in the corpus is listed (acceptance criterion 2).
            self.assertIn("Demo project overview", body)
            self.assertIn("Demo decision", body)
            self.assertIn("Accepted decision", body)
            # The skill is listed.
            self.assertIn("demo-skill", body)
            self.assertIn("A demo skill.", body)
            # The one project has an entry point.
            self.assertIn('href="/p/demo"', body)
            # The draft decision is called out as still waiting on a position;
            # the accepted one is not shown with that phrasing.
            self.assertIn("demo-decision", body)
            self.assertIn("Proposal — nobody has taken a position yet", body)
            # No contract vocabulary in the reading path.
            self.assertNotIn(">draft<", body)
            self.assertNotIn("project:demo", body)

    def test_empty_project_and_skill_groups_stay_visible_with_a_sentence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/general-note.md",
                {
                    "id": "general-note",
                    "title": "General note",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )

            with serve(root, PORT) as base_url:
                status, body = _get(base_url, "/")

            self.assertEqual(status, 200)
            self.assertIn("General note", body)
            # No project scope exists, and no skill is installed: both
            # groups explain themselves rather than disappearing or showing
            # a bare dash (Sec.6 "Empty project group").
            self.assertIn("No project exists yet.", body)
            self.assertIn("No skill is installed yet.", body)
            self.assertIn("No decision is waiting on a position.", body)

    def test_no_route_returns_a_server_error_and_workspace_is_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/general-note.md",
                {
                    "id": "general-note",
                    "title": "General note",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            before = {path: path.stat().st_mtime for path in root.rglob("*") if path.is_file()}

            with serve(root, PORT) as base_url:
                for route in ("/", "/search", "/everything"):
                    status, _ = _get(base_url, route)
                    self.assertEqual(status, 200, f"{route} returned {status}")

            after = {path: path.stat().st_mtime for path in root.rglob("*") if path.is_file()}
            self.assertEqual(before, after)

    def test_health_line_reports_missing_index_and_no_broken_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/general-note.md",
                {
                    "id": "general-note",
                    "title": "General note",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )

            with serve(root, PORT) as base_url:
                status, body = _get(base_url, "/")

            self.assertEqual(status, 200)
            # No indexes/catalog.sqlite3 was built, so the index is absent;
            # this is Library.index's own user-facing message, not one this
            # view invents.
            self.assertIn("Search is unavailable. Run `kos index` to build it.", body)
            # No broken record exists, so no broken-record count is shown.
            self.assertNotIn("broken record", body)

    def test_broken_record_is_counted_in_the_health_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/good.md",
                {
                    "id": "good",
                    "title": "Good",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            (root / "knowledge" / "broken.md").write_text("no frontmatter here\n", encoding="utf-8")

            with serve(root, PORT) as base_url:
                status, body = _get(base_url, "/")

            self.assertEqual(status, 200)
            # The broken file is not a record; its neighbour still renders.
            self.assertIn("Good", body)
            # The rail now renders through partials/health.html (unit 9):
            # the lint-issue count and the affected file's own path/message,
            # rather than this view's own former "N broken record(s)" line.
            self.assertIn("1 issue(s) found by", body)
            self.assertIn("knowledge/broken.md", body)


if __name__ == "__main__":
    unittest.main()
