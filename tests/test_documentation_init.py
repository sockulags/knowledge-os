from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

import yaml

import knowledge_os.documentation_init as documentation_init


REPOSITORY = Path(__file__).resolve().parents[1]


def run_kos(cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPOSITORY) + os.pathsep + environment.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "knowledge_os", *arguments],
        cwd=cwd,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )


def create_workspace(root: Path, *, projects: tuple[str, ...] = ("demo",)) -> None:
    root.mkdir(parents=True)
    (root / "knowledge-os.toml").write_text('[workspace]\nname = "test-workspace"\nversion = 1\n', encoding="utf-8")
    for directory in ("knowledge", "projects", "sources", "memory", "syntheses", "discoveries", "skills", "indexes", "tooling"):
        (root / directory).mkdir()
    for project_id in projects:
        path = root / "projects" / project_id / "README.md"
        path.parent.mkdir()
        metadata = {
            "id": project_id,
            "title": f"{project_id} overview",
            "type": "project",
            "status": "active",
            "scope": f"project:{project_id}",
            "created": "2026-09-12",
            "updated": "2026-09-12",
            "provenance": [{"kind": "test", "reference": project_id}],
        }
        path.write_text(f"---\n{yaml.safe_dump(metadata, sort_keys=False)}---\n\nOverview.\n", encoding="utf-8")


class DocumentationInitTests(unittest.TestCase):
    def test_global_preserves_surrounding_text_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            home = root / "home"
            create_workspace(workspace)
            codex = home / ".codex" / "AGENTS.md"
            codex.parent.mkdir(parents=True)
            codex.write_text("before\n\nuser text\n", encoding="utf-8")

            first = run_kos(root, "documentation", "init-global", "--workspace", str(workspace), "--user-home", str(home), "--json")
            self.assertEqual(first.returncode, 0, first.stderr)
            before = codex.read_bytes()
            second = run_kos(root, "documentation", "init-global", "--workspace", str(workspace), "--user-home", str(home), "--json")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(before, codex.read_bytes())
            self.assertIn(b"before\r\n\r\nuser text\r\n", before)
            result = json.loads(second.stdout)
            self.assertFalse(result["changed"])
            self.assertTrue((home / ".claude" / "CLAUDE.md").exists())
            config = tomllib.loads((home / ".knowledge-os" / "config.toml").read_text(encoding="utf-8"))
            self.assertEqual(config, {"knowledge_os": {"version": 1, "workspace": str(workspace.resolve())}})

    def test_global_replaces_only_managed_block_and_rejects_config_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            home = root / "home"
            create_workspace(workspace)
            agents = home / ".codex" / "AGENTS.md"
            agents.parent.mkdir(parents=True)
            agents.write_text("prefix\n<!-- BEGIN KNOWLEDGE OS DOCUMENTATION -->\nold\n<!-- END KNOWLEDGE OS DOCUMENTATION -->\nsuffix\n", encoding="utf-8")
            first = run_kos(root, "documentation", "init-global", "--workspace", str(workspace), "--host", "codex", "--user-home", str(home))
            self.assertEqual(first.returncode, 0, first.stderr)
            text = agents.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("prefix\n"))
            self.assertTrue(text.endswith("suffix\n"))
            self.assertIn("Write only with authority from the current request.", text)
            config = home / ".knowledge-os" / "config.toml"
            config.write_text("[knowledge_os]\nversion = 1\nworkspace = \"other\"\n", encoding="utf-8")
            failed = run_kos(root, "documentation", "init-global", "--workspace", str(workspace), "--host", "codex", "--user-home", str(home))
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("use --replace", failed.stderr)
            self.assertIn('workspace = "other"', config.read_text(encoding="utf-8"))

    def test_repo_writes_multiple_mappings_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            home = root / "home"
            repo = root / "repo"
            create_workspace(workspace, projects=("alpha", "beta"))
            (repo / "docs").mkdir(parents=True)
            initialized = run_kos(root, "documentation", "init-global", "--workspace", str(workspace), "--user-home", str(home))
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            first = run_kos(root, "documentation", "init-repo", "--repo", str(repo), "--project", "alpha", "--project", "beta=docs", "--user-home", str(home), "--json")
            self.assertEqual(first.returncode, 0, first.stderr)
            binding = repo / ".knowledge-os-project.toml"
            content = binding.read_bytes()
            parsed = tomllib.loads(content.decode("utf-8"))
            self.assertEqual(parsed["knowledge_os"]["version"], 1)
            self.assertEqual([(item["id"], item["path"]) for item in parsed["knowledge_os"]["projects"]], [("alpha", "."), ("beta", "docs")])
            second = run_kos(root, "documentation", "init-repo", "--repo", str(repo), "--project", "alpha", "--project", "beta=docs", "--user-home", str(home), "--json")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(content, binding.read_bytes())
            self.assertFalse(json.loads(second.stdout)["changed"])

    def test_repo_rejects_invalid_paths_and_missing_overview_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            home = root / "home"
            repo = root / "repo"
            create_workspace(workspace)
            repo.mkdir()
            self.assertEqual(run_kos(root, "documentation", "init-global", "--workspace", str(workspace), "--user-home", str(home)).returncode, 0)
            for mapping in ("bad_ID", "demo=../outside", "demo=missing"):
                result = run_kos(root, "documentation", "init-repo", "--repo", str(repo), "--project", mapping, "--user-home", str(home))
                self.assertNotEqual(result.returncode, 0, mapping)
                self.assertFalse((repo / ".knowledge-os-project.toml").exists())
            missing = run_kos(root, "documentation", "init-repo", "--repo", str(repo), "--project", "missing", "--user-home", str(home))
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("overview", missing.stderr)

    @unittest.skipUnless(os.name == "nt", "case-insensitive path alias is Windows-specific")
    def test_repo_rejects_paths_that_resolve_to_the_same_windows_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            home = root / "home"
            repo = root / "repo"
            create_workspace(workspace, projects=("alpha", "beta"))
            (repo / "docs").mkdir(parents=True)
            initialized = run_kos(
                root,
                "documentation",
                "init-global",
                "--workspace",
                str(workspace),
                "--user-home",
                str(home),
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)

            result = run_kos(
                root,
                "documentation",
                "init-repo",
                "--repo",
                str(repo),
                "--project",
                "alpha=docs",
                "--project",
                "beta=DOCS",
                "--user-home",
                str(home),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("resolve to the same directory", result.stderr)
            self.assertFalse((repo / ".knowledge-os-project.toml").exists())

    def test_global_write_failure_restores_files_changed_by_the_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            home = root / "home"
            create_workspace(workspace)
            real_atomic_write = documentation_init.atomic_write
            calls = 0

            def fail_on_second_write(path: Path, content: bytes) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("test write failure")
                real_atomic_write(path, content)

            with patch.object(documentation_init, "atomic_write", side_effect=fail_on_second_write):
                with self.assertRaises(documentation_init.DocumentationInitError):
                    documentation_init.init_global(workspace, user_home=home)
            self.assertFalse((home / ".knowledge-os" / "config.toml").exists())
            self.assertFalse((home / ".codex" / "AGENTS.md").exists())
            self.assertFalse((home / ".claude" / "CLAUDE.md").exists())


if __name__ == "__main__":
    unittest.main()
