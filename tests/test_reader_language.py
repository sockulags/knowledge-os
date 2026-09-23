"""Tests for language.py: the one place a record's raw status/trust_label/
scope/provenance kind becomes the plain sentence the API sends. Pure, no
server needed -- every ``api/*.py`` endpoint calls into this module rather
than composing sentences itself, so this is the single place that behaviour
needs pinning.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reader_support import create_workspace, write_record

from knowledge_os.reader import language
from knowledge_os.reader.library import load_library
from knowledge_os.workspace import Workspace


def _load(build) -> "language.Library":
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        create_workspace(root)
        build(root)
        return load_library(Workspace(root))


class FormatDateShortTests(unittest.TestCase):
    def test_abbreviated_month(self) -> None:
        self.assertEqual(language.format_date_short("2026-09-12"), "12 Sep 2026")

    def test_none_in_none_out(self) -> None:
        self.assertIsNone(language.format_date_short(None))

    def test_unparseable_value_falls_back_unchanged(self) -> None:
        self.assertEqual(language.format_date_short("not-a-date"), "not-a-date")


class DisplayProjectTitleTests(unittest.TestCase):
    """Every project overview in the real corpus is titled "<Name> project
    overview" or "<Name> overview"; anywhere that title names the project
    rather than titling the overview page itself, the suffix is stripped."""

    def test_strips_project_overview_suffix(self) -> None:
        self.assertEqual(language.display_project_title("Knowledge OS project overview"), "Knowledge OS")

    def test_strips_bare_overview_suffix(self) -> None:
        self.assertEqual(language.display_project_title("Demo overview"), "Demo")

    def test_is_case_insensitive(self) -> None:
        self.assertEqual(language.display_project_title("Demo Project Overview"), "Demo")

    def test_leaves_an_unrelated_title_unchanged(self) -> None:
        self.assertEqual(language.display_project_title("Demo project"), "Demo project")

    def test_falls_back_to_the_full_title_when_nothing_would_remain(self) -> None:
        self.assertEqual(language.display_project_title("Overview"), "Overview")


class FormatDateTests(unittest.TestCase):
    def test_plain_date(self) -> None:
        self.assertEqual(language.format_date("2026-08-30"), "30 August 2026")

    def test_timestamp(self) -> None:
        self.assertEqual(language.format_date("2026-08-30T00:00:00Z"), "30 August 2026")

    def test_none_in_none_out(self) -> None:
        self.assertIsNone(language.format_date(None))
        self.assertIsNone(language.format_date(""))

    def test_unparseable_value_falls_back_unchanged(self) -> None:
        self.assertEqual(language.format_date("not-a-date"), "not-a-date")


class StatusSentenceTests(unittest.TestCase):
    def test_draft_decision_reads_as_a_proposal(self) -> None:
        def build(root: Path) -> None:
            write_record(
                root,
                "projects/demo/README.md",
                {
                    "id": "demo",
                    "title": "Demo",
                    "type": "project",
                    "status": "active",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            write_record(
                root,
                "projects/demo/decisions/idea.md",
                {
                    "id": "idea",
                    "title": "Idea",
                    "type": "project",
                    "record_kind": "decision",
                    "status": "draft",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )

        library = _load(build)
        sentence, accent = language.status_sentence(library, library.records_by_id["idea"])
        self.assertEqual(sentence, "Proposal — nobody has taken a position yet")
        self.assertEqual(accent, "proposed")

    def test_active_decision_names_the_acceptance_date(self) -> None:
        def build(root: Path) -> None:
            write_record(
                root,
                "projects/demo/README.md",
                {
                    "id": "demo",
                    "title": "Demo",
                    "type": "project",
                    "status": "active",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            write_record(
                root,
                "projects/demo/decisions/choice.md",
                {
                    "id": "choice",
                    "title": "Choice",
                    "type": "project",
                    "record_kind": "decision",
                    "status": "active",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [
                        {
                            "kind": "decision-acceptance",
                            "reference": "conversation:2026-08-30:choice",
                            "captured": "2026-08-30T00:00:00Z",
                        }
                    ],
                },
            )

        library = _load(build)
        sentence, accent = language.status_sentence(library, library.records_by_id["choice"])
        self.assertEqual(sentence, "In force — accepted 30 August 2026")
        self.assertIsNone(accent)

    def test_superseded_decision_names_its_successor(self) -> None:
        def build(root: Path) -> None:
            write_record(
                root,
                "projects/demo/README.md",
                {
                    "id": "demo",
                    "title": "Demo",
                    "type": "project",
                    "status": "active",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            write_record(
                root,
                "projects/demo/decisions/old.md",
                {
                    "id": "old",
                    "title": "Old choice",
                    "type": "project",
                    "record_kind": "decision",
                    "status": "superseded",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [
                        {"kind": "decision-acceptance", "reference": "c1", "captured": "2026-08-29T00:00:00Z"}
                    ],
                },
            )
            write_record(
                root,
                "projects/demo/decisions/new.md",
                {
                    "id": "new",
                    "title": "New choice",
                    "type": "project",
                    "record_kind": "decision",
                    "status": "active",
                    "scope": "project:demo",
                    "supersedes": ["old"],
                    "created": "2026-09-01",
                    "updated": "2026-09-01",
                    "provenance": [
                        {"kind": "decision-acceptance", "reference": "c2", "captured": "2026-09-01T00:00:00Z"}
                    ],
                },
            )

        library = _load(build)
        sentence, accent = language.status_sentence(library, library.records_by_id["old"])
        self.assertEqual(sentence, "Replaced by New choice on 1 September 2026")
        self.assertEqual(accent, "retired")


class TrustAndScopeSentenceTests(unittest.TestCase):
    def test_raw_source_reads_as_unchecked_material(self) -> None:
        def build(root: Path) -> None:
            write_record(
                root,
                "sources/raw.md",
                {
                    "id": "raw",
                    "title": "Raw",
                    "type": "source",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )

        library = _load(build)
        sentence, accent = language.trust_sentence(library.records_by_id["raw"])
        self.assertEqual(sentence, "Raw material. Nobody has checked it.")
        self.assertEqual(accent, "raw")

    def test_verified_durable_fills_in_the_date(self) -> None:
        def build(root: Path) -> None:
            write_record(
                root,
                "knowledge/checked.md",
                {
                    "id": "checked",
                    "title": "Checked",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "verified": "2026-08-29",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )

        library = _load(build)
        sentence, _accent = language.trust_sentence(library.records_by_id["checked"])
        self.assertEqual(sentence, "Confirmed 29 August 2026")

    def test_scope_general_applies_everywhere(self) -> None:
        def build(root: Path) -> None:
            write_record(
                root,
                "knowledge/fact.md",
                {
                    "id": "fact",
                    "title": "Fact",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )

        library = _load(build)
        self.assertEqual(language.scope_sentence(library, library.records_by_id["fact"]), "Applies everywhere")

    def test_scope_project_names_the_project_title(self) -> None:
        def build(root: Path) -> None:
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

        library = _load(build)
        self.assertEqual(language.scope_sentence(library, library.records_by_id["demo"]), "Demo project")


class ProvenanceSentenceTests(unittest.TestCase):
    def test_user_approved_conversation_names_the_date(self) -> None:
        def build(root: Path) -> None:
            write_record(
                root,
                "knowledge/fact.md",
                {
                    "id": "fact",
                    "title": "Fact",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [
                        {
                            "kind": "user-approved-conversation",
                            "reference": "conversation:2026-08-30:fact",
                            "captured": "2026-08-30T00:00:00Z",
                        }
                    ],
                },
            )

        library = _load(build)
        record = library.records_by_id["fact"]
        sentence = language.provenance_sentence(library, record, record.provenance[0])
        self.assertEqual(sentence, "A conversation you approved on 30 August 2026")

    def test_interface_provenance_reads_as_written_and_accepted_in_the_app(self) -> None:
        def build(root: Path) -> None:
            write_record(
                root,
                "knowledge/choice.md",
                {
                    "id": "choice",
                    "title": "Choice",
                    "type": "knowledge",
                    "record_kind": "decision",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-09-22",
                    "updated": "2026-09-23",
                    "provenance": [
                        {"kind": "interface-authored", "reference": "interface:2026-09-22T10:00:00Z:create"},
                        {
                            "kind": "decision-acceptance",
                            "reference": "interface:2026-09-23T08:00:00Z:accept",
                            "captured": "2026-09-23T08:00:00Z",
                        },
                    ],
                },
            )

        library = _load(build)
        record = library.records_by_id["choice"]
        sentences = [language.provenance_sentence(library, record, entry) for entry in record.provenance]
        self.assertEqual(sentences, ["Written by you in this app", "Accepted in this app on 23 September 2026"])

    def test_repository_file_provenance_never_shows_its_path(self) -> None:
        """``repository-file``'s own reference is a workspace-relative
        path; the reading path must never show a file path (design brief),
        so this kind gets reference-free bespoke phrasing rather than the
        generic kind/reference fallback."""

        def build(root: Path) -> None:
            write_record(
                root,
                "knowledge/fact.md",
                {
                    "id": "fact",
                    "title": "Fact",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "repository-file", "reference": "docs/thing.md"}],
                },
            )

        library = _load(build)
        record = library.records_by_id["fact"]
        sentence = language.provenance_sentence(library, record, record.provenance[0])
        self.assertEqual(sentence, "Copied from a file already in the repository")
        self.assertNotIn("docs/thing.md", sentence)

    def test_unknown_kind_falls_back_without_leaking_its_reference(self) -> None:
        def build(root: Path) -> None:
            write_record(
                root,
                "knowledge/fact.md",
                {
                    "id": "fact",
                    "title": "Fact",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "some-future-kind", "reference": "/etc/secret-path.md"}],
                },
            )

        library = _load(build)
        record = library.records_by_id["fact"]
        sentence = language.provenance_sentence(library, record, record.provenance[0])
        self.assertEqual(sentence, "Recorded provenance, not otherwise described here")
        self.assertNotIn("/etc/secret-path.md", sentence)
        self.assertNotIn("some-future-kind", sentence)


if __name__ == "__main__":
    unittest.main()
