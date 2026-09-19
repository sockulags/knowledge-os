"""End-to-end tests for ``GET /api/workspace``, ``GET /api/nav``, and
``GET /api/home``: the shell's own data (sidebar tree, quick-find index,
health) and the landing page."""

from __future__ import annotations

import json
import unittest
import urllib.request

from reader_support import REPOSITORY, serve

PORT = 8838


def _get(base_url: str, path: str) -> dict:
    with urllib.request.urlopen(base_url + path, timeout=5) as response:
        return json.loads(response.read())


class WorkspaceHealthTests(unittest.TestCase):
    def test_real_corpus_lint_is_clean(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            data = _get(base_url, "/api/workspace")
            self.assertEqual(data["health"]["issue_count"], 0)
            self.assertTrue(data["health"]["lint_ok"])


class NavTests(unittest.TestCase):
    def test_quick_find_index_covers_records_skills_and_docs(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            data = _get(base_url, "/api/nav")
            kinds = {entry["kind"] for entry in data["record_index"]}
            self.assertIn("decision", kinds)
            self.assertIn("skill", kinds)
            self.assertIn("doc", kinds)
            titles = {entry["title"] for entry in data["record_index"]}
            self.assertIn("Read-only reader for Knowledge OS", titles)

    def test_skills_and_repo_docs_sections_are_populated(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            data = _get(base_url, "/api/nav")
            self.assertEqual(len(data["skills"]), 4)
            self.assertGreater(len(data["repo_docs"]), 0)

    def test_project_tree_is_nested_under_the_knowledge_os_project(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            data = _get(base_url, "/api/nav")
            project = next(p for p in data["projects"] if p["id"] == "knowledge-os")
            self.assertEqual(project["tree"]["name"], "")
            child_names = {child["name"] for child in project["tree"]["children"]}
            self.assertIn("decisions", child_names)
            self.assertIn("architecture", child_names)


class HomeTests(unittest.TestCase):
    def test_waiting_and_in_force_match_the_real_corpus(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            data = _get(base_url, "/api/home")
            waiting_ids = {r["id"] for r in data["waiting_on_you"]}
            in_force_ids = {r["id"] for r in data["in_force"]}
            self.assertEqual(waiting_ids, {"openknowledge-pivot"})
            self.assertEqual(
                in_force_ids,
                {"conversational-memory-capture", "project-directory-layout", "knowledge-os-reader"},
            )
            self.assertIn("3 decision(s)", data["subtitle"])
            self.assertTrue(any(project["id"] == "knowledge-os" for project in data["projects"]))


if __name__ == "__main__":
    unittest.main()
