"""Tests for the unmanaged repo-document tier: knowledge_os/reader/repodocs.py
and knowledge_os/reader/views/repodoc.py (``GET /f/{path:path}``).

Two layers, following the repository's existing convention (unittest, no
pytest, no fixtures, workspaces built on disk in a TemporaryDirectory):

- Unit-level tests exercise ``repodocs.py`` directly against a synthetic
  workspace built with ``reader_support.create_workspace`` plus plain files
  written straight onto disk (this tier has no frontmatter, so
  ``reader_support.write_record`` does not apply to it).
- Route-level tests start a real server (``reader_support.serve``, port
  8818, this unit's assigned port) and exercise ``GET /f/{path:path}``
  end to end: each of the eight real repository documents, path traversal
  and its encoded variants, a path outside the fixed tier, a missing file,
  non-UTF-8 content, and a file deleted while the server keeps running.
"""

from __future__ import annotations

import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from reader_support import REPOSITORY, create_workspace, serve

from knowledge_os.reader import repodocs, strings
from knowledge_os.workspace import Workspace

PORT = 8818


def _write(root: Path, rel_path: str, text: str) -> Path:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


# ---------------------------------------------------------------------------
# repodocs.REPO_DOCUMENT_PATHS — the fixed, closed list
# ---------------------------------------------------------------------------


class RepoDocumentPathsTests(unittest.TestCase):
    def test_fixed_list_matches_the_eight_documented_paths(self) -> None:
        self.assertEqual(
            set(repodocs.REPO_DOCUMENT_PATHS),
            {
                "SYSTEM.md",
                "README.md",
                "AGENTS.md",
                "docs/architecture.md",
                "docs/architecture-audit-v0.1.md",
                "docs/openknowledge-governance-compatibility.md",
                "docs/decisions/0001-stack-and-index.md",
                "docs/plans/reader-v1.md",
            },
        )
        self.assertEqual(len(repodocs.REPO_DOCUMENT_PATHS), 8)

    def test_the_eight_real_files_exist_in_this_repository(self) -> None:
        # Sanity check against the actual repository this test runs inside
        # (not the synthetic per-test workspace): confirms the fixed list
        # still matches reality rather than a path that moved or was renamed.
        for rel_path in repodocs.REPO_DOCUMENT_PATHS:
            self.assertTrue((REPOSITORY / rel_path).is_file(), rel_path)


# ---------------------------------------------------------------------------
# repodocs.is_skill_reference_path — task 8's second, pattern-based
# admission rule
# ---------------------------------------------------------------------------


class IsSkillReferencePathTests(unittest.TestCase):
    def test_admits_a_reference_file_under_a_skill(self) -> None:
        self.assertTrue(
            repodocs.is_skill_reference_path("skills/knowledge-os-documentation/references/init.md")
        )

    def test_refuses_the_skills_own_skill_md(self) -> None:
        # SKILL.md is a managed record, reached at /s/<name>, not this route.
        self.assertFalse(repodocs.is_skill_reference_path("skills/knowledge-os-documentation/SKILL.md"))

    def test_refuses_a_nested_subdirectory_under_references(self) -> None:
        self.assertFalse(
            repodocs.is_skill_reference_path("skills/knowledge-os-documentation/references/sub/init.md")
        )

    def test_refuses_a_non_markdown_file(self) -> None:
        self.assertFalse(repodocs.is_skill_reference_path("skills/knowledge-os-documentation/references/init.txt"))

    def test_refuses_a_bare_skills_directory_listing(self) -> None:
        self.assertFalse(repodocs.is_skill_reference_path("skills"))
        self.assertFalse(repodocs.is_skill_reference_path("skills/knowledge-os-documentation"))

    def test_refuses_traversal_shapes(self) -> None:
        self.assertFalse(repodocs.is_skill_reference_path("skills/../references/x.md"))
        self.assertFalse(repodocs.is_skill_reference_path("skills/foo/references/../../etc/passwd.md"))


# ---------------------------------------------------------------------------
# repodocs.read_entry / list_repo_documents
# ---------------------------------------------------------------------------


class ReadEntryTests(unittest.TestCase):
    def test_readable_file_uses_the_first_heading_as_title_not_the_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            _write(root, "SYSTEM.md", "# System Contract\n\nBody text.\n")
            workspace = Workspace(root)
            entry = repodocs.read_entry(workspace, "SYSTEM.md")
            self.assertTrue(entry.readable)
            self.assertEqual(entry.title, "System Contract")
            self.assertIsNone(entry.detail)
            self.assertEqual(entry.path, "SYSTEM.md")

    def test_missing_file_stays_listed_with_a_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            workspace = Workspace(root)
            entry = repodocs.read_entry(workspace, "README.md")
            self.assertFalse(entry.readable)
            self.assertEqual(entry.title, "README.md")
            self.assertIsNotNone(entry.detail)
            self.assertIn("no longer exists", entry.detail)

    def test_non_utf8_file_stays_listed_with_a_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            (root / "AGENTS.md").write_bytes(b"\xff\xfe# not utf-8\n")
            workspace = Workspace(root)
            entry = repodocs.read_entry(workspace, "AGENTS.md")
            self.assertFalse(entry.readable)
            self.assertIn("not valid UTF-8", entry.detail)

    def test_traversal_outside_the_workspace_is_refused_not_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            outside = Path(directory).parent / f"{root.name}-outside.md"
            outside.write_text("# Outside\n\nShould never be read.\n", encoding="utf-8")
            try:
                workspace = Workspace(root)
                entry = repodocs.read_entry(workspace, "../" + outside.name)
                self.assertFalse(entry.readable)
                self.assertIsNotNone(entry.detail)
            finally:
                outside.unlink(missing_ok=True)

    def test_symlink_is_refused_not_followed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            outside = root.parent / f"{root.name}-symlink-target.md"
            outside.write_text("# Secret\n\nOutside the workspace.\n", encoding="utf-8")
            link = root / "SYSTEM.md"
            try:
                try:
                    link.symlink_to(outside)
                except (OSError, NotImplementedError):
                    self.skipTest("symlinks are unavailable on this platform")
                workspace = Workspace(root)
                entry = repodocs.read_entry(workspace, "SYSTEM.md")
                self.assertFalse(entry.readable)
                self.assertIsNotNone(entry.detail)
            finally:
                outside.unlink(missing_ok=True)


class ListRepoDocumentsTests(unittest.TestCase):
    def test_every_fixed_path_is_listed_in_order_readable_or_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            # Only write some of the eight; the rest must still appear,
            # marked unreadable, never silently dropped from the listing.
            _write(root, "SYSTEM.md", "# System\n\nBody.\n")
            _write(root, "docs/plans/reader-v1.md", "# Plan\n\nBody.\n")
            workspace = Workspace(root)
            entries = repodocs.list_repo_documents(workspace)
            self.assertEqual(tuple(entry.path for entry in entries), repodocs.REPO_DOCUMENT_PATHS)
            by_path = {entry.path: entry for entry in entries}
            self.assertTrue(by_path["SYSTEM.md"].readable)
            self.assertTrue(by_path["docs/plans/reader-v1.md"].readable)
            self.assertFalse(by_path["README.md"].readable)
            self.assertFalse(by_path["docs/architecture.md"].readable)


# ---------------------------------------------------------------------------
# repodocs.render_document — heading/anchor pairing
# ---------------------------------------------------------------------------


class RenderDocumentTests(unittest.TestCase):
    def test_headings_get_matching_ids_in_document_order(self) -> None:
        text = "# Title\n\nIntro.\n\n## Section One\n\nBody.\n\n## Section Two\n\nMore body.\n"
        html, toc = repodocs.render_document(text)
        self.assertEqual([entry[1] for entry in toc], ["Title", "Section One", "Section Two"])
        for _level, _text, anchor in toc:
            self.assertIn(f'id="{anchor}"', html)

    def test_heading_inside_a_fenced_code_block_is_not_treated_as_a_heading(self) -> None:
        text = "# Real Title\n\n```\n# not a heading\n```\n"
        html, toc = repodocs.render_document(text)
        self.assertEqual([entry[1] for entry in toc], ["Real Title"])
        self.assertEqual(html.count("id=\""), 1)

    def test_document_without_headings_returns_empty_toc_and_plain_html(self) -> None:
        text = "Just a paragraph, no headings at all.\n"
        html, toc = repodocs.render_document(text)
        self.assertEqual(toc, ())
        self.assertNotIn("<h1", html)

    def test_real_architecture_audit_headings_all_get_ids(self) -> None:
        # The real regression case named in the unit brief: 563 lines, 52
        # headings across four levels — the actual table-of-contents test.
        text = (REPOSITORY / "docs" / "architecture-audit-v0.1.md").read_text(encoding="utf-8")
        html, toc = repodocs.render_document(text)
        self.assertEqual(len(toc), 52)
        for _level, _text, anchor in toc:
            self.assertIn(f'id="{anchor}"', html)


# ---------------------------------------------------------------------------
# GET /f/{path:path} — route-level, end to end
# ---------------------------------------------------------------------------


def _build_real_workspace(root: Path) -> None:
    """A synthetic workspace carrying real copies of the eight repo documents
    plus one ordinary managed record, so the route is exercised against the
    actual content named in the unit brief without depending on this test
    running from any particular checkout state of the real repository."""

    create_workspace(root)
    for rel_path in repodocs.REPO_DOCUMENT_PATHS:
        text = (REPOSITORY / rel_path).read_text(encoding="utf-8")
        _write(root, rel_path, text)


class RepodocRouteTests(unittest.TestCase):
    def test_start_page_serves(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_real_workspace(root)
            with serve(root, PORT) as base_url:
                with urllib.request.urlopen(f"{base_url}/") as response:
                    self.assertEqual(response.status, 200)

    def test_every_repo_document_renders_with_its_heading_as_title_and_the_unmanaged_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_real_workspace(root)
            with serve(root, PORT) as base_url:
                for rel_path in repodocs.REPO_DOCUMENT_PATHS:
                    text = (REPOSITORY / rel_path).read_text(encoding="utf-8")
                    title = next(line for line in text.splitlines() if line.startswith("# ")).removeprefix("# ").strip()
                    with self.subTest(rel_path=rel_path):
                        with urllib.request.urlopen(f"{base_url}/f/{rel_path}") as response:
                            self.assertEqual(response.status, 200)
                            body = response.read().decode("utf-8")
                        self.assertIn(title, body)
                        self.assertIn(strings.UNMANAGED_TIER_LABEL, body)

    def test_decision_numbered_note_is_not_shown_as_a_governed_decision(self) -> None:
        # docs/decisions/0001-stack-and-index.md is an ADR-numbered note, not
        # a record_kind: decision record; this unit's own page must not
        # invent decision-lifecycle vocabulary for it.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_real_workspace(root)
            with serve(root, PORT) as base_url:
                url = f"{base_url}/f/docs/decisions/0001-stack-and-index.md"
                with urllib.request.urlopen(url) as response:
                    body = response.read().decode("utf-8")
                # DECISION_STATUS phrasing (decision-lifecycle vocabulary a
                # governed decision record would carry); none of it belongs
                # on an unmanaged-tier page.
                for phrase in ("nobody has taken a position yet", "In force — accepted", "Replaced by"):
                    self.assertNotIn(phrase, body)

    def test_path_traversal_is_refused_cleanly_not_a_500(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_real_workspace(root)
            with serve(root, PORT) as base_url:
                attempts = [
                    "/f/../../etc/passwd",
                    "/f/..%2f..%2fetc%2fpasswd",
                    "/f/..%2F..%2Fetc%2Fpasswd",
                    "/f/%2e%2e/%2e%2e/etc/passwd",
                ]
                for suffix in attempts:
                    with self.subTest(suffix=suffix):
                        request = urllib.request.Request(base_url + suffix)
                        try:
                            response = urllib.request.urlopen(request)
                        except urllib.error.HTTPError as error:
                            response = error
                        self.assertLess(response.status, 500, f"{suffix} -> {response.status}")
                        self.assertNotEqual(response.status, 200, f"{suffix} should be refused, not served")
                        body = response.read().decode("utf-8")
                        self.assertNotIn("Traceback", body)

    def test_absolute_path_is_refused_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_real_workspace(root)
            with serve(root, PORT) as base_url:
                request = urllib.request.Request(f"{base_url}/f//etc/passwd")
                try:
                    response = urllib.request.urlopen(request)
                except urllib.error.HTTPError as error:
                    response = error
                self.assertLess(response.status, 500)
                self.assertNotEqual(response.status, 200)

    def test_path_outside_the_fixed_tier_is_refused_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_real_workspace(root)
            # A real, readable, safely-contained markdown file that simply
            # is not one of the eight tier entries (e.g. a managed record) —
            # must still be refused, since /f/ is not a general file browser.
            _write(root, "knowledge/not-a-repo-doc.md", "---\nid: x\n---\n\nBody.\n")
            with serve(root, PORT) as base_url:
                request = urllib.request.Request(f"{base_url}/f/knowledge/not-a-repo-doc.md")
                try:
                    response = urllib.request.urlopen(request)
                except urllib.error.HTTPError as error:
                    response = error
                self.assertEqual(response.status, 404)
                body = response.read().decode("utf-8")
                self.assertNotIn("Traceback", body)

    def test_skill_reference_file_is_served_but_another_skills_path_is_refused(self) -> None:
        """Task 8: the allowlist grows a second, pattern-based rule for a
        skill's own references/*.md files (linked from the skill view),
        without turning /f/ into a general skills/ browser."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_real_workspace(root)
            _write(
                root,
                "skills/demo-skill/SKILL.md",
                "---\nname: demo-skill\ndescription: d\n---\n\nUses [x](references/x.md).\n",
            )
            _write(root, "skills/demo-skill/references/x.md", "# Reference\n\nSupporting detail.\n")

            with serve(root, PORT) as base_url:
                with urllib.request.urlopen(f"{base_url}/f/skills/demo-skill/references/x.md") as response:
                    self.assertEqual(response.status, 200)
                    body = response.read().decode("utf-8")
                self.assertIn("Reference", body)
                self.assertIn("Supporting detail.", body)
                self.assertIn(strings.UNMANAGED_TIER_LABEL, body)

                # A different path under the same skills/ tree -- the
                # skill's own SKILL.md -- is not part of this tier at all
                # (it is a managed record, reached at /s/demo-skill).
                request = urllib.request.Request(f"{base_url}/f/skills/demo-skill/SKILL.md")
                try:
                    response = urllib.request.urlopen(request)
                except urllib.error.HTTPError as error:
                    response = error
                self.assertEqual(response.status, 404)
                self.assertNotIn("Traceback", response.read().decode("utf-8"))

    def test_nonexistent_path_is_refused_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_real_workspace(root)
            with serve(root, PORT) as base_url:
                request = urllib.request.Request(f"{base_url}/f/docs/does-not-exist.md")
                try:
                    response = urllib.request.urlopen(request)
                except urllib.error.HTTPError as error:
                    response = error
                self.assertEqual(response.status, 404)

    def test_non_utf8_content_is_refused_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_real_workspace(root)
            (root / "AGENTS.md").write_bytes(b"\xff\xfeNot UTF-8 at all\n")
            with serve(root, PORT) as base_url:
                request = urllib.request.Request(f"{base_url}/f/AGENTS.md")
                try:
                    response = urllib.request.urlopen(request)
                except urllib.error.HTTPError as error:
                    response = error
                self.assertLess(response.status, 500)
                self.assertNotEqual(response.status, 200)
                body = response.read().decode("utf-8")
                self.assertIn(strings.UNMANAGED_TIER_LABEL, body)

    def test_file_deleted_while_server_runs_is_refused_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_real_workspace(root)
            with serve(root, PORT) as base_url:
                url = f"{base_url}/f/SYSTEM.md"
                with urllib.request.urlopen(url) as response:
                    self.assertEqual(response.status, 200)
                (root / "SYSTEM.md").unlink()
                request = urllib.request.Request(url)
                try:
                    response = urllib.request.urlopen(request)
                except urllib.error.HTTPError as error:
                    response = error
                self.assertLess(response.status, 500)
                self.assertNotEqual(response.status, 200)
                body = response.read().decode("utf-8")
                self.assertNotIn("Traceback", body)

    def test_symlinked_repo_document_is_refused_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_real_workspace(root)
            target = root.parent / f"{root.name}-symlink-target.md"
            target.write_text("# Secret\n\nOutside the workspace.\n", encoding="utf-8")
            readme = root / "README.md"
            try:
                readme.unlink()
                try:
                    readme.symlink_to(target)
                except (OSError, NotImplementedError):
                    self.skipTest("symlinks are unavailable on this platform")
                with serve(root, PORT) as base_url:
                    request = urllib.request.Request(f"{base_url}/f/README.md")
                    try:
                        response = urllib.request.urlopen(request)
                    except urllib.error.HTTPError as error:
                        response = error
                    self.assertLess(response.status, 500)
                    self.assertNotEqual(response.status, 200)
            finally:
                target.unlink(missing_ok=True)

    def test_workspace_is_byte_identical_after_serving(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_real_workspace(root)
            before = {
                path: (path.stat().st_mtime_ns, path.read_bytes())
                for path in root.rglob("*")
                if path.is_file()
            }
            with serve(root, PORT) as base_url:
                for rel_path in repodocs.REPO_DOCUMENT_PATHS:
                    urllib.request.urlopen(f"{base_url}/f/{rel_path}").close()
            after = {
                path: (path.stat().st_mtime_ns, path.read_bytes())
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
