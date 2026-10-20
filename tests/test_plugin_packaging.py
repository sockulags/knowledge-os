import contextlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
import tempfile
import unittest
from pathlib import Path

from knowledge_os.skills import parse_skill


ROOT = Path(__file__).resolve().parents[1]
SKILL_FILES = sorted((ROOT / "skills").rglob("*.md"))
LAUNCHER = "-m knowledge_os"
CAPTURE = ROOT / "skills" / "knowledge-os-capture"
CAPTURE_REFERENCES = ("setup.md", "cli-fallback.md")


def _capture_text() -> str:
    """The capture skill body plus the references it loads on demand."""

    paths = [CAPTURE / "SKILL.md", *(CAPTURE / "references" / name for name in CAPTURE_REFERENCES)]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def _code_snippets(text: str) -> list[str]:
    """Each line of a fenced block and each inline code span, whitespace-normalized."""

    fenced: list[str] = []
    prose: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        (fenced if in_fence else prose).append(line)
    spans = re.findall(r"`([^`]+)`", "\n".join(prose))
    return [" ".join(snippet.split()) for snippet in fenced + spans]


def _cli_commands(text: str) -> list[str]:
    """The arguments after ``-m knowledge_os`` in every snippet that runs the CLI.

    The generic ``... --root <root> ...`` form and optional ``[...]`` groups are
    not commands, so they are skipped and stripped."""

    commands = []
    for snippet in _code_snippets(text):
        if LAUNCHER not in snippet:
            continue
        rest = snippet.split(LAUNCHER, 1)[1]
        rest = re.sub(r"\[[^\]]*\]", "", rest).strip()
        if not rest or rest.endswith("...") or rest.endswith("COMMAND"):
            continue
        commands.append(rest)
    return commands


def _sh_blocks(text: str) -> list[str]:
    return re.findall(r"^```sh\n(.*?)^```", text, flags=re.MULTILINE | re.DOTALL)


class PluginPackagingTests(unittest.TestCase):
    def test_plugin_manifest_and_marketplace_keep_the_root_skill_packaged(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        package = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "knowledge-os")
        self.assertEqual(manifest["version"], package["project"]["version"])
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertIn("repository documentation", manifest["description"])
        self.assertNotIn("hooks", manifest)

        skill_path = ROOT / "skills" / "knowledge-os-capture" / "SKILL.md"
        skill = parse_skill(skill_path, root=ROOT)
        self.assertEqual(skill.name, "knowledge-os-capture")

        documentation_skill_path = ROOT / "skills" / "knowledge-os-documentation" / "SKILL.md"
        documentation_skill = parse_skill(documentation_skill_path, root=ROOT)
        self.assertEqual(documentation_skill.name, "knowledge-os-documentation")
        self.assertTrue(
            (documentation_skill_path.parent / "references" / "init.md").is_file()
        )
        self.assertTrue(
            (documentation_skill_path.parent / "references" / "documentation-workflow.md").is_file()
        )
        self.assertEqual(list(documentation_skill_path.parent.glob("scripts/*")), [])

        self.assertIn("documentation", manifest["description"])
        self.assertIn("Capture approved Knowledge OS records", manifest["interface"]["capabilities"])
        self.assertIn(
            "Initialize global Codex and Claude documentation guidance",
            manifest["interface"]["capabilities"],
        )
        self.assertIn(
            "Initialize repository project bindings",
            manifest["interface"]["capabilities"],
        )
        self.assertIn(
            "Retrieve and maintain task-relevant documentation",
            manifest["interface"]["capabilities"],
        )

        documentation_body = documentation_skill_path.read_text(encoding="utf-8")
        init_body = (documentation_skill_path.parent / "references" / "init.md").read_text(
            encoding="utf-8"
        )
        workflow_body = (
            documentation_skill_path.parent / "references" / "documentation-workflow.md"
        ).read_text(encoding="utf-8")
        for required in (
            "direct user authorization",
            "Missing or ambiguous project bindings are safe no-ops",
            "Never capture conversational memory",
            "-m knowledge_os --root <root> search",
            "-m knowledge_os --root <root> context",
            "-m knowledge_os --root <root> capture",
            "-m knowledge_os --root <root> inspect",
            "-m knowledge_os --root <root> update",
            "--writer agent",
        ):
            self.assertIn(required, documentation_body + init_body + workflow_body)
        self.assertIn("~/.knowledge-os/config.toml", init_body)
        self.assertIn(".knowledge-os-project.toml", init_body)
        self.assertIn("[[knowledge_os.projects]]", init_body)
        self.assertIn("longest matching path", init_body)
        for required in (
            "init-global --workspace PATH",
            "--host codex",
            "--host claude",
            "init-repo --repo PATH",
            "--project ID[=RELATIVE_PATH]",
            "--user-home PATH",
            "--replace",
            "--json",
        ):
            self.assertIn(required, init_body)
        self.assertIn("Search relevance is not", workflow_body)
        self.assertIn("--root <root> lint", workflow_body)
        self.assertIn("knowledge_os --root <root> index", " ".join(workflow_body.split()))

        marketplace = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
        )
        self.assertEqual(marketplace["name"], "knowledge-os")
        self.assertIn("documentation", marketplace["interface"]["description"])
        self.assertIn(
            "Capture approved Knowledge OS records",
            marketplace["interface"]["capabilities"],
        )
        self.assertIn(
            "Retrieve and maintain task-relevant documentation",
            marketplace["interface"]["capabilities"],
        )
        self.assertEqual(len(marketplace["plugins"]), 1)
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "knowledge-os")
        self.assertEqual(entry["source"], {"source": "local", "path": "./"})
        self.assertEqual(
            entry["policy"],
            {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        )
        self.assertEqual(entry["category"], "Productivity")

    def test_claude_code_plugin_manifest_and_marketplace_keep_the_root_skill_packaged(self) -> None:
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        package = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "knowledge-os")
        self.assertEqual(manifest["version"], package["project"]["version"])
        self.assertEqual(manifest["skills"], "./skills/")

        marketplace = json.loads(
            (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        self.assertEqual(marketplace["name"], "knowledge-os")
        self.assertEqual(len(marketplace["plugins"]), 1)
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "knowledge-os")
        self.assertEqual(entry["source"], "./")
        self.assertEqual(entry["version"], manifest["version"])
        self.assertEqual(entry["category"], "Productivity")
        self.assertIn("repository documentation", entry["description"])

    def test_both_plugins_register_the_kos_mcp_server(self) -> None:
        expected = {"knowledge-os": {"command": "kos", "args": ["mcp"]}}

        claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(claude["mcpServers"], expected)

        codex = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(codex["mcpServers"], "./.codex-plugin/mcp.json")
        servers = json.loads((ROOT / codex["mcpServers"]).read_text(encoding="utf-8"))
        self.assertEqual(servers, {"mcpServers": expected})
        # No root .mcp.json: Claude Code would otherwise offer the server as a
        # project server to anyone working in this repository.
        self.assertFalse((ROOT / ".mcp.json").exists())

        # The command the plugins run exists and takes no workspace argument.
        from knowledge_os.cli import build_parser

        args = build_parser().parse_args(["mcp"])
        self.assertEqual(args.command, "mcp")

    def test_skills_prefer_the_mcp_tools_and_keep_a_cli_fallback(self) -> None:
        tools = ("search", "read_page", "write_note", "propose_decision", "list_proposed_decisions")
        for name in ("knowledge-os-capture", "knowledge-os-documentation"):
            with self.subTest(skill=name):
                body = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("MCP", body)
                for tool in tools[:3]:
                    self.assertIn(f"`{tool}`", body)
                self.assertIn("CLI fallback", body)
        capture = (CAPTURE / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`propose_decision`", capture)

    def test_capture_skill_loads_the_cli_details_only_on_demand(self) -> None:
        body = (CAPTURE / "SKILL.md").read_text(encoding="utf-8")
        self.assertLess(len(body.splitlines()), 80)
        # The CLI setup and capture flow live in references, so the body that
        # loads on every trigger (and is exported into context) has no scripts.
        self.assertNotIn("```", body)
        for name in CAPTURE_REFERENCES:
            with self.subTest(reference=name):
                self.assertIn(f"](references/{name})", body)
                reference = (CAPTURE / "references" / name).read_text(encoding="utf-8")
                self.assertIn("Read this only when", reference)

    def test_every_skill_description_says_when_and_when_not_to_use_it(self) -> None:
        names = {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")}
        for name in sorted(names):
            with self.subTest(skill=name):
                description = parse_skill(ROOT / "skills" / name / "SKILL.md", root=ROOT).description
                self.assertTrue(description.startswith("Use when"), description)
                not_for = description.split("Not for", 1)
                self.assertEqual(len(not_for), 2, description)
                # The "Not for" part points at another skill that does that job.
                pointed = {other for other in names - {name} if f"(use {other})" in not_for[1]}
                self.assertTrue(pointed, not_for[1])

    def test_capture_skill_keeps_approval_and_safe_noop_contract(self) -> None:
        body = (CAPTURE / "SKILL.md").read_text(encoding="utf-8")
        for required in ("save this", "spara detta", "Never write before approval."):
            self.assertIn(required, body)
        self.assertNotIn("disable-model-invocation", body)
        # The POSIX blocks run in test_capture_posix_setup_runs_under_set_u_in_a_clean_shell;
        # the PowerShell blocks are not run here, so keep their launcher and install branches.
        setup = (CAPTURE / "references" / "setup.md").read_text(encoding="utf-8")
        for required in (
            "py', '-3.11",
            "py', '-3')",
            "$venv -eq 'True'",
            "$venv -eq 'False'",
            "-m pip install \"${pluginRoot}[mcp]\"",
            "-m pip install --user \"${pluginRoot}[mcp]\"",
        ):
            self.assertIn(required, setup)
        cli = (CAPTURE / "references" / "cli-fallback.md").read_text(encoding="utf-8")
        self.assertIn("`finally`-style", cli)
        self.assertIn("Never recursively remove", " ".join(cli.split()))

    def test_capture_and_documentation_skills_report_writes_held_for_review(self) -> None:
        documentation = ROOT / "skills" / "knowledge-os-documentation"
        bodies = {
            "knowledge-os-capture": _capture_text(),
            "knowledge-os-documentation": (documentation / "SKILL.md").read_text(encoding="utf-8"),
        }
        for name, body in bodies.items():
            with self.subTest(skill=name):
                for required in (
                    "waiting_for_review",
                    "Decide inbox",
                    "nothing is written yet",
                    "do not write it again",
                    "`list_proposed_changes`",
                    "`read_proposed_change`",
                    "--writer agent",
                ):
                    self.assertIn(required, " ".join(body.split()))
        capture = " ".join(bodies["knowledge-os-capture"].split())
        self.assertIn("Do not report it as saved", capture)
        self.assertIn("`record_kind: decision`", capture)
        self.assertIn("only `knowledge` and `project` records may carry", capture)

    def test_skills_never_run_a_bare_kos_and_name_the_workspace_root(self) -> None:
        for path in SKILL_FILES:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(re.findall(r"(?<![\w./-])kos [a-z<-][\w-]*", text), [])
        for name in ("ingest-source", "review-discovery", "knowledge-os-capture", "knowledge-os-documentation"):
            with self.subTest(skill=name):
                body = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("KNOWLEDGE_OS_ROOT", body)
                self.assertIn("~/.knowledge-os/config.toml", body)
                self.assertIn("never as a bare `kos`", " ".join(body.split()))
        ingest = (ROOT / "skills" / "ingest-source" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("inferred from the current directory", ingest)
        self.assertIn("Knowledge OS repository itself", ingest)

    def test_every_cli_command_in_the_skills_parses(self) -> None:
        from knowledge_os.cli import build_parser

        seen: set[str] = set()
        for path in SKILL_FILES:
            for command in _cli_commands(path.read_text(encoding="utf-8")):
                with self.subTest(path=path.relative_to(ROOT).as_posix(), command=command):
                    argv = shlex.split(command)
                    stderr = io.StringIO()
                    try:
                        with contextlib.redirect_stderr(stderr):
                            args = build_parser().parse_args(argv)
                    except SystemExit:
                        self.fail(f"{command!r} does not parse: {stderr.getvalue().strip()}")
                    self.assertIsNotNone(args.command, command)
                    seen.add(args.command)
                    if args.command != "documentation":
                        self.assertIn("root", vars(args), f"{command!r} has no --root")
        self.assertLessEqual(
            {"capture", "update", "inspect", "search", "context", "ingest", "lint", "index",
             "discovery", "decision", "supersede", "documentation"},
            seen,
        )

    @unittest.skipUnless(shutil.which("sh"), "needs a POSIX sh")
    def test_capture_posix_setup_runs_under_set_u_in_a_clean_shell(self) -> None:
        skill_path = CAPTURE / "SKILL.md"
        blocks = [
            block
            for name in CAPTURE_REFERENCES
            for block in _sh_blocks((CAPTURE / "references" / name).read_text(encoding="utf-8"))
        ]
        self.assertGreaterEqual(len(blocks), 5)
        body = "".join(blocks).replace("<absolute path to the loaded SKILL.md>", skill_path.as_posix())
        stub = (
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$KOS_STUB_LOG\"\n"
            "case \"$*\" in\n"
            "  *sys.base_prefix*) echo True ;;\n"
            "  *config.toml*) printf '%s\\n' \"${KOS_STUB_CONFIG_ROOT:-}\" ;;\n"
            "esac\n"
            "exit 0\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            (temp / "bin").mkdir()
            for name in ("python3.11", "pip"):
                (temp / "bin" / name).write_text(stub, encoding="utf-8", newline="\n")
                (temp / "bin" / name).chmod(0o755)
            script = temp / "setup.sh"
            script.write_text(
                "set -eu\n"
                'PATH="$(cd "$(dirname "$0")" && pwd)/bin:$PATH"\n'
                "candidate=candidate.md\n" + body,
                encoding="utf-8",
                newline="\n",
            )
            workspace = temp / "kb"
            workspace.mkdir()
            (workspace / "knowledge-os.toml").write_text("[workspace]\nversion = 1\n", encoding="utf-8")
            home = temp / "home"
            home.mkdir()
            log = temp / "calls.log"

            def run(**extra: str) -> list[str]:
                log.write_text("", encoding="utf-8")
                env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home), "KOS_STUB_LOG": log.as_posix()}
                for key in ("SYSTEMROOT", "WINDIR"):
                    if key in os.environ:
                        env[key] = os.environ[key]
                env.update(extra)
                done = subprocess.run(
                    [shutil.which("sh"), script.as_posix()],
                    cwd=temp, env=env, capture_output=True, text=True, check=False,
                )
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(done.stderr, "")
                return log.read_text(encoding="utf-8").splitlines()

            calls = run(KNOWLEDGE_OS_ROOT=workspace.as_posix())
            installs = [call for call in calls if call.startswith("-m pip install")]
            self.assertEqual(len(installs), 1, calls)
            self.assertTrue(installs[0].endswith(f"{ROOT.name}[mcp]"), installs[0])
            self.assertIn(
                f"-m knowledge_os --root {workspace.as_posix()} capture candidate.md --writer agent --json", calls
            )

            # Neither KNOWLEDGE_OS_ROOT nor a configured workspace: a safe no-op.
            calls = run()
            self.assertFalse([call for call in calls if "knowledge_os --root" in call], calls)
            self.assertFalse([call for call in calls if "pip install" in call], calls)

            # The workspace named in ~/.knowledge-os/config.toml is used when the variable is unset.
            calls = run(KOS_STUB_CONFIG_ROOT=workspace.as_posix())
            self.assertIn(
                f"-m knowledge_os --root {workspace.as_posix()} capture candidate.md --writer agent --json", calls
            )

    @unittest.skipUnless(sys.version_info >= (3, 11), "Knowledge OS requires Python >=3.11")
    def test_local_package_installs_and_runs_from_another_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp_root = Path(directory)
            venv_root = temp_root / "venv"
            other_cwd = temp_root / "other-cwd"
            other_cwd.mkdir()

            created = subprocess.run(
                [sys.executable, "-m", "venv", "--system-site-packages", str(venv_root)],
                cwd=other_cwd,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            python_path = (
                venv_root / "Scripts" / "python.exe"
                if os.name == "nt"
                else venv_root / "bin" / "python"
            )
            self.assertTrue(python_path.is_file())

            venv_state = subprocess.run(
                [
                    str(python_path),
                    "-c",
                    "import sys; print(sys.prefix != sys.base_prefix)",
                ],
                cwd=other_cwd,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(venv_state.returncode, 0, venv_state.stderr)
            self.assertEqual(venv_state.stdout.strip(), "True")

            install_command = [
                str(python_path),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-build-isolation",
                str(ROOT),
            ]
            self.assertNotIn("--user", install_command)
            installed = subprocess.run(
                install_command,
                cwd=other_cwd,
                capture_output=True,
                text=True,
                check=False,
            )
            python_environment = os.environ.copy()
            if installed.returncode != 0:
                self.assertIn("bdist_wheel", installed.stderr)
                source_copy = temp_root / "source"
                shutil.copytree(
                    ROOT,
                    source_copy,
                    ignore=shutil.ignore_patterns(
                        ".git", ".venv", ".ruff_cache", "build", "dist", "*.pyc", "__pycache__"
                    ),
                )
                legacy_setup = source_copy / "setup.py"
                legacy_setup.write_text(
                    f"import os\nos.chdir({str(source_copy)!r})\nfrom setuptools import setup\nsetup()\n",
                    encoding="utf-8",
                )
                install_lib = temp_root / "installed"
                legacy = subprocess.run(
                    [
                        str(python_path),
                        str(legacy_setup),
                        "install",
                        "--single-version-externally-managed",
                        "--record",
                        str(temp_root / "install-record.txt"),
                        "--install-lib",
                        str(install_lib),
                        "--install-scripts",
                        str(temp_root / "bin"),
                        "--no-compile",
                    ],
                    cwd=other_cwd,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(legacy.returncode, 0, legacy.stderr)
                python_environment["PYTHONPATH"] = str(install_lib)
            else:
                self.assertNotIn(str(ROOT), installed.stdout + installed.stderr)

            imported = subprocess.run(
                [
                    str(python_path),
                    "-c",
                    "import knowledge_os; print(knowledge_os.__file__)",
                ],
                cwd=other_cwd,
                capture_output=True,
                text=True,
                check=False,
                env=python_environment,
            )
            self.assertEqual(imported.returncode, 0, imported.stderr)
            self.assertIn("knowledge_os", imported.stdout)
            self.assertIn(str(temp_root), imported.stdout)
            self.assertNotIn(str(ROOT), imported.stdout)

            cli = subprocess.run(
                [str(python_path), "-m", "knowledge_os", "--help"],
                cwd=other_cwd,
                capture_output=True,
                text=True,
                check=False,
                env=python_environment,
            )
            self.assertEqual(cli.returncode, 0, cli.stderr)
            self.assertIn("usage:", cli.stdout.lower())


if __name__ == "__main__":
    unittest.main()
