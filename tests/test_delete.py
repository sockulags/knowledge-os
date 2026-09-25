"""Deleting pages and folders in the core and on the command line (issue #78).

Checks what a deletion removes, which references it cleans up, which ones
refuse it, that the decision lifecycle decides which decisions may go, that
a failure injected halfway restores every file, and that ``kos lint``
passes afterwards.
"""

from __future__ import annotations

import json
import pathlib
from pathlib import Path
from unittest.mock import patch

from test_structure import PROVENANCE, StructureTestCase, run_kos, snapshot, write_page

from knowledge_os import structure
from knowledge_os.model import content_sha256, parse_document
from knowledge_os.mutations import RecordNotFoundError, StaleRevisionError
from knowledge_os.structure import (
    StructureError,
    delete_folder,
    delete_record,
    plan_folder_deletion,
    plan_page_deletion,
)
from knowledge_os.workspace import CorpusValidationError

ACCEPTANCE = {"kind": "decision-acceptance", "reference": "conversation:accepted", "captured": "2026-09-02T10:00:00Z"}


class DeleteTestCase(StructureTestCase):
    """Adds to the structure fixture: ``acme/notes/todo.md``, listed under
    ``related`` and ``sources`` by ``plan`` and linked from ``guide``."""

    def setUp(self) -> None:
        super().setUp()
        write_page(self.root, "projects/acme/notes/todo.md", "todo", "project:acme", "Things to do.\n")
        plan = parse_document(self.root / "projects/acme/plan.md", check_filename=False)
        write_page(self.root, "projects/acme/plan.md", "plan", "project:acme", plan.body, related=["todo", "kickoff"],
                   sources=["todo"])
        guide = self.root / "knowledge/guide.md"
        guide.write_text(guide.read_text(encoding="utf-8") + "\nSee [todo](../projects/acme/notes/todo.md).\n",
                         encoding="utf-8")
        self.assert_valid()

    def metadata(self, relative: str) -> dict:
        return parse_document(self.root / relative, check_filename=False).metadata

    def decision(self, relative: str, record_id: str, status: str, **extra: object) -> None:
        provenance = [*PROVENANCE, ACCEPTANCE] if status in {"active", "superseded"} else list(PROVENANCE)
        write_page(self.root, relative, record_id, "project:acme", "We decide.\n", record_kind="decision",
                   status=status, provenance=provenance, **extra)


class DeletePageTests(DeleteTestCase):
    def test_delete_removes_the_page_and_its_structured_references(self) -> None:
        plan = plan_page_deletion(self.workspace, "todo")
        self.assertTrue(plan.deletable)
        self.assertEqual(plan.files, ("projects/acme/notes/todo.md",))
        referrers = {item.id: item for item in plan.referrers}
        self.assertEqual(referrers["plan"].fields, ("related", "sources"))
        self.assertFalse(referrers["plan"].links)
        self.assertEqual(referrers["guide"].fields, ())
        self.assertTrue(referrers["guide"].links)
        self.assertEqual(set(plan.expected), {"projects/acme/notes/todo.md", "projects/acme/plan.md"})

        guide_before = (self.root / "knowledge/guide.md").read_bytes()
        result = delete_record(
            self.workspace, "todo", expected_sha256=self.sha("projects/acme/notes/todo.md"), expected=plan.expected
        )
        self.assertFalse((self.root / "projects/acme/notes/todo.md").exists())
        self.assertEqual(result.deleted, ("projects/acme/notes/todo.md",))
        self.assertEqual(result.title, "Todo")
        self.assertEqual(result.touched, ("projects/acme/notes/todo.md", "projects/acme/plan.md"))
        plan_metadata = self.metadata("projects/acme/plan.md")
        self.assertEqual(plan_metadata["related"], ["kickoff"])
        self.assertNotIn("sources", plan_metadata)
        # Markdown links are reported, never rewritten.
        self.assertEqual((self.root / "knowledge/guide.md").read_bytes(), guide_before)
        self.assert_valid()

    def test_emptied_folder_without_a_page_disappears(self) -> None:
        write_page(self.root, "projects/acme/loose/only.md", "only", "project:acme", "Alone.\n")
        delete_record(self.workspace, "only", expected_sha256=self.sha("projects/acme/loose/only.md"))
        self.assertFalse((self.root / "projects/acme/loose").exists())
        self.assert_valid()

    def test_refusals_write_nothing(self) -> None:
        before = snapshot(self.root)
        cases = {
            "acme": "project overview",
            "acme-notes": "folder's own page",
        }
        for record_id, message in cases.items():
            with self.subTest(record_id=record_id):
                relative = "projects/acme/README.md" if record_id == "acme" else "projects/acme/notes/README.md"
                with self.assertRaisesRegex(StructureError, message):
                    delete_record(self.workspace, record_id, expected_sha256=self.sha(relative))
        with self.assertRaises(RecordNotFoundError):
            delete_record(self.workspace, "missing", expected_sha256="0" * 64)
        with self.assertRaises(StaleRevisionError):
            delete_record(self.workspace, "todo", expected_sha256="1" * 64)
        self.assertEqual(snapshot(self.root), before)

    def test_expected_must_cover_every_file_it_rewrites(self) -> None:
        before = snapshot(self.root)
        with self.assertRaisesRegex(StaleRevisionError, "projects/acme/plan.md"):
            delete_record(
                self.workspace,
                "todo",
                expected_sha256=self.sha("projects/acme/notes/todo.md"),
                expected={"projects/acme/notes/todo.md": self.sha("projects/acme/notes/todo.md")},
            )
        self.assertEqual(snapshot(self.root), before)

    def test_provenance_evidence_and_raw_references_refuse(self) -> None:
        write_page(self.root, "projects/acme/derived.md", "derived", "project:acme", "From todo.\n",
                   provenance=[{"kind": "record", "reference": "todo"}])
        self.assert_valid()
        plan = plan_page_deletion(self.workspace, "todo")
        self.assertFalse(plan.deletable)
        self.assertEqual([(item.kind, item.other_id) for item in plan.blockers], [("origin", "derived")])
        before = snapshot(self.root)
        with self.assertRaisesRegex(StructureError, "provenance"):
            delete_record(self.workspace, "todo", expected_sha256=self.sha("projects/acme/notes/todo.md"))
        self.assertEqual(snapshot(self.root), before)


class DecisionDeletionTests(DeleteTestCase):
    def test_proposed_and_withdrawn_decisions_may_be_deleted(self) -> None:
        self.decision("projects/acme/proposal.md", "proposal", "draft")
        withdrawal = {"kind": "decision-withdrawal", "reference": "cli:2026-09-02T10:00:00Z:withdraw",
                      "captured": "2026-09-02T10:00:00Z"}
        write_page(self.root, "projects/acme/dropped.md", "dropped", "project:acme", "No.\n",
                   record_kind="decision", status="archived", provenance=[*PROVENANCE, withdrawal])
        self.assert_valid()
        for record_id in ("proposal", "dropped"):
            with self.subTest(record_id=record_id):
                delete_record(self.workspace, record_id, expected_sha256=self.sha(f"projects/acme/{record_id}.md"))
                self.assertFalse((self.root / f"projects/acme/{record_id}.md").exists())
        self.assert_valid()

    def test_decisions_in_force_or_replaced_and_their_lineage_cannot_be_deleted(self) -> None:
        self.decision("projects/acme/old-rule.md", "old-rule", "superseded")
        self.decision("projects/acme/rule.md", "rule", "active", supersedes=["old-rule"])
        self.decision("projects/acme/next-rule.md", "next-rule", "draft", supersedes=["rule"])
        self.assert_valid()
        before = snapshot(self.root)
        kinds = {
            "rule": {("in_force", None), ("replaced_by", "next-rule")},
            "old-rule": {("replaced", None), ("replaced_by", "rule")},
        }
        for record_id, expected in kinds.items():
            with self.subTest(record_id=record_id):
                plan = plan_page_deletion(self.workspace, record_id)
                self.assertEqual({(item.kind, item.other_id) for item in plan.blockers}, expected)
                with self.assertRaises(StructureError):
                    delete_record(self.workspace, record_id, expected_sha256=self.sha(f"projects/acme/{record_id}.md"))
        self.assertEqual(snapshot(self.root), before)
        # The proposed replacement itself may go: nothing points at it.
        delete_record(self.workspace, "next-rule", expected_sha256=self.sha("projects/acme/next-rule.md"))
        self.assert_valid()


class DeleteFolderTests(DeleteTestCase):
    def test_folder_with_contents_is_removed_with_every_file(self) -> None:
        (self.root / "projects/acme/notes/meetings/diagram.png").write_bytes(b"\x89PNG")
        plan = plan_folder_deletion(self.workspace, "acme", "notes")
        self.assertTrue(plan.deletable)
        self.assertEqual(plan.id, "acme-notes")
        self.assertEqual(plan.title, "Notes")
        self.assertEqual(
            plan.files,
            (
                "projects/acme/notes/README.md",
                "projects/acme/notes/meetings/README.md",
                "projects/acme/notes/meetings/diagram.png",
                "projects/acme/notes/meetings/kickoff.md",
                "projects/acme/notes/todo.md",
            ),
        )
        self.assertEqual({record.id for record in plan.records}, {"acme-notes", "acme-notes-meetings", "kickoff", "todo"})
        referrers = {item.id: item for item in plan.referrers}
        # plan lists todo and kickoff and links into the folder; beta and guide link into it.
        self.assertEqual(referrers["plan"].fields, ("related", "sources"))
        self.assertTrue(referrers["plan"].links)
        self.assertTrue(referrers["beta"].links)
        self.assertTrue(referrers["guide"].links)
        self.assertNotIn("kickoff", referrers)  # inside the folder

        result = delete_folder(self.workspace, "acme", "notes", expected=plan.expected)
        self.assertFalse((self.root / "projects/acme/notes").exists())
        self.assertEqual(result.deleted, plan.files)
        self.assertEqual(result.path, "projects/acme/notes")
        self.assertNotIn("related", self.metadata("projects/acme/plan.md"))
        self.assert_valid()

    def test_a_file_added_after_the_preview_refuses_the_deletion(self) -> None:
        plan = plan_folder_deletion(self.workspace, "acme", "notes")
        (self.root / "projects/acme/notes/late.txt").write_text("new", encoding="utf-8")
        before = snapshot(self.root)
        with self.assertRaisesRegex(StaleRevisionError, "late.txt"):
            delete_folder(self.workspace, "acme", "notes", expected=plan.expected)
        self.assertEqual(snapshot(self.root), before)

    def test_a_decision_in_force_inside_refuses_the_whole_folder(self) -> None:
        self.decision("projects/acme/notes/rule.md", "rule", "active")
        self.assert_valid()
        before = snapshot(self.root)
        plan = plan_folder_deletion(self.workspace, "acme", "notes")
        self.assertEqual([item.kind for item in plan.blockers], ["in_force"])
        with self.assertRaisesRegex(StructureError, "in force"):
            delete_folder(self.workspace, "acme", "notes")
        self.assertEqual(snapshot(self.root), before)

    def test_refusals_for_missing_and_top_level(self) -> None:
        with self.assertRaises(RecordNotFoundError):
            delete_folder(self.workspace, "acme", "nowhere")
        with self.assertRaises(StructureError):
            delete_folder(self.workspace, "acme", "")
        with self.assertRaises(RecordNotFoundError):
            delete_folder(self.workspace, "nobody", "notes")

    def test_failure_in_the_middle_restores_every_file_and_directory(self) -> None:
        before = snapshot(self.root)
        real_unlink = pathlib.Path.unlink
        calls = {"live": 0}

        def failing_unlink(path: Path, missing_ok: bool = False) -> None:
            if str(path).startswith(str(self.root)) and not path.name.startswith("."):
                calls["live"] += 1
                if calls["live"] == 3:
                    raise OSError("disk gone (injected)")
            real_unlink(path, missing_ok=missing_ok)

        with patch.object(pathlib.Path, "unlink", failing_unlink):
            with self.assertRaisesRegex(StructureError, "every file was restored"):
                delete_folder(self.workspace, "acme", "notes")
        self.assertEqual(calls["live"], 3)
        self.assertEqual(snapshot(self.root), before)
        self.assert_valid()

    def test_anything_else_lint_rejects_is_refused_by_staged_validation(self) -> None:
        # A discovery's related list is cleaned, but a staged lint still runs;
        # simulate a rule the pre-checks do not know by breaking the corpus
        # through a patched cleanup.
        before = snapshot(self.root)

        def broken(content: bytes, removed: set[str]) -> bytes:
            return content.replace(b"status: active", b"status: nonsense")

        with patch.object(structure, "_without_references", broken):
            with self.assertRaises(CorpusValidationError):
                delete_record(self.workspace, "todo", expected_sha256=self.sha("projects/acme/notes/todo.md"))
        self.assertEqual(snapshot(self.root), before)


class DeleteCliTests(DeleteTestCase):
    def kos(self, *arguments: str):
        return run_kos(self.root, *arguments)

    def test_dry_run_delete_and_folder_delete_leave_lint_passing(self) -> None:
        dry = self.kos("delete", "todo", "--dry-run", "--json")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        preview = json.loads(dry.stdout)
        self.assertTrue(preview["deletable"])
        self.assertTrue((self.root / "projects/acme/notes/todo.md").exists())

        missing_hash = self.kos("delete", "todo")
        self.assertEqual(missing_hash.returncode, 1)
        self.assertIn("--expected-sha256", missing_hash.stderr)

        deleted = self.kos("delete", "todo", "--expected-sha256", content_sha256(self.root / "projects/acme/notes/todo.md"))
        self.assertEqual(deleted.returncode, 0, deleted.stderr)
        self.assertIn("Deleted projects/acme/notes/todo.md", deleted.stdout)
        self.assertIn("Updated projects/acme/plan.md", deleted.stdout)

        refused = self.kos("delete", "acme", "--dry-run")
        self.assertEqual(refused.returncode, 0)
        self.assertIn("Refused:", refused.stdout)

        folder = self.kos("folder", "delete", "acme", "notes", "--json")
        self.assertEqual(folder.returncode, 0, folder.stderr)
        self.assertIn("projects/acme/notes/meetings/kickoff.md", json.loads(folder.stdout)["deleted"])
        self.assertFalse((self.root / "projects/acme/notes").exists())

        lint = self.kos("lint")
        self.assertEqual(lint.returncode, 0, lint.stderr)


if __name__ == "__main__":
    import unittest

    unittest.main()
