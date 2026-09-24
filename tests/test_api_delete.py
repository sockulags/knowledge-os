"""Deleting pages and folders through the local API (issue #78), against a
served workspace that is its own Git repository: the preview a confirmation
dialog shows, the delete itself as exactly one commit covering every removed
and rewritten file, refusals that write nothing, and a withdrawal without a
reason."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import yaml
from reader_support import serve
from test_api_structure import git, write_page

from knowledge_os.init_workspace import init_workspace
from knowledge_os.model import content_sha256, parse_document
from knowledge_os.workspace import Workspace, validate_workspace

PORT = 8871
TOKEN_HEADER = "X-KOS-Write-Token"
GIT = shutil.which("git")


def write_decision(root: Path, relative: str, record_id: str, status: str, body: str = "We decide.\n") -> None:
    provenance: list[dict[str, str]] = [{"kind": "fixture", "reference": "test"}]
    if status == "active":
        provenance.append(
            {"kind": "decision-acceptance", "reference": "conversation:yes", "captured": "2026-09-02T10:00:00Z"}
        )
    metadata = {
        "id": record_id,
        "title": record_id.replace("-", " ").capitalize(),
        "type": "project",
        "record_kind": "decision",
        "status": status,
        "scope": "project:acme",
        "created": "2026-09-01",
        "updated": "2026-09-01",
        "provenance": provenance,
    }
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{yaml.safe_dump(metadata, sort_keys=False)}---\n\n{body}", encoding="utf-8")


@unittest.skipIf(GIT is None, "git is not installed")
class DeleteApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._stack = ExitStack()
        base = Path(cls._stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        home = base / "home"
        home.mkdir()
        (base / "gitconfig").write_text("", encoding="utf-8")
        cls._stack.enter_context(
            patch.dict(
                os.environ,
                {
                    "HOME": str(home),
                    "USERPROFILE": str(home),
                    "XDG_CONFIG_HOME": str(home / ".config"),
                    "GIT_CONFIG_GLOBAL": str(base / "gitconfig"),
                    "GIT_CONFIG_NOSYSTEM": "1",
                },
            )
        )
        cls.root = init_workspace(base / "kb")
        cls.workspace = Workspace(cls.root)
        git(cls.root, "init", "--quiet", "-b", "main")
        git(cls.root, "config", "user.name", "Alice")
        git(cls.root, "config", "user.email", "alice@example.invalid")
        git(cls.root, "config", "core.autocrlf", "false")
        git(cls.root, "add", "-A")
        git(cls.root, "commit", "--quiet", "-m", "Initial knowledge base")
        cls.base_url = cls._stack.enter_context(serve(cls.root, PORT))
        status, session = cls.request("GET", "/api/session")
        assert status == 200, session
        cls.token = session["write_token"]
        status, body = cls.request("POST", "/api/projects", {"id": "acme", "title": "Acme"})
        assert status == 201, body

    @classmethod
    def tearDownClass(cls) -> None:
        cls._stack.close()

    @classmethod
    def request(cls, method: str, path: str, payload: object | None = None, *, token: bool = True) -> tuple[int, dict]:
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(cls.base_url + path, data=data, method=method)
        if payload is not None:
            request.add_header("Content-Type", "application/json")
            if token:
                request.add_header(TOKEN_HEADER, cls.token)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    # -- helpers ------------------------------------------------------------

    def get(self, path: str) -> dict:
        status, body = self.request("GET", path)
        self.assertEqual(status, 200, body)
        return body

    def commit_all(self, message: str) -> None:
        git(self.root, "add", "-A", "--", "projects", "knowledge")
        git(self.root, "commit", "--quiet", "-m", message)

    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD")

    def last_commit(self) -> tuple[str, set[str]]:
        message = git(self.root, "log", "-1", "--format=%s")
        files = set(git(self.root, "show", "--name-only", "--no-renames", "--format=", "HEAD").splitlines())
        return message, files

    def assert_clean_and_valid(self) -> None:
        self.assertEqual(git(self.root, "status", "--porcelain", "--", "projects", "knowledge"), "")
        _documents, issues = validate_workspace(self.workspace)
        self.assertEqual(issues, [])

    # -- tests --------------------------------------------------------------

    def test_delete_a_page_with_references_is_one_commit(self) -> None:
        write_page(self.root, "projects/acme/page-gone.md", "page-gone", "acme", "Soon gone.\n")
        write_page(self.root, "projects/acme/page-keeper.md", "page-keeper", "acme", "See [it](page-gone.md).\n")
        keeper = self.root / "projects/acme/page-keeper.md"
        keeper.write_text(keeper.read_text(encoding="utf-8").replace("provenance:", "related:\n- page-gone\nprovenance:"),
                          encoding="utf-8")
        self.commit_all("Add pages")

        preview = self.get("/api/records/page-gone/delete-preview")
        self.assertEqual(preview["kind"], "page")
        self.assertTrue(preview["deletable"])
        self.assertEqual(preview["dialog"]["title"], "Delete “Page gone”?")
        self.assertEqual(preview["dialog"]["confirm"], "Delete")
        self.assertEqual([item["id"] for item in preview["cleaned"]], ["page-keeper"])
        self.assertEqual(preview["cleaned"][0]["fields"], ["related"])
        self.assertEqual([item["id"] for item in preview["linked"]], ["page-keeper"])
        self.assertEqual(preview["blockers"], [])

        status, result = self.request(
            "POST",
            "/api/records/page-gone/delete",
            {"expected_sha256": content_sha256(self.root / "projects/acme/page-gone.md"), "expected": preview["expected"]},
        )
        self.assertEqual(status, 200, result)
        self.assertEqual(result["deleted"], ["projects/acme/page-gone.md"])
        self.assertTrue(result["commit"]["committed"], result["commit"])
        message, files = self.last_commit()
        self.assertEqual(message, "Delete Page gone")
        self.assertEqual(files, {"projects/acme/page-gone.md", "projects/acme/page-keeper.md"})
        self.assertNotIn("related", parse_document(keeper, check_filename=False).metadata)
        self.assert_clean_and_valid()

    def test_delete_a_folder_with_contents_is_one_commit(self) -> None:
        status, body = self.request("POST", "/api/projects/acme/folders", {"path": "old-notes", "title": "Old notes"})
        self.assertEqual(status, 201, body)
        write_page(self.root, "projects/acme/old-notes/old-first.md", "old-first", "acme", "One.\n")
        write_page(self.root, "projects/acme/old-notes/deeper/old-second.md", "old-second", "acme", "Two.\n")
        (self.root / "projects/acme/old-notes/deeper/picture.png").write_bytes(b"\x89PNG")
        self.commit_all("Add old notes")

        query = urllib.parse.urlencode({"path": "old-notes"})
        preview = self.get(f"/api/projects/acme/folders/delete-preview?{query}")
        self.assertEqual(preview["kind"], "folder")
        self.assertEqual(preview["dialog"]["title"], "Delete the folder “Old notes”?")
        self.assertEqual(preview["dialog"]["other_files"], "and 1 other file")
        self.assertEqual({item["id"] for item in preview["records"]}, {"acme-old-notes", "old-first", "old-second"})

        status, result = self.request(
            "POST", "/api/projects/acme/folders/delete", {"path": "old-notes", "expected": preview["expected"]}
        )
        self.assertEqual(status, 200, result)
        message, files = self.last_commit()
        self.assertEqual(message, "Delete folder Old notes")
        self.assertEqual(
            files,
            {
                "projects/acme/old-notes/README.md",
                "projects/acme/old-notes/old-first.md",
                "projects/acme/old-notes/deeper/old-second.md",
                "projects/acme/old-notes/deeper/picture.png",
            },
        )
        self.assertFalse((self.root / "projects/acme/old-notes").exists())
        self.assert_clean_and_valid()

    def test_refusals_write_nothing(self) -> None:
        write_decision(self.root, "projects/acme/rule-in-force.md", "rule-in-force", "active")
        self.commit_all("Add a rule")
        head = self.head()

        preview = self.get("/api/records/rule-in-force/delete-preview")
        self.assertFalse(preview["deletable"])
        self.assertEqual(
            preview["blockers"],
            ["“Rule in force” is a decision in force. Propose a decision that replaces it instead."],
        )
        sha = content_sha256(self.root / "projects/acme/rule-in-force.md")
        status, result = self.request("POST", "/api/records/rule-in-force/delete", {"expected_sha256": sha})
        self.assertEqual(status, 422, result)
        status, result = self.request("POST", "/api/records/rule-in-force/delete", {"expected_sha256": "f" * 64})
        self.assertEqual(status, 409, result)
        status, result = self.request("POST", "/api/records/no-such-page/delete", {"expected_sha256": "f" * 64})
        self.assertEqual(status, 404, result)
        status, result = self.request("GET", "/api/records/no-such-page/delete-preview")
        self.assertEqual(status, 404, result)
        status, result = self.request("GET", "/api/projects/acme/folders/delete-preview")
        self.assertEqual(status, 400, result)
        status, result = self.request(
            "POST", "/api/records/rule-in-force/delete", {"expected_sha256": sha}, token=False
        )
        self.assertEqual(status, 403, result)
        overview = self.get("/api/records/acme/delete-preview")
        self.assertFalse(overview["deletable"])
        self.assertEqual(self.head(), head)
        self.assertTrue((self.root / "projects/acme/rule-in-force.md").exists())

    def test_record_payload_names_what_its_delete_action_removes(self) -> None:
        status, body = self.request("POST", "/api/projects/acme/folders", {"path": "kept", "title": "Kept"})
        self.assertEqual(status, 201, body)
        self.assertEqual(
            self.get(f"/api/records/{body['id']}")["editing"]["delete"],
            {"kind": "folder", "project_id": "acme", "path": "kept"},
        )
        self.assertIsNone(self.get("/api/records/acme")["editing"]["delete"])
        write_page(self.root, "projects/acme/kept/kept-plain.md", "kept-plain", "acme", "Plain.\n")
        self.assertEqual(self.get("/api/records/kept-plain")["editing"]["delete"], {"kind": "page"})

    def test_a_proposal_can_be_withdrawn_without_a_reason(self) -> None:
        write_decision(self.root, "projects/acme/maybe.md", "maybe", "draft")
        self.commit_all("Propose maybe")
        status, result = self.request(
            "POST",
            "/api/records/maybe/withdraw",
            {"expected_sha256": content_sha256(self.root / "projects/acme/maybe.md")},
        )
        self.assertEqual(status, 200, result)
        message, files = self.last_commit()
        self.assertEqual(message, "Withdraw decision Maybe")
        self.assertEqual(files, {"projects/acme/maybe.md"})
        page = self.get("/api/records/maybe")
        self.assertRegex(page["properties"]["source"]["value"][-1], r"^Withdrawn on \d{1,2} \w+ \d{4}$")
        self.assertRegex(page["properties"]["status"]["value"], r"^Withdrawn on .*, without being accepted$")
        # A withdrawn proposal may then be deleted.
        preview = self.get("/api/records/maybe/delete-preview")
        self.assertTrue(preview["deletable"])
        self.assertEqual(preview["dialog"]["notes"], ["It is a withdrawn proposal that was never in force."])
        self.assert_clean_and_valid()


if __name__ == "__main__":
    unittest.main()
