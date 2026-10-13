"""A project's documentation kept in step with its code (issue #84).

The ``repositories`` field of a project overview, the deterministic check of
what changed in a linked Git repository since its checked commit, the
suggestions it makes, and ``kos code`` on the command line.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from knowledge_os import codedocs
from knowledge_os.init_workspace import init_workspace
from knowledge_os.model import MetadataError, validate_metadata
from knowledge_os.workspace import Workspace, validate_workspace

REPOSITORY = Path(__file__).resolve().parents[1]
SHA = "a" * 40


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def run_kos(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPOSITORY) + os.pathsep + environment.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "knowledge_os", *arguments, "--root", str(root)],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )


def overview(**extra: object) -> dict[str, object]:
    return {
        "id": "demo",
        "title": "Demo",
        "type": "project",
        "status": "active",
        "scope": "project:demo",
        "created": "2026-09-01",
        "updated": "2026-09-01",
        "provenance": [{"kind": "fixture", "reference": "test"}],
        **extra,
    }


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def page(root: Path, record_id: str, body: str, **extra: object) -> None:
    metadata = {**overview(), "id": record_id, "title": record_id.replace("-", " ").capitalize(), **extra}
    text = "---\n" + yaml.safe_dump(metadata, sort_keys=False) + "---\n\n" + body
    folder = "decisions/" if extra.get("record_kind") == "decision" else ""
    write(root / "projects" / "demo" / f"{folder}{record_id}.md", text)


class RepositoriesFieldTests(unittest.TestCase):
    def test_accepts_links_on_the_overview_only(self) -> None:
        links = [{"path": "../code", "remote": "https://example.invalid/code.git", "checked": SHA, "checked_on": "2026-09-01"}]
        validate_metadata(overview(repositories=links), Path("README.md"), check_filename=False)
        validate_metadata(overview(repositories=[{"path": "/abs/code"}]), Path("README.md"), check_filename=False)
        page_metadata = {**overview(repositories=links), "id": "other"}
        with self.assertRaisesRegex(MetadataError, "only allowed on a project overview"):
            validate_metadata(page_metadata, Path("other.md"))

    def test_refuses_malformed_links(self) -> None:
        cases = {
            "non-empty list": [],
            "must be an object": ["../code"],
            "unknown field": [{"path": "x", "branch": "main"}],
            "path must be a non-empty string": [{"path": " "}],
            "more than once": [{"path": "x"}, {"path": "x"}],
            "full commit hash": [{"path": "x", "checked": "abc123", "checked_on": "2026-09-01"}],
            "both checked and checked_on": [{"path": "x", "checked": SHA}],
        }
        for message, value in cases.items():
            with self.subTest(message=message), self.assertRaisesRegex(MetadataError, message):
                validate_metadata(overview(repositories=value), Path("README.md"), check_filename=False)


class ManifestTests(unittest.TestCase):
    def test_reads_dependencies_and_commands_from_common_manifests(self) -> None:
        facts = codedocs._manifest_facts
        self.assertEqual(
            facts(
                "pyproject.toml",
                '[project]\ndependencies = ["Requests>=2", "pyyaml"]\n[project.optional-dependencies]\nmcp = ["mcp>=1"]\n'
                '[project.scripts]\nkos = "x:main"\n',
            ),
            ({"requests", "pyyaml", "mcp"}, {"kos"}),
        )
        self.assertEqual(
            facts("web/package.json", json.dumps({"name": "@a/tool", "bin": "cli.js", "dependencies": {"react": "1"}, "devDependencies": {"vite": "1"}})),
            ({"react", "vite"}, {"tool"}),
        )
        self.assertEqual(facts("requirements-dev.txt", "# tools\nruff==1\n-r base.txt\nhttpx[http2]>=0.27\n"), ({"ruff", "httpx"}, set()))
        self.assertEqual(
            facts("go.mod", "module x\n\nrequire (\n\tgithub.com/a/b v1.0.0\n)\nrequire github.com/c/d v2.0.0\n"),
            ({"github.com/a/b", "github.com/c/d"}, set()),
        )
        self.assertEqual(facts("Cargo.toml", '[dependencies]\nserde = "1"\n[[bin]]\nname = "tool"\n'), ({"serde"}, {"tool"}))
        self.assertEqual(facts("pyproject.toml", "not toml ["), (set(), set()))
        self.assertEqual(facts("pyproject.toml", None), (set(), set()))

    def test_finds_commands_and_routes_on_changed_lines(self) -> None:
        diff = (
            "+++ b/app/cli.py\n"
            '+    sub.add_parser("serve", help="x")\n'
            '-    sub.add_parser("run")\n'
            "+++ b/app/web.py\n"
            '+    Route("/api/items", items)\n'
            "+@app.get('/health')\n"
            "+router.post(`/upload`, h)\n"
        )
        added, removed = codedocs._declarations(diff)
        self.assertEqual(set(added), {"command:serve", "route:/api/items", "route:/health", "route:/upload"})
        self.assertEqual(set(removed), {"command:run"})
        self.assertEqual(added["route:/api/items"], {"app/web.py"})

    def test_classifies_files(self) -> None:
        self.assertTrue(codedocs._is_code("pkg/module.py"))
        self.assertFalse(codedocs._is_code("tests/test_module.py"))
        self.assertFalse(codedocs._is_code("src/app.test.ts"))
        self.assertFalse(codedocs._is_code("pkg/static/app/assets/index-1a2b.js"))
        self.assertTrue(codedocs._is_config(".github/workflows/ci.yml"))
        self.assertTrue(codedocs._is_config("vite.config.ts"))
        self.assertFalse(codedocs._is_config("package-lock.json"))
        self.assertFalse(codedocs._is_config("pyproject.toml"))
        self.assertTrue(codedocs._is_doc("README.md"))
        self.assertTrue(codedocs._is_doc("docs/guide.md"))
        self.assertFalse(codedocs._is_doc("pkg/notes.md"))


class CheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base, True)
        self.root = init_workspace(self.base / "kb")
        self.code = self.base / "code"
        self.code.mkdir()
        git(self.code, "init", "--quiet", "-b", "main")
        git(self.code, "config", "user.name", "Bob")
        git(self.code, "config", "user.email", "bob@example.invalid")
        write(self.code / "pyproject.toml", '[project]\nname = "demo"\ndependencies = ["requests"]\n[project.scripts]\ndemo = "demo.cli:main"\n')
        write(self.code / "demo" / "cli.py", "import argparse\n")
        write(self.code / "README.md", "# Demo\n")
        self.first = self.commit("Start")
        page(self.root, "http", "We call services with requests, from demo/cli.py.\n")
        page(self.root, "use-requests", "Use requests.\n", record_kind="decision", status="draft")

    def commit(self, message: str) -> str:
        git(self.code, "add", "-A")
        git(self.code, "commit", "--quiet", "-m", message)
        return git(self.code, "rev-parse", "HEAD")

    def link(self, **extra: object) -> None:
        links = [{"path": "../code", "checked": self.first, "checked_on": "2026-09-01", **extra}]
        write(self.root / "projects" / "demo" / "README.md", "---\n" + yaml.safe_dump(overview(repositories=links), sort_keys=False) + "---\n\n# Demo\n")

    def check(self, **since: str) -> codedocs.RepositoryCheck:
        workspace = Workspace(self.root)
        documents, issues = validate_workspace(workspace)
        self.assertEqual(issues, [])
        return codedocs.check_documentation(workspace.root, "demo", documents, workspace.relative, since=since or None).repositories[0]

    def test_reports_what_changed_and_suggests_updates_and_decisions(self) -> None:
        self.link()
        write(self.code / "pyproject.toml", '[project]\nname = "demo"\ndependencies = ["httpx"]\n[project.scripts]\ndemo = "demo.cli:main"\n')
        switch = self.commit("Switch to httpx")
        write(self.code / "demo" / "storage" / "__init__.py", "def save():\n    pass\n")
        write(self.code / "demo" / "storage" / "files.py", "def load():\n    pass\n")
        storage = self.commit("Add storage")
        (self.code / "demo" / "cli.py").unlink()
        write(self.code / "demo" / "server.py", 'routes = [Route("/health", h)]\n')
        write(self.code / "README.md", "# Demo\n\nNow a server.\n")
        write(self.code / "tests" / "test_server.py", "def test():\n    pass\n")
        server = self.commit("Replace the CLI with a server")

        result = self.check()
        self.assertEqual(result.state, "changed")
        self.assertEqual((result.base, result.head), (self.first, server))
        self.assertEqual([commit.subject for commit in result.commits], ["Switch to httpx", "Add storage", "Replace the CLI with a server"])
        changes = {change.key: change for change in result.changes}
        self.assertEqual(
            set(changes),
            {
                "dependency-added:httpx",
                "dependency-removed:requests",
                "route-added:/health",
                "documentation-changed:README.md",
                "module-added:demo/storage",
                "module-added:demo/server.py",
                "module-removed:demo/cli.py",
            },
        )
        self.assertEqual(changes["dependency-added:httpx"].commits, (switch,))
        self.assertEqual(changes["module-added:demo/storage"].detail, "2 files")
        self.assertEqual(changes["module-added:demo/storage"].commits, (storage,))
        self.assertEqual(changes["route-added:/health"].commits, (server,))

        pages = {suggestion.page_id: suggestion for suggestion in result.pages}
        self.assertEqual(list(pages), ["demo", "http"])  # the overview first; never a decision
        overview_reasons = [reason.text for reason in pages["demo"].reasons]
        self.assertEqual(overview_reasons[0], "The repository's README.md was changed; the overview may need the same change.")
        self.assertIn("No page mentions the new dependency `httpx` yet.", overview_reasons)
        self.assertIn("No page mentions the new module `demo/storage` yet.", overview_reasons)
        self.assertIn("No page mentions the new API route `/health` yet.", overview_reasons)
        self.assertEqual(
            [reason.text for reason in pages["http"].reasons],
            ["Mentions the dependency `requests` removed (in pyproject.toml).", "Mentions the module `demo/cli.py` removed."],
        )
        self.assertEqual(pages["http"].commits, (switch, server))

        self.assertEqual(
            [(decision.key, decision.title, decision.commits) for decision in result.decisions],
            [
                ("dependency-added:httpx", "Add the dependency httpx", (switch,)),
                ("dependency-removed:requests", "Remove the dependency requests", (switch,)),
                ("module-added:demo/storage", "Add the module demo/storage", (storage,)),
            ],
        )

        title, body, provenance = codedocs.decision_draft(result, "dependency-added:httpx")
        self.assertEqual(title, "Add the dependency httpx")
        self.assertIn(f"`{switch[:12]}` Switch to httpx (Bob,", body)
        self.assertEqual([(item["kind"], item["reference"]) for item in provenance], [("repository-commit", f"code@{switch}")])
        with self.assertRaisesRegex(codedocs.CodeDocsError, "suggests no decision"):
            codedocs.decision_draft(result, "dependency-added:nope")

    def test_names_an_existing_decision_and_refuses_to_draft_it_again(self) -> None:
        self.link()
        write(self.code / "pyproject.toml", '[project]\nname = "demo"\ndependencies = []\n')
        self.commit("Drop requests")
        page(self.root, "remove-the-dependency-requests", "x\n", record_kind="decision", status="draft", title="Remove the dependency requests")
        result = self.check()
        decision = next(item for item in result.decisions if item.key == "dependency-removed:requests")
        self.assertEqual(decision.existing, "remove-the-dependency-requests")
        with self.assertRaisesRegex(codedocs.CodeDocsError, "already exists"):
            codedocs.decision_draft(result, decision.key)

    def test_up_to_date_unavailable_and_since(self) -> None:
        self.link()
        self.assertEqual(self.check().state, "up-to-date")
        write(self.code / "notes.txt", "x\n")
        second = self.commit("Notes")
        self.assertEqual(self.check().state, "changed")
        self.assertEqual(self.check(**{"../code": second}).state, "up-to-date")

        self.link(checked=SHA)
        self.assertEqual(self.check().state, "unavailable")
        self.assertIn("not in this repository", self.check().message)

        git(self.code, "checkout", "--quiet", "--orphan", "other")
        self.commit("Unrelated history")
        self.link()
        self.assertIn("does not come after", self.check().message)

        (self.root / "projects" / "demo" / "README.md").unlink()
        write(self.root / "projects" / "demo" / "README.md", "---\n" + yaml.safe_dump(overview(repositories=[{"path": "../missing"}]), sort_keys=False) + "---\n")
        missing = self.check()
        self.assertEqual(missing.state, "unavailable")
        self.assertIn("does not exist on this computer", missing.message)

    def test_link_and_record_a_check(self) -> None:
        links, link = codedocs.with_link(self.root, [], "../code", remote="https://user:secret@example.invalid/code.git")
        self.assertEqual((link.path, link.checked, link.remote), ("../code", self.first, "https://example.invalid/code.git"))
        with self.assertRaisesRegex(codedocs.CodeDocsError, "already linked"):
            codedocs.with_link(self.root, links, str(self.code))
        with self.assertRaisesRegex(codedocs.CodeDocsError, "not a Git repository"):
            codedocs.with_link(self.root, links, str(self.root))
        write(self.code / "x.py", "x = 1\n")
        second = self.commit("More")
        marked = codedocs.with_checked(self.root, links, "../code", second[:8])
        self.assertEqual(marked[0].checked, second)
        with self.assertRaisesRegex(codedocs.CodeDocsError, "does not come after"):
            codedocs.with_checked(self.root, marked, "../code", self.first)
        self.assertEqual(codedocs.without_link(self.root, marked, "../code"), [])
        self.assertIsNone(codedocs.links_metadata([]))

    def test_commit_details(self) -> None:
        details = codedocs.commit_details(self.code, self.first[:7])
        self.assertEqual((details["sha"], details["subject"], details["author"]), (self.first, "Start", "Bob"))
        self.assertIn({"status": "added", "path": "demo/cli.py"}, details["files"])
        self.assertIn("+import argparse", details["diff"])
        with self.assertRaisesRegex(codedocs.CodeDocsError, "not a commit hash"):
            codedocs.commit_details(self.code, "HEAD; rm -rf /")

    def test_kos_code_command_line(self) -> None:
        page(self.root, "readme-page", "x\n")  # a lint-clean workspace
        write(self.root / "projects" / "demo" / "README.md", "---\n" + yaml.safe_dump(overview(), sort_keys=False) + "---\n\n# Demo\n")
        linked = run_kos(self.root, "code", "link", "demo", "../code", "--json")
        self.assertEqual(linked.returncode, 0, linked.stderr)
        self.assertEqual(json.loads(linked.stdout)["repositories"][0]["checked"], self.first)

        write(self.code / "pyproject.toml", '[project]\nname = "demo"\ndependencies = ["httpx"]\n')
        head = self.commit("Switch to httpx")
        checked = run_kos(self.root, "code", "check", "demo")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("Propose decision: Add the dependency httpx", checked.stdout)
        self.assertIn(f"kos code mark demo --commit {head[:12]}", checked.stdout)

        proposed = run_kos(self.root, "code", "propose", "demo", "dependency-added:httpx", "--json")
        self.assertEqual(proposed.returncode, 0, proposed.stderr)
        self.assertEqual(json.loads(proposed.stdout)["path"], "projects/demo/decisions/add-the-dependency-httpx.md")
        refused = run_kos(self.root, "code", "propose", "demo", "dependency-added:httpx")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("already exists", refused.stderr)

        self.assertEqual(run_kos(self.root, "code", "mark", "demo").returncode, 0)
        report = json.loads(run_kos(self.root, "code", "check", "demo", "--json").stdout)
        self.assertEqual(report["repositories"][0]["state"], "up-to-date")
        self.assertEqual(run_kos(self.root, "lint").returncode, 0)
        self.assertEqual(run_kos(self.root, "code", "unlink", "demo", "../code").returncode, 0)
        self.assertNotIn("repositories", (self.root / "projects" / "demo" / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
