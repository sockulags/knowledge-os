"""``kos proposal list|show|accept|discard``: handling proposed changes from
the command line with the same functions the app's Decide uses."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from test_review import AGENT, PROVENANCE, _page

from knowledge_os.cli import main as kos_main
from knowledge_os.init_workspace import init_workspace
from knowledge_os.review import list_proposals, propose
from knowledge_os.structure import create_folder, create_project
from knowledge_os.workspace import Workspace


class CliProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = init_workspace(Path(self._temp.name) / "kb")
        self.workspace = Workspace(self.root)
        create_project(self.workspace, "acme", title="Acme", provenance=PROVENANCE)
        create_folder(self.workspace, "acme", "notes", title="Notes", provenance=PROVENANCE)

    def kos(self, *arguments: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = kos_main([*arguments, "--root", str(self.root)])
        return code, out.getvalue(), err.getvalue()

    def kos_json(self, *arguments: str) -> dict:
        code, out, err = self.kos(*arguments, "--json")
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def create_proposal(self, record_id: str = "plan"):  # type: ignore[no-untyped-def]
        return propose(
            self.workspace,
            action="create",
            text=_page(record_id),
            proposed_by=AGENT,
            rule="agents in project acme",
            project_path=f"notes/{record_id}.md",
        )

    def test_list_and_show(self) -> None:
        self.assertEqual(self.kos_json("proposal", "list"), {"proposals": [], "broken": []})
        code, out, _err = self.kos("proposal", "list")
        self.assertEqual((code, out.strip()), (0, "No proposed changes."))

        proposal = self.create_proposal()
        listed = self.kos_json("proposal", "list")["proposals"]
        self.assertEqual([item["id"] for item in listed], [proposal.id])
        self.assertEqual(listed[0]["sha256"], proposal.sha256)
        self.assertEqual((listed[0]["action"], listed[0]["record_id"]), ("create", "plan"))

        shown = self.kos_json("proposal", "show", proposal.id)
        self.assertEqual(shown["sha256"], proposal.sha256)
        self.assertIn("id: plan", shown["markdown"])
        code, out, _err = self.kos("proposal", "show", proposal.id)
        self.assertEqual(code, 0)
        self.assertIn(f"SHA-256: {proposal.sha256}", out)

        code, _out, err = self.kos("proposal", "show", "no-such-proposal")
        self.assertEqual(code, 1)
        self.assertIn("not found", err)

    def test_accept_writes_the_page_and_removes_the_proposal(self) -> None:
        proposal = self.create_proposal()
        result = self.kos_json("proposal", "accept", proposal.id, "--expected-sha256", proposal.sha256)
        self.assertEqual((result["proposal"], result["id"]), (proposal.id, "plan"))
        self.assertEqual(result["path"], "projects/acme/notes/plan.md")
        self.assertIn("index_count", result)
        page = self.root / result["path"]
        self.assertEqual(result["sha256"], hashlib.sha256(page.read_bytes()).hexdigest())
        self.assertEqual(list_proposals(self.workspace), ([], []))

    def test_discard_drops_the_proposal(self) -> None:
        proposal = self.create_proposal()
        code, out, err = self.kos("proposal", "discard", proposal.id, "--expected-sha256", proposal.sha256)
        self.assertEqual(code, 0, err)
        self.assertIn("Discarded", out)
        self.assertFalse((self.root / "projects/acme/notes/plan.md").exists())
        self.assertEqual(list_proposals(self.workspace), ([], []))

    def test_accept_and_discard_require_the_current_sha256(self) -> None:
        proposal = self.create_proposal()
        for action in ("accept", "discard"):
            with self.subTest(action=action):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
                    kos_main(["proposal", action, proposal.id, "--root", str(self.root)])
                self.assertIn("--expected-sha256", stderr.getvalue())

                code, _out, err = self.kos("proposal", action, proposal.id, "--expected-sha256", "0" * 64)
                self.assertEqual(code, 1)
                self.assertIn("conflict", err)
        self.assertEqual(len(list_proposals(self.workspace)[0]), 1)
        self.assertFalse((self.root / "projects/acme/notes/plan.md").exists())

    def test_an_edit_against_a_changed_page_can_only_be_discarded(self) -> None:
        relative = "projects/acme/notes/README.md"
        page = self.root / relative
        base = hashlib.sha256(page.read_bytes()).hexdigest()
        current = page.read_text(encoding="utf-8")
        first = propose(
            self.workspace,
            action="edit",
            text=current.replace("# Notes", "# Notes\n\nMore."),
            proposed_by=AGENT,
            rule="r",
            base_sha256=base,
        )
        second = propose(
            self.workspace, action="edit", text=current + "Other.\n", proposed_by=AGENT, rule="r", base_sha256=base
        )
        self.kos_json("proposal", "accept", first.id, "--expected-sha256", first.sha256)

        code, _out, err = self.kos("proposal", "accept", second.id, "--expected-sha256", second.sha256)
        self.assertEqual(code, 1)
        self.assertIn("can only be discarded", err)
        self.kos_json("proposal", "discard", second.id, "--expected-sha256", second.sha256)
        self.assertEqual(list_proposals(self.workspace), ([], []))


if __name__ == "__main__":
    unittest.main()
