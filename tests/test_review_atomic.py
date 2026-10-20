"""Accepting and discarding one proposed change is a single locked step: a
concurrent accept and discard of the same change yield exactly one outcome."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from knowledge_os import review
from knowledge_os.init_workspace import init_workspace
from knowledge_os.model import render_document
from knowledge_os.review import ProposalNotFoundError, accept_proposal, discard_proposal, list_proposals, propose
from knowledge_os.structure import create_project
from knowledge_os.workspace import Workspace

PROVENANCE = [{"kind": "fixture", "reference": "test:review-atomic"}]
AGENT = {"kind": "agent-authored", "reference": "agent:claude-code:repo"}


def _page(record_id: str) -> str:
    metadata: dict[str, object] = {
        "id": record_id,
        "title": record_id.replace("-", " ").capitalize(),
        "type": "project",
        "status": "active",
        "scope": "project:acme",
        "created": "2026-09-27",
        "updated": "2026-09-27",
        "provenance": [AGENT],
    }
    return render_document(metadata, "Text.\n").decode("utf-8")


class AcceptDiscardRaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = init_workspace(Path(self._temp.name) / "kb")
        self.workspace = Workspace(self.root)
        create_project(self.workspace, "acme", title="Acme", provenance=PROVENANCE)

    def _propose(self, record_id: str):
        return propose(
            self.workspace,
            action="create",
            text=_page(record_id),
            proposed_by=AGENT,
            rule="r",
            project_path=f"{record_id}.md",
        )

    def _page_exists(self, record_id: str) -> bool:
        return (self.root / f"projects/acme/{record_id}.md").exists()

    def _pending(self) -> list[str]:
        return [item.id for item in list_proposals(self.workspace)[0]]

    def test_a_discard_during_an_accept_waits_and_finds_nothing(self) -> None:
        proposal = self._propose("plan")
        discarded = threading.Event()
        errors: list[BaseException] = []
        discarder: list[threading.Thread] = []

        def discard() -> None:
            try:
                discard_proposal(self.workspace, proposal.id, expected_sha256=proposal.sha256)
            except BaseException as exc:  # noqa: BLE001 - reported to the test thread
                errors.append(exc)
            finally:
                discarded.set()

        real_check = review._check_unchanged

        def check_then_race(*args, **kwargs):
            real_check(*args, **kwargs)
            if threading.current_thread() is threading.main_thread() and not discarder:
                # The accept has loaded and checked the proposal; a discard
                # now must wait for the whole accept instead of slipping in.
                thread = threading.Thread(target=discard)
                thread.start()
                discarder.append(thread)
                self.assertFalse(discarded.wait(0.5), "the discard ran between the accept's check and its write")

        with mock.patch.object(review, "_check_unchanged", check_then_race):
            accept_proposal(self.workspace, proposal.id, expected_sha256=proposal.sha256)
        discarder[0].join(30)

        self.assertTrue(self._page_exists("plan"))
        self.assertEqual(self._pending(), [])
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ProposalNotFoundError)

    def test_concurrent_accept_and_discard_yield_one_outcome(self) -> None:
        for number in range(12):
            record_id = f"race-{number}"
            proposal = self._propose(record_id)
            start = threading.Barrier(2)
            outcomes: dict[str, object] = {}

            def run(name: str, action) -> None:
                start.wait()
                try:
                    action(self.workspace, proposal.id, expected_sha256=proposal.sha256)
                    outcomes[name] = "done"
                except ProposalNotFoundError as exc:
                    outcomes[name] = exc

            threads = [
                threading.Thread(target=run, args=("accept", accept_proposal)),
                threading.Thread(target=run, args=("discard", discard_proposal)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(60)

            with self.subTest(number=number, outcomes=outcomes):
                self.assertEqual(sorted(outcomes), ["accept", "discard"])
                self.assertEqual([outcomes["accept"], outcomes["discard"]].count("done"), 1)
                self.assertEqual(self._page_exists(record_id), outcomes["accept"] == "done")
                self.assertNotIn(proposal.id, self._pending())


if __name__ == "__main__":
    unittest.main()
