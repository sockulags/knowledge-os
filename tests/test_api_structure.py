"""The structure endpoints against a served workspace that is its own Git
repository: create a project and folders, move and rename pages and folders,
and check the error mapping and that each change is exactly one commit with a
readable message covering every touched path."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import yaml
from reader_support import serve

from knowledge_os.init_workspace import init_workspace
from knowledge_os.model import content_sha256, parse_document
from knowledge_os.workspace import Workspace, validate_workspace

PORT = 8861
TOKEN_HEADER = "X-KOS-Write-Token"
GIT = shutil.which("git")


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.rstrip()


def write_page(root: Path, relative: str, record_id: str, project: str, body: str) -> None:
    metadata = {
        "id": record_id,
        "title": record_id.replace("-", " ").capitalize(),
        "type": "project",
        "status": "active",
        "scope": f"project:{project}",
        "created": "2026-09-01",
        "updated": "2026-09-01",
        "provenance": [{"kind": "fixture", "reference": "test"}],
    }
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{yaml.safe_dump(metadata, sort_keys=False)}---\n\n{body}", encoding="utf-8")


@unittest.skipIf(GIT is None, "git is not installed")
class StructureApiTests(unittest.TestCase):
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

    def post(self, path: str, payload: dict) -> tuple[int, dict]:
        return self.request("POST", path, payload)

    def project(self, project_id: str, title: str) -> None:
        status, body = self.post("/api/projects", {"id": project_id, "title": title})
        self.assertEqual(status, 201, body)

    def folder(self, project_id: str, path: str, title: str) -> dict:
        status, body = self.post(f"/api/projects/{project_id}/folders", {"path": path, "title": title})
        self.assertEqual(status, 201, body)
        return body

    def commit_page(self, relative: str, record_id: str, project: str, body: str) -> None:
        write_page(self.root, relative, record_id, project, body)
        git(self.root, "add", "--", relative)
        git(self.root, "commit", "--quiet", "-m", f"Add {record_id}")

    def sha(self, relative: str) -> str:
        return content_sha256(self.root / relative)

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

    def test_create_project_and_nested_folders(self) -> None:
        status, body = self.post("/api/projects", {"id": "gamma", "title": "Gamma", "description": "What Gamma is.\n"})
        self.assertEqual(status, 201, body)
        self.assertEqual(body["path"], "projects/gamma/README.md")
        self.assertEqual(body["content_sha256"], self.sha("projects/gamma/README.md"))
        self.assertTrue(body["commit"]["committed"], body["commit"])
        self.assertEqual(self.last_commit(), ("Create project Gamma", {"projects/gamma/README.md"}))
        self.assertEqual(parse_document(self.root / body["path"], check_filename=False).body, "What Gamma is.\n")

        created = self.folder("gamma", "notes", "Notes")
        self.assertEqual(created["id"], "gamma-notes")
        self.assertEqual(self.last_commit(), ("Create folder Notes", {"projects/gamma/notes/README.md"}))
        self.folder("gamma", "notes/deep", "Deep")

        status, nav = self.request("GET", "/api/nav")
        tree = next(project for project in nav["projects"] if project["id"] == "gamma")["tree"]
        self.assertEqual(tree["path"], "")
        notes = tree["children"][0]
        self.assertEqual((notes["path"], notes["overview"]["id"]), ("notes", "gamma-notes"))
        self.assertEqual(notes["children"][0]["path"], "notes/deep")
        self.assert_clean_and_valid()

    def test_create_errors_map_to_statuses(self) -> None:
        self.project("delta", "Delta")
        head = self.head()
        cases = [
            ("/api/projects", {"id": "delta", "title": "Again"}, 409, "duplicate"),
            ("/api/projects", {"id": "Bad Id", "title": "Bad"}, 422, "validation"),
            ("/api/projects", {"title": "No id"}, 400, "bad_request"),
            ("/api/projects/delta/folders", {"path": "x", "title": 3}, 400, "bad_request"),
            ("/api/projects/nope/folders", {"path": "x", "title": "X"}, 404, "not_found"),
            ("/api/projects/delta/folders", {"path": "Two Words", "title": "X"}, 422, "validation"),
        ]
        for path, payload, expected_status, kind in cases:
            with self.subTest(path=path, payload=payload):
                status, body = self.post(path, payload)
                self.assertEqual((status, body.get("error")), (expected_status, kind), body)
        self.folder("delta", "notes", "Notes")
        status, body = self.post("/api/projects/delta/folders", {"path": "notes", "title": "Notes"})
        self.assertEqual((status, body["error"]), (409, "duplicate"))
        status, body = self.request("POST", "/api/projects", {"id": "epsilon", "title": "E"}, token=False)
        self.assertEqual(status, 403)
        self.assertEqual(git(self.root, "rev-parse", "HEAD~1"), head)  # only the folder commit
        self.assertFalse((self.root / "projects/epsilon").exists())

    def test_move_page_is_one_commit_with_every_touched_path(self) -> None:
        self.project("zeta", "Zeta")
        self.folder("zeta", "archive", "Archive")
        self.folder("zeta", "notes", "Notes")
        self.commit_page("projects/zeta/notes/zeta-kickoff.md", "zeta-kickoff", "zeta", "Up to [notes](README.md).\n")
        self.commit_page("projects/zeta/zeta-plan.md", "zeta-plan", "zeta", "See [kickoff](notes/zeta-kickoff.md#agenda).\n")
        before = self.head()
        status, body = self.post(
            "/api/records/zeta-kickoff/move",
            {"expected_sha256": self.sha("projects/zeta/notes/zeta-kickoff.md"), "folder": "archive"},
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body["path"], "projects/zeta/archive/zeta-kickoff.md")
        self.assertEqual(body["content_sha256"], self.sha(body["path"]))
        changed = {item["path"]: item for item in body["changed"]}
        self.assertEqual(changed[body["path"]]["old_path"], "projects/zeta/notes/zeta-kickoff.md")
        self.assertEqual(changed["projects/zeta/zeta-plan.md"]["content_sha256"], self.sha("projects/zeta/zeta-plan.md"))
        message, files = self.last_commit()
        self.assertEqual(message, "Move Zeta kickoff to Archive")
        self.assertEqual(
            files,
            {"projects/zeta/notes/zeta-kickoff.md", "projects/zeta/archive/zeta-kickoff.md", "projects/zeta/zeta-plan.md"},
        )
        self.assertEqual(git(self.root, "rev-parse", "HEAD~1"), before)
        self.assertIn("(archive/zeta-kickoff.md#agenda)", (self.root / "projects/zeta/zeta-plan.md").read_text("utf-8"))
        self.assert_clean_and_valid()

        # Back to the top level: named after the project.
        status, body = self.post(
            "/api/records/zeta-kickoff/move", {"expected_sha256": body["content_sha256"], "folder": ""}
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(self.last_commit()[0], "Move Zeta kickoff to Zeta")

    def test_move_page_conflicts_and_refusals_write_nothing(self) -> None:
        self.project("eta", "Eta")
        self.folder("eta", "notes", "Notes")
        self.commit_page("projects/eta/eta-page.md", "eta-page", "eta", "Body.\n")
        head = self.head()
        sha = self.sha("projects/eta/eta-page.md")
        cases = [
            ({"expected_sha256": "0" * 64, "folder": "notes"}, 409, "conflict"),
            ({"expected_sha256": "short", "folder": "notes"}, 400, "bad_request"),
            ({"expected_sha256": sha}, 400, "bad_request"),
            ({"expected_sha256": sha, "folder": "missing"}, 404, "not_found"),
            ({"expected_sha256": sha, "folder": ""}, 422, "validation"),
            ({"expected_sha256": sha, "folder": "", "project": "nope"}, 404, "not_found"),
        ]
        for payload, expected_status, kind in cases:
            with self.subTest(payload=payload):
                status, body = self.post("/api/records/eta-page/move", payload)
                self.assertEqual((status, body.get("error")), (expected_status, kind), body)
                if kind == "conflict":
                    self.assertEqual(body["current_sha256"], sha)
        status, body = self.post("/api/records/nope/move", {"expected_sha256": sha, "folder": ""})
        self.assertEqual(status, 404)
        self.assertEqual(self.head(), head)
        self.assert_clean_and_valid()

    def test_move_to_another_project_needs_the_flag(self) -> None:
        self.project("theta", "Theta")
        self.project("iota", "Iota")
        self.folder("iota", "inbox", "Inbox")
        self.commit_page("projects/theta/theta-idea.md", "theta-idea", "theta", "An idea.\n")
        head = self.head()
        payload = {"expected_sha256": self.sha("projects/theta/theta-idea.md"), "folder": "inbox", "project": "iota"}
        status, body = self.post("/api/records/theta-idea/move", payload)
        self.assertEqual((status, body["error"]), (422, "validation"))
        self.assertIn("changes its scope", body["detail"])
        self.assertEqual(self.head(), head)
        status, body = self.post("/api/records/theta-idea/move", {**payload, "allow_scope_change": True})
        self.assertEqual(status, 200, body)
        self.assertTrue(body["scope_changed"])
        self.assertEqual(body["project"], "iota")
        self.assertEqual(self.last_commit()[0], "Move Theta idea to Inbox in Iota")
        self.assertEqual(
            parse_document(self.root / body["path"]).metadata["scope"], "project:iota"
        )
        self.assert_clean_and_valid()

    def test_rename_page(self) -> None:
        self.project("kappa", "Kappa")
        self.commit_page("projects/kappa/kappa-draft.md", "kappa-draft", "kappa", "Text.\n")
        status, body = self.post(
            "/api/records/kappa-draft/rename",
            {"expected_sha256": self.sha("projects/kappa/kappa-draft.md"), "title": "Final plan"},
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body["title"], "Final plan")
        self.assertEqual(self.last_commit(), ("Rename Kappa draft to Final plan", {"projects/kappa/kappa-draft.md"}))
        status, body = self.post("/api/records/kappa-draft/rename", {"expected_sha256": "1" * 64, "title": "X"})
        self.assertEqual((status, body["error"]), (409, "conflict"))
        status, body = self.post(
            "/api/records/kappa-draft/rename", {"expected_sha256": self.sha("projects/kappa/kappa-draft.md"), "title": " "}
        )
        self.assertEqual((status, body["error"]), (422, "validation"))
        self.assert_clean_and_valid()

    def test_move_and_rename_folders(self) -> None:
        self.project("lambda", "Lambda")
        self.folder("lambda", "notes", "Notes")
        self.folder("lambda", "notes/meetings", "Meetings")
        self.folder("lambda", "archive", "Archive")
        self.commit_page("projects/lambda/notes/meetings/lambda-sync.md", "lambda-sync", "lambda", "Up [one](../README.md).\n")
        self.commit_page("projects/lambda/lambda-index.md", "lambda-index", "lambda", "[m](notes/meetings/README.md)\n")

        status, body = self.post(
            "/api/projects/lambda/folders/move", {"path": "notes/meetings", "to_parent": "archive"}
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body["folder"], "archive/meetings")
        message, files = self.last_commit()
        self.assertEqual(message, "Move folder Meetings to Archive")
        self.assertEqual(
            files,
            {
                "projects/lambda/notes/meetings/README.md",
                "projects/lambda/notes/meetings/lambda-sync.md",
                "projects/lambda/archive/meetings/README.md",
                "projects/lambda/archive/meetings/lambda-sync.md",
                "projects/lambda/lambda-index.md",
            },
        )
        self.assertIn("(archive/meetings/README.md)", (self.root / "projects/lambda/lambda-index.md").read_text("utf-8"))

        status, body = self.post(
            "/api/projects/lambda/folders/move", {"path": "notes", "name": "journal", "title": "Journal"}
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(self.last_commit()[0], "Rename folder Notes to Journal")
        self.assertTrue((self.root / "projects/lambda/journal/README.md").is_file())

        head = self.head()
        for payload, expected_status, kind in [
            ({"path": "journal", "to_parent": "journal"}, 422, "validation"),
            ({"path": "journal", "name": "archive"}, 409, "duplicate"),
            ({"path": "missing", "name": "x"}, 404, "not_found"),
            ({"path": "journal", "to_project": "zzz"}, 404, "not_found"),
            ({"path": "journal", "allow_scope_change": "yes"}, 400, "bad_request"),
            ({"path": "journal", "name": "j2", "expected": {"projects/lambda/lambda-index.md": "2" * 64}}, 409, "conflict"),
        ]:
            with self.subTest(payload=payload):
                status, body = self.post("/api/projects/lambda/folders/move", payload)
                self.assertEqual((status, body.get("error")), (expected_status, kind), body)
        self.assertEqual(self.head(), head)
        self.assert_clean_and_valid()

    def test_a_page_that_was_never_committed_can_still_be_moved(self) -> None:
        self.project("mu", "Mu")
        self.folder("mu", "notes", "Notes")
        write_page(self.root, "projects/mu/mu-loose.md", "mu-loose", "mu", "Loose.\n")
        status, body = self.post(
            "/api/records/mu-loose/move", {"expected_sha256": self.sha("projects/mu/mu-loose.md"), "folder": "notes"}
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(body["commit"]["committed"], body["commit"])
        self.assertEqual(self.last_commit(), ("Move Mu loose to Notes", {"projects/mu/notes/mu-loose.md"}))
        self.assert_clean_and_valid()


if __name__ == "__main__":
    unittest.main()
