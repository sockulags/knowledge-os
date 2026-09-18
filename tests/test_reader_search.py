"""Tests for the search view, knowledge_os/reader/views/search.py.

Covers the behaviours the unit-4 contract calls out: an FTS phrase query, a
missing/stale index degrading gracefully instead of erroring, filter state
narrowing results and round-tripping through the query string, a no-match
query rendering an explaining empty state, and contract vocabulary (in
particular the literal words "draft" and "scope") never leaking into the
rendered page. Follows the repository's convention: unittest, no pytest, no
fixtures, workspaces built on disk in a TemporaryDirectory, end-to-end
coverage through ``tests/reader_support.py``'s ``serve``.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from reader_support import create_workspace, serve, write_record

from knowledge_os.index import rebuild_indexes
from knowledge_os.workspace import Workspace

PORT = 8815


def _knowledge_metadata(**overrides: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "id": "demo",
        "title": "Demo",
        "type": "knowledge",
        "status": "active",
        "scope": "general",
        "created": "2026-08-29",
        "updated": "2026-08-29",
        "provenance": [{"kind": "fixture", "reference": "demo"}],
    }
    metadata.update(overrides)
    return metadata


def _visible_text(html: str) -> str:
    """Strip every tag (attributes included, since they are always inside
    the tag's own angle brackets) down to the text a reader actually sees.

    A raw contract value legitimately lives in an <option value="draft">
    attribute or an href -- that is plumbing for the query-string round
    trip, not prose "at the reader" (docs/plans/reader-v1.md's own
    phrasing). What must never leak is the word appearing as something a
    person reads, which is what this strips down to.
    """

    return re.sub(r"<[^>]+>", " ", html)


def _get(base_url: str, path: str) -> tuple[int, str]:
    request = urllib.request.Request(base_url + path)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:  # a 4xx/5xx still has a body worth inspecting
        return exc.code, exc.read().decode("utf-8")


def _build_searchable_workspace(root: Path) -> None:
    """A small workspace covering every filter dimension: a decision, an
    ordinary knowledge record, a project overview, and a discovery, so
    type/status/record_kind/scope/trust all have more than one value to
    narrow between."""

    create_workspace(root)
    write_record(
        root,
        "projects/demo-project/README.md",
        {
            "id": "demo-project",
            "title": "Demo project",
            "type": "project",
            "status": "active",
            "scope": "project:demo-project",
            "created": "2026-08-29",
            "updated": "2026-08-29",
            "provenance": [{"kind": "fixture", "reference": "demo"}],
        },
        body="The demo project keeps a xylophone workshop running.\n",
    )
    write_record(
        root,
        "projects/demo-project/decisions/choice.md",
        {
            "id": "choice",
            "title": "Xylophone tuning choice",
            "type": "project",
            "status": "draft",
            "scope": "project:demo-project",
            "record_kind": "decision",
            "created": "2026-08-29",
            "updated": "2026-08-29",
            "provenance": [{"kind": "fixture", "reference": "demo"}],
        },
        body="Proposal: retune the xylophone before the next session.\n",
    )
    write_record(
        root,
        "knowledge/plain.md",
        _knowledge_metadata(id="plain", title="Xylophone care notes"),
        body="A xylophone needs a dry room and a soft mallet.\n",
    )
    write_record(
        root,
        "discoveries/observed.md",
        {
            "id": "observed",
            "title": "Observed xylophone squeak",
            "type": "discovery",
            "status": "proposed",
            "scope": "project:demo-project",
            "created": "2026-08-29",
            "updated": "2026-08-29",
            "provenance": [{"kind": "agent-run", "reference": "run-1"}],
            "evidence": [{"kind": "record", "reference": "demo-project"}],
        },
        body="An agent noticed the xylophone squeaks on the low end.\n",
    )
    workspace = Workspace(root)
    rebuild_indexes(workspace)


class SearchUnavailableTests(unittest.TestCase):
    def test_missing_index_disables_search_but_browsing_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/plain.md", _knowledge_metadata(id="plain"))
            # Deliberately no rebuild_indexes(): the index is absent, which
            # the acceptance criteria call out as the default state on a
            # fresh clone, not an edge case.
            with serve(root, PORT) as base_url:
                status, home_body = _get(base_url, "/")
                self.assertEqual(status, 200)

                status, body = _get(base_url, "/search")
                self.assertEqual(status, 200)
                self.assertIn("Search is unavailable", body)
                self.assertIn("kos index", body)
                # No filter form or results markup should render in this state.
                self.assertNotIn("search-filters", body)

    def test_catalog_removed_after_indexing_still_reports_unavailable(self) -> None:
        """Acceptance criterion 7: with indexes/catalog.sqlite3 removed,
        browsing still works and search reports it is unavailable. Builds
        the index first, then moves the database aside in a *copy* of the
        workspace (never the original)."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_searchable_workspace(root)
            self.assertTrue((root / "indexes" / "catalog.sqlite3").exists())

            with tempfile.TemporaryDirectory() as copy_directory:
                copy_root = Path(copy_directory) / "workspace"
                shutil.copytree(root, copy_root)
                (copy_root / "indexes" / "catalog.sqlite3").unlink()

                with serve(copy_root, PORT) as base_url:
                    status, body = _get(base_url, "/")
                    self.assertEqual(status, 200)

                    status, body = _get(base_url, "/search")
                    self.assertEqual(status, 200)
                    self.assertIn("Search is unavailable", body)
                    self.assertIn("kos index", body)

    def test_stale_index_shows_notice_but_search_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_searchable_workspace(root)
            path = root / "knowledge" / "plain.md"
            path.write_text(path.read_text(encoding="utf-8") + "\nExtra content.\n", encoding="utf-8")

            with serve(root, PORT) as base_url:
                status, body = _get(base_url, "/search?q=xylophone")
                self.assertEqual(status, 200)
                self.assertIn("Run", body)
                self.assertIn("kos index", body)
                self.assertIn("search-filters", body)
                self.assertIn("matching record", body)


class SearchResultsTests(unittest.TestCase):
    def test_query_matches_and_narrows_via_filters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_searchable_workspace(root)

            with serve(root, PORT) as base_url:
                status, body = _get(base_url, "/search?q=xylophone")
                self.assertEqual(status, 200)
                self.assertIn("4 matching record(s)", body)
                self.assertIn("Xylophone tuning choice", body)
                self.assertIn("Xylophone care notes", body)
                self.assertIn("Observed xylophone squeak", body)
                self.assertIn("Demo project", body)
                # The snippet highlights the match without corrupting markup.
                self.assertIn("<mark>xylophone</mark>", body)

                status, narrowed = _get(base_url, "/search?q=xylophone&type=discovery")
                self.assertEqual(status, 200)
                self.assertIn("1 matching record(s)", narrowed)
                self.assertIn("Observed xylophone squeak", narrowed)
                self.assertNotIn("Xylophone care notes", narrowed)

                # Filter state round-trips through the query string: the
                # selected <option> is marked selected on the narrowed page.
                self.assertIn('<option value="discovery" selected>', narrowed)
                self.assertIn('name="q"', narrowed)
                self.assertIn('value="xylophone"', narrowed)

    def test_record_kind_and_scope_filters_narrow_independently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_searchable_workspace(root)

            with serve(root, PORT) as base_url:
                status, decisions_only = _get(base_url, "/search?q=xylophone&record_kind=decision")
                self.assertEqual(status, 200)
                self.assertIn("1 matching record(s)", decisions_only)
                self.assertIn("Xylophone tuning choice", decisions_only)

                scope = urllib.parse.quote("project:demo-project")
                status, scoped = _get(base_url, f"/search?q=xylophone&scope={scope}")
                self.assertEqual(status, 200)
                self.assertIn("3 matching record(s)", scoped)
                self.assertNotIn("Xylophone care notes", scoped)
                # The project's own title resolves in the scope option, not
                # a raw "project:demo-project" token.
                self.assertIn("Demo project</option>", scoped)

    def test_trust_filter_narrows_by_the_records_actual_trust_label(self) -> None:
        """library.search()'s row has no trust column (only id, title, type,
        record_kind, status, scope, path, snippet -- see its docstring), so
        this filter has to cross-reference Library.records instead of the
        row itself; this guards against that lookup being skipped."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_searchable_workspace(root)

            with serve(root, PORT) as base_url:
                trust = urllib.parse.quote("active durable; not verified")
                status, body = _get(base_url, f"/search?q=xylophone&trust={trust}")
                self.assertEqual(status, 200)
                # "plain" (knowledge, active) and "demo-project" (project
                # overview, active) share this trust label; the draft
                # decision and the discovery do not.
                self.assertIn("2 matching record(s)", body)
                self.assertIn("Xylophone care notes", body)
                self.assertIn("Demo project", body)
                self.assertNotIn("Xylophone tuning choice", body)
                self.assertNotIn("Observed xylophone squeak", body)

    def test_combined_filters_can_produce_no_matches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_searchable_workspace(root)

            with serve(root, PORT) as base_url:
                status, body = _get(base_url, "/search?q=xylophone&type=discovery&record_kind=decision")
                self.assertEqual(status, 200)
                self.assertIn("No matching records.", body)

    def test_query_matching_nothing_renders_explaining_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_searchable_workspace(root)

            with serve(root, PORT) as base_url:
                status, body = _get(base_url, "/search?q=nonexistentzzzquery")
                self.assertEqual(status, 200)
                self.assertIn("No matching records.", body)

    def test_empty_query_prompts_without_erroring(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_searchable_workspace(root)

            with serve(root, PORT) as base_url:
                status, body = _get(base_url, "/search")
                self.assertEqual(status, 200)
                self.assertIn("Type something to search", body)
                self.assertIn("search-filters", body)

    def test_query_is_wrapped_as_a_single_phrase_word_order_matters(self) -> None:
        """The adapter wraps the query as a single FTS phrase (inherited
        core behaviour, see library.search's docstring): multi-word queries
        match only that exact word order, not "contains every word in any
        order". This is documented behaviour to preserve, not a bug to
        route around, and it is why a query that happens to hit no phrase
        must still render the explaining empty state rather than a blank
        page (covered by test_query_matching_nothing_renders_explaining_
        empty_state above)."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/plain.md",
                _knowledge_metadata(id="plain", title="Read-only reader"),
                body="A read-only reader never writes to the workspace.\n",
            )
            workspace = Workspace(root)
            rebuild_indexes(workspace)

            with serve(root, PORT) as base_url:
                # The words appear in this order in the body ("reader never
                # writes"): matches.
                status, body = _get(base_url, "/search?q=reader+never")
                self.assertEqual(status, 200)
                self.assertIn("Read-only reader", body)

                # Reversed order: the same two words, but not as a phrase,
                # so no match -- and still a clean 200 with the empty state.
                status, body = _get(base_url, "/search?q=never+reader")
                self.assertEqual(status, 200)
                self.assertIn("No matching records.", body)


class SearchContractVocabularyTests(unittest.TestCase):
    def test_raw_contract_words_never_reach_the_page(self) -> None:
        """"draft" and "scope" are named explicitly in the forbidden
        vocabulary list (docs/plans/reader-v1.md Sec.5); this workspace's
        one draft decision and one project scope exercise both. The raw
        token still legitimately appears inside <option value="draft"> and
        <option value="project:demo-project"> attributes -- that is the
        query-string plumbing filters round-trip through, not prose a
        person reads -- so this checks the visible text only."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_searchable_workspace(root)

            with serve(root, PORT) as base_url:
                status, body = _get(base_url, "/search?q=xylophone")
                self.assertEqual(status, 200)
                # The raw values are still present as attribute plumbing.
                self.assertIn('<option value="draft"', body)
                self.assertIn('<option value="project:demo-project"', body)

                visible = _visible_text(body).lower()
                self.assertNotIn("draft", visible)
                self.assertNotRegex(visible, r"\bscope\b")


class SearchWorkspaceIntegrityTests(unittest.TestCase):
    def test_serving_leaves_workspace_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_searchable_workspace(root)
            before = {
                path: (path.stat().st_mtime_ns, path.read_bytes())
                for path in root.rglob("*")
                if path.is_file()
            }

            with serve(root, PORT) as base_url:
                _get(base_url, "/search?q=xylophone&type=knowledge&status=active")
                _get(base_url, "/search")
                _get(base_url, "/search?q=")

            after = {
                path: (path.stat().st_mtime_ns, path.read_bytes())
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
