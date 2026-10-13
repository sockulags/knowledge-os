"""Page templates (issue #85): the built-in ones, the knowledge base's own
``templates/`` files, and ``GET /api/templates``."""

from __future__ import annotations

import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from reader_support import create_workspace, serve

from knowledge_os.init_workspace import init_workspace
from knowledge_os.templates import BUILT_IN, built_in_files, fill, list_templates, parse_template
from knowledge_os.workspace import Workspace

PORT = 8881


def _names(workspace: Workspace) -> list[str]:
    return [template.name for template in list_templates(workspace)]


class TemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        create_workspace(self.root)
        self.workspace = Workspace(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, name: str, text: str) -> None:
        (self.root / "templates").mkdir(exist_ok=True)
        (self.root / "templates" / name).write_text(text, encoding="utf-8")

    def test_without_a_templates_folder_the_built_in_ones_are_offered(self) -> None:
        self.assertEqual(_names(self.workspace), ["blank", "meeting-notes", "how-to", "decision", "requirement", "plan"])
        decision = list_templates(self.workspace)[3]
        self.assertEqual(decision.kind, "decision")
        for section in ("## Context", "## Decision", "## Alternatives considered", "## Consequences"):
            self.assertIn(section, decision.body)

    def test_a_file_replaces_a_built_in_template_and_others_are_added(self) -> None:
        self.write("meeting-notes.md", "---\ntitle: Möte\n---\n## Beslut\n")
        self.write("retro.md", "## Went well\n")
        self.write("README.md", "# Templates\n")
        self.write("notes.txt", "not a template")

        templates = {template.name: template for template in list_templates(self.workspace)}
        self.assertEqual(_names(self.workspace), ["blank", "meeting-notes", "how-to", "decision", "requirement", "plan", "retro"])
        self.assertEqual(templates["meeting-notes"].title, "Möte")
        self.assertEqual(templates["meeting-notes"].source, "workspace")
        self.assertEqual(templates["meeting-notes"].path, "templates/meeting-notes.md")
        self.assertEqual(templates["meeting-notes"].body, "## Beslut\n")
        self.assertEqual(templates["retro"].title, "Retro")
        self.assertEqual(templates["retro"].kind, "note")
        self.assertEqual(templates["how-to"].source, "built-in")

    def test_a_broken_file_is_listed_with_the_reason(self) -> None:
        self.write("bad-kind.md", "---\nkind: essay\n---\nText\n")
        self.write("extra.md", "---\nstatus: draft\n---\nText\n")
        self.write("Bad Name.md", "Text\n")
        self.write("unclosed.md", "---\ntitle: x\nText\n")

        errors = {template.name: template.error for template in list_templates(self.workspace)}
        self.assertIn("kind must be", errors["bad-kind"])
        self.assertIn("unknown field", errors["extra"])
        self.assertIn("file name", errors["Bad Name"])
        self.assertIn("not closed", errors["unclosed"])
        self.assertIsNone(errors["blank"])

    def test_date_placeholder_is_filled(self) -> None:
        self.assertEqual(fill("On {{date}} and {{ date }}.", "2026-09-27"), "On 2026-09-27 and 2026-09-27.")

    def test_built_in_files_round_trip(self) -> None:
        # What kos init writes reads back as the same template.
        for template in BUILT_IN:
            if template.name == "blank":
                continue
            parsed = parse_template(template.name, f"templates/{template.name}.md", built_in_files()[f"{template.name}.md"])
            self.assertIsNone(parsed.error)
            self.assertEqual((parsed.title, parsed.description, parsed.kind, parsed.body),
                             (template.title, template.description, template.kind, template.body))

    def test_kos_init_writes_the_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = init_workspace(Path(tmp) / "kb")
            self.assertEqual(
                sorted(path.name for path in (root / "templates").iterdir()),
                ["README.md", "decision.md", "how-to.md", "meeting-notes.md", "plan.md", "requirement.md"],
            )
            sources = {template.name: template.source for template in list_templates(Workspace(root))}
            self.assertEqual(sources, {"blank": "built-in", "meeting-notes": "workspace", "how-to": "workspace", "decision": "workspace",
                                       "requirement": "workspace", "plan": "workspace"})


class TemplatesApiTests(unittest.TestCase):
    def test_lists_templates_with_the_date_filled_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_workspace(root)
            (root / "templates").mkdir()
            (root / "templates" / "daily.md").write_text("---\ndescription: One day\n---\nLog for {{date}}\n", encoding="utf-8")
            with serve(root, PORT) as base_url:
                with urllib.request.urlopen(f"{base_url}/api/templates", timeout=10) as response:
                    payload = json.loads(response.read())

        daily = next(item for item in payload["templates"] if item["name"] == "daily")
        self.assertEqual(daily["description"], "One day")
        self.assertRegex(daily["body"], r"^Log for \d{4}-\d{2}-\d{2}\n$")
        self.assertEqual(daily["source"], "workspace")
        self.assertEqual(payload["templates"][0]["name"], "blank")
        self.assertIn("templates/", payload["language"]["hint"])


if __name__ == "__main__":
    unittest.main()
