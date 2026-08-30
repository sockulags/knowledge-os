import json
import os
import shutil
import subprocess
import sys
import tomllib
import tempfile
import unittest
from pathlib import Path

from knowledge_os.skills import parse_skill


ROOT = Path(__file__).resolve().parents[1]


class PluginPackagingTests(unittest.TestCase):
    def test_plugin_manifest_and_marketplace_keep_the_root_skill_packaged(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        package = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "knowledge-os")
        self.assertEqual(manifest["version"], package["project"]["version"])
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertNotIn("hooks", manifest)

        skill_path = ROOT / "skills" / "knowledge-os-capture" / "SKILL.md"
        skill = parse_skill(skill_path, root=ROOT)
        self.assertEqual(skill.name, "knowledge-os-capture")

        marketplace = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
        )
        self.assertEqual(marketplace["name"], "knowledge-os")
        self.assertEqual(len(marketplace["plugins"]), 1)
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "knowledge-os")
        self.assertEqual(entry["source"], {"source": "local", "path": "./"})
        self.assertEqual(
            entry["policy"],
            {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        )
        self.assertEqual(entry["category"], "Productivity")

    def test_capture_skill_keeps_approval_and_safe_noop_contract(self) -> None:
        body = (ROOT / "skills" / "knowledge-os-capture" / "SKILL.md").read_text(encoding="utf-8")
        for required in (
            "save this",
            "spara detta",
            "Never write before approval.",
            "KNOWLEDGE_OS_ROOT",
            "py -3.11",
            "python3.11",
            "python3` fallback",
            "py', '-3.11",
            "sys.prefix != sys.base_prefix",
            "$venv -eq 'True'",
            "$venv -eq 'False'",
            "venv_state=$(\"$python_cmd\"",
            "case \"$venv_state\" in",
            "-m pip install \"$pluginRoot\"",
            "-m pip install --user \"$pluginRoot\"",
            "-m pip install \"$plugin_root\"",
            "-m pip install --user \"$plugin_root\"",
            "import knowledge_os",
            "-m knowledge_os --root",
            "`finally`-style",
            "cleanup. Never recursively remove",
        ):
            self.assertIn(required, body)
        self.assertNotIn("disable-model-invocation", body)

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
