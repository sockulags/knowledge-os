"""Tests for the project view: grouping.py (pure, unit-tested directly) and
the end-to-end ``GET /p/{project_id}`` route (served, asserted on rendered
HTML). Follows the repository's convention: unittest, no pytest, no
fixtures, workspaces built on disk in a TemporaryDirectory. Port 8813 is
this unit's assigned port for ``tests.reader_support.serve``.
"""

from __future__ import annotations

import re
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from reader_support import create_workspace, serve, write_record

from knowledge_os.reader import grouping
from knowledge_os.reader.library import Library, load_library
from knowledge_os.workspace import Workspace

PORT = 8813


def _project_overview(project_id: str, **overrides: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "id": project_id,
        "title": overrides.pop("title", project_id.title()),
        "type": "project",
        "status": "active",
        "scope": f"project:{project_id}",
        "created": "2026-08-29",
        "updated": "2026-08-29",
        "provenance": [{"kind": "project-definition", "reference": "fixture"}],
    }
    metadata.update(overrides)
    return metadata


def _decision(project_id: str, decision_id: str, **overrides: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "id": decision_id,
        "title": overrides.pop("title", decision_id.title()),
        "type": "project",
        "record_kind": "decision",
        "status": "draft",
        "scope": f"project:{project_id}",
        "created": "2026-08-29",
        "updated": "2026-08-29",
        "provenance": [{"kind": "user-approved-conversation", "reference": "conversation:demo"}],
    }
    metadata.update(overrides)
    return metadata


def _accepted(reference: str = "conversation:demo-approval", captured: str = "2026-08-30T00:00:00Z") -> dict:
    return {"kind": "decision-acceptance", "reference": reference, "captured": captured}


class DecisionGroupingTests(unittest.TestCase):
    """grouping.group_project_records: pure, no server needed."""

    def _load(self, build) -> Library:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            build(root)
            return load_library(Workspace(root))

    def test_accepted_active_decision_is_governing(self) -> None:
        def build(root: Path) -> None:
            write_record(root, "projects/demo/README.md", _project_overview("demo"))
            write_record(
                root,
                "projects/demo/decisions/choice.md",
                _decision("demo", "choice", status="active", provenance=[_accepted()]),
            )

        library = self._load(build)
        groups = grouping.group_project_records(library.records, "demo")
        self.assertEqual([r.id for r in groups.governing], ["choice"])
        self.assertEqual(groups.proposed, ())
        self.assertEqual(groups.historical, ())

    def test_draft_decision_with_no_acceptance_is_proposed(self) -> None:
        def build(root: Path) -> None:
            write_record(root, "projects/demo/README.md", _project_overview("demo"))
            write_record(root, "projects/demo/decisions/idea.md", _decision("demo", "idea", status="draft"))

        library = self._load(build)
        groups = grouping.group_project_records(library.records, "demo")
        self.assertEqual([r.id for r in groups.proposed], ["idea"])
        self.assertEqual(groups.governing, ())

    def test_superseded_decision_is_historical_not_by_directory(self) -> None:
        """A decision that lives outside any 'decisions/' directory, at an
        arbitrary nested path, is still grouped correctly: on status and
        accepted_at, never on the directory it happens to live in."""

        def build(root: Path) -> None:
            write_record(root, "projects/demo/README.md", _project_overview("demo"))
            write_record(
                root,
                "projects/demo/architecture/old-choice.md",
                _decision("demo", "old-choice", status="superseded", provenance=[_accepted()]),
            )
            write_record(
                root,
                "projects/demo/architecture/new-choice.md",
                _decision(
                    "demo",
                    "new-choice",
                    status="active",
                    provenance=[_accepted()],
                    supersedes=["old-choice"],
                ),
            )

        library = self._load(build)
        groups = grouping.group_project_records(library.records, "demo")
        self.assertEqual([r.id for r in groups.historical], ["old-choice"])
        self.assertEqual([r.id for r in groups.governing], ["new-choice"])
        # The reversed supersedes edge is visible on the superseded record.
        old_choice = library.records_by_id["old-choice"]
        self.assertTrue(
            any(rel.field == "supersedes" and rel.record_id == "new-choice" for rel in old_choice.inbound)
        )

    def test_user_approved_conversation_alone_confers_nothing(self) -> None:
        """A decision with only user-approved-conversation provenance (no
        decision-acceptance) is proposed, never governing -- provenance kind
        determines this, not any keyword in the reference string."""

        def build(root: Path) -> None:
            write_record(root, "projects/demo/README.md", _project_overview("demo"))
            write_record(
                root,
                "projects/demo/decisions/pending.md",
                _decision(
                    "demo",
                    "pending",
                    status="draft",
                    provenance=[{"kind": "user-approved-conversation", "reference": "conversation:2026-08-30:approved-by-user"}],
                ),
            )

        library = self._load(build)
        groups = grouping.group_project_records(library.records, "demo")
        self.assertEqual([r.id for r in groups.proposed], ["pending"])
        self.assertEqual(groups.governing, ())

    def test_discovery_and_source_form_observations_and_raw_material(self) -> None:
        def build(root: Path) -> None:
            write_record(root, "projects/demo/README.md", _project_overview("demo"))
            write_record(
                root,
                "discoveries/obs.md",
                {
                    "id": "obs",
                    "title": "Observation",
                    "type": "discovery",
                    "status": "proposed",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                    "evidence": [{"kind": "fixture", "reference": "demo"}],
                },
                body="An observation body.\n",
            )
            write_record(
                root,
                "sources/raw.md",
                {
                    "id": "raw",
                    "title": "Raw source",
                    "type": "source",
                    "status": "active",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )

        library = self._load(build)
        groups = grouping.group_project_records(library.records, "demo")
        self.assertEqual([r.id for r in groups.observations], ["obs"])
        self.assertEqual([r.id for r in groups.raw_material], ["raw"])
        self.assertEqual(groups.ordinary, ())

    def test_ordinary_project_record_is_neither_decision_nor_meaning_group(self) -> None:
        def build(root: Path) -> None:
            write_record(root, "projects/demo/README.md", _project_overview("demo"))
            write_record(
                root,
                "projects/demo/notes/architecture.md",
                {
                    "id": "architecture",
                    "title": "Architecture",
                    "type": "project",
                    "status": "active",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )

        library = self._load(build)
        groups = grouping.group_project_records(library.records, "demo")
        self.assertEqual([r.id for r in groups.ordinary], ["architecture"])
        self.assertEqual(groups.governing, ())
        self.assertEqual(groups.overview.id, "demo")

    def test_unrelated_project_scope_is_excluded(self) -> None:
        def build(root: Path) -> None:
            write_record(root, "projects/demo/README.md", _project_overview("demo"))
            write_record(root, "projects/other/README.md", _project_overview("other"))
            write_record(
                root,
                "projects/other/decisions/other-choice.md",
                _decision("other", "other-choice", status="active", provenance=[_accepted()]),
            )

        library = self._load(build)
        groups = grouping.group_project_records(library.records, "demo")
        self.assertEqual(groups.governing, ())
        self.assertEqual(groups.proposed, ())
        self.assertEqual(groups.ordinary, ())


class RelatedGeneralTests(unittest.TestCase):
    def test_general_scope_durable_record_is_related(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/general-fact.md",
                {
                    "id": "general-fact",
                    "title": "General fact",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            write_record(
                root,
                "projects/demo/README.md",
                _project_overview("demo"),
            )
            library = load_library(Workspace(root))
            related = grouping.related_general_records(library.records)
            self.assertEqual([r.id for r in related], ["general-fact"])

    def test_source_and_discovery_are_not_in_the_general_side_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "sources/general-source.md",
                {
                    "id": "general-source",
                    "title": "General source",
                    "type": "source",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            library = load_library(Workspace(root))
            self.assertEqual(grouping.related_general_records(library.records), ())


class ProjectTreeTests(unittest.TestCase):
    def test_nested_readme_becomes_a_directory_overview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "projects/demo/README.md", _project_overview("demo"))
            write_record(
                root,
                "projects/demo/architecture/README.md",
                {
                    "id": "demo-architecture",
                    "title": "Demo architecture",
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
                "projects/demo/architecture/demo-detail.md",
                {
                    "id": "demo-detail",
                    "title": "Demo detail",
                    "type": "project",
                    "status": "active",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            library = load_library(Workspace(root))
            groups = grouping.group_project_records(library.records, "demo")
            tree = grouping.build_project_tree("demo", groups.ordinary, library.broken)
            self.assertEqual(len(tree.children), 1)
            architecture_node = tree.children[0]
            self.assertEqual(architecture_node.name, "architecture")
            self.assertEqual(architecture_node.overview.id, "demo-architecture")
            self.assertEqual([r.id for r in architecture_node.records], ["demo-detail"])

    def test_decision_is_absent_from_the_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "projects/demo/README.md", _project_overview("demo"))
            write_record(
                root,
                "projects/demo/decisions/choice.md",
                _decision("demo", "choice", status="active", provenance=[_accepted()]),
            )
            library = load_library(Workspace(root))
            groups = grouping.group_project_records(library.records, "demo")
            tree = grouping.build_project_tree("demo", groups.ordinary, library.broken)
            self.assertEqual(tree.children, ())
            self.assertTrue(tree.is_empty())

    def test_broken_file_in_project_directory_is_placed_in_its_node(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "projects/demo/README.md", _project_overview("demo"))
            (root / "projects" / "demo" / "notes").mkdir(parents=True)
            (root / "projects" / "demo" / "notes" / "broken.md").write_text("no frontmatter\n", encoding="utf-8")
            library = load_library(Workspace(root))
            groups = grouping.group_project_records(library.records, "demo")
            tree = grouping.build_project_tree("demo", groups.ordinary, library.broken)
            self.assertEqual(len(tree.children), 1)
            notes_node = tree.children[0]
            self.assertEqual(notes_node.name, "notes")
            self.assertEqual(len(notes_node.broken), 1)
            self.assertEqual(notes_node.broken[0].path, "projects/demo/notes/broken.md")

    def test_empty_tree_when_only_the_overview_and_decisions_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "projects/demo/README.md", _project_overview("demo"))
            library = load_library(Workspace(root))
            groups = grouping.group_project_records(library.records, "demo")
            tree = grouping.build_project_tree("demo", groups.ordinary, library.broken)
            self.assertTrue(tree.is_empty())


class ProjectViewEndToEndTests(unittest.TestCase):
    """GET /p/{project_id} against a real served workspace."""

    def _get(self, base_url: str, path: str) -> tuple[int, str]:
        request = urllib.request.Request(f"{base_url}{path}")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    def test_real_knowledge_os_project_groups_the_four_decisions(self) -> None:
        """The reader's own repository is the real corpus described in the
        unit brief: conversational-memory-capture, project-directory-layout,
        and knowledge-os-reader govern now; openknowledge-pivot is proposed;
        nothing is superseded yet."""

        repository = Path(__file__).resolve().parents[1]
        with serve(repository, PORT) as base_url:
            status, body = self._get(base_url, "/")
            self.assertEqual(status, 200)

            status, body = self._get(base_url, "/p/knowledge-os")
            self.assertEqual(status, 200)

            governing_index = body.index("Governing now")
            proposed_index = body.index("Proposed", governing_index)
            historical_index = body.index("Historical", proposed_index)

            governing_section = body[governing_index:proposed_index]
            proposed_section = body[proposed_index:historical_index]
            historical_section = body[historical_index:]

            for record_id, title in (
                ("conversational-memory-capture", "Conversational memory capture"),
                ("project-directory-layout", "Project directory layout"),
                ("knowledge-os-reader", "Read-only reader for Knowledge OS"),
            ):
                self.assertIn(f"/r/{record_id}", governing_section)
                self.assertIn(title, governing_section)

            self.assertIn("/r/openknowledge-pivot", proposed_section)
            self.assertNotIn("/r/openknowledge-pivot", governing_section)

            self.assertIn("No decision has been superseded yet.", historical_section)
            self.assertNotIn("record-card", historical_section.split("</section>")[0])

            # No contract vocabulary in the primary reading path: strip the
            # collapsed technical-details disclosure (which is allowed to
            # hold the exact status/scope/trust values) and check what is
            # left never shows the raw word "draft" or the field name
            # "content_sha256" as visible text.
            reading_path = re.sub(
                r'<details class="tech-details".*?</details>', "", body, flags=re.DOTALL
            )
            self.assertNotIn(">draft<", reading_path)
            self.assertNotIn("content_sha256", reading_path)

    def test_unknown_project_returns_404_not_500(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        with serve(repository, PORT) as base_url:
            status, body = self._get(base_url, "/p/does-not-exist")
            self.assertEqual(status, 404)
            self.assertIn("does-not-exist", body)

    def test_no_project_route_returns_500(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        with serve(repository, PORT) as base_url:
            for path in ("/", "/p/knowledge-os", "/p/does-not-exist", "/search", "/everything"):
                status, _ = self._get(base_url, path)
                self.assertNotEqual(status, 500, f"{path} returned 500")

    def test_workspace_is_untouched_after_serving(self) -> None:
        """Acceptance criterion 1: byte-identical afterwards, no mtime
        change -- exercised here against a throwaway copy of a small
        workspace built specifically for this project view."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "projects/demo/README.md", _project_overview("demo"))
            path = root / "projects" / "demo" / "README.md"
            before_bytes = path.read_bytes()
            before_mtime = path.stat().st_mtime_ns

            with serve(root, PORT) as base_url:
                status, _ = self._get(base_url, "/p/demo")
                self.assertEqual(status, 200)

            self.assertEqual(path.read_bytes(), before_bytes)
            self.assertEqual(path.stat().st_mtime_ns, before_mtime)


if __name__ == "__main__":
    unittest.main()
