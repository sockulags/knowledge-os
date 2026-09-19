"""End-to-end tests for ``GET /api/skills/{name}``, against the real
workspace's four skills."""

from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.request

from reader_support import REPOSITORY, serve

PORT = 8836


def _get(base_url: str, path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(base_url + path, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


class SkillViewTests(unittest.TestCase):
    def test_known_skill_reads_as_operational_guidance(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            status, data = _get(base_url, "/api/skills/ingest-source")
            self.assertEqual(status, 200)
            self.assertEqual(data["name"], "ingest-source")
            self.assertIn("Operational guidance", data["trust_label"])
            self.assertIsNone(data["broken"])
            # The body's own leading H1 (a nicer-cased echo of `name`) is
            # promoted to `title` and stripped from body_html, so it is not
            # shown twice; the page's own <h2>s stay in the rendered body.
            self.assertEqual(data["title"], "Ingest source")
            self.assertIn("<h2", data["body_html"])
            self.assertNotIn("<h1", data["body_html"])

    def test_skill_with_references_lists_them(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            status, data = _get(base_url, "/api/skills/knowledge-os-documentation")
            self.assertEqual(status, 200)
            self.assertGreater(len(data["references"]), 0)
            for reference in data["references"]:
                self.assertTrue(reference["readable"])
                self.assertTrue(reference["path"].startswith("skills/knowledge-os-documentation/references/"))

    def test_unknown_skill_is_404_json(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            status, data = _get(base_url, "/api/skills/does-not-exist")
            self.assertEqual(status, 404)
            self.assertIn("does-not-exist", data["detail"])


if __name__ == "__main__":
    unittest.main()
