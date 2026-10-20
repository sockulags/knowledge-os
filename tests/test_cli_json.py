"""``--json`` on the commands agents use most, the help texts that describe
them, and the ``kos mcp`` help that lists the agent tools."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from test_discovery import create_workspace, discovery_metadata, write_input

from knowledge_os.agent_access.tools import TOOLS
from knowledge_os.cli import build_parser, main as kos_main, mcp_tool_names


def _subparser(parser, *names: str):  # type: ignore[no-untyped-def]
    for name in names:
        action = next(item for item in parser._actions if item.__class__.__name__ == "_SubParsersAction")
        parser = action.choices[name]
    return parser


class CliJsonTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name) / "kb"
        self.root.mkdir()
        create_workspace(self.root)
        self.assertEqual(self.kos("index")[0], 0)

    def kos(self, *arguments: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = kos_main([*arguments, "--root", str(self.root)])
        return code, out.getvalue(), err.getvalue()

    def kos_json(self, *arguments: str) -> dict:
        code, out, err = self.kos(*arguments, "--json")
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertEqual(len(lines), 1, out)
        return json.loads(lines[0])

    def test_index_lint_ingest_and_inspect(self) -> None:
        self.assertEqual(self.kos_json("index"), {"index_count": 1})
        self.assertEqual(self.kos_json("lint"), {"ok": True, "record_count": 1, "issues": []})

        source = self.root / "inbox" / "note.md"
        source.write_text("# A note\n\nAbout xylophones.\n", encoding="utf-8")
        ingested = self.kos_json("ingest", str(source))
        self.assertTrue(ingested["created"])
        self.assertEqual(ingested["index_count"], 2)
        again = self.kos_json("ingest", str(source))
        self.assertEqual((again["id"], again["created"]), (ingested["id"], False))

        inspected = self.kos_json("inspect", "demo")
        self.assertEqual(inspected["id"], "demo")
        page = self.root / inspected["path"]
        self.assertEqual(inspected["content_sha256"], hashlib.sha256(page.read_bytes()).hexdigest())
        self.assertNotIn("content", inspected)
        self.assertIn("content", self.kos_json("inspect", "demo", "--full"))

    def test_lint_json_reports_issues_and_fails(self) -> None:
        (self.root / "knowledge" / "broken.md").write_text("no frontmatter\n", encoding="utf-8")
        code, out, err = self.kos("lint", "--json")
        self.assertEqual(code, 1, err)
        result = json.loads(out)
        self.assertFalse(result["ok"])
        self.assertTrue(any("broken.md" in issue["path"] for issue in result["issues"]))

    def test_search_without_hits_says_so(self) -> None:
        code, out, err = self.kos("search", "nothingmatchesthis")
        self.assertEqual((code, out), (0, ""))
        self.assertIn("No results.", err)
        code, out, err = self.kos("search", "nothingmatchesthis", "--json")
        self.assertEqual((code, json.loads(out)), (0, []))
        self.assertNotIn("No results.", err)

    def test_update_reports_the_index_count(self) -> None:
        page = self.root / "projects" / "demo" / "README.md"
        sha = hashlib.sha256(page.read_bytes()).hexdigest()
        replacement = Path(self._temp.name) / "replacement.md"
        replacement.write_text(page.read_text(encoding="utf-8") + "\nMore.\n", encoding="utf-8")
        result = self.kos_json(
            "update", str(replacement), "--expected-sha256", sha, "--confirm-non-material", "--change-reference", "t"
        )
        self.assertEqual((result["id"], result["index_count"]), ("demo", 1))

    def test_discovery_commands(self) -> None:
        for record_id in ("kept-signal", "dropped-signal", "promotable-signal"):
            path = write_input(
                self.root, discovery_metadata(record_id), f"A unique {record_id} body.\n", name=f"{record_id}.md"
            )
            added = self.kos_json("discovery", "add", str(path))
            self.assertEqual((added["id"], added["created"]), (record_id, True))

        inspected = self.kos_json("discovery", "inspect", "kept-signal")
        self.assertEqual((inspected["id"], inspected["status"]), ("kept-signal", "proposed"))

        review = self.kos_json("discovery", "review", "kept-signal")
        self.assertEqual(review["id"], "kept-signal")
        self.assertIn("# Discovery review packet", review["packet"])
        self.assertIsInstance(review["related"], list)

        retained = self.kos_json("discovery", "retain", "kept-signal", "--reviewer", "human")
        self.assertEqual(retained["status"], "retained")
        self.assertIn("index_count", retained)
        rejected = self.kos_json("discovery", "reject", "dropped-signal", "--reason", "Not reproducible.")
        self.assertEqual(rejected["status"], "rejected")

        promoted = self.kos_json(
            "discovery",
            "promote",
            "promotable-signal",
            "--target-id",
            "promoted-fact",
            "--title",
            "Promoted fact",
            "--scope",
            "project:demo",
        )
        self.assertEqual(
            (promoted["id"], promoted["status"], promoted["target_id"]), ("promotable-signal", "promoted", "promoted-fact")
        )
        self.assertEqual(promoted["acknowledged_related"], [])

    def test_discovery_reject_requires_a_reason(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            build_parser().parse_args(["discovery", "reject", "some-id"])
        self.assertIn("--reason", stderr.getvalue())


class CliHelpTests(unittest.TestCase):
    def test_every_command_agents_use_takes_json(self) -> None:
        parser = build_parser()
        for path in (
            ("ingest",),
            ("index",),
            ("lint",),
            ("search",),
            ("inspect",),
            ("capture",),
            ("update",),
            *(("discovery", name) for name in ("add", "inspect", "review", "retain", "reject", "promote")),
            *(("proposal", name) for name in ("list", "show", "accept", "discard")),
        ):
            with self.subTest(command=" ".join(path)):
                options = {option for action in _subparser(parser, *path)._actions for option in action.option_strings}
                self.assertIn("--json", options)

    def test_decision_help_names_both_actions(self) -> None:
        commands = next(item for item in build_parser()._actions if item.__class__.__name__ == "_SubParsersAction")
        help_text = next(action.help for action in commands._choices_actions if action.dest == "decision")
        self.assertIn("accept", help_text)
        self.assertIn("withdraw", help_text)

    def test_mcp_help_lists_exactly_the_served_tools(self) -> None:
        names = [tool.name for tool in TOOLS]
        self.assertEqual(mcp_tool_names(), names)
        description = _subparser(build_parser(), "mcp").description
        listed = description.split("(", 1)[1].split(")", 1)[0].split(", ")
        self.assertEqual(listed, names)

    def test_architecture_names_the_same_tools(self) -> None:
        text = (Path(__file__).resolve().parents[1] / "docs" / "architecture.md").read_text(encoding="utf-8")
        section = " ".join(text.split("## Agent access over MCP", 1)[1].split("\n\n", 2)[1].split())
        for name in mcp_tool_names():
            self.assertIn(f"`{name}`", section)


if __name__ == "__main__":
    unittest.main()
