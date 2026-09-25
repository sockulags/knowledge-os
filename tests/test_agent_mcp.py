"""The MCP server for agents (issue #59, ``knowledge_os.agent_access``).

Covers finding the app through its runtime file (missing, damaged, stale PID,
wrong port or token, valid), every tool against a real ``kos-read`` server on
a temporary workspace that is its own Git repository (including conflict,
duplicate, validation, and refused decision edits), agent provenance and
commit messages, that no tool accepts, withdraws, or supersedes, that nothing
is written while the app is closed, and the MCP handshake and tool listing
over stdio with the official SDK's client.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from reader_support import REPOSITORY, serve, write_record

from knowledge_os.agent_access import runtime
from knowledge_os.agent_access.server import default_place
from knowledge_os.agent_access.tools import TOOLS, Caller, call_tool
from knowledge_os.index import rebuild_indexes
from knowledge_os.init_workspace import init_workspace
from knowledge_os.workspace import Workspace

PORT = 8851
GIT = shutil.which("git")
CALLER = Caller(client="claude-code", place="my-repo")
AGENT_REFERENCE = "agent:claude-code:my-repo"
EXPECTED_TOOLS = {
    "search",
    "read_page",
    "list_projects",
    "list_folder",
    "write_note",
    "propose_decision",
    "list_proposed_decisions",
}

try:
    import mcp  # noqa: F401

    HAVE_SDK = True
except ImportError:
    HAVE_SDK = False


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def _session_token(base_url: str) -> str:
    with urllib.request.urlopen(base_url + "/api/session", timeout=5) as response:
        return json.loads(response.read())["write_token"]


def write_runtime_file(path: Path, *, port: int, token: str, root: Path, pid: int | None = None) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "app_version": "0.2.0",
                "port": port,
                "url": f"http://127.0.0.1:{port}",
                "write_token": token,
                "workspace": {"root": str(root), "name": root.name},
                "core_pid": os.getpid() if pid is None else pid,
                "shell_pid": os.getpid(),
                "written_at": "2026-09-23T20:00:00Z",
            }
        ),
        encoding="utf-8",
    )


def _dead_pid() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


class IsolatedTestCase(unittest.TestCase):
    """A temporary folder, an isolated Git configuration, and a runtime file path."""

    def setUp(self) -> None:
        self._temp = tempfile.mkdtemp(prefix="kos-mcp-")
        self.addCleanup(self._cleanup)
        self.base = Path(self._temp).resolve()
        home = self.base / "home"
        home.mkdir()
        global_config = self.base / "gitconfig"
        global_config.write_text("", encoding="utf-8")
        self.runtime_path = self.base / "runtime.json"
        environment = {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "GIT_CONFIG_GLOBAL": str(global_config),
            "GIT_CONFIG_NOSYSTEM": "1",
            "KOS_RUNTIME_FILE": str(self.runtime_path),
        }
        patcher = patch.dict(os.environ, environment)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_DIR"):
            os.environ.pop(name, None)

    def _cleanup(self) -> None:
        def force(function, path, _info):  # type: ignore[no-untyped-def]
            os.chmod(path, 0o700)
            function(path)

        shutil.rmtree(self._temp, onerror=force)


class RuntimeFileTests(IsolatedTestCase):
    def test_default_location_is_the_desktop_apps_user_data_folder(self) -> None:
        self.assertEqual(
            runtime.runtime_file({"APPDATA": "C:\\Users\\a\\AppData\\Roaming"}, "win32"),
            Path("C:\\Users\\a\\AppData\\Roaming") / "knowledge-os-desktop" / "runtime.json",
        )
        self.assertEqual(
            runtime.runtime_file({"XDG_CONFIG_HOME": "/home/a/.config"}, "linux"),
            Path("/home/a/.config/knowledge-os-desktop/runtime.json"),
        )
        self.assertEqual(
            runtime.runtime_file({"KOS_DESKTOP_USER_DATA": "/tmp/kos-test"}, "win32"),
            Path("/tmp/kos-test/runtime.json"),
        )
        self.assertEqual(runtime.runtime_file({"KOS_RUNTIME_FILE": "/x/y.json"}, "win32"), Path("/x/y.json"))

    def test_missing_file_means_the_app_is_not_open(self) -> None:
        with self.assertRaises(runtime.AppUnavailable) as caught:
            runtime.connect()
        self.assertEqual(caught.exception.kind, "app_not_open")

    def test_damaged_file_is_not_used(self) -> None:
        self.runtime_path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(runtime.AppUnavailable) as caught:
            runtime.connect()
        self.assertEqual(caught.exception.kind, "app_not_responding")

    def test_file_whose_core_process_is_gone_is_stale(self) -> None:
        write_runtime_file(self.runtime_path, port=PORT, token="t", root=self.base, pid=_dead_pid())
        with self.assertRaises(runtime.AppUnavailable) as caught:
            runtime.connect()
        self.assertEqual(caught.exception.kind, "app_not_responding")

    def test_file_whose_port_does_not_answer_is_stale(self) -> None:
        # The process is alive (this test), but nothing listens on the port.
        write_runtime_file(self.runtime_path, port=PORT + 9, token="t", root=self.base)
        with self.assertRaises(runtime.AppUnavailable) as caught:
            runtime.connect()
        self.assertEqual(caught.exception.kind, "app_not_responding")

    def test_valid_file_and_a_server_with_another_token(self) -> None:
        root = init_workspace(self.base / "kb")
        with serve(root, PORT) as base_url:
            write_runtime_file(self.runtime_path, port=PORT, token="someone-elses-token", root=root)
            with self.assertRaises(runtime.AppUnavailable) as caught:
                runtime.connect()
            self.assertEqual(caught.exception.kind, "app_not_responding")

            write_runtime_file(self.runtime_path, port=PORT, token=_session_token(base_url), root=root)
            info = runtime.connect()
            self.assertEqual(info.port, PORT)
            self.assertEqual(info.workspace_name, "kb")


class PlaceTests(unittest.TestCase):
    def test_place_is_a_label_or_the_working_directory_name_never_a_path(self) -> None:
        self.assertEqual(default_place("backend", {"KOS_AGENT_PLACE": "x"}, Path("/a/b")), "backend")
        self.assertEqual(default_place(None, {"KOS_AGENT_PLACE": "labelled"}, Path("/a/b")), "labelled")
        self.assertEqual(default_place(None, {}, Path("/home/me/code/my-repo")), "my-repo")


@unittest.skipIf(GIT is None, "git is not installed")
class ToolTests(IsolatedTestCase):
    """Every tool against a real core serving a Git-versioned knowledge base."""

    def setUp(self) -> None:
        super().setUp()
        self.root = init_workspace(self.base / "kb")
        write_record(
            self.root,
            "projects/demo/README.md",
            {
                "id": "demo",
                "title": "Demo project overview",
                "type": "project",
                "status": "active",
                "scope": "project:demo",
                "created": "2026-09-01",
                "updated": "2026-09-01",
                "provenance": [{"kind": "project-definition", "reference": "test:demo"}],
            },
            "The demo project.\n",
        )
        write_record(
            self.root,
            "projects/demo/architecture/retry-policy.md",
            {
                "id": "retry-policy",
                "title": "Retry policy",
                "type": "project",
                "status": "active",
                "scope": "project:demo",
                "created": "2026-09-01",
                "updated": "2026-09-01",
                "provenance": [{"kind": "user-request", "reference": "test:retry"}],
            },
            "Requests are retried three times with a xylophone backoff.\n",
        )
        write_record(
            self.root,
            "projects/demo/decisions/use-postgres.md",
            {
                "id": "use-postgres",
                "title": "Use Postgres",
                "type": "project",
                "record_kind": "decision",
                "status": "active",
                "scope": "project:demo",
                "created": "2026-09-01",
                "updated": "2026-09-01",
                "provenance": [
                    {"kind": "user-request", "reference": "test:pg"},
                    {"kind": "decision-acceptance", "reference": "test:pg-accepted", "captured": "2026-09-01T10:00:00Z"},
                ],
            },
            "## Decision\n\nUse Postgres.\n",
        )
        rebuild_indexes(Workspace(self.root))
        git(self.root, "init", "--quiet", "-b", "main")
        git(self.root, "config", "user.name", "Alice")
        git(self.root, "config", "user.email", "alice@example.invalid")
        git(self.root, "config", "core.autocrlf", "false")
        git(self.root, "add", "-A")
        git(self.root, "commit", "--quiet", "-m", "Initial knowledge base")
        self.server = serve(self.root, PORT)
        self.base_url = self.server.__enter__()
        self.addCleanup(self.server.__exit__, None, None, None)
        write_runtime_file(self.runtime_path, port=PORT, token=_session_token(self.base_url), root=self.root)

    def call(self, name: str, **arguments: object) -> dict:
        result = call_tool(name, arguments, CALLER)
        self.assertIsInstance(result.data, dict)
        self.assertEqual(result.is_error, not result.data["ok"], result.data)
        return result.data

    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD")

    def commits_since(self, sha: str) -> list[str]:
        log = git(self.root, "log", "--format=%s", f"{sha}..HEAD")
        return log.splitlines() if log else []

    def front_matter(self, rel_path: str) -> dict:
        import yaml

        text = (self.root / rel_path).read_text(encoding="utf-8")
        return yaml.safe_load(text.split("---", 2)[1])

    def test_the_tool_list_has_no_way_to_accept_withdraw_or_supersede(self) -> None:
        self.assertEqual({tool.name for tool in TOOLS}, EXPECTED_TOOLS)
        for tool in TOOLS:
            self.assertNotRegex(tool.name, r"accept|withdraw|supersede|approve|delete")
            self.assertEqual(tool.input_schema["type"], "object")
            self.assertFalse(tool.input_schema.get("additionalProperties", True))
        propose = next(tool for tool in TOOLS if tool.name == "propose_decision")
        self.assertNotIn("status", propose.input_schema["properties"])
        for name in ("accept_decision", "withdraw_decision", "supersede_decision", "delete_page", "delete_folder"):
            with self.subTest(tool=name):
                self.assertTrue(call_tool(name, {"id": "x"}, CALLER).is_error)

    def test_no_tool_reaches_the_delete_or_lifecycle_routes(self) -> None:
        """Deleting, accepting, withdrawing, and superseding stay human actions
        (issue #78): the tools' source never names those API routes."""

        import inspect

        from knowledge_os.agent_access import local_api, tools

        source = inspect.getsource(tools) + inspect.getsource(local_api)
        for route in ("/delete", "/accept", "/withdraw", "/supersede"):
            with self.subTest(route=route):
                self.assertNotIn(route, source)

    def test_search_read_and_list(self) -> None:
        found = self.call("search", query="xylophone")
        self.assertEqual([row["id"] for row in found["results"]], ["retry-policy"])
        self.assertEqual(found["results"][0]["project"], "demo")
        self.assertIn("xylophone", found["results"][0]["snippet"])
        self.assertEqual(found["knowledge_base"], "kb")
        self.assertEqual(self.call("search", query="xylophone", project="general")["results"], [])

        page = self.call("read_page", id="retry-policy")
        self.assertEqual(page["content"], "Requests are retried three times with a xylophone backoff.\n")
        self.assertEqual(page["folder"], "architecture")
        self.assertTrue(page["editable_with_write_note"])
        import hashlib

        raw = (self.root / "projects/demo/architecture/retry-policy.md").read_bytes()
        self.assertEqual(page["content_sha256"], hashlib.sha256(raw).hexdigest())

        decision = self.call("read_page", id="use-postgres")
        self.assertEqual((decision["kind"], decision["state"]), ("decision", "in force"))
        self.assertFalse(decision["editable_with_write_note"])

        missing = self.call("read_page", id="no-such-page")
        self.assertEqual(missing["error"], "not_found")

        projects = self.call("list_projects")
        self.assertEqual(projects["projects"], [{"id": "demo", "title": "Demo", "folders": ["architecture", "decisions"]}])
        top = self.call("list_folder", project="demo")
        self.assertEqual(top["folders"], ["architecture", "decisions"])
        folder = self.call("list_folder", project="demo", folder="architecture")
        self.assertEqual([page["id"] for page in folder["pages"]], ["retry-policy"])
        self.assertEqual(self.call("list_folder", project="demo", folder="nope")["error"], "not_found")
        self.assertEqual(self.call("list_folder", project="nope")["error"], "not_found")

    def test_write_note_creates_and_edits_with_agent_provenance_and_one_commit_each(self) -> None:
        before = self.head()
        created = self.call(
            "write_note", title="Cache warmup", content="Warm the cache on deploy.\n", project="demo", folder="architecture"
        )
        self.assertEqual(created["action"], "created")
        self.assertEqual(created["path"], "projects/demo/architecture/cache-warmup.md")
        self.assertEqual(created["state"], "active")
        self.assertTrue(created["commit"]["committed"])
        self.assertEqual(self.commits_since(before), ["Claude Code: Create Cache warmup"])
        provenance = self.front_matter(created["path"])["provenance"]
        self.assertEqual([(p["kind"], p["reference"]) for p in provenance], [("agent-authored", AGENT_REFERENCE)])
        self.assertIn("captured", provenance[0])

        after_create = self.head()
        edited = self.call(
            "write_note", id="cache-warmup", content="Warm the cache on every deploy.\n", expected_sha256=created["content_sha256"]
        )
        self.assertEqual(edited["action"], "updated")
        self.assertEqual(self.commits_since(after_create), ["Claude Code: Edit Cache warmup"])
        # The same agent in the same place is recorded once.
        self.assertEqual(len(self.front_matter(created["path"])["provenance"]), 1)

        # Another agent's edit adds its own entry.
        other = call_tool(
            "write_note",
            {"id": "cache-warmup", "content": "Warm it.\n", "expected_sha256": edited["content_sha256"]},
            Caller(client="codex-mcp-client", place="ops"),
        )
        self.assertFalse(other.is_error, other.data)
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "Codex: Edit Cache warmup")
        references = [p["reference"] for p in self.front_matter(created["path"])["provenance"]]
        self.assertEqual(references, [AGENT_REFERENCE, "agent:codex-mcp-client:ops"])

        general = self.call("write_note", title="Tabs over spaces", content="Use tabs.\n")
        self.assertEqual(general["path"], "knowledge/tabs-over-spaces.md")
        self.assertEqual(self.front_matter(general["path"])["scope"], "general")

    def test_refused_writes_write_nothing(self) -> None:
        page = self.call("read_page", id="retry-policy")
        path = self.root / "projects/demo/architecture/retry-policy.md"
        original = path.read_bytes()
        before = self.head()

        stale = self.call("write_note", id="retry-policy", content="New.\n", expected_sha256="0" * 64)
        self.assertEqual(stale["error"], "conflict")
        self.assertEqual(stale["current_sha256"], page["content_sha256"])
        self.assertFalse(stale["written"])
        self.assertIn("read_page", stale["next_step"])

        duplicate = self.call("write_note", title="Retry policy", content="Again.\n", project="demo")
        self.assertEqual(duplicate["error"], "duplicate")

        invalid = self.call("write_note", title="Orphan", content="Text.\n", project="no-such-project")
        self.assertEqual(invalid["error"], "validation")

        bad_id = self.call("write_note", title="X", id="Not An Id", content="Text.\n")
        self.assertEqual(bad_id["error"], "bad_request")

        decision_edit = self.call(
            "write_note", id="use-postgres", content="Use MySQL.\n", expected_sha256=self.call("read_page", id="use-postgres")["content_sha256"]
        )
        self.assertEqual(decision_edit["error"], "not_allowed")
        self.assertIn("propose_decision", decision_edit["next_step"])

        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.head(), before)
        self.assertEqual(git(self.root, "status", "--porcelain", "--", "projects", "knowledge"), "")

    def test_propose_decision_is_always_a_draft_labelled_with_the_agent(self) -> None:
        before = self.head()
        proposed = self.call(
            "propose_decision",
            title="Use SQLite for tests",
            content="## Decision\n\nTests use SQLite.\n\n## Why\n\nFaster.\n",
            project="demo",
        )
        self.assertEqual((proposed["action"], proposed["state"]), ("proposed", "draft"))
        self.assertEqual(proposed["path"], "projects/demo/decisions/use-sqlite-for-tests.md")
        self.assertIn("Decide inbox", proposed["next_step"])
        self.assertEqual(self.commits_since(before), ["Claude Code: Create Use SQLite for tests"])
        metadata = self.front_matter(proposed["path"])
        self.assertEqual((metadata["record_kind"], metadata["status"]), ("decision", "draft"))
        self.assertEqual(metadata["provenance"][0]["reference"], AGENT_REFERENCE)

        replacement = self.call(
            "propose_decision",
            title="Use CockroachDB",
            content="## Decision\n\nReplace Postgres.\n",
            project="demo",
            supersedes="use-postgres",
        )
        self.assertFalse(replacement.get("error"), replacement)
        self.assertEqual(self.front_matter(replacement["path"])["supersedes"], ["use-postgres"])
        self.assertEqual(self.front_matter("projects/demo/decisions/use-postgres.md")["status"], "active")

        inbox = self.call("list_proposed_decisions", project="demo")
        by_id = {item["id"]: item for item in inbox["decisions"]}
        self.assertEqual(set(by_id), {"use-sqlite-for-tests", "use-cockroachdb"})
        self.assertEqual(by_id["use-sqlite-for-tests"]["proposed_by"], "Proposed by Claude Code in my-repo")
        self.assertEqual(by_id["use-cockroachdb"]["replaces"], {"id": "use-postgres", "title": "Use Postgres"})

        # The Decide inbox the person sees says the same.
        with urllib.request.urlopen(self.base_url + "/api/decisions/proposed", timeout=5) as response:
            items = json.loads(response.read())["items"]
        labels = {item["id"]: item["proposed_by"]["label"] for item in items}
        self.assertEqual(labels["use-sqlite-for-tests"], "Proposed by Claude Code in my-repo")

    def test_with_the_app_closed_every_tool_says_so_and_writes_nothing(self) -> None:
        before = self.head()
        self.runtime_path.unlink()
        arguments = {
            "search": {"query": "xylophone"},
            "read_page": {"id": "retry-policy"},
            "list_projects": {},
            "list_folder": {"project": "demo"},
            "write_note": {"title": "Closed", "content": "Text.\n"},
            "propose_decision": {"title": "Closed decision", "content": "Text.\n"},
            "list_proposed_decisions": {},
        }
        self.assertEqual(set(arguments), EXPECTED_TOOLS)
        for name, args in arguments.items():
            with self.subTest(tool=name):
                result = self.call(name, **args)
                self.assertEqual(result["error"], "app_not_open")
                self.assertFalse(result["written"])
                self.assertIn("open the Knowledge OS app", result["next_step"])
        self.assertEqual(self.head(), before)
        self.assertEqual(git(self.root, "status", "--porcelain", "--", "projects", "knowledge"), "")
        self.assertFalse((self.root / "knowledge" / "closed.md").exists())


@unittest.skipUnless(HAVE_SDK, "the mcp extra is not installed")
class StdioProtocolTests(IsolatedTestCase):
    """``python -m knowledge_os mcp`` spoken to by the SDK's own stdio client."""

    def _run(self, cwd: Path, script: str) -> dict:
        import anyio
        import mcp_types as types
        from mcp.client import Client
        from mcp.client.stdio import StdioServerParameters

        environment = {
            "PYTHONPATH": str(REPOSITORY) + os.pathsep + os.environ.get("PYTHONPATH", ""),
            "KOS_RUNTIME_FILE": str(self.runtime_path),
        }
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "knowledge_os", "mcp"], env=environment, cwd=str(cwd)
        )
        outcome: dict = {}

        async def main() -> None:
            async with Client(params, client_info=types.Implementation(name="claude-code", version="0")) as client:
                outcome["server"] = client.server_info.name if client.server_info else None
                tools = (await client.list_tools()).tools
                outcome["tools"] = {tool.name: tool for tool in tools}
                if script == "write":
                    result = await client.call_tool("write_note", {"title": "From stdio", "content": "Hello.\n"})
                else:
                    result = await client.call_tool("search", {"query": "anything"})
                outcome["result"] = result

        anyio.run(main)
        return outcome

    def test_handshake_lists_the_tools_and_reports_a_closed_app(self) -> None:
        cwd = self.base / "my-repo"
        cwd.mkdir()
        outcome = self._run(cwd, "search")
        self.assertEqual(outcome["server"], "knowledge-os")
        self.assertEqual(set(outcome["tools"]), EXPECTED_TOOLS)
        self.assertTrue(outcome["tools"]["search"].annotations.read_only_hint)
        self.assertFalse(outcome["tools"]["write_note"].annotations.read_only_hint)
        result = outcome["result"]
        self.assertTrue(result.is_error)
        self.assertEqual(result.structured_content["error"], "app_not_open")
        self.assertEqual(json.loads(result.content[0].text)["error"], "app_not_open")

    @unittest.skipIf(GIT is None, "git is not installed")
    def test_a_write_names_the_client_and_its_working_directory(self) -> None:
        root = init_workspace(self.base / "kb")
        git(root, "init", "--quiet", "-b", "main")
        git(root, "config", "user.name", "Alice")
        git(root, "config", "user.email", "alice@example.invalid")
        git(root, "add", "-A")
        git(root, "commit", "--quiet", "-m", "Initial knowledge base")
        cwd = self.base / "service-repo"
        cwd.mkdir()
        with serve(root, PORT + 1) as base_url:
            write_runtime_file(self.runtime_path, port=PORT + 1, token=_session_token(base_url), root=root)
            outcome = self._run(cwd, "write")
        result = outcome["result"]
        self.assertFalse(result.is_error, result.structured_content)
        text = (root / "knowledge" / "from-stdio.md").read_text(encoding="utf-8")
        self.assertIn("reference: agent:claude-code:service-repo", text)
        self.assertEqual(git(root, "log", "-1", "--format=%s"), "Claude Code: Create From stdio")


if __name__ == "__main__":
    unittest.main()
