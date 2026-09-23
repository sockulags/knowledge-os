"""Git auto-commit and sync, against real temporary repositories.

Each test builds a bare "remote" and two clones (A and B) of one ``kos
init`` workspace inside a temporary directory. Git never sees the user's own
configuration: ``HOME`` and ``GIT_CONFIG_GLOBAL`` point into the temporary
directory, ``GIT_CONFIG_NOSYSTEM`` drops the system file (and with it any
credential helper that could open a prompt), and each clone gets its own
identity. The only remotes are local paths or loopback addresses.
"""

from __future__ import annotations

import http.server
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from reader_support import serve

from knowledge_os import gitsync
from knowledge_os.init_workspace import init_workspace
from knowledge_os.model import content_sha256, parse_document
from knowledge_os.reader import library
from knowledge_os.workspace import Workspace, validate_workspace

PORT = 8846
GIT = shutil.which("git")


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.rstrip()


def configure(repo: Path, name: str) -> None:
    git(repo, "config", "user.name", name)
    git(repo, "config", "user.email", f"{name.lower()}@example.invalid")
    git(repo, "config", "core.autocrlf", "false")


def note(record_id: str, title: str) -> dict[str, object]:
    return {
        "id": record_id,
        "title": title,
        "type": "knowledge",
        "status": "active",
        "scope": "general",
        "provenance": [{"kind": "user-authored", "reference": f"test:{record_id}"}],
    }


def sha(workspace: Workspace, rel_path: str) -> str:
    return content_sha256(workspace.root / rel_path)


@unittest.skipIf(GIT is None, "git is not installed")
class GitTestCase(unittest.TestCase):
    """Isolated Git environment plus a remote and two clones of one workspace."""

    def setUp(self) -> None:
        self._temp = tempfile.mkdtemp(prefix="kos-git-")
        self.addCleanup(self._cleanup)
        self.base = Path(self._temp).resolve()
        home = self.base / "home"
        home.mkdir()
        global_config = self.base / "gitconfig"
        global_config.write_text("", encoding="utf-8")
        environment = {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "GIT_CONFIG_GLOBAL": str(global_config),
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        patcher = patch.dict(os.environ, environment)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_DIR"):
            os.environ.pop(name, None)

    def _cleanup(self) -> None:
        # Git marks object files read-only on Windows.
        def force(function, path, _info):  # type: ignore[no-untyped-def]
            os.chmod(path, 0o700)
            function(path)

        shutil.rmtree(self._temp, onerror=force)

    def make_remote_and_clones(self) -> tuple[Workspace, Workspace, Path]:
        remote = self.base / "remote.git"
        git(self.base, "init", "--quiet", "--bare", "-b", "main", str(remote))
        a_root = init_workspace(self.base / "a")
        git(a_root, "init", "--quiet", "-b", "main")
        configure(a_root, "Alice")
        git(a_root, "add", "-A")
        git(a_root, "commit", "--quiet", "-m", "Initial knowledge base")
        git(a_root, "remote", "add", "origin", str(remote))
        git(a_root, "push", "--quiet", "-u", "origin", "main")
        b_root = self.base / "b"
        git(self.base, "clone", "--quiet", str(remote), str(b_root))
        configure(b_root, "Bob")
        a, b = Workspace(a_root), Workspace(b_root)
        from knowledge_os.index import rebuild_indexes

        rebuild_indexes(b)
        return a, b, remote

    def create(self, workspace: Workspace, record_id: str, title: str, body: str = "First version.\n") -> library.WriteResult:
        result = library.create_record(workspace, metadata=note(record_id, title), body=body)
        self.assertTrue(result.commit and result.commit.committed, result.commit)
        return result

    def edit(self, workspace: Workspace, record_id: str, path: str, body: str) -> library.WriteResult:
        return library.edit_record(
            workspace, record_id, expected_sha256=sha(workspace, path), changes={}, body=body
        )


class AutoCommitTests(GitTestCase):
    def test_commits_only_the_touched_paths_with_a_readable_message(self) -> None:
        a, _b, _remote = self.make_remote_and_clones()
        # Unrelated changes made outside the app: modified, untracked, staged.
        (a.root / "knowledge" / "README.md").write_text("# Knowledge\n\nChanged by hand.\n", encoding="utf-8")
        (a.root / "inbox" / "scratch.md").write_text("scratch\n", encoding="utf-8")
        (a.root / "tooling" / "README.md").write_text("# Tooling\n\nStaged by hand.\n", encoding="utf-8")
        git(a.root, "add", "tooling/README.md")

        result = self.create(a, "git-note", "Git note")

        self.assertEqual(result.commit.message, "Create Git note")
        self.assertEqual(git(a.root, "log", "-1", "--format=%s"), "Create Git note")
        self.assertEqual(git(a.root, "log", "-1", "--format=%an <%ae>"), "Alice <alice@example.invalid>")
        self.assertEqual(git(a.root, "show", "--name-only", "--format=", "HEAD").splitlines(), [result.path])
        status = git(a.root, "status", "--porcelain")
        self.assertIn(" M knowledge/README.md", status)
        self.assertIn("?? inbox/scratch.md", status)
        self.assertIn("M  tooling/README.md", status)  # still staged, not committed
        self.assertEqual(git(a.root, "ls-files", "indexes"), "indexes/README.md")

        edited = self.edit(a, "git-note", result.path, "Second version.\n")
        self.assertEqual(edited.commit.message, "Edit Git note")
        self.assertEqual(git(a.root, "show", "--name-only", "--format=", "HEAD").splitlines(), [result.path])

    def test_decision_actions_commit_with_decision_messages(self) -> None:
        a, _b, _remote = self.make_remote_and_clones()
        decision = note("pick-git", "Pick Git")
        decision["record_kind"] = "decision"
        decision["status"] = "draft"
        created = library.create_record(a, metadata=decision, body="Use Git.\n")
        accepted = library.accept_record(a, "pick-git", expected_sha256=created.content_sha256)
        self.assertTrue(accepted.commit.committed)
        self.assertEqual(git(a.root, "log", "-1", "--format=%s"), "Accept decision Pick Git")

    def test_no_repository_means_no_commit_and_a_reason(self) -> None:
        root = init_workspace(self.base / "plain")
        workspace = Workspace(root)
        result = library.create_record(workspace, metadata=note("plain-note", "Plain"), body="Text.\n")
        self.assertFalse(result.commit.committed)
        self.assertEqual(result.commit.skipped, "not_a_repo")
        self.assertIn("git init", result.commit.detail)
        status = library.sync_status(workspace)
        self.assertFalse(status.available)
        self.assertEqual(status.reason, "not_a_repo")

    def test_workspace_nested_in_another_repository_is_not_committed(self) -> None:
        outer = self.base / "outer"
        outer.mkdir()
        git(outer, "init", "--quiet", "-b", "main")
        configure(outer, "Outer")
        root = init_workspace(outer / "kb")
        result = library.create_record(Workspace(root), metadata=note("nested", "Nested"), body="Text.\n")
        self.assertEqual(result.commit.skipped, "not_a_repo")
        self.assertIn("inside the Git repository", result.commit.detail)
        self.assertEqual(subprocess.run(["git", "rev-parse", "-q", "--verify", "HEAD"], cwd=outer).returncode, 1)

    def test_missing_identity_is_reported_not_invented(self) -> None:
        root = init_workspace(self.base / "anon")
        git(root, "init", "--quiet", "-b", "main")
        git(root, "config", "user.useConfigOnly", "true")
        result = library.create_record(Workspace(root), metadata=note("anon", "Anon"), body="Text.\n")
        self.assertFalse(result.commit.committed)
        self.assertEqual(result.commit.skipped, "no_identity")
        self.assertIn("git config user.name", result.commit.detail)
        self.assertIsNone(library.sync_status(Workspace(root)).identity)


class SyncTests(GitTestCase):
    def test_fast_forward_both_directions_and_reindex(self) -> None:
        a, b, _remote = self.make_remote_and_clones()
        created = self.create(a, "shared-note", "Shared note")
        status = library.sync_status(a)
        self.assertEqual((status.ahead, status.behind, status.upstream), (1, 0, "origin/main"))
        self.assertIsNone(status.last_sync)

        pushed = library.run_sync(a)
        self.assertEqual((pushed.pulled, pushed.pushed, pushed.reindexed), (0, 1, False))
        self.assertIsNotNone(library.sync_status(a).last_sync)

        pulled = library.run_sync(b)
        self.assertEqual((pulled.pulled, pulled.pushed, pulled.reindexed), (1, 0, True))
        self.assertIsNone(pulled.index_error)
        self.assertEqual((b.root / created.path).read_bytes(), (a.root / created.path).read_bytes())
        self.assertIn("shared-note", (b.root / "indexes" / "catalog.md").read_text(encoding="utf-8"))
        self.assertEqual([hit["id"] for hit in library.search(b, "Shared")], ["shared-note"])

        self.edit(b, "shared-note", created.path, "Edited on B.\n")
        self.assertEqual(library.run_sync(b).pushed, 1)
        back = library.run_sync(a)
        self.assertEqual((back.pulled, back.reindexed), (1, True))
        self.assertIn("Edited on B.", (a.root / created.path).read_text(encoding="utf-8"))
        for workspace in (a, b):
            status = library.sync_status(workspace)
            self.assertEqual((status.ahead, status.behind, status.uncommitted), (0, 0, 0))

    def test_pull_never_overwrites_uncommitted_local_changes(self) -> None:
        a, b, _remote = self.make_remote_and_clones()
        created = self.create(a, "guarded", "Guarded")
        library.run_sync(a)
        library.run_sync(b)
        self.edit(a, "guarded", created.path, "From A.\n")
        library.run_sync(a)
        target = b.root / created.path
        target.write_text(target.read_text(encoding="utf-8").replace("First version.", "Unsaved on B."), encoding="utf-8")
        with self.assertRaises(gitsync.GitSyncError) as caught:
            library.run_sync(b)
        self.assertEqual(caught.exception.kind, "blocked")
        self.assertIn("Unsaved on B.", target.read_text(encoding="utf-8"))
        self.assertFalse(library.sync_status(b).merging)

    def test_missing_remote_and_missing_upstream(self) -> None:
        root = init_workspace(self.base / "lonely")
        git(root, "init", "--quiet", "-b", "main")
        configure(root, "Lone")
        workspace = Workspace(root)
        self.create(workspace, "lonely-note", "Lonely")
        with self.assertRaises(gitsync.GitSyncError) as caught:
            library.run_sync(workspace)
        self.assertEqual(caught.exception.kind, "no_upstream")
        self.assertIn("git remote add origin", caught.exception.message)

        git(root, "remote", "add", "origin", str(self.base / "nowhere.git"))
        with self.assertRaises(gitsync.GitSyncError) as caught:
            library.run_sync(workspace)
        self.assertEqual(caught.exception.kind, "no_upstream")
        self.assertIn("git push -u origin main", caught.exception.message)
        self.assertIsNone(library.sync_status(workspace).upstream)


class ConflictTests(GitTestCase):
    def conflicted(self) -> tuple[Workspace, Workspace, str]:
        a, b, _remote = self.make_remote_and_clones()
        created = self.create(a, "contested", "Contested")
        library.run_sync(a)
        library.run_sync(b)
        self.edit(a, "contested", created.path, "Alice's version.\n")
        library.run_sync(a)
        self.edit(b, "contested", created.path, "Bob's version.\n")
        with self.assertRaises(gitsync.GitSyncError) as caught:
            library.run_sync(b)
        self.assertEqual(caught.exception.kind, "conflict")
        self.assertEqual(caught.exception.conflicts, (created.path,))
        status = library.sync_status(b)
        self.assertTrue(status.merging)
        self.assertEqual(status.conflicts, 1)
        (conflict,) = library.sync_conflicts(b)
        self.assertEqual(conflict.path, created.path)
        self.assertIn("Bob's version.", conflict.ours)
        self.assertIn("Alice's version.", conflict.theirs)
        self.assertIn("<<<<<<<", conflict.working)
        return a, b, created.path

    def finish(self, a: Workspace, b: Workspace, path: str, expected: str) -> None:
        done = library.run_sync(b)
        self.assertEqual(done.state, "synced")
        self.assertGreaterEqual(done.pushed, 1)
        self.assertFalse(library.sync_status(b).merging)
        library.run_sync(a)
        self.assertEqual((a.root / path).read_bytes(), (b.root / path).read_bytes())
        self.assertIn(expected, (a.root / path).read_text(encoding="utf-8"))
        for workspace in (a, b):
            self.assertEqual(library.sync_status(workspace).uncommitted, 0)
            _documents, issues = validate_workspace(workspace)
            self.assertEqual(issues, [])

    def test_resolve_with_ours(self) -> None:
        a, b, path = self.conflicted()
        outcome = library.resolve_sync_conflict(b, path, "ours", None)
        self.assertEqual((outcome.remaining, outcome.issues), ((), ()))
        self.finish(a, b, path, "Bob's version.")

    def test_resolve_with_theirs(self) -> None:
        a, b, path = self.conflicted()
        library.resolve_sync_conflict(b, path, "theirs", None)
        self.finish(a, b, path, "Alice's version.")

    def test_resolve_with_edited_text(self) -> None:
        a, b, path = self.conflicted()
        (conflict,) = library.sync_conflicts(b)
        merged = conflict.ours.replace("Bob's version.", "Both versions, merged by hand.")
        library.resolve_sync_conflict(b, path, "merged", merged)
        self.finish(a, b, path, "Both versions, merged by hand.")

    def test_lint_failure_blocks_completion_until_fixed(self) -> None:
        a, b, path = self.conflicted()
        outcome = library.resolve_sync_conflict(b, path, "merged", "no frontmatter at all\n")
        self.assertEqual(outcome.remaining, ())
        self.assertTrue(outcome.issues)
        self.assertEqual(outcome.issues[0][0], path)
        with self.assertRaises(gitsync.GitSyncError) as caught:
            library.run_sync(b)
        self.assertEqual(caught.exception.kind, "lint")
        self.assertTrue(any(item_path == path for item_path, _message in caught.exception.issues))
        self.assertTrue(library.sync_status(b).merging)  # nothing was committed
        # The resolved file is still listed, and a version can be chosen again.
        (listed,) = library.sync_conflicts(b)
        self.assertTrue(listed.resolved)
        self.assertIn("Alice's version.", listed.theirs)
        self.assertEqual(listed.working, "no frontmatter at all\n")
        library.resolve_sync_conflict(b, path, "theirs", None)
        self.finish(a, b, path, "Alice's version.")

    def test_abort_restores_the_state_before_the_pull(self) -> None:
        _a, b, path = self.conflicted()
        library.abort_sync(b)
        self.assertFalse(library.sync_status(b).merging)
        self.assertIn("Bob's version.", (b.root / path).read_text(encoding="utf-8"))
        self.assertEqual(library.sync_status(b).ahead, 1)

    def test_only_conflicted_files_can_be_resolved(self) -> None:
        _a, b, _path = self.conflicted()
        with self.assertRaises(gitsync.GitSyncError) as caught:
            library.resolve_sync_conflict(b, "knowledge-os.toml", "merged", "x")
        self.assertEqual(caught.exception.kind, "not_conflicted")


class _Unauthorized(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="test"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        pass


class RemoteFailureTests(GitTestCase):
    def workspace_with_remote(self, url: str) -> Workspace:
        a, _b, _remote = self.make_remote_and_clones()
        git(a.root, "remote", "set-url", "origin", url)
        return a

    def test_unreachable_remote_is_a_network_error(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        workspace = self.workspace_with_remote(f"http://127.0.0.1:{port}/kb.git")
        started = time.monotonic()
        with self.assertRaises(gitsync.GitSyncError) as caught:
            gitsync.sync(workspace, timeout=20)
        self.assertEqual(caught.exception.kind, "network")
        self.assertLess(time.monotonic() - started, 20)

    def test_silent_remote_times_out_instead_of_hanging(self) -> None:
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(8)
        self.addCleanup(listener.close)
        port = listener.getsockname()[1]
        workspace = self.workspace_with_remote(f"http://127.0.0.1:{port}/kb.git")
        started = time.monotonic()
        with self.assertRaises(gitsync.GitSyncError) as caught:
            gitsync.sync(workspace, timeout=2)
        elapsed = time.monotonic() - started
        self.assertEqual(caught.exception.kind, "timeout")
        self.assertLess(elapsed, 15)

    def test_missing_credentials_are_an_auth_error_not_a_prompt(self) -> None:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Unauthorized)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        workspace = self.workspace_with_remote(f"http://user:secret-token@127.0.0.1:{port}/kb.git")
        with self.assertRaises(gitsync.GitSyncError) as caught:
            gitsync.sync(workspace, timeout=20)
        self.assertEqual(caught.exception.kind, "auth")
        self.assertNotIn("secret-token", caught.exception.message)


class SyncApiTests(GitTestCase):
    def request(self, base: str, method: str, path: str, payload: object | None = None, token: str | None = None) -> tuple[int, dict]:
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(base + path, data=data, method=method)
        if payload is not None:
            request.add_header("Content-Type", "application/json")
        if token is not None:
            request.add_header("X-KOS-Write-Token", token)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_status_sync_conflict_and_resolve_over_http(self) -> None:
        a, b, _remote = self.make_remote_and_clones()
        created = self.create(a, "api-note", "Api note")
        library.run_sync(a)
        library.run_sync(b)
        self.edit(a, "api-note", created.path, "A over HTTP.\n")
        library.run_sync(a)
        with serve(b.root, PORT) as base:
            code, status = self.request(base, "GET", "/api/sync/status")
            self.assertEqual(code, 200)
            self.assertTrue(status["available"])
            self.assertEqual(status["upstream"], "origin/main")
            code, session = self.request(base, "GET", "/api/session")
            token = session["write_token"]
            self.assertEqual(self.request(base, "POST", "/api/sync", {})[0], 403)

            code, edit = self.request(
                base,
                "PATCH",
                "/api/records/api-note",
                {"expected_sha256": sha(b, created.path), "body": "B over HTTP.\n"},
                token,
            )
            self.assertEqual(code, 200)
            self.assertEqual(edit["commit"]["committed"], True)
            self.assertEqual(edit["commit"]["message"], "Edit Api note")

            code, failed = self.request(base, "POST", "/api/sync", {}, token)
            self.assertEqual(code, 409)
            self.assertEqual(failed["error"], "conflict")
            self.assertEqual(failed["conflicts"], [created.path])
            self.assertTrue(failed["status"]["merging"])

            code, conflicts = self.request(base, "GET", "/api/sync/conflicts")
            self.assertEqual(code, 200)
            (item,) = conflicts["files"]
            self.assertIn("B over HTTP.", item["ours"])
            self.assertIn("A over HTTP.", item["theirs"])

            code, resolved = self.request(
                base, "POST", "/api/sync/resolve", {"path": created.path, "choice": "theirs"}, token
            )
            self.assertEqual(code, 200)
            self.assertEqual(resolved["remaining"], [])
            code, done = self.request(base, "POST", "/api/sync", {}, token)
            self.assertEqual(code, 200, done)
            self.assertEqual(done["state"], "synced")
            self.assertFalse(done["status"]["merging"])
            self.assertEqual(done["status"]["ahead"], 0)
        library.run_sync(a)
        self.assertEqual((a.root / created.path).read_bytes(), (b.root / created.path).read_bytes())
        self.assertEqual(parse_document(a.root / created.path).body.strip(), "A over HTTP.")


if __name__ == "__main__":
    unittest.main()
