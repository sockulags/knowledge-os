"""Tests for the skill view, ``GET /s/{skill_name}``.

A skill is not a record: the skill frontmatter contract (``knowledge_os/
skills.py``) allows exactly ``name``, ``description``, ``tags``, has no
lifecycle and no supersession, and is absent from the search index. These
tests check that the view never borrows record vocabulary for a skill, that
the two untagged skills in the real workspace render cleanly, that
``knowledge-os-documentation``'s ``references/`` files surface as secondary
material, and that an unknown or broken skill name renders a clean page
rather than a 500 or a silent gap.

Follows the repository's existing test convention (see
tests/test_reader_library.py and tests/test_vertical_slice.py): unittest
only, no pytest, no fixtures, workspaces built on disk in a
TemporaryDirectory. HTTP-level checks go through ``reader_support.serve``
(a real ``kos-read`` subprocess, port 8819 as assigned); a few fast,
precise checks call the view module's own helpers directly against a
``library.Library`` built in-process, matching test_reader_library.py's
style.
"""

from __future__ import annotations

import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from reader_support import REPOSITORY, create_workspace, serve

from knowledge_os.reader import library
from knowledge_os.reader.views import skill as skill_view
from knowledge_os.workspace import Workspace

PORT = 8819


def _write_skill(
    root: Path,
    directory: str,
    *,
    name: str | None = None,
    description: str = "A demo skill for the reader test suite.",
    tags: list[str] | None = None,
    body: str = "# Demo skill\n\nDo the demo thing.\n",
) -> Path:
    """Write one skill under ``skills/<directory>/SKILL.md``.

    Mirrors the shape ``knowledge_os/skills.py`` requires (frontmatter with
    only ``name``/``description``/``tags``, directory name matching
    ``name``); local to this test file since ``reader_support.py`` is
    shared scaffolding this unit does not own.
    """

    skill_root = root / "skills" / directory
    skill_root.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"name: {name or directory}", f"description: {description}"]
    if tags:
        lines.append("tags:")
        lines.extend(f"  - {tag}" for tag in tags)
    lines.extend(["---", "", body])
    (skill_root / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")
    return skill_root


class HelperTests(unittest.TestCase):
    """Fast, in-process checks of the view's own helper functions."""

    def test_find_skill_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            _write_skill(root, "tagged-skill", tags=["alpha", "beta"])
            lib = library.load_library(Workspace(root))

            found = skill_view._find_skill(lib, "tagged-skill")
            self.assertIsNotNone(found)
            self.assertEqual(found.tags, ("alpha", "beta"))
            self.assertIsNone(skill_view._find_skill(lib, "no-such-skill"))

    def test_untagged_skill_has_empty_tags_not_a_crash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            _write_skill(root, "untagged-skill")
            lib = library.load_library(Workspace(root))

            found = skill_view._find_skill(lib, "untagged-skill")
            self.assertEqual(found.tags, ())

    def test_broken_skill_issue_is_found_by_directory_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            (root / "skills" / "broken-skill").mkdir(parents=True)
            (root / "skills" / "broken-skill" / "SKILL.md").write_text(
                "no frontmatter here\n", encoding="utf-8"
            )
            lib = library.load_library(Workspace(root))

            self.assertIsNone(skill_view._find_skill(lib, "broken-skill"))
            message = skill_view._find_broken_issue(lib, "broken-skill")
            self.assertIsNotNone(message)
            self.assertIn("frontmatter", message)
            self.assertIsNone(skill_view._find_broken_issue(lib, "never-existed"))

    def test_references_are_discovered_from_body_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            skill_root = _write_skill(
                root,
                "documented-skill",
                body=(
                    "# Documented skill\n\n"
                    "See [references/guide.md](references/guide.md) for details.\n"
                    "Also see [references/missing.md](references/missing.md).\n"
                ),
            )
            (skill_root / "references").mkdir()
            (skill_root / "references" / "guide.md").write_text(
                "# The guide\n\nBody text.\n", encoding="utf-8"
            )
            # references/missing.md is deliberately never created.

            lib = library.load_library(Workspace(root))
            found = skill_view._find_skill(lib, "documented-skill")
            workspace = Workspace(root)
            references = skill_view._references(workspace, found)

            by_path = {entry["path"]: entry for entry in references}
            self.assertEqual(len(references), 2)
            guide = by_path["skills/documented-skill/references/guide.md"]
            self.assertTrue(guide["readable"])
            self.assertEqual(guide["title"], "The guide")
            missing = by_path["skills/documented-skill/references/missing.md"]
            self.assertFalse(missing["readable"])
            self.assertIsNotNone(missing["detail"])

    def test_skill_with_no_reference_links_has_no_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            _write_skill(root, "plain-skill")
            lib = library.load_library(Workspace(root))
            found = skill_view._find_skill(lib, "plain-skill")
            workspace = Workspace(root)
            self.assertEqual(skill_view._references(workspace, found), ())


class SkillViewHttpTests(unittest.TestCase):
    """Black-box HTTP checks through a real ``kos-read`` server."""

    def _get(self, base_url: str, path: str) -> tuple[int, str]:
        request = urllib.request.Request(f"{base_url}{path}")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # still a clean response, just non-200
            return exc.code, exc.read().decode("utf-8")

    def test_tagged_and_untagged_skills_and_missing_and_broken_all_render_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            _write_skill(
                root,
                "tagged-skill",
                description="Has tags.",
                tags=["ingest", "local-file"],
                body="# Tagged skill\n\nDoes tagged things.\n",
            )
            _write_skill(root, "untagged-skill", description="Has no tags at all.")
            (root / "skills" / "broken-skill").mkdir(parents=True)
            (root / "skills" / "broken-skill" / "SKILL.md").write_text(
                "---\nname: broken-skill\ndescription: d\nnope: not-allowed\n---\n\nBody.\n",
                encoding="utf-8",
            )

            with serve(root, PORT) as base_url:
                status, body = self._get(base_url, "/s/tagged-skill")
                self.assertEqual(status, 200)
                self.assertIn("Tagged skill", body)
                self.assertIn("Has tags.", body)
                self.assertIn("ingest", body)
                self.assertIn("Operational guidance", body)
                # Record-only vocabulary must never appear on a skill page.
                self.assertNotIn("Current", body)

                status, body = self._get(base_url, "/s/untagged-skill")
                self.assertEqual(status, 200)
                self.assertIn("Has no tags at all.", body)
                self.assertIn("No tags recorded.", body)

                status, body = self._get(base_url, "/s/does-not-exist")
                self.assertEqual(status, 404)
                self.assertIn("No such skill", body)

                status, body = self._get(base_url, "/s/broken-skill")
                self.assertEqual(status, 200)
                self.assertIn("This skill could not be read", body)
                self.assertIn("unknown frontmatter field", body)

    def test_documentation_skill_surfaces_references_as_secondary_material(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            skill_root = _write_skill(
                root,
                "documented-skill",
                body=(
                    "# Documented skill\n\n"
                    "Use [references/init.md](references/init.md) for setup.\n"
                ),
            )
            (skill_root / "references").mkdir()
            (skill_root / "references" / "init.md").write_text(
                "# Setup\n\nDo the setup.\n", encoding="utf-8"
            )

            with serve(root, PORT) as base_url:
                status, body = self._get(base_url, "/s/documented-skill")
                self.assertEqual(status, 200)
                self.assertIn("Supporting references", body)
                self.assertIn("Lives in the repository, not in the library", body)
                self.assertIn("/f/skills/documented-skill/references/init.md", body)
                self.assertIn("Setup", body)


class RealWorkspaceSkillViewTests(unittest.TestCase):
    """The four real skills in this repository, served from the repo root."""

    def test_all_four_real_skills_render_and_documentation_lists_its_references(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            for name in (
                "ingest-source",
                "knowledge-os-capture",
                "knowledge-os-documentation",
                "review-discovery",
            ):
                request = urllib.request.Request(f"{base_url}/s/{name}")
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    body = response.read().decode("utf-8")
                self.assertIn(name, body)

            request = urllib.request.Request(f"{base_url}/s/knowledge-os-documentation")
            with urllib.request.urlopen(request, timeout=5) as response:
                body = response.read().decode("utf-8")
            self.assertIn("/f/skills/knowledge-os-documentation/references/init.md", body)
            self.assertIn(
                "/f/skills/knowledge-os-documentation/references/documentation-workflow.md", body
            )

            request = urllib.request.Request(f"{base_url}/s/no-such-skill-anywhere")
            try:
                urllib.request.urlopen(request, timeout=5)
                self.fail("expected HTTPError for an unknown skill name")
            except urllib.error.HTTPError as exc:
                self.assertEqual(exc.code, 404)
                body = exc.read().decode("utf-8")
            self.assertIn("No such skill", body)


if __name__ == "__main__":
    unittest.main()
