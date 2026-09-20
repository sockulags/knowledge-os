"""End-to-end tests for ``GET /api/everything``: acceptance criterion 10 --
sources and rejected discoveries are reachable, carry their trust label,
and never sit inside a governing group (there is no such group on this
page at all)."""

from __future__ import annotations

import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from reader_support import create_workspace, serve, write_record

PORT = 8835


def _get(base_url: str, path: str) -> dict:
    with urllib.request.urlopen(base_url + path, timeout=5) as response:
        return json.loads(response.read())


class EverythingCatalogTests(unittest.TestCase):
    def test_sources_and_rejected_discoveries_are_listed_with_their_trust_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "sources/raw.md",
                {
                    "id": "raw",
                    "title": "Raw source",
                    "type": "source",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            write_record(
                root,
                "discoveries/dismissed.md",
                {
                    "id": "dismissed",
                    "title": "Dismissed observation",
                    "type": "discovery",
                    "status": "rejected",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-30",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                    "evidence": [{"kind": "fixture", "reference": "demo"}],
                    "reviews": [{"decision": "reject", "date": "2026-08-30", "reason": "Not corroborated."}],
                },
            )
            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/everything")
                ids = {entry["id"]: entry for entry in data["entries"]}
                self.assertIn("raw", ids)
                self.assertIn("dismissed", ids)
                self.assertEqual(ids["raw"]["trust_phrase"], "Raw material. Nobody has checked it.")
                self.assertEqual(ids["dismissed"]["trust_phrase"], "Dismissed observation")
                # Never inside a governing pill/tone: a rejected discovery
                # and a raw source both carry a neutral-or-grey tone here,
                # never "In force" green.
                for entry_id in ("raw", "dismissed"):
                    pill = ids[entry_id]["status_pill"]
                    self.assertFalse(pill and pill["tone"] == "green")

    def test_broken_file_is_listed_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            (root / "knowledge" / "bad.md").write_text("not a record\n", encoding="utf-8")
            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/everything")
                self.assertEqual(len(data["broken"]), 1)
                self.assertEqual(data["broken"][0]["path"], "knowledge/bad.md")


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


class FilterAndSortWorkspace:
    """A workspace with one record per axis the filter vocabulary covers,
    shared by the filter/sort tests below so each test only names what it
    cares about."""

    def __enter__(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        create_workspace(root)
        # Ordinary knowledge, unverified -> "active durable; not verified".
        write_record(root, "knowledge/apple.md", _record("apple", title="Apple notes", updated="2026-08-29"))
        # Ordinary knowledge, verified -> "verified durable".
        write_record(
            root,
            "knowledge/banana.md",
            _record("banana", title="Banana notes", updated="2026-08-30", verified="2026-08-30"),
        )
        # Raw source material.
        write_record(
            root,
            "sources/cherry-source.md",
            _record("cherry-source", type="source", title="Cherry source material", updated="2026-08-31"),
        )
        # A project overview, to give the scope filter a real project scope.
        write_record(
            root,
            "projects/demo/README.md",
            _record("demo", type="project", title="Demo project overview", scope="project:demo", updated="2026-09-01"),
        )
        # A decision scoped to that project.
        write_record(
            root,
            "projects/demo/decisions/choice.md",
            _record(
                "choice",
                type="project",
                title="Choice decision",
                scope="project:demo",
                record_kind="decision",
                updated="2026-09-02",
                provenance=[
                    {
                        "kind": "decision-acceptance",
                        "reference": "conversation:2026-09-02:demo",
                        "captured": "2026-09-02T00:00:00Z",
                    }
                ],
            ),
        )
        self.root = root
        return root

    def __exit__(self, *exc: object) -> None:
        self._tmp.cleanup()


class FilterTests(unittest.TestCase):
    def test_type_filter_narrows_to_that_type(self) -> None:
        with FilterAndSortWorkspace() as root:
            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/everything?type=source")
                self.assertEqual({e["id"] for e in data["entries"]}, {"cherry-source"})
                self.assertEqual(data["filters"], {"type": "source"})

    def test_status_filter_narrows(self) -> None:
        with FilterAndSortWorkspace() as root:
            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/everything?status=active")
                ids = {e["id"] for e in data["entries"]}
                # Every fixture record above is "active"; a status filter
                # that matches everything still narrows correctly (it just
                # narrows to "everything").
                self.assertEqual(ids, {"apple", "banana", "cherry-source", "demo", "choice"})

    def test_record_kind_filter_covers_every_non_decision_type(self) -> None:
        with FilterAndSortWorkspace() as root:
            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/everything?record_kind=decision")
                self.assertEqual({e["id"] for e in data["entries"]}, {"choice"})

                # "Not a decision" must also cover a source record, whose own
                # `record_kind` field is never set at all (it is not a
                # knowledge/project record) -- the filter's own label says
                # this covers "every non-decision record".
                data = _get(base_url, "/api/everything?record_kind=ordinary")
                ids = {e["id"] for e in data["entries"]}
                self.assertEqual(ids, {"apple", "banana", "cherry-source", "demo"})

    def test_scope_filter_narrows_to_one_project(self) -> None:
        with FilterAndSortWorkspace() as root:
            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/everything?scope=project:demo")
                self.assertEqual({e["id"] for e in data["entries"]}, {"demo", "choice"})

    def test_trust_filter_narrows(self) -> None:
        with FilterAndSortWorkspace() as root:
            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/everything?trust=verified+durable")
                self.assertEqual({e["id"] for e in data["entries"]}, {"banana"})

    def test_filters_combine(self) -> None:
        with FilterAndSortWorkspace() as root:
            with serve(root, PORT) as base_url:
                # type=project alone matches "demo" and "choice"; adding
                # record_kind=decision narrows that pair down to "choice".
                data = _get(base_url, "/api/everything?type=project&record_kind=decision")
                self.assertEqual({e["id"] for e in data["entries"]}, {"choice"})

    def test_unknown_filter_value_is_dropped_not_trusted(self) -> None:
        with FilterAndSortWorkspace() as root:
            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/everything?type=not-a-real-type")
                self.assertEqual(data["filters"], {})
                self.assertEqual({e["id"] for e in data["entries"]}, {"apple", "banana", "cherry-source", "demo", "choice"})

    def test_filter_options_only_offer_values_present_in_the_data(self) -> None:
        with FilterAndSortWorkspace() as root:
            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/everything")
                type_values = {o["value"] for o in data["filter_options"]["type"]}
                self.assertEqual(type_values, {"knowledge", "project", "source"})
                status_values = {o["value"] for o in data["filter_options"]["status"]}
                self.assertEqual(status_values, {"active"})
                trust_values = {o["value"] for o in data["filter_options"]["trust"]}
                self.assertNotIn("unusable durable record", trust_values)


class SortTests(unittest.TestCase):
    def test_default_sort_is_title_ascending(self) -> None:
        with FilterAndSortWorkspace() as root:
            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/everything")
                self.assertEqual(data["sort"], "title")
                self.assertEqual(data["dir"], "asc")
                titles = [e["title"] for e in data["entries"]]
                self.assertEqual(titles, sorted(titles, key=str.casefold))

    def test_sort_by_updated_both_directions(self) -> None:
        with FilterAndSortWorkspace() as root:
            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/everything?sort=updated&dir=asc")
                ids = [e["id"] for e in data["entries"]]
                self.assertEqual(ids, ["apple", "banana", "cherry-source", "demo", "choice"])

                data = _get(base_url, "/api/everything?sort=updated&dir=desc")
                ids = [e["id"] for e in data["entries"]]
                self.assertEqual(ids, ["choice", "demo", "cherry-source", "banana", "apple"])

    def test_unknown_sort_and_direction_fall_back_to_the_default(self) -> None:
        with FilterAndSortWorkspace() as root:
            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/everything?sort=nonsense&dir=sideways")
                self.assertEqual(data["sort"], "title")
                self.assertEqual(data["dir"], "asc")


if __name__ == "__main__":
    unittest.main()
