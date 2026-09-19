"""End-to-end tests for ``GET /api/projects/{project_id}``: the real
``kos-read`` server against the real ``knowledge-os`` corpus (acceptance
criterion 3) and a small synthetic workspace for the 404 and empty-group
cases.
"""

from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from reader_support import REPOSITORY, create_workspace, serve, write_record

PORT = 8832


def _get(base_url: str, path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(base_url + path, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


class RealCorpusProjectTests(unittest.TestCase):
    """Acceptance criterion 3: the knowledge-os project groups its four
    decisions as in force now / waiting on you / replaced."""

    def test_decisions_group_as_the_plan_describes(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            status, data = _get(base_url, "/api/projects/knowledge-os")
            self.assertEqual(status, 200)

            governing_ids = {entry["id"] for entry in data["groups"]["governing"]["records"]}
            proposed_ids = {entry["id"] for entry in data["groups"]["proposed"]["records"]}
            historical_ids = {entry["id"] for entry in data["groups"]["historical"]["records"]}

            self.assertEqual(
                governing_ids,
                {"conversational-memory-capture", "project-directory-layout", "knowledge-os-reader"},
            )
            self.assertEqual(proposed_ids, {"openknowledge-pivot"})
            self.assertEqual(historical_ids, set())

            # Sec.4/design brief group labels, not the old "GOVERNING NOW".
            self.assertEqual(data["groups"]["governing"]["header"], "In force now")
            self.assertEqual(data["groups"]["proposed"]["header"], "Waiting on you")
            self.assertEqual(data["groups"]["historical"]["header"], "Replaced")
            self.assertEqual(data["groups"]["historical"]["empty_text"], "No decision has been superseded yet.")

    def test_page_tree_includes_decisions_unlike_the_meaning_groups(self) -> None:
        """The sidebar/page tree mirrors the whole project directory
        (design brief: "the project, its directories and its records"),
        unlike the meaning-groups' own tree which used to exclude
        decisions entirely."""

        with serve(REPOSITORY, PORT) as base_url:
            _status, data = _get(base_url, "/api/projects/knowledge-os")

            def _collect_ids(node: dict) -> set[str]:
                ids = {r["id"] for r in node["records"]}
                if node["overview"]:
                    ids.add(node["overview"]["id"])
                for child in node["children"]:
                    ids |= _collect_ids(child)
                return ids

            tree_ids = _collect_ids(data["tree"])
            self.assertIn("openknowledge-pivot", tree_ids)
            self.assertIn("conversational-memory-capture", tree_ids)


class ProjectNotFoundTests(unittest.TestCase):
    def test_unknown_project_id_is_404_json(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            status, data = _get(base_url, "/api/projects/does-not-exist")
            self.assertEqual(status, 404)
            self.assertIn("does-not-exist", data["detail"])


class EmptyGroupTests(unittest.TestCase):
    """Sec.6 "Empty project group": the header stays, with an explaining
    sentence, never hidden."""

    def test_project_with_no_decisions_still_shows_every_group_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "projects/demo/README.md",
                {
                    "id": "demo",
                    "title": "Demo project",
                    "type": "project",
                    "status": "active",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            with serve(root, PORT) as base_url:
                status, data = _get(base_url, "/api/projects/demo")
                self.assertEqual(status, 200)
                for slug in ("governing", "proposed", "historical"):
                    self.assertEqual(data["groups"][slug]["records"], [])
                    self.assertTrue(data["groups"][slug]["empty_text"])
                self.assertEqual(data["observations"]["records"], [])
                self.assertTrue(data["observations"]["empty_text"])


if __name__ == "__main__":
    unittest.main()
