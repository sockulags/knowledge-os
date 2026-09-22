"""End-to-end tests for ``GET /api/search``: filters, a missing index, and
a stale index (Sec.6 "Missing index" / "Stale index", acceptance
criterion 7).
"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from reader_support import REPOSITORY, create_workspace, serve, write_record

from knowledge_os.index import rebuild_indexes
from knowledge_os.workspace import Workspace

PORT = 8834


def _get(base_url: str, path: str) -> dict:
    with urllib.request.urlopen(base_url + path, timeout=5) as response:
        return json.loads(response.read())


def _record(record_id: str, **overrides: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "id": record_id,
        "title": overrides.pop("title", record_id.title()),
        "type": "knowledge",
        "status": "active",
        "scope": "general",
        "created": "2026-08-29",
        "updated": "2026-08-29",
        "provenance": [{"kind": "fixture", "reference": record_id}],
    }
    metadata.update(overrides)
    return metadata


class MissingIndexTests(unittest.TestCase):
    def test_search_reports_unavailable_and_browsing_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/plain.md", _record("plain"))
            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/search?q=plain")
                self.assertFalse(data["search_available"])
                self.assertIn("kos index", data["disabled_reason"])
                self.assertEqual(data["results"], [])

                # Browsing still works.
                with urllib.request.urlopen(base_url + "/api/records/plain", timeout=5) as response:
                    self.assertEqual(response.status, 200)


class StaleIndexTests(unittest.TestCase):
    def test_search_reports_stale_after_an_edit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            path = write_record(root, "knowledge/plain.md", _record("plain"))
            workspace = Workspace(root)
            rebuild_indexes(workspace)

            # Edit the record after indexing, with a newer mtime than the
            # index build (a filesystem-timestamp race on a very fast
            # machine is why this sleeps briefly rather than editing
            # instantly).
            time.sleep(0.05)
            path.write_text(path.read_text(encoding="utf-8").replace("Body.", "Edited body."), encoding="utf-8")

            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/workspace")
                self.assertTrue(data["health"]["index_stale"])
                self.assertTrue(data["health"]["search_disabled"])


class SnippetMarkdownStrippingTests(unittest.TestCase):
    """A search snippet is a raw slice of a record's own Markdown source,
    not rendered HTML, so it can contain a heading marker, a link's
    `[text](url)` syntax, or backticks verbatim. None of that belongs in a
    preview -- coordinator review of PR #17 flagged `## Decision` and
    `[OpenKnowledge pivot decision](../decisions/openknowledge-pivot.md)`
    showing up raw in real search results."""

    def test_snippet_strips_heading_link_and_code_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/plan.md",
                _record("plan", title="Plan"),
                body=(
                    "## Decision\n\n"
                    "See the [OpenKnowledge pivot decision](../decisions/openknowledge-pivot.md) "
                    "for context, and run `kos index` to refresh the decision catalog.\n"
                ),
            )
            workspace = Workspace(root)
            rebuild_indexes(workspace)

            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/search?q=decision")
                self.assertTrue(data["search_available"])
                self.assertEqual(len(data["results"]), 1)
                snippet = data["results"][0]["snippet_html"]
                self.assertNotIn("##", snippet)
                self.assertNotIn("](", snippet)
                self.assertNotIn("`", snippet)
                self.assertNotIn("[OpenKnowledge", snippet)
                # The highlighting itself must survive the stripping pass:
                # the matched word "decision" inside the link text is still
                # its own <mark>, even though the link syntax around it
                # (including a *second* matched "Decision" as the snippet's
                # own heading word) is gone.
                self.assertIn("<mark>Decision</mark>", snippet)
                self.assertIn("OpenKnowledge pivot <mark>decision</mark>", snippet)


class RealCorpusSnippetTests(unittest.TestCase):
    def test_real_corpus_snippets_have_no_raw_markdown_syntax(self) -> None:
        # This only exercises the real repository's own index if one is
        # already built (`kos index`), and skips cleanly otherwise; the
        # synthetic test above is the deterministic, always-run regression
        # check for the same bug.
        database = REPOSITORY / "indexes" / "catalog.sqlite3"
        if not database.is_file():
            self.skipTest("no search index built in the real repository; run `kos index` to exercise this check")
        with serve(REPOSITORY, PORT) as base_url:
            data = _get(base_url, "/api/search?q=decision")
            if not data["search_available"] or not data["results"]:
                self.skipTest("search index present but stale or empty for this query")
            for result in data["results"]:
                snippet = result["snippet_html"]
                self.assertNotIn("##", snippet)
                self.assertNotIn("](", snippet)


class FilterTests(unittest.TestCase):
    def test_type_filter_narrows_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/apple.md", _record("apple", title="Apple pie recipe"))
            write_record(
                root,
                "sources/apple-source.md",
                _record("apple-source", type="source", title="Apple pie source material"),
            )
            workspace = Workspace(root)
            rebuild_indexes(workspace)

            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/search?q=apple&type=source")
                self.assertTrue(data["search_available"])
                ids = {r["id"] for r in data["results"]}
                self.assertEqual(ids, {"apple-source"})

    def test_unknown_filter_value_is_dropped_not_trusted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/apple.md", _record("apple"))
            workspace = Workspace(root)
            rebuild_indexes(workspace)

            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/search?q=apple&type=not-a-real-type")
                self.assertEqual(data["filters"], {})
                self.assertEqual({r["id"] for r in data["results"]}, {"apple"})

    def test_record_kind_ordinary_filter_matches_a_source_too(self) -> None:
        # A source record's own `record_kind` field is never set (it is not
        # a knowledge/project record); the "Not a decision" filter option is
        # documented to cover it anyway (SEARCH_RECORD_KIND_FILTER).
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "sources/apple-source.md",
                _record("apple-source", type="source", title="Apple pie source material"),
            )
            workspace = Workspace(root)
            rebuild_indexes(workspace)

            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/search?q=apple&record_kind=ordinary")
                self.assertEqual({r["id"] for r in data["results"]}, {"apple-source"})


if __name__ == "__main__":
    unittest.main()
