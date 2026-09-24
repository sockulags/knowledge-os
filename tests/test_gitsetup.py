"""Cloning a knowledge base from a URL and the guided sync setup (issue #56).

Built on ``test_gitsync.GitTestCase``: Git runs isolated from the user's own
configuration (``HOME``, ``GIT_CONFIG_GLOBAL``, ``GIT_CONFIG_NOSYSTEM``),
the only remotes are local bare repositories and loopback servers, and the
global identity is empty unless a test sets one.
"""

from __future__ import annotations

import http.server
import json
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from reader_support import serve
from test_gitsync import GitTestCase, _Unauthorized, configure, git

from knowledge_os import gitsetup
from knowledge_os.gitsync import GitSyncError
from knowledge_os.init_workspace import init_workspace
from knowledge_os.reader import library
from knowledge_os.workspace import Workspace

PORT = 8847


class _Servers:
    """Loopback endpoints for failure tests, closed by the test's cleanups."""

    @staticmethod
    def unauthorized(case: unittest.TestCase) -> str:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Unauthorized)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        case.addCleanup(server.server_close)
        case.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}/kb.git"

    @staticmethod
    def closed_port() -> str:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        return f"http://127.0.0.1:{port}/kb.git"

    @staticmethod
    def silent(case: unittest.TestCase) -> str:
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(8)
        case.addCleanup(listener.close)
        return f"http://127.0.0.1:{listener.getsockname()[1]}/kb.git"


class UrlValidationTests(unittest.TestCase):
    def test_accepts_the_usual_forms(self) -> None:
        for url in (
            "https://github.com/you/notes.git",
            "http://127.0.0.1:8080/kb.git",
            "ssh://git@example.com:2222/you/notes.git",
            "git@github.com:you/notes.git",
            "example.com:notes.git",
            "file:///C:/repos/notes.git",
            "C:\\repos\\notes.git",
            "D:/repos/notes.git",
            "\\\\server\\share\\notes.git",
            "/srv/git/notes.git",
            "https://you@github.com/you/notes.git",
        ):
            with self.subTest(url=url):
                self.assertEqual(gitsetup.validate_remote_url(f"  {url} "), url)

    def test_refuses_bad_forms_and_credentials(self) -> None:
        for url in (
            "",
            "   ",
            "notes",
            "relative/path.git",
            "ftp://example.com/notes.git",
            "ext::sh -c touch% /tmp/x",
            "-uhttps://example.com/x.git",
            "https://example.com/has space.git",
            "https:///no-host.git",
            "https://you:secret-token@github.com/you/notes.git",
        ):
            with self.subTest(url=url):
                with self.assertRaises(GitSyncError) as caught:
                    gitsetup.validate_remote_url(url)
                self.assertEqual(caught.exception.kind, "bad_url")
                self.assertNotIn("secret-token", caught.exception.message)


class CloneTests(GitTestCase):
    def remote_with_knowledge_base(self) -> Path:
        _a, _b, remote = self.make_remote_and_clones()
        return remote

    def test_clones_a_knowledge_base_and_builds_its_indexes(self) -> None:
        remote = self.remote_with_knowledge_base()
        phases: list[str] = []
        outcome = gitsetup.clone_workspace(str(remote), self.base / "clones" / "c", on_progress=lambda p: phases.append(p.phase))
        root = self.base / "clones" / "c"
        self.assertEqual(outcome.root, root)
        self.assertTrue(outcome.reindexed)
        self.assertEqual(outcome.issues, ())
        self.assertTrue((root / "knowledge-os.toml").is_file())
        self.assertTrue((root / "indexes" / "catalog.sqlite3").is_file())
        self.assertEqual(phases[0], "clone")
        self.assertIn("check", phases)
        self.assertEqual(phases[-1], "index")
        # The clone tracks the remote, so sync works right away.
        configure(root, "Carol")
        self.assertEqual(library.sync_status(Workspace(root)).upstream, "origin/main")
        self.assertEqual(gitsetup.setup_status(Workspace(root)).state, "ready")

    def test_clones_into_an_existing_empty_folder(self) -> None:
        remote = self.remote_with_knowledge_base()
        target = self.base / "empty"
        target.mkdir()
        outcome = gitsetup.clone_workspace(str(remote), target)
        self.assertTrue(outcome.reindexed)

    def test_repository_that_is_not_a_knowledge_base_is_reported_and_left_alone(self) -> None:
        plain = self.base / "plain"
        plain.mkdir()
        git(plain, "init", "--quiet", "-b", "main")
        configure(plain, "Alice")
        (plain / "README.md").write_text("# Not a knowledge base\n", encoding="utf-8")
        git(plain, "add", "-A")
        git(plain, "commit", "--quiet", "-m", "Plain")
        target = self.base / "clone-of-plain"
        with self.assertRaises(GitSyncError) as caught:
            gitsetup.clone_workspace(str(plain), target)
        self.assertEqual(caught.exception.kind, "not_a_knowledge_base")
        self.assertIn(str(target), caught.exception.message)
        self.assertTrue((target / "README.md").is_file(), "nothing destructive: the clone stays")

    def test_refuses_a_folder_that_is_not_empty(self) -> None:
        remote = self.remote_with_knowledge_base()
        target = self.base / "busy"
        target.mkdir()
        (target / "keep.txt").write_text("mine\n", encoding="utf-8")
        with self.assertRaises(GitSyncError) as caught:
            gitsetup.clone_workspace(str(remote), target)
        self.assertEqual(caught.exception.kind, "target_not_empty")
        self.assertEqual(sorted(path.name for path in target.iterdir()), ["keep.txt"])

    def test_auth_failure_is_reported_without_prompting_and_leaves_nothing(self) -> None:
        url = _Servers.unauthorized(self)
        target = self.base / "auth"
        started = time.monotonic()
        with self.assertRaises(GitSyncError) as caught:
            gitsetup.clone_workspace(url.replace("http://", "http://someone@"), target, idle_timeout=20)
        self.assertEqual(caught.exception.kind, "auth")
        self.assertNotIn("Cloning into", caught.exception.message)
        self.assertLess(time.monotonic() - started, 20)
        self.assertFalse(target.exists())

    def test_unreachable_remote_is_a_network_error(self) -> None:
        target = self.base / "unreachable"
        with self.assertRaises(GitSyncError) as caught:
            gitsetup.clone_workspace(_Servers.closed_port(), target, idle_timeout=20)
        self.assertEqual(caught.exception.kind, "network")
        self.assertFalse(target.exists())

    def test_missing_repository_is_not_found(self) -> None:
        target = self.base / "missing"
        with self.assertRaises(GitSyncError) as caught:
            gitsetup.clone_workspace(str(self.base / "no-such-repo.git"), target)
        self.assertEqual(caught.exception.kind, "not_found")
        self.assertFalse(target.exists())

    def test_silent_remote_times_out(self) -> None:
        target = self.base / "silent"
        started = time.monotonic()
        with self.assertRaises(GitSyncError) as caught:
            gitsetup.clone_workspace(_Servers.silent(self), target, idle_timeout=2)
        self.assertEqual(caught.exception.kind, "timeout")
        self.assertLess(time.monotonic() - started, 15)
        self.assertFalse(target.exists())

    def test_cancel_stops_git_and_removes_the_partial_clone(self) -> None:
        target = self.base / "cancelled"
        cancel = threading.Event()
        threading.Timer(1.0, cancel.set).start()
        started = time.monotonic()
        with self.assertRaises(GitSyncError) as caught:
            gitsetup.clone_workspace(_Servers.silent(self), target, idle_timeout=60, cancel=cancel)
        self.assertEqual(caught.exception.kind, "cancelled")
        self.assertLess(time.monotonic() - started, 15)
        self.assertFalse(target.exists())

    def test_cli_reports_json_lines_and_cancels_when_stdin_closes(self) -> None:
        remote = self.remote_with_knowledge_base()
        target = self.base / "cli"
        result = subprocess.run(
            [sys.executable, "-m", "knowledge_os", "clone", str(remote), str(target), "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            stdin=subprocess.DEVNULL,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(events[0]["event"], "progress")
        self.assertEqual(events[-1]["event"], "done")
        self.assertEqual(Path(events[-1]["root"]), target)
        self.assertTrue(events[-1]["reindexed"])

        cancelled = self.base / "cli-cancelled"
        process = subprocess.Popen(
            [sys.executable, "-m", "knowledge_os", "clone", _Servers.silent(self), str(cancelled), "--json", "--cancel-on-stdin-eof"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        time.sleep(2)
        assert process.stdin is not None
        process.stdin.close()
        stdout, _stderr = process.communicate(timeout=30)
        self.assertEqual(process.returncode, 1)
        last = json.loads(stdout.splitlines()[-1])
        self.assertEqual(last["event"], "error")
        self.assertEqual(last["error"], "cancelled")
        self.assertFalse(cancelled.exists())


class SetupTests(GitTestCase):
    def fresh(self, name: str = "kb") -> Workspace:
        return Workspace(init_workspace(self.base / name))

    def bare(self, name: str = "remote.git") -> Path:
        remote = self.base / name
        git(self.base, "init", "--quiet", "--bare", "-b", "main", str(remote))
        return remote

    def test_states_walk_from_init_to_ready(self) -> None:
        workspace = self.fresh()
        self.assertEqual(gitsetup.setup_status(workspace).state, "init")
        gitsetup.init_repository(workspace, identity=("Alice", "alice@example.invalid"))
        self.assertEqual(gitsetup.setup_status(workspace).state, "remote")
        remote = self.bare()
        outcome = gitsetup.connect_remote(workspace, str(remote))
        self.assertEqual(outcome.state, "published")
        self.assertEqual(outcome.pushed, 1)
        setup = gitsetup.setup_status(workspace)
        self.assertEqual(setup.state, "ready")
        self.assertEqual(setup.remote, "origin")
        status = library.sync_status(workspace)
        self.assertEqual(status.upstream, "origin/main")
        self.assertEqual(status.ahead, 0)
        self.assertEqual(git(remote, "rev-parse", "main"), git(workspace.root, "rev-parse", "HEAD"))

        # A second computer clones it, edits, syncs; the first sees the change.
        clone = gitsetup.clone_workspace(str(remote), self.base / "second")
        second = Workspace(clone.root)
        configure(second.root, "Bob")
        created = library.create_record(
            second,
            metadata={
                "id": "from-second",
                "title": "From the second computer",
                "type": "knowledge",
                "status": "active",
                "scope": "general",
                "provenance": [{"kind": "user-authored", "reference": "test:from-second"}],
            },
            body="Written on the second computer.\n",
        )
        self.assertTrue(created.commit and created.commit.committed)
        self.assertEqual(library.run_sync(second).pushed, 1)
        self.assertEqual(library.run_sync(workspace).pulled, 1)
        self.assertTrue((workspace.root / created.path).is_file())

    def test_init_needs_an_identity_and_changes_nothing_without_one(self) -> None:
        workspace = self.fresh()
        with self.assertRaises(GitSyncError) as caught:
            gitsetup.init_repository(workspace)
        self.assertEqual(caught.exception.kind, "no_identity")
        self.assertIn("--global", caught.exception.message)
        self.assertFalse((workspace.root / ".git").exists())

    def test_init_commits_current_files_but_not_generated_indexes(self) -> None:
        workspace = self.fresh()
        (workspace.root / ".gitignore").unlink()  # an older knowledge base without the rules
        (workspace.root / "inbox" / "note.md").write_text("an idea\n", encoding="utf-8")
        outcome = gitsetup.init_repository(workspace, identity=("Alice", "alice@example.invalid"))
        self.assertTrue(outcome.created_repository)
        tracked = git(workspace.root, "ls-files").splitlines()
        self.assertIn("knowledge-os.toml", tracked)
        self.assertIn("inbox/note.md", tracked)
        self.assertIn(".gitignore", tracked)
        self.assertIn("indexes/README.md", tracked)
        self.assertFalse([path for path in tracked if path.startswith("indexes/catalog")], tracked)
        self.assertEqual(outcome.files, len(tracked))
        self.assertEqual(git(workspace.root, "log", "--format=%s"), gitsetup.FIRST_COMMIT_MESSAGE)
        self.assertEqual(git(workspace.root, "symbolic-ref", "--short", "HEAD"), "main")
        # The identity is repository-local, never global.
        self.assertEqual(git(workspace.root, "config", "--local", "user.name"), "Alice")
        self.assertEqual((self.base / "gitconfig").read_text(encoding="utf-8"), "")
        self.assertEqual(library.sync_status(workspace).uncommitted, 0)

    def test_init_uses_the_global_identity_when_there_is_one(self) -> None:
        workspace = self.fresh()
        git(self.base, "config", "--global", "user.name", "Global Person")
        git(self.base, "config", "--global", "user.email", "global@example.invalid")
        gitsetup.init_repository(workspace)
        self.assertEqual(git(workspace.root, "log", "--format=%an"), "Global Person")

    def test_bad_identity_fields_are_refused(self) -> None:
        workspace = self.fresh()
        for name, email in (("", "a@example.invalid"), ("Alice", "not-an-email"), ("Al\nice", "a@example.invalid")):
            with self.subTest(name=name, email=email):
                with self.assertRaises(GitSyncError) as caught:
                    gitsetup.init_repository(workspace, identity=(name, email))
                self.assertEqual(caught.exception.kind, "bad_identity")
        self.assertFalse((workspace.root / ".git").exists())

    def test_set_identity_is_repository_local(self) -> None:
        workspace = self.fresh()
        git(workspace.root, "init", "--quiet", "-b", "main")
        self.assertIsNone(library.sync_status(workspace).identity)
        gitsetup.set_identity(workspace, " Bob ", "bob@example.invalid")
        self.assertEqual(library.sync_status(workspace).identity, {"name": "Bob", "email": "bob@example.invalid"})
        self.assertEqual(git(workspace.root, "config", "--local", "user.email"), "bob@example.invalid")

    def test_existing_repository_without_commits_gets_its_first_commit(self) -> None:
        workspace = self.fresh()
        git(workspace.root, "init", "--quiet", "-b", "trunk")
        configure(workspace.root, "Alice")
        self.assertEqual(gitsetup.setup_status(workspace).state, "init")
        outcome = gitsetup.init_repository(workspace)
        self.assertFalse(outcome.created_repository)
        self.assertEqual(gitsetup.setup_status(workspace).branch, "trunk")

    def test_check_reports_an_empty_remote_and_changes_nothing(self) -> None:
        workspace = self.fresh()
        gitsetup.init_repository(workspace, identity=("Alice", "alice@example.invalid"))
        check = gitsetup.check_remote(workspace, str(self.bare()))
        self.assertTrue(check.empty)
        self.assertEqual(git(workspace.root, "remote"), "")

    def test_non_empty_unrelated_remote_is_refused_without_changes(self) -> None:
        _a, _b, other_remote = self.make_remote_and_clones()
        workspace = self.fresh("mine")
        gitsetup.init_repository(workspace, identity=("Alice", "alice@example.invalid"))
        before = git(other_remote, "rev-parse", "main")
        check = gitsetup.check_remote(workspace, str(other_remote))
        self.assertFalse(check.empty)
        self.assertFalse(check.related)
        self.assertEqual(check.branch, "main")
        with self.assertRaises(GitSyncError) as caught:
            gitsetup.connect_remote(workspace, str(other_remote))
        self.assertEqual(caught.exception.kind, "remote_not_empty")
        self.assertIn("Clone", caught.exception.message)
        self.assertEqual(git(workspace.root, "remote"), "")
        self.assertEqual(git(other_remote, "rev-parse", "main"), before)
        self.assertEqual(git(workspace.root, "for-each-ref", "refs/kos-setup"), "")

    def test_remote_with_shared_history_is_connected_by_an_ordinary_sync(self) -> None:
        workspace = self.fresh()
        gitsetup.init_repository(workspace, identity=("Alice", "alice@example.invalid"))
        remote = self.bare()
        # Published by hand earlier, without setting an upstream.
        git(workspace.root, "remote", "add", "origin", str(remote))
        git(workspace.root, "push", "--quiet", "origin", "main")
        self.assertEqual(gitsetup.setup_status(workspace).state, "publish")
        check = gitsetup.check_remote(workspace)
        self.assertTrue(check.related)
        outcome = gitsetup.connect_remote(workspace)
        self.assertEqual(outcome.state, "synced")
        self.assertEqual(gitsetup.setup_status(workspace).state, "ready")

    def test_remote_failures_say_what_to_fix(self) -> None:
        workspace = self.fresh()
        gitsetup.init_repository(workspace, identity=("Alice", "alice@example.invalid"))
        cases = {
            "auth": _Servers.unauthorized(self).replace("http://", "http://someone@"),
            "network": _Servers.closed_port(),
            "not_found": str(self.base / "nowhere.git"),
        }
        for kind, url in cases.items():
            with self.subTest(kind=kind):
                with self.assertRaises(GitSyncError) as caught:
                    gitsetup.check_remote(workspace, url, timeout=20)
                self.assertEqual(caught.exception.kind, kind, caught.exception.message)
                with self.assertRaises(GitSyncError):
                    gitsetup.connect_remote(workspace, url, timeout=20)
        with self.assertRaises(GitSyncError) as caught:
            gitsetup.connect_remote(workspace, "https://me:hunter2@example.com/x.git")
        self.assertEqual(caught.exception.kind, "bad_url")
        self.assertEqual(git(workspace.root, "remote"), "")

    def test_silent_remote_times_out_on_check(self) -> None:
        workspace = self.fresh()
        gitsetup.init_repository(workspace, identity=("Alice", "alice@example.invalid"))
        with self.assertRaises(GitSyncError) as caught:
            gitsetup.check_remote(workspace, _Servers.silent(self), timeout=2)
        self.assertEqual(caught.exception.kind, "timeout")

    def test_steps_refuse_when_they_do_not_apply(self) -> None:
        workspace = self.fresh()
        with self.assertRaises(GitSyncError) as caught:
            gitsetup.connect_remote(workspace, str(self.bare()))
        self.assertEqual(caught.exception.kind, "wrong_step")
        gitsetup.init_repository(workspace, identity=("Alice", "alice@example.invalid"))
        with self.assertRaises(GitSyncError) as caught:
            gitsetup.init_repository(workspace)
        self.assertEqual(caught.exception.kind, "wrong_step")

    def test_source_repository_is_never_offered_setup(self) -> None:
        root = init_workspace(self.base / "source")
        (root / "pyproject.toml").write_text('[project]\nname = "knowledge-os"\n', encoding="utf-8")
        (root / "knowledge_os").mkdir()
        workspace = Workspace(root)
        self.assertEqual(gitsetup.setup_status(workspace).state, "source_repo")
        with self.assertRaises(GitSyncError) as caught:
            gitsetup.init_repository(workspace, identity=("Alice", "alice@example.invalid"))
        self.assertEqual(caught.exception.kind, "source_repo")
        self.assertFalse((root / ".git").exists())
        git(root, "init", "--quiet", "-b", "main")
        configure(root, "Alice")
        git(root, "add", "-A")
        git(root, "commit", "--quiet", "-m", "Source")
        self.assertEqual(gitsetup.setup_status(workspace).state, "source_repo")
        for step in (lambda: gitsetup.check_remote(workspace, str(self.bare())), lambda: gitsetup.connect_remote(workspace, str(self.bare("r2.git")))):
            with self.assertRaises(GitSyncError) as caught:
                step()
            self.assertEqual(caught.exception.kind, "source_repo")
        self.assertEqual(git(root, "remote"), "")

    def test_knowledge_base_inside_another_repository_is_not_offered_init(self) -> None:
        outer = self.base / "outer"
        outer.mkdir()
        git(outer, "init", "--quiet", "-b", "main")
        workspace = Workspace(init_workspace(outer / "kb"))
        setup = gitsetup.setup_status(workspace)
        self.assertEqual(setup.state, "nested")
        with self.assertRaises(GitSyncError) as caught:
            gitsetup.init_repository(workspace, identity=("Alice", "alice@example.invalid"))
        self.assertEqual(caught.exception.kind, "not_a_repo")
        self.assertFalse((workspace.root / ".git").exists())


class SetupApiTests(GitTestCase):
    def request(self, base: str, method: str, path: str, payload: object | None = None, token: str | None = None) -> tuple[int, dict]:
        import urllib.error
        import urllib.request

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

    def test_guided_setup_over_http(self) -> None:
        root = init_workspace(self.base / "kb")
        remote = self.base / "remote.git"
        git(self.base, "init", "--quiet", "--bare", "-b", "main", str(remote))
        with serve(root, PORT) as base:
            code, setup = self.request(base, "GET", "/api/sync/setup")
            self.assertEqual(code, 200)
            self.assertEqual(setup["state"], "init")
            self.assertIn("not versioned", setup["sentence"])
            self.assertEqual(setup["label"], "Set up sync")
            self.assertIn("init_action", setup["language"])
            code, status = self.request(base, "GET", "/api/sync/status")
            self.assertEqual(status["setup"]["state"], "init")

            token = self.request(base, "GET", "/api/session")[1]["write_token"]
            self.assertEqual(self.request(base, "POST", "/api/sync/setup/init", {})[0], 403)
            code, failed = self.request(base, "POST", "/api/sync/setup/init", {}, token)
            self.assertEqual(code, 409)
            self.assertEqual(failed["error"], "no_identity")
            code, done = self.request(
                base, "POST", "/api/sync/setup/init", {"name": "Alice", "email": "alice@example.invalid"}, token
            )
            self.assertEqual(code, 200, done)
            self.assertGreater(done["files"], 5)
            self.assertEqual(done["setup"]["state"], "remote")
            self.assertTrue(done["status"]["available"])

            code, bad = self.request(base, "POST", "/api/sync/setup/check", {"url": "notes"}, token)
            self.assertEqual((code, bad["error"]), (400, "bad_url"))
            code, check = self.request(base, "POST", "/api/sync/setup/check", {"url": str(remote)}, token)
            self.assertEqual(code, 200, check)
            self.assertTrue(check["check"]["empty"])
            code, connected = self.request(base, "POST", "/api/sync/setup/connect", {"url": str(remote)}, token)
            self.assertEqual(code, 200, connected)
            self.assertEqual(connected["state"], "published")
            self.assertEqual(connected["setup"]["state"], "ready")
            self.assertIsNone(connected["setup"]["sentence"])
            self.assertEqual(connected["status"]["upstream"], "origin/main")

            code, identity = self.request(
                base, "POST", "/api/sync/setup/identity", {"name": "Alice B", "email": "ab@example.invalid"}, token
            )
            self.assertEqual(code, 200, identity)
            self.assertEqual(identity["status"]["identity"]["name"], "Alice B")


if __name__ == "__main__":
    unittest.main()
