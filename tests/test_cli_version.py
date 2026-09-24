"""Tests for ``kos --version`` and the PATH-shadowing warning (issue #60).

Covers: version output in both frozen (installed app) and Python modes,
each warning condition, that the warning never reaches stdout (including
under ``--json`` and for ``kos mcp``), and that ``KOS_NO_PATH_WARNING``
silences it.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge_os import __version__
from knowledge_os.cli import main as kos_main
from knowledge_os.init_workspace import init_workspace
from knowledge_os.version_info import (
    KOS_LAUNCHED_BY_SHIM_ENV,
    KOS_NO_PATH_WARNING_ENV,
    path_warning,
    runtime_description,
    version_lines,
)


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = kos_main(argv)
    return code, out.getvalue(), err.getvalue()


class VersionOutputTests(unittest.TestCase):
    def test_python_mode_reports_interpreter_and_package(self) -> None:
        with patch.object(sys, "frozen", False, create=True):
            lines = version_lines()
        self.assertEqual(lines[0], f"kos {__version__}")
        self.assertIn(sys.executable, lines[1])
        self.assertIn("Python", lines[1])
        self.assertIn(str(Path(__file__).resolve().parents[1] / "knowledge_os"), lines[1])

    def test_python_mode_detects_editable_install(self) -> None:
        # This checkout is installed editable in the test venv, so the
        # heuristic (a pyproject.toml next to the package dir, outside
        # site-packages) should find it.
        description = runtime_description()
        if "site-packages" not in str(Path(__file__).resolve()):
            self.assertIn("editable install", description)

    def test_frozen_mode_reports_bundled_core(self) -> None:
        fake_exe = str(Path(tempfile.gettempdir()) / "kos-core.exe")
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", fake_exe):
            lines = version_lines()
        self.assertEqual(lines[0], f"kos {__version__}")
        self.assertTrue(lines[1].startswith("installed app (bundled core at "))
        self.assertIn("kos-core.exe", lines[1])

    def test_cli_version_flag_prints_and_exits_zero(self) -> None:
        with patch("knowledge_os.cli.path_warning", return_value=None):
            code, out, err = _run(["--version"])
        self.assertEqual(code, 0)
        self.assertIn(f"kos {__version__}", out)
        self.assertEqual(err, "")

    def test_cli_version_flag_works_without_a_workspace(self) -> None:
        # --version must not require discovering a workspace from cwd.
        with tempfile.TemporaryDirectory() as tmp, patch("knowledge_os.cli.path_warning", return_value=None):
            code, out, _err = _run(["--root", str(Path(tmp) / "does-not-exist"), "--version"])
        self.assertEqual(code, 0)
        self.assertIn(f"kos {__version__}", out)

    def test_no_command_still_errors(self) -> None:
        with patch("knowledge_os.cli.path_warning", return_value=None):
            with self.assertRaises(SystemExit):
                _run([])


class PathWarningConditionTests(unittest.TestCase):
    def test_no_warning_by_default_in_python_mode(self) -> None:
        with patch.object(sys, "frozen", False, create=True), patch.dict(
            "os.environ", {}, clear=False
        ), patch("knowledge_os.version_info._installed_app_core_exe", return_value=None):
            self.assertIsNone(path_warning())

    def test_python_mode_warns_when_installed_app_exists(self) -> None:
        fake_core = Path(tempfile.gettempdir()) / "knowledge-os-desktop" / "resources" / "core" / "kos-core.exe"
        with patch.object(sys, "frozen", False, create=True), patch(
            "knowledge_os.version_info._installed_app_core_exe", return_value=fake_core
        ):
            warning = path_warning()
        self.assertIsNotNone(warning)
        assert warning is not None
        self.assertIn("pip uninstall knowledge-os", warning)
        self.assertIn(str(fake_core), warning)

    def test_frozen_mode_no_shim_env_no_warning(self) -> None:
        with patch.object(sys, "frozen", True, create=True), patch.dict(
            "os.environ", {}, clear=False
        ):
            import os as _os

            _os.environ.pop(KOS_LAUNCHED_BY_SHIM_ENV, None)
            self.assertIsNone(path_warning())

    def test_frozen_mode_warns_when_shim_is_shadowed(self) -> None:
        shim_path = str(Path(tempfile.gettempdir()) / "app-bin" / "kos.cmd")
        other_kos = str(Path(tempfile.gettempdir()) / "pip-scripts" / "kos.exe")
        with patch.object(sys, "frozen", True, create=True), patch.dict(
            "os.environ", {KOS_LAUNCHED_BY_SHIM_ENV: shim_path}
        ), patch("shutil.which", return_value=other_kos):
            warning = path_warning()
        self.assertIsNotNone(warning)
        assert warning is not None
        self.assertIn(other_kos, warning)
        self.assertIn("pip uninstall knowledge-os", warning)

    def test_frozen_mode_no_warning_when_shim_matches_path(self) -> None:
        shim_path = str(Path(tempfile.gettempdir()) / "app-bin" / "kos.cmd")
        with patch.object(sys, "frozen", True, create=True), patch.dict(
            "os.environ", {KOS_LAUNCHED_BY_SHIM_ENV: shim_path}
        ), patch("shutil.which", return_value=shim_path):
            self.assertIsNone(path_warning())

    def test_frozen_mode_no_warning_when_kos_not_on_path(self) -> None:
        shim_path = str(Path(tempfile.gettempdir()) / "app-bin" / "kos.cmd")
        with patch.object(sys, "frozen", True, create=True), patch.dict(
            "os.environ", {KOS_LAUNCHED_BY_SHIM_ENV: shim_path}
        ), patch("shutil.which", return_value=None):
            self.assertIsNone(path_warning())

    def test_env_var_silences_any_warning(self) -> None:
        fake_core = Path(tempfile.gettempdir()) / "knowledge-os-desktop" / "resources" / "core" / "kos-core.exe"
        with patch.object(sys, "frozen", False, create=True), patch(
            "knowledge_os.version_info._installed_app_core_exe", return_value=fake_core
        ), patch.dict("os.environ", {KOS_NO_PATH_WARNING_ENV: "1"}):
            self.assertIsNone(path_warning())


class WarningNeverOnStdoutTests(unittest.TestCase):
    def _with_forced_warning(self):
        fake_core = Path(tempfile.gettempdir()) / "knowledge-os-desktop" / "resources" / "core" / "kos-core.exe"
        return patch.object(sys, "frozen", False, create=True), patch(
            "knowledge_os.version_info._installed_app_core_exe", return_value=fake_core
        )

    def test_warning_goes_to_stderr_not_stdout_on_lint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = init_workspace(Path(tmp) / "kb")
            p1, p2 = self._with_forced_warning()
            with p1, p2:
                code, out, err = _run(["--root", str(root), "lint"])
        self.assertEqual(code, 0)
        self.assertNotIn("pip uninstall", out)
        self.assertIn("pip uninstall", err)

    def test_json_output_stays_valid_json_even_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = init_workspace(Path(tmp) / "kb")
            p1, p2 = self._with_forced_warning()
            with p1, p2:
                code, out, err = _run(["--root", str(root), "search", "xyz", "--json"])
        self.assertEqual(code, 0)
        parsed = json.loads(out)  # raises if the warning leaked into stdout
        self.assertEqual(parsed, [])
        self.assertIn("pip uninstall", err)

    def test_mcp_command_prints_warning_only_to_stderr(self) -> None:
        # kos mcp hands stdio to the MCP server; we only need to verify that
        # the warning itself is emitted to stderr before that handoff, and
        # never mixed into stdout, without actually starting the server.
        p1, p2 = self._with_forced_warning()
        with p1, p2, patch("knowledge_os.agent_access.server.run", return_value=0):
            code, out, err = _run(["mcp"])
        self.assertEqual(code, 0)
        self.assertNotIn("pip uninstall", out)
        self.assertIn("pip uninstall", err)


if __name__ == "__main__":
    unittest.main()
