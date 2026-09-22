"""End-to-end tests for the write API: ``POST /api/records``,
``PATCH /api/records/{id}``, and the ``GET /api/session`` token they need.

One real ``kos-read`` server serves one temporary workspace for the whole
class; every test uses its own record IDs so the tests stay independent. The
reindex-failure path is tested in process against the adapter, since it needs
the core's index refresh to fail on purpose.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from reader_support import FIXTURE_PROJECT_ID, FIXTURE_PROPOSED_ID, serve, write_decision_fixture

from knowledge_os import capture as capture_module
from knowledge_os import mutations as mutations_module
from knowledge_os.reader import library
from knowledge_os.workspace import Workspace, WorkspaceError

PORT = 8842
TOKEN_HEADER = "X-KOS-Write-Token"


def _request(
    base_url: str,
    method: str,
    path: str,
    payload: object | None = None,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(base_url + path, data=data, method=method)
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _note(record_id: str, **overrides: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "id": record_id,
        "title": record_id.replace("-", " ").capitalize(),
        "type": "knowledge",
        "status": "active",
        "scope": "general",
        "provenance": [{"kind": "user-authored", "reference": f"test:{record_id}"}],
    }
    metadata.update(overrides)
    return metadata


class WriteApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._stack = ExitStack()
        directory = cls._stack.enter_context(tempfile.TemporaryDirectory())
        cls.root = Path(directory)
        write_decision_fixture(cls.root)
        cls.base_url = cls._stack.enter_context(serve(cls.root, PORT))
        status, session = _request(cls.base_url, "GET", "/api/session")
        assert status == 200, session
        cls.token = session["write_token"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls._stack.close()

    def write(self, method: str, path: str, payload: object, **headers: str) -> tuple[int, dict]:
        return _request(self.base_url, method, path, payload, headers={TOKEN_HEADER: self.token, **headers})

    def create(self, metadata: dict[str, object], body: str = "Body text.\n", **extra: object) -> tuple[int, dict]:
        return self.write("POST", "/api/records", {"metadata": metadata, "body": body, **extra})

    def sha(self, relative: str) -> str:
        return hashlib.sha256((self.root / relative).read_bytes()).hexdigest()

    # -- create ---------------------------------------------------------------

    def test_create_writes_the_record_reindexes_and_returns_its_hash(self) -> None:
        status, result = self.create(_note("created-note"), "Mentions quetzalcoatlus once.\n")

        self.assertEqual(status, 201, result)
        self.assertEqual(result["id"], "created-note")
        self.assertEqual(result["path"], "knowledge/created-note.md")
        self.assertEqual(result["content_sha256"], self.sha("knowledge/created-note.md"))
        self.assertEqual(result["index"]["refreshed"], True)
        self.assertIsNone(result["index"]["error"])
        status, found = _request(self.base_url, "GET", "/api/search?q=quetzalcoatlus")
        self.assertEqual(status, 200)
        self.assertIn("created-note", json.dumps(found))

    def test_create_project_record_honours_project_path(self) -> None:
        metadata = _note(
            "nested-project-note",
            type="project",
            scope=f"project:{FIXTURE_PROJECT_ID}",
        )
        status, result = self.create(metadata, project_path="notes/nested-project-note.md")

        self.assertEqual(status, 201, result)
        self.assertEqual(result["path"], f"projects/{FIXTURE_PROJECT_ID}/notes/nested-project-note.md")

    def test_create_decision_must_be_draft(self) -> None:
        metadata = _note(
            "active-decision",
            type="project",
            record_kind="decision",
            scope=f"project:{FIXTURE_PROJECT_ID}",
            provenance=[
                {"kind": "decision-acceptance", "reference": "test:self-accepted", "captured": "2026-09-22T00:00:00Z"}
            ],
        )
        status, result = self.create(metadata)

        self.assertEqual(status, 422, result)
        self.assertIn("capture creates decision records as draft", result["detail"])

    def test_duplicate_id_is_a_conflict(self) -> None:
        self.assertEqual(self.create(_note("twice-note"))[0], 201)
        before = self.sha("knowledge/twice-note.md")

        status, result = self.create(_note("twice-note", title="Second"))

        self.assertEqual(status, 409, result)
        self.assertEqual(result["error"], "duplicate")
        self.assertEqual(self.sha("knowledge/twice-note.md"), before)

    def test_invalid_frontmatter_is_a_validation_error(self) -> None:
        status, result = self.create(_note("bad-status-note", status="finished"))
        self.assertEqual(status, 422, result)
        self.assertEqual(result["error"], "validation")
        self.assertIn("status", result["detail"])
        self.assertFalse((self.root / "knowledge" / "bad-status-note.md").exists())

    def test_invalid_resulting_corpus_reports_lint_issues(self) -> None:
        status, result = self.create(_note("dangling-note", related=["no-such-record"]))

        self.assertEqual(status, 422, result)
        self.assertTrue(result["issues"], result)
        self.assertEqual(result["issues"][0]["path"], "knowledge/dangling-note.md")
        self.assertIn("no-such-record", result["issues"][0]["message"])

    def test_malformed_request_is_a_bad_request(self) -> None:
        status, result = self.write("POST", "/api/records", {"metadata": "not an object", "body": "x"})
        self.assertEqual(status, 400, result)
        status, result = self.write("POST", "/api/records", ["not", "an", "object"])
        self.assertEqual(status, 400, result)

    # -- edit -----------------------------------------------------------------

    def test_edit_changes_body_and_metadata_and_chains_hashes(self) -> None:
        self.assertEqual(self.create(_note("edited-note"))[0], 201)
        first = self.sha("knowledge/edited-note.md")

        status, result = self.write(
            "PATCH",
            "/api/records/edited-note",
            {"expected_sha256": first, "metadata": {"title": "Renamed", "tags": ["x"]}, "body": "New body.\n"},
        )
        self.assertEqual(status, 200, result)
        self.assertEqual(result["content_sha256"], self.sha("knowledge/edited-note.md"))
        text = (self.root / "knowledge" / "edited-note.md").read_text(encoding="utf-8")
        self.assertIn("title: Renamed", text)
        self.assertTrue(text.endswith("New body.\n"))

        # The returned hash is enough for the next edit.
        status, second = self.write(
            "PATCH",
            "/api/records/edited-note",
            {"expected_sha256": result["content_sha256"], "metadata": {"tags": None}},
        )
        self.assertEqual(status, 200, second)
        self.assertNotIn("tags:", (self.root / "knowledge" / "edited-note.md").read_text(encoding="utf-8"))

    def test_stale_hash_is_a_conflict_and_writes_nothing(self) -> None:
        self.assertEqual(self.create(_note("stale-note"))[0], 201)
        stale = self.sha("knowledge/stale-note.md")
        status, _ = self.write("PATCH", "/api/records/stale-note", {"expected_sha256": stale, "body": "One.\n"})
        self.assertEqual(status, 200)
        current = self.sha("knowledge/stale-note.md")

        status, result = self.write("PATCH", "/api/records/stale-note", {"expected_sha256": stale, "body": "Two.\n"})

        self.assertEqual(status, 409, result)
        self.assertEqual(result["error"], "conflict")
        self.assertEqual(result["current_sha256"], current)
        self.assertEqual(self.sha("knowledge/stale-note.md"), current)

    def test_edit_follows_kos_update_immutable_fields(self) -> None:
        relative = f"projects/{FIXTURE_PROJECT_ID}/{FIXTURE_PROPOSED_ID}.md"
        status, result = self.write(
            "PATCH",
            f"/api/records/{FIXTURE_PROPOSED_ID}",
            {"expected_sha256": self.sha(relative), "metadata": {"status": "archived"}},
        )
        self.assertEqual(status, 422, result)
        self.assertIn("must not change status", result["detail"])

    def test_unknown_id_is_not_found(self) -> None:
        status, result = self.write("PATCH", "/api/records/no-such-record", {"expected_sha256": "0" * 64})
        self.assertEqual(status, 404, result)
        self.assertEqual(result["error"], "not_found")

    # -- request origin -------------------------------------------------------

    def test_writes_without_the_token_are_refused(self) -> None:
        payload = {"metadata": _note("tokenless-note"), "body": "x\n"}
        status, result = _request(self.base_url, "POST", "/api/records", payload)
        self.assertEqual(status, 403, result)
        status, result = _request(
            self.base_url, "POST", "/api/records", payload, headers={TOKEN_HEADER: "wrong"}
        )
        self.assertEqual(status, 403, result)
        self.assertFalse((self.root / "knowledge" / "tokenless-note.md").exists())

    def test_cross_origin_and_foreign_host_writes_are_refused(self) -> None:
        payload = {"metadata": _note("foreign-note"), "body": "x\n"}
        for headers in (
            {"Origin": "https://evil.example"},
            {"Sec-Fetch-Site": "cross-site"},
            {"Host": "evil.example"},
        ):
            with self.subTest(headers=headers):
                status, result = self.write("POST", "/api/records", payload, **headers)
                self.assertEqual(status, 403, result)
        self.assertFalse((self.root / "knowledge" / "foreign-note.md").exists())
        # The token itself is not served to a rebinding host name.
        status, _ = _request(self.base_url, "GET", "/api/session", headers={"Host": "evil.example"})
        self.assertEqual(status, 403)

    def test_loopback_origin_is_accepted(self) -> None:
        status, result = self.write(
            "POST",
            "/api/records",
            {"metadata": _note("dev-origin-note"), "body": "x\n"},
            Origin="http://localhost:5173",
        )
        self.assertEqual(status, 201, result)


class ReindexFailureTests(unittest.TestCase):
    """If the canonical write succeeds but reindexing fails, the write is
    reported as done, with the index failure alongside it."""

    def test_create_and_edit_report_an_index_failure_without_failing_the_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_decision_fixture(root)
            workspace = Workspace(root)
            broken = WorkspaceError("derived indexes could not be rebuilt")

            with patch.object(capture_module, "refresh_derived_indexes", side_effect=broken):
                created = library.create_record(workspace, metadata=_note("index-failure-note"), body="x\n")
            path = root / "knowledge" / "index-failure-note.md"
            self.assertTrue(path.is_file())
            self.assertFalse(created.index_refreshed)
            self.assertIn("could not be rebuilt", created.index_error)
            self.assertEqual(created.content_sha256, hashlib.sha256(path.read_bytes()).hexdigest())

            with patch.object(mutations_module, "refresh_derived_indexes", side_effect=broken):
                edited = library.edit_record(
                    workspace,
                    "index-failure-note",
                    expected_sha256=created.content_sha256,
                    changes={},
                    body="y\n",
                )
            self.assertFalse(edited.index_refreshed)
            self.assertEqual(edited.content_sha256, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertTrue(path.read_text(encoding="utf-8").endswith("y\n"))


if __name__ == "__main__":
    unittest.main()
