"""Tests for language.py: the one place a record's raw status/trust_label/
scope/provenance kind becomes the plain sentence the API sends. Pure, no
server needed -- every ``api/*.py`` endpoint calls into this module rather
than composing sentences itself, so this is the single place that behaviour
needs pinning.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from reader_support import create_workspace, write_record

from knowledge_os.reader import language, strings
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
        self.assertEqual(sentence, "Proposed — not in force until you accept it")
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

    def test_referat_meeting_provenance_names_the_meeting_date(self) -> None:
        def build(root: Path) -> None:
            write_record(
                root,
                "knowledge/minutes.md",
                {
                    "id": "minutes",
                    "title": "Minutes",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-09-23",
                    "updated": "2026-09-23",
                    "provenance": [
                        {
                            "kind": "referat-meeting",
                            "reference": "referat:20260920120300-k3j9x2",
                            "captured": "2026-09-23T08:00:00Z",
                        },
                        {"kind": "referat-meeting", "reference": "referat:not-a-meeting-id"},
                    ],
                },
            )

        library = _load(build)
        record = library.records_by_id["minutes"]
        sentences = [language.provenance_sentence(library, record, entry) for entry in record.provenance]
        # The date is the meeting's (from its id), not the import's (captured).
        self.assertEqual(
            sentences,
            ["Imported from a Referat meeting on 20 September 2026", "Imported from a Referat meeting"],
        )

    def test_decision_withdrawal_names_the_date_and_reason(self) -> None:
        def build(root: Path) -> None:
            write_record(
                root,
                "knowledge/choice.md",
                {
                    "id": "choice",
                    "title": "Choice",
                    "type": "knowledge",
                    "record_kind": "decision",
                    "status": "archived",
                    "scope": "general",
                    "created": "2026-09-22",
                    "updated": "2026-09-23",
                    "provenance": [
                        {
                            "kind": "decision-acceptance",
                            "reference": "interface:2026-09-22T10:00:00Z:accept",
                            "captured": "2026-09-22T10:00:00Z",
                        },
                        {
                            "kind": "decision-withdrawal",
                            "reference": "No longer needed <after the merge>",
                            "captured": "2026-09-23T08:00:00Z",
                        },
                    ],
                },
            )

        library = _load(build)
        record = library.records_by_id["choice"]
        sentence = language.provenance_sentence(library, record, record.provenance[1])
        self.assertEqual(sentence, "Withdrawn on 23 September 2026: No longer needed <after the merge>")

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

    def test_agent_authored_names_the_agent_and_where_it_ran(self) -> None:
        references = {
            "agent:claude-code:my-repo": "Written by Claude Code in my-repo",
            "agent:codex-mcp-client": "Written by Codex",
            "agent:some-bot:web": "Written by some-bot in web",
            "agent:bad/client:x": "Written by an agent",
        }

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
                    "provenance": [{"kind": "agent-authored", "reference": reference} for reference in references],
                },
            )

        library = _load(build)
        record = library.records_by_id["fact"]
        sentences = [language.provenance_sentence(library, record, entry) for entry in record.provenance]
        self.assertEqual(sentences, list(references.values()))

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
        self.assertEqual(sentence, "From a source this app does not describe yet")
        self.assertNotIn("/etc/secret-path.md", sentence)
        self.assertNotIn("some-future-kind", sentence)


def _demo_decision(root: Path, record_id: str, provenance: list[dict[str, str]], **overrides: object) -> None:
    metadata: dict[str, object] = {
        "id": record_id,
        "title": record_id.replace("-", " ").capitalize(),
        "type": "project",
        "record_kind": "decision",
        "status": "draft",
        "scope": "project:demo",
        "created": "2026-09-10",
        "updated": "2026-09-10",
        "provenance": provenance,
    }
    metadata.update(overrides)
    write_record(root, f"projects/demo/decisions/{record_id}.md", metadata)


def _demo_project(root: Path) -> None:
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


class ProposedByTests(unittest.TestCase):
    """Who proposed a decision, from the first provenance entry that is not
    an acceptance or a withdrawal (issue #53)."""

    def test_each_known_kind_and_the_fallback(self) -> None:
        cases = {
            "by-app": ({"kind": "interface-authored", "reference": "interface:2026-09-20T10:00:00Z:create", "captured": "2026-09-20T10:00:00Z"}, "you", "Proposed by you in this app"),
            "by-request": ({"kind": "user-request", "reference": "conversation:x"}, "you", "Proposed at your request"),
            "by-conversation": ({"kind": "user-approved-conversation", "reference": "conversation:y"}, "conversation", "Proposed in a conversation you approved"),
            "by-meeting": ({"kind": "referat-meeting", "reference": "referat:20260918093000-ab12cd"}, "meeting", "Proposed in a Referat meeting on 18 September 2026"),
            "by-meeting-undated": ({"kind": "referat-meeting", "reference": "referat:not-an-id"}, "meeting", "Proposed in a Referat meeting"),
            "by-agent": ({"kind": "agent-authored", "reference": "agent:codex"}, "agent", "Proposed by Codex"),
            "by-agent-in-repo": ({"kind": "agent-authored", "reference": "agent:claude-code:my-repo"}, "agent", "Proposed by Claude Code in my-repo"),
            "by-agent-unlisted": ({"kind": "agent-authored", "reference": "agent:some-bot:web app"}, "agent", "Proposed by some-bot in web app"),
            "by-agent-unnamed": ({"kind": "agent-authored", "reference": "not-an-agent-reference"}, "agent", "Proposed by an agent"),
            "by-unknown": ({"kind": "some-future-kind", "reference": "/etc/secret-path.md"}, "other", "Proposed from a source this app does not describe yet"),
        }

        def build(root: Path) -> None:
            _demo_project(root)
            for record_id, (entry, _source, _label) in cases.items():
                _demo_decision(root, record_id, [entry])

        library = _load(build)
        for record_id, (entry, source, label) in cases.items():
            with self.subTest(record_id=record_id):
                proposer = language.proposed_by(library, library.records_by_id[record_id])
                self.assertEqual(proposer["source"], source)
                self.assertEqual(proposer["label"], label)
                self.assertEqual(proposer["kind"], entry["kind"])
                self.assertEqual(proposer["when"], entry.get("captured", "2026-09-10"))

    def test_skips_lifecycle_entries(self) -> None:
        def build(root: Path) -> None:
            _demo_project(root)
            _demo_decision(
                root,
                "accepted",
                [
                    {"kind": "decision-acceptance", "reference": "conversation:a", "captured": "2026-09-12T10:00:00Z"},
                    {"kind": "referat-meeting", "reference": "referat:20260911080000-zz", "captured": "2026-09-11T10:00:00Z"},
                ],
                status="active",
            )

        library = _load(build)
        proposer = language.proposed_by(library, library.records_by_id["accepted"])
        self.assertEqual(proposer["source"], "meeting")
        self.assertEqual(proposer["when"], "2026-09-11T10:00:00Z")

    def test_withdrawn_decision_reads_as_withdrawn_with_its_date(self) -> None:
        def build(root: Path) -> None:
            _demo_project(root)
            _demo_decision(
                root,
                "dropped",
                [
                    {"kind": "interface-authored", "reference": "interface:x"},
                    {"kind": "decision-withdrawal", "reference": "No longer needed.", "captured": "2026-09-14T10:00:00Z"},
                ],
                status="archived",
                updated="2026-09-14",
            )

        library = _load(build)
        sentence, accent = language.status_sentence(library, library.records_by_id["dropped"])
        self.assertEqual(sentence, "Withdrawn on 14 September 2026, without being accepted")
        self.assertEqual(accent, "retired")


class DecisionVocabularyTests(unittest.TestCase):
    """The decision words a person reads must not use contract vocabulary
    (issue #54); the exact values stay in Technical details."""

    CONTRACT_WORDS = re.compile(
        r"\b(records?|provenance|supersedes?|superseded|supersession|draft|active|archived|lineage|scope)\b",
        re.IGNORECASE,
    )

    def _texts(self) -> list[str]:
        texts: list[str] = [
            *strings.DECISION_STATUS.values(),
            strings.DECISION_WITHDRAWN_UNDATED,
            *strings.PILL_LABELS.values(),
            *strings.PROJECT_GROUP_HEADERS.values(),
            *strings.PROJECT_GROUP_EMPTY.values(),
            strings.HOME_WAITING_HEADER,
            strings.HOME_NO_WAITING,
            strings.HOME_DECIDE_LINK,
            strings.START_OPEN_DECISIONS,
            strings.START_NO_OPEN_DECISIONS,
            strings.LINEAGE_SUPERSEDES,
            strings.LINEAGE_SUPERSEDED_BY,
            strings.LINEAGE_NO_COMPARISON,
            strings.LINEAGE_TARGET_NOT_DECISION,
            strings.LINEAGE_CALLOUT_SUPERSEDES,
            strings.LINEAGE_CALLOUT_WOULD_REPLACE,
            strings.LINEAGE_CALLOUT_SUPERSEDED_BY,
            strings.TRUST_LABELS["draft durable; not verified"],
            strings.LIFECYCLE_STATUS["draft"],
            strings.PROVENANCE_KIND_FALLBACK,
            strings.DOCUMENT_RELATED_EMPTY,
            strings.SEARCH_STATUS_FILTER["draft"],
            strings.SEARCH_STATUS_FILTER["active"],
            strings.SEARCH_STATUS_FILTER["superseded"],
            *strings.DECISION_STATE_LABELS.values(),
            *strings.DECISION_ACTION_LABELS.values(),
            *strings.DECISION_SUMMARY.values(),
            strings.DECISION_GUIDE_TITLE,
            strings.DECISION_GUIDE_INTRO,
            strings.DECISION_GUIDE_UNDO,
            *strings.DECISION_GUIDE_STATES.values(),
            strings.DECISION_DIALOG_ACCEPTED_TODAY,
            strings.DECISION_DIALOG_REPLACED_BY,
            *strings.PROPOSED_BY.values(),
            strings.PROPOSED_BY_REFERAT_UNDATED,
            strings.PROPOSED_BY_FALLBACK,
        ]
        for dialog in strings.DECISION_DIALOGS.values():
            texts.extend(dialog.values())
        texts.extend(value for name, value in vars(strings).items() if name.startswith("DECIDE_") and isinstance(value, str))
        return texts

    def test_no_contract_words(self) -> None:
        # PILL_LABELS["archived"] is the pill of an archived ordinary note,
        # not of a decision; a withdrawn decision reads "Withdrawn".
        for text in self._texts():
            if text == strings.PILL_LABELS["archived"]:
                continue
            with self.subTest(text=text):
                self.assertIsNone(self.CONTRACT_WORDS.search(text))

    def test_every_state_has_a_label_and_a_guide_line(self) -> None:
        self.assertEqual(set(strings.DECISION_STATE_LABELS), set(strings.DECISION_GUIDE_STATES))
        self.assertEqual(
            list(strings.DECISION_STATE_LABELS.values()), ["Proposed", "In force", "Replaced", "Withdrawn"]
        )

    def test_every_dialog_says_whether_it_can_be_undone(self) -> None:
        for action, dialog in strings.DECISION_DIALOGS.items():
            with self.subTest(action=action):
                self.assertRegex(dialog["body"], r"undo|undone")


class ShellVocabularyTests(unittest.TestCase):
    """The reader's shell-wide and catalog copy -- the not-found/load-error
    fallbacks every record-backed page shares, the quick-find placeholder,
    and the Everything catalog's own title and intro -- must not use
    contract vocabulary either (issue #63's follow-up cleanup), the same
    rule ``DecisionVocabularyTests`` already pins for decision copy."""

    CONTRACT_WORDS = DecisionVocabularyTests.CONTRACT_WORDS

    def _texts(self) -> list[str]:
        return [
            strings.DOCUMENT_NOT_FOUND_TITLE,
            strings.DOCUMENT_NOT_FOUND_BODY,
            strings.DOCUMENT_LOAD_ERROR,
            strings.QUICK_FIND_PLACEHOLDER,
            strings.EVERYTHING_TITLE,
            strings.EVERYTHING_INTRO,
        ]

    def test_no_contract_words(self) -> None:
        for text in self._texts():
            with self.subTest(text=text):
                self.assertIsNone(self.CONTRACT_WORDS.search(text))


if __name__ == "__main__":
    unittest.main()
