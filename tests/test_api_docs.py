"""End-to-end tests for ``GET /api/docs/{path}``: the fixed, closed
repository-document tier allowlist. Every path outside it, including every
path-traversal shape, must be refused with the same 404 JSON shape before
touching the filesystem.
"""

from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.request

from reader_support import REPOSITORY, serve

PORT = 8837


def _get(base_url: str, path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(base_url + path, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


class RepoDocumentAllowlistTests(unittest.TestCase):
    def test_readme_is_served_with_the_unmanaged_label(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            status, data = _get(base_url, "/api/docs/README.md")
            self.assertEqual(status, 200)
            self.assertEqual(data["path"], "README.md")
            self.assertIn("Lives in the repository", data["unmanaged_label"])
            # The body's own leading H1 (identical to `title`, since
            # read_repo_document derives the title from that same heading)
            # is stripped so the page does not show it twice under the
            # page's own <h1>.
            self.assertEqual(data["title"], "Knowledge OS")
            self.assertNotIn("<h1", data["body_html"])
            self.assertIn("<h2", data["body_html"])

    def test_long_document_yields_a_table_of_contents(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            status, data = _get(base_url, "/api/docs/docs/architecture-audit-v0.1.md")
            self.assertEqual(status, 200)
            self.assertGreater(len(data["headings"]), 10)

    def test_path_outside_the_tier_is_refused(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            status, _data = _get(base_url, "/api/docs/pyproject.toml")
            self.assertEqual(status, 404)

    def test_path_traversal_is_refused(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            for attempt in ("../../etc/passwd", "..%2F..%2Fetc%2Fpasswd", "docs/../../pyproject.toml"):
                with self.subTest(attempt=attempt):
                    status, _data = _get(base_url, f"/api/docs/{attempt}")
                    self.assertEqual(status, 404)

    def test_skill_reference_file_is_served(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            status, data = _get(
                base_url, "/api/docs/skills/knowledge-os-documentation/references/init.md"
            )
            self.assertEqual(status, 200)
            self.assertTrue(data["title"])


if __name__ == "__main__":
    unittest.main()
