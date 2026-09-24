"""Structure editing in the core and on the command line (issue #52).

Creates projects and folders, moves and renames pages and folders, and
checks after every change that relative links still resolve and that
``kos lint`` passes. Refusals and a failure injected in the middle of a move
must leave every file byte-identical.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from knowledge_os import links, structure
from knowledge_os.capture import DuplicateRecordError
from knowledge_os.init_workspace import init_workspace
from knowledge_os.model import content_sha256, parse_document
from knowledge_os.mutations import RecordNotFoundError, StaleRevisionError
from knowledge_os.reader import markdown as reader_markdown
from knowledge_os.structure import (
    StructureError,
    cli_provenance,
    create_folder,
    create_project,
    move_folder,
    move_record,
    rename_record,
)
from knowledge_os.workspace import CorpusValidationError, Workspace, validate_workspace

REPOSITORY = Path(__file__).resolve().parents[1]
PROVENANCE = [{"kind": "fixture", "reference": "test:structure"}]


def run_kos(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPOSITORY) + os.pathsep + environment.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "knowledge_os", "--root", str(root), *arguments],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )


def write_page(root: Path, relative: str, record_id: str, scope: str, body: str, **extra: object) -> Path:
    metadata: dict[str, object] = {
        "id": record_id,
        "title": record_id.replace("-", " ").capitalize(),
        "type": "project",
        "status": "active",
        "scope": scope,
        "created": "2026-09-01",
        "updated": "2026-09-01",
        "provenance": PROVENANCE,
    }
    metadata.update(extra)
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{yaml.safe_dump(metadata, sort_keys=False)}---\n\n{body}", encoding="utf-8")
    return path


def snapshot(root: Path) -> dict[str, bytes | None]:
    """Every file's bytes and every directory (as None) below the managed roots."""

    state: dict[str, bytes | None] = {}
    for directory in ("projects", "knowledge", "memory", "sources", "syntheses", "discoveries"):
        for path in sorted((root / directory).rglob("*")):
            state[path.relative_to(root).as_posix()] = path.read_bytes() if path.is_file() else None
    return state


def body_of(path: Path) -> str:
    return parse_document(path, check_filename=False).body


class StructureTestCase(unittest.TestCase):
    """A workspace with projects ``acme`` and ``beta``:

    acme/README.md                    overview
    acme/plan.md                      links into notes/ in every supported form
    acme/notes/README.md              folder page
    acme/notes/meetings/README.md     nested folder page
    acme/notes/meetings/kickoff.md    links out of its own folder
    acme/archive/README.md            an empty folder (only its page)
    beta/README.md                    overview; links into acme
    knowledge/guide.md                general knowledge linking into acme
    """

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = init_workspace(Path(self._temp.name) / "kb")
        self.workspace = Workspace(self.root)
        create_project(self.workspace, "acme", title="Acme", provenance=PROVENANCE)
        create_project(
            self.workspace,
            "beta",
            title="Beta",
            provenance=PROVENANCE,
            body="See [the kickoff](../acme/notes/meetings/kickoff.md#agenda).\n",
        )
        create_folder(self.workspace, "acme", "notes", title="Notes", provenance=PROVENANCE)
        create_folder(self.workspace, "acme", "notes/meetings", title="Meetings", provenance=PROVENANCE)
        create_folder(self.workspace, "acme", "archive", title="Archive", provenance=PROVENANCE)
        write_page(
            self.root,
            "projects/acme/notes/meetings/kickoff.md",
            "kickoff",
            "project:acme",
            "Back to [notes](../README.md), [the plan](../../plan.md#goals), and [site](https://example.com/a.md).\n",
        )
        write_page(
            self.root,
            "projects/acme/plan.md",
            "plan",
            "project:acme",
            "## Goals\n\n"
            "Read [the kickoff](notes/meetings/kickoff.md#agenda), ![diagram](<notes/meetings/kickoff.md>),\n"
            "[meetings](notes/meetings/README.md), the [folder](notes/meetings/), and [ref][k].\n"
            "Inline code `[not](notes/meetings/kickoff.md)` stays.\n\n"
            "```\n[fenced](notes/meetings/kickoff.md)\n```\n\n"
            "[k]: notes/meetings/kickoff.md \"Kickoff\"\n",
        )
        (self.root / "knowledge").mkdir(exist_ok=True)
        guide = write_page(
            self.root,
            "knowledge/guide.md",
            "guide",
            "general",
            "The [kickoff](../projects/acme/notes/meetings/kickoff.md) explains it.\n",
        )
        text = guide.read_text(encoding="utf-8").replace("type: project", "type: knowledge")
        guide.write_text(text, encoding="utf-8")
        self.assert_valid()

    # -- helpers ------------------------------------------------------------

    def assert_valid(self) -> None:
        _documents, issues = validate_workspace(self.workspace)
        self.assertEqual(issues, [], "\n".join(f"{issue.path}: {issue.message}" for issue in issues))

    def assert_links_resolve(self) -> None:
        """Every relative link in every record points at an existing file or folder."""

        documents, _issues = validate_workspace(self.workspace)
        for document in documents:
            source = self.workspace.relative(document.path)
            for target, _fragment in links.relative_links(document.body, source):
                if target.startswith("../") or "example.com" in target:
                    continue
                self.assertTrue((self.root / target).exists(), f"{source} links to missing {target}")

    def sha(self, relative: str) -> str:
        return content_sha256(self.root / relative)


class CreateTests(StructureTestCase):
    def test_created_project_is_a_valid_overview(self) -> None:
        document = parse_document(self.root / "projects/acme/README.md", check_filename=False)
        self.assertEqual(document.metadata["id"], "acme")
        self.assertEqual(document.metadata["scope"], "project:acme")
        self.assertEqual(document.metadata["status"], "active")
        self.assertEqual(document.metadata["provenance"], PROVENANCE)
        self.assertEqual(document.body, "# Acme\n")

    def test_project_refusals_write_nothing(self) -> None:
        before = snapshot(self.root)
        with self.assertRaises(DuplicateRecordError):
            create_project(self.workspace, "acme", title="Again", provenance=PROVENANCE)
        with self.assertRaises(StructureError):
            create_project(self.workspace, "Not Kebab", title="Bad", provenance=PROVENANCE)
        with self.assertRaises(StructureError):
            create_project(self.workspace, "gamma", title="  ", provenance=PROVENANCE)
        self.assertEqual(snapshot(self.root), before)

    def test_folder_is_its_readme_page_with_a_path_based_id(self) -> None:
        result = create_folder(self.workspace, "acme", "notes/meetings/2026", title="2026", provenance=PROVENANCE)
        self.assertEqual(result.path, "projects/acme/notes/meetings/2026/README.md")
        self.assertEqual(result.id, "acme-notes-meetings-2026")
        document = parse_document(self.root / result.path, check_filename=False)
        self.assertEqual(document.metadata["title"], "2026")
        self.assertEqual(result.sha256, self.sha(result.path))
        self.assert_valid()

    def test_folder_id_gets_a_suffix_when_taken(self) -> None:
        write_page(self.root, "projects/acme/acme-drafts.md", "acme-drafts", "project:acme", "Taken.\n")
        result = create_folder(self.workspace, "acme", "drafts", title="Drafts", provenance=PROVENANCE)
        self.assertEqual(result.id, "acme-drafts-2")
        self.assert_valid()

    def test_folder_refusals_write_nothing(self) -> None:
        before = snapshot(self.root)
        with self.assertRaises(DuplicateRecordError):
            create_folder(self.workspace, "acme", "notes", title="Notes", provenance=PROVENANCE)
        with self.assertRaises(RecordNotFoundError):
            create_folder(self.workspace, "acme", "missing/child", title="Child", provenance=PROVENANCE)
        with self.assertRaises(RecordNotFoundError):
            create_folder(self.workspace, "nope", "notes", title="Notes", provenance=PROVENANCE)
        with self.assertRaises(StructureError):
            create_folder(self.workspace, "acme", "Meeting Notes", title="Notes", provenance=PROVENANCE)
        with self.assertRaises(StructureError):
            create_folder(self.workspace, "acme", "../escape", title="Escape", provenance=PROVENANCE)
        self.assertEqual(snapshot(self.root), before)


class MovePageTests(StructureTestCase):
    def test_move_rewrites_links_from_other_folders_projects_and_itself(self) -> None:
        guide_before = (self.root / "knowledge/guide.md").read_bytes()
        result = move_record(
            self.workspace,
            "kickoff",
            expected_sha256=self.sha("projects/acme/notes/meetings/kickoff.md"),
            folder="archive",
        )
        self.assertEqual(result.path, "projects/acme/archive/kickoff.md")
        self.assertFalse((self.root / "projects/acme/notes/meetings/kickoff.md").exists())
        moved = parse_document(self.root / result.path)
        self.assertEqual(moved.metadata["id"], "kickoff")
        self.assertEqual(str(moved.metadata["updated"]), "2026-09-01")
        self.assertEqual(
            moved.body,
            "Back to [notes](../notes/README.md), [the plan](../plan.md#goals), and [site](https://example.com/a.md).\n",
        )
        plan = body_of(self.root / "projects/acme/plan.md")
        self.assertIn("[the kickoff](archive/kickoff.md#agenda)", plan)
        self.assertIn("![diagram](<archive/kickoff.md>)", plan)
        self.assertIn("[k]: archive/kickoff.md \"Kickoff\"", plan)
        self.assertIn("[meetings](notes/meetings/README.md)", plan)
        self.assertIn("`[not](notes/meetings/kickoff.md)`", plan)
        self.assertIn("[fenced](notes/meetings/kickoff.md)", plan)
        self.assertIn(
            "(../acme/archive/kickoff.md#agenda)", body_of(self.root / "projects/beta/README.md")
        )
        self.assertNotEqual((self.root / "knowledge/guide.md").read_bytes(), guide_before)
        self.assertIn("(../projects/acme/archive/kickoff.md)", body_of(self.root / "knowledge/guide.md"))
        changed = {item.path: item for item in result.changed}
        self.assertEqual(changed[result.path].old_path, "projects/acme/notes/meetings/kickoff.md")
        for path in ("projects/acme/plan.md", "projects/beta/README.md", "knowledge/guide.md"):
            self.assertEqual(changed[path].sha256, self.sha(path))
        self.assertIn("projects/acme/notes/meetings/kickoff.md", result.touched)
        self.assert_valid()
        self.assert_links_resolve()

    def test_unrelated_files_keep_their_exact_bytes(self) -> None:
        overview = (self.root / "projects/acme/README.md").read_bytes()
        move_record(
            self.workspace, "plan", expected_sha256=self.sha("projects/acme/plan.md"), folder="notes"
        )
        self.assertEqual((self.root / "projects/acme/README.md").read_bytes(), overview)
        self.assert_links_resolve()
        self.assert_valid()

    def test_source_records_are_never_rewritten(self) -> None:
        source = self.root / "sources/raw-note.md"
        source.write_text(
            "---\nid: raw-note\ntitle: Raw\ntype: source\nstatus: active\nscope: general\n"
            "created: '2026-09-01'\nupdated: '2026-09-01'\nprovenance:\n- kind: file\n  reference: x\n---\n\n"
            "See [it](../projects/acme/plan.md).\n",
            encoding="utf-8",
        )
        before = source.read_bytes()
        move_record(self.workspace, "plan", expected_sha256=self.sha("projects/acme/plan.md"), folder="notes")
        self.assertEqual(source.read_bytes(), before)

    def test_emptied_folder_without_a_page_disappears(self) -> None:
        write_page(self.root, "projects/acme/loose/lonely.md", "lonely", "project:acme", "Alone.\n")
        move_record(self.workspace, "lonely", expected_sha256=self.sha("projects/acme/loose/lonely.md"), folder="")
        self.assertFalse((self.root / "projects/acme/loose").exists())
        self.assertTrue((self.root / "projects/acme/lonely.md").is_file())

    def test_refusals_write_nothing(self) -> None:
        kickoff = self.sha("projects/acme/notes/meetings/kickoff.md")
        (self.root / "projects/acme/archive/kickoff.md").mkdir()
        cases = [
            (StaleRevisionError, dict(record_id="kickoff", expected_sha256="0" * 64, folder="archive")),
            (RecordNotFoundError, dict(record_id="nope", expected_sha256=kickoff, folder="archive")),
            (RecordNotFoundError, dict(record_id="kickoff", expected_sha256=kickoff, folder="missing")),
            (StructureError, dict(record_id="kickoff", expected_sha256=kickoff, folder="notes/meetings")),
            (DuplicateRecordError, dict(record_id="kickoff", expected_sha256=kickoff, folder="archive")),
            (StructureError, dict(record_id="acme", expected_sha256=self.sha("projects/acme/README.md"), folder="notes")),
            (
                StructureError,
                dict(record_id="acme-notes", expected_sha256=self.sha("projects/acme/notes/README.md"), folder=""),
            ),
            (StructureError, dict(record_id="kickoff", expected_sha256=kickoff, folder="../beta")),
        ]
        before = snapshot(self.root)
        for error, arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises(error):
                record_id = arguments.pop("record_id")
                move_record(self.workspace, record_id, **arguments)
            self.assertEqual(snapshot(self.root), before)

    def test_move_to_another_project_needs_confirmation_and_changes_scope(self) -> None:
        sha = self.sha("projects/acme/notes/meetings/kickoff.md")
        before = snapshot(self.root)
        with self.assertRaisesRegex(StructureError, "changes its scope"):
            move_record(self.workspace, "kickoff", expected_sha256=sha, project="beta", folder="")
        self.assertEqual(snapshot(self.root), before)

        result = move_record(
            self.workspace, "kickoff", expected_sha256=sha, project="beta", folder="", allow_scope_change=True
        )
        self.assertTrue(result.scope_changed)
        self.assertEqual(result.path, "projects/beta/kickoff.md")
        moved = parse_document(self.root / result.path)
        self.assertEqual(moved.metadata["scope"], "project:beta")
        self.assertIn("[notes](../acme/notes/README.md)", moved.body)
        self.assertIn("(kickoff.md#agenda)", body_of(self.root / "projects/beta/README.md"))
        self.assert_valid()
        self.assert_links_resolve()

    def test_decision_lineage_cannot_cross_projects(self) -> None:
        acceptance = {"kind": "decision-acceptance", "reference": "test:accept", "captured": "2026-09-01T00:00:00Z"}
        write_page(
            self.root,
            "projects/acme/old-rule.md",
            "old-rule",
            "project:acme",
            "Old rule.\n",
            record_kind="decision",
            provenance=[*PROVENANCE, acceptance],
        )
        write_page(
            self.root,
            "projects/acme/new-rule.md",
            "new-rule",
            "project:acme",
            "New rule.\n",
            record_kind="decision",
            status="draft",
            supersedes=["old-rule"],
        )
        self.assert_valid()
        before = snapshot(self.root)
        for record_id in ("new-rule", "old-rule"):
            with self.subTest(record_id=record_id), self.assertRaisesRegex(StructureError, "lineage"):
                move_record(
                    self.workspace,
                    record_id,
                    expected_sha256=self.sha(f"projects/acme/{record_id}.md"),
                    project="beta",
                    folder="",
                    allow_scope_change=True,
                )
        self.assertEqual(snapshot(self.root), before)
        # Inside one project the pair may move freely.
        move_record(self.workspace, "new-rule", expected_sha256=self.sha("projects/acme/new-rule.md"), folder="notes")
        self.assert_valid()

    def test_anything_else_lint_rejects_is_refused_by_staged_validation(self) -> None:
        write_page(self.root, "projects/acme/finding.md", "finding", "project:acme", "Target.\n",
                   status="draft", provenance=[{"kind": "discovery", "reference": "seen-it"}])
        (self.root / "discoveries/seen-it.md").write_text(
            "---\n"
            + yaml.safe_dump(
                {
                    "id": "seen-it",
                    "title": "Seen it",
                    "type": "discovery",
                    "status": "promoted",
                    "scope": "project:acme",
                    "created": "2026-09-01",
                    "updated": "2026-09-01",
                    "provenance": PROVENANCE,
                    "evidence": [{"kind": "note", "reference": "x"}],
                    "reviews": [{"decision": "promote", "date": "2026-09-01", "target": "finding"}],
                },
                sort_keys=False,
            )
            + "---\n\nObserved.\n",
            encoding="utf-8",
        )
        self.assert_valid()
        before = snapshot(self.root)
        with self.assertRaises(CorpusValidationError) as raised:
            move_record(
                self.workspace,
                "finding",
                expected_sha256=self.sha("projects/acme/finding.md"),
                project="beta",
                folder="",
                allow_scope_change=True,
            )
        self.assertTrue(any("different project scope" in message for _path, message in raised.exception.issues))
        self.assertEqual(snapshot(self.root), before)

    def test_failure_in_the_middle_restores_every_file(self) -> None:
        before = snapshot(self.root)
        real_write = structure.atomic_write
        calls = {"live": 0}

        def failing_write(path: Path, content: bytes) -> None:
            if str(path).startswith(str(self.root)):
                calls["live"] += 1
                if calls["live"] == 2:
                    raise OSError("disk full (injected)")
            real_write(path, content)

        with patch.object(structure, "atomic_write", failing_write):
            with self.assertRaisesRegex(StructureError, "every file was restored"):
                move_record(
                    self.workspace,
                    "kickoff",
                    expected_sha256=self.sha("projects/acme/notes/meetings/kickoff.md"),
                    folder="archive",
                )
        self.assertGreaterEqual(calls["live"], 2)
        self.assertEqual(snapshot(self.root), before)
        self.assert_valid()

    def test_optional_expected_hashes_guard_other_files(self) -> None:
        before = snapshot(self.root)
        with self.assertRaises(StaleRevisionError):
            move_record(
                self.workspace,
                "kickoff",
                expected_sha256=self.sha("projects/acme/notes/meetings/kickoff.md"),
                folder="archive",
                expected={"projects/acme/plan.md": "1" * 64},
            )
        self.assertEqual(snapshot(self.root), before)


class MoveFolderTests(StructureTestCase):
    def test_move_folder_into_another_folder_rewrites_links_into_it(self) -> None:
        (self.root / "projects/acme/notes/meetings/diagram.png").write_bytes(b"\x89PNG")
        result = move_folder(self.workspace, "acme", "notes/meetings", to_parent="archive")
        self.assertEqual(result.path, "projects/acme/archive/meetings/README.md")
        self.assertEqual(result.id, "acme-notes-meetings")
        self.assertEqual(result.folder, "archive/meetings")
        self.assertTrue((self.root / "projects/acme/archive/meetings/kickoff.md").is_file())
        self.assertTrue((self.root / "projects/acme/archive/meetings/diagram.png").is_file())
        self.assertFalse((self.root / "projects/acme/notes/meetings").exists())
        plan = body_of(self.root / "projects/acme/plan.md")
        self.assertIn("[the kickoff](archive/meetings/kickoff.md#agenda)", plan)
        self.assertIn("[meetings](archive/meetings/README.md)", plan)
        self.assertIn("the [folder](archive/meetings/)", plan)
        kickoff = body_of(self.root / "projects/acme/archive/meetings/kickoff.md")
        self.assertIn("[notes](../../notes/README.md)", kickoff)
        self.assertIn("[the plan](../../plan.md#goals)", kickoff)
        moved_paths = {item.old_path: item.path for item in result.changed}
        self.assertEqual(
            moved_paths["projects/acme/notes/meetings/diagram.png"], "projects/acme/archive/meetings/diagram.png"
        )
        self.assertIn("projects/acme/notes/meetings/kickoff.md", result.touched)
        self.assertIn("projects/acme/archive/meetings/kickoff.md", result.touched)
        self.assert_valid()
        self.assert_links_resolve()

    def test_rename_folder_changes_directory_and_page_title(self) -> None:
        result = move_folder(self.workspace, "acme", "notes", name="journal", title="Journal")
        self.assertEqual(result.path, "projects/acme/journal/README.md")
        self.assertEqual(result.title, "Journal")
        self.assertEqual(parse_document(self.root / result.path, check_filename=False).metadata["title"], "Journal")
        self.assertIn("[meetings](journal/meetings/README.md)", body_of(self.root / "projects/acme/plan.md"))
        self.assert_valid()
        self.assert_links_resolve()

    def test_title_only_rename_keeps_the_directory(self) -> None:
        result = move_folder(self.workspace, "acme", "notes", title="Field notes")
        self.assertEqual(result.path, "projects/acme/notes/README.md")
        self.assertEqual(result.touched, ("projects/acme/notes/README.md",))
        self.assert_valid()

    def test_refusals_write_nothing(self) -> None:
        before = snapshot(self.root)
        cases = [
            (StructureError, dict(folder="notes", to_parent="notes/meetings")),
            (DuplicateRecordError, dict(folder="archive", name="notes")),
            (RecordNotFoundError, dict(folder="missing", to_parent="")),
            (RecordNotFoundError, dict(folder="notes", to_parent="missing")),
            (StructureError, dict(folder="notes")),
            (StructureError, dict(folder="notes", name="Bad Name")),
            (StructureError, dict(folder="", to_parent="notes")),
            (StructureError, dict(folder="notes", to_project="beta")),
        ]
        for error, arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises(error):
                move_folder(self.workspace, "acme", arguments.pop("folder"), **arguments)
            self.assertEqual(snapshot(self.root), before)

    def test_move_folder_to_another_project_changes_every_scope(self) -> None:
        result = move_folder(self.workspace, "acme", "notes", to_project="beta", to_parent="", allow_scope_change=True)
        self.assertTrue(result.scope_changed)
        for relative in ("projects/beta/notes/README.md", "projects/beta/notes/meetings/kickoff.md"):
            self.assertEqual(
                parse_document(self.root / relative, check_filename=False).metadata["scope"], "project:beta"
            )
        self.assertIn("(../beta/notes/meetings/kickoff.md#agenda)", body_of(self.root / "projects/acme/plan.md"))
        self.assertIn("(notes/meetings/kickoff.md#agenda)", body_of(self.root / "projects/beta/README.md"))
        self.assert_valid()
        self.assert_links_resolve()

    def test_decision_pair_may_move_together_but_not_apart(self) -> None:
        acceptance = {"kind": "decision-acceptance", "reference": "test:accept", "captured": "2026-09-01T00:00:00Z"}
        write_page(self.root, "projects/acme/notes/old-rule.md", "old-rule", "project:acme", "Old.\n",
                   record_kind="decision", provenance=[*PROVENANCE, acceptance])
        write_page(self.root, "projects/acme/notes/meetings/new-rule.md", "new-rule", "project:acme", "New.\n",
                   record_kind="decision", status="draft", supersedes=["old-rule"])
        self.assert_valid()
        before = snapshot(self.root)
        with self.assertRaisesRegex(StructureError, "lineage"):
            move_folder(self.workspace, "acme", "notes/meetings", to_project="beta", to_parent="",
                        allow_scope_change=True)
        self.assertEqual(snapshot(self.root), before)
        move_folder(self.workspace, "acme", "notes", to_project="beta", to_parent="", allow_scope_change=True)
        self.assert_valid()

    def test_failure_in_the_middle_restores_every_file_and_directory(self) -> None:
        before = snapshot(self.root)
        real_write = structure.atomic_write

        def failing_write(path: Path, content: bytes) -> None:
            if str(path).startswith(str(self.root)) and path.name == "guide.md":
                raise OSError("permission denied (injected)")
            real_write(path, content)

        with patch.object(structure, "atomic_write", failing_write):
            with self.assertRaisesRegex(StructureError, "every file was restored"):
                move_folder(self.workspace, "acme", "notes", to_parent="archive")
        self.assertEqual(snapshot(self.root), before)
        self.assert_valid()


class RenamePageTests(StructureTestCase):
    def test_rename_changes_only_the_title(self) -> None:
        path = self.root / "projects/acme/plan.md"
        body = body_of(path)
        result = rename_record(self.workspace, "plan", expected_sha256=self.sha("projects/acme/plan.md"), title="Roadmap")
        document = parse_document(path)
        self.assertEqual(document.metadata["title"], "Roadmap")
        self.assertEqual(document.body, body)
        self.assertEqual(result.path, "projects/acme/plan.md")
        self.assertEqual(result.sha256, self.sha("projects/acme/plan.md"))
        self.assert_valid()

    def test_stale_rename_is_refused(self) -> None:
        before = snapshot(self.root)
        with self.assertRaises(StaleRevisionError):
            rename_record(self.workspace, "plan", expected_sha256="2" * 64, title="Roadmap")
        self.assertEqual(snapshot(self.root), before)


class LinkRuleTests(unittest.TestCase):
    def test_core_and_reader_resolve_links_the_same_way(self) -> None:
        source = "projects/acme/notes/page.md"
        for href in ("../plan.md", "./x.md#a", "sub/dir/", "../../beta/README.md#top", "x.md?y=1", "a/../b.md"):
            with self.subTest(href=href):
                self.assertEqual(
                    links.resolve_link_target(source, href), reader_markdown._resolve_link_target(source, href)
                )
        for href in ("https://x.org/a.md", "mailto:a@b", "//cdn/x.md", "#section"):
            with self.subTest(href=href):
                self.assertTrue(links.EXTERNAL_LINK.match(href))
                self.assertTrue(reader_markdown._EXTERNAL_LINK.match(href))

    def test_rewrite_keeps_unrelated_text_byte_for_byte(self) -> None:
        body = "Crlf line [a](x.md)\r\nand `code [b](x.md)` [c](y.md \"t\")\r\n"
        rewritten = links.rewrite_links(body, "p/s.md", "p/s.md", lambda t: "p/q/x.md" if t == "p/x.md" else None)
        self.assertEqual(rewritten, "Crlf line [a](q/x.md)\r\nand `code [b](x.md)` [c](y.md \"t\")\r\n")


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = init_workspace(Path(self._temp.name) / "kb")

    def kos(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return run_kos(self.root, *arguments)

    def ok(self, *arguments: str) -> dict:
        result = self.kos(*arguments, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_create_move_rename_and_lint(self) -> None:
        self.ok("project", "create", "acme", "--title", "Acme")
        self.ok("project", "create", "beta", "--title", "Beta")
        folder = self.ok("folder", "create", "acme", "notes", "--title", "Notes")
        self.assertEqual(folder["path"], "projects/acme/notes/README.md")
        self.assertEqual(folder["id"], "acme-notes")
        provenance = parse_document(self.root / folder["path"], check_filename=False).metadata["provenance"]
        self.assertEqual(provenance[0]["kind"], "cli-authored")
        self.ok("folder", "create", "acme", "notes/deep", "--title", "Deep", "--id", "deep-folder")
        write_page(self.root, "projects/acme/page.md", "page", "project:acme", "To [deep](notes/deep/README.md).\n")

        sha = content_sha256(self.root / "projects/acme/page.md")
        moved = self.ok("move", "page", "--expected-sha256", sha, "--folder", "notes")
        self.assertEqual(moved["path"], "projects/acme/notes/page.md")
        self.assertIn("(deep/README.md)", body_of(self.root / moved["path"]))

        renamed = self.ok("folder", "rename", "acme", "notes", "--name", "journal", "--title", "Journal")
        self.assertEqual(renamed["folder"], "journal")
        self.assertEqual(renamed["id"], "acme-notes")

        sha = content_sha256(self.root / "projects/acme/journal/page.md")
        refused = self.kos("move", "page", "--expected-sha256", sha, "--to-project", "beta")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("changes its scope", refused.stderr)
        crossed = self.ok("move", "page", "--expected-sha256", sha, "--to-project", "beta", "--allow-scope-change")
        self.assertTrue(crossed["scope_changed"])

        self.ok("folder", "move", "acme", "journal/deep", "--to-parent", ".")
        sha = content_sha256(self.root / "projects/beta/page.md")
        self.ok("rename", "page", "--title", "Front page", "--expected-sha256", sha)

        text = self.kos("folder", "create", "acme", "journal", "--title", "Again")
        self.assertEqual(text.returncode, 1)
        self.assertIn("already exists", text.stderr)

        lint = self.kos("lint")
        self.assertEqual(lint.returncode, 0, lint.stderr)
        plain = self.kos("rename", "page", "--title", "Home", "--expected-sha256",
                         content_sha256(self.root / "projects/beta/page.md"))
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertIn("Updated projects/beta/page.md", plain.stdout)


if __name__ == "__main__":
    unittest.main()
