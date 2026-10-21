from __future__ import annotations

import contextlib
import io
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import knowledge_os.workspace as workspace_module
from knowledge_os import cli
from knowledge_os.index import rebuild_indexes
from knowledge_os.init_workspace import init_workspace
from knowledge_os.workspace import Workspace, WorkspaceError, workspace_mutation_lock

REPOSITORY = Path(__file__).resolve().parents[1]

HOLD_LOCK = """
import sys, time
from pathlib import Path
from knowledge_os.workspace import Workspace, workspace_mutation_lock
with workspace_mutation_lock(Workspace(Path(sys.argv[1]))):
    print("locked", flush=True)
    time.sleep(float(sys.argv[2]))
"""


class LockWaitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = init_workspace(Path(self.temporary.name) / "kb")
        self.workspace = Workspace(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_waits_past_the_old_ten_second_limit_for_another_process(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(REPOSITORY) + os.pathsep + environment.get("PYTHONPATH", "")
        environment.pop(workspace_module.LOCK_TIMEOUT_ENV, None)
        holder = subprocess.Popen(
            [sys.executable, "-c", HOLD_LOCK, str(self.root), "13"],
            stdout=subprocess.PIPE,
            text=True,
            env=environment,
        )
        try:
            self.assertEqual(holder.stdout.readline().strip(), "locked")
            started = time.monotonic()
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop(workspace_module.LOCK_TIMEOUT_ENV, None)
                with workspace_mutation_lock(self.workspace):
                    waited = time.monotonic() - started
            self.assertGreater(waited, 11)
        finally:
            holder.wait(timeout=60)
            holder.stdout.close()

    def test_gives_up_at_the_deadline_with_a_readable_message(self) -> None:
        held = threading.Event()
        release = threading.Event()

        def hold() -> None:
            with workspace_mutation_lock(self.workspace):
                held.set()
                release.wait(10)

        thread = threading.Thread(target=hold)
        thread.start()
        try:
            self.assertTrue(held.wait(10))
            started = time.monotonic()
            with patch.dict(os.environ, {workspace_module.LOCK_TIMEOUT_ENV: "0.5"}):
                with self.assertRaisesRegex(WorkspaceError, "another kos operation"):
                    with workspace_mutation_lock(self.workspace):
                        pass
            self.assertLess(time.monotonic() - started, 5)
        finally:
            release.set()
            thread.join()

    def test_rejects_a_timeout_that_is_not_a_number(self) -> None:
        with patch.dict(os.environ, {workspace_module.LOCK_TIMEOUT_ENV: "soon"}):
            with self.assertRaisesRegex(WorkspaceError, workspace_module.LOCK_TIMEOUT_ENV):
                with workspace_mutation_lock(self.workspace):
                    pass


class IndexSwapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = init_workspace(Path(self.temporary.name) / "kb")
        self.workspace = Workspace(self.root)
        rebuild_indexes(self.workspace)
        self.database = self.root / "indexes" / "catalog.sqlite3"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _open_reader(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"file:{self.database.as_posix()}?mode=ro", uri=True, check_same_thread=False
        )
        connection.execute("SELECT count(*) FROM documents_fts").fetchone()
        return connection

    def test_rebuild_waits_for_a_reader_to_close_the_catalog(self) -> None:
        reader = self._open_reader()
        closer = threading.Timer(1.0, reader.close)
        closer.start()
        try:
            rebuild_indexes(self.workspace)
        finally:
            closer.join()
        connection = sqlite3.connect(f"file:{self.database.as_posix()}?mode=ro", uri=True)
        try:
            self.assertIsNotNone(connection.execute("SELECT count(*) FROM documents_fts").fetchone())
        finally:
            connection.close()

    @unittest.skipUnless(os.name == "nt", "only Windows refuses to replace an open file")
    def test_index_command_reports_a_catalog_held_open_too_long(self) -> None:
        reader = self._open_reader()
        stderr = io.StringIO()
        try:
            with patch.object(workspace_module, "REPLACE_RETRY_SECONDS", 0.3), patch.object(
                cli, "_refresh_semantic_index", lambda workspace: None
            ):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                    code = cli.main(["--root", str(self.root), "index"])
        finally:
            reader.close()
        self.assertEqual(code, 1)
        self.assertIn("could not be replaced", stderr.getvalue())
        self.assertFalse((self.root / "indexes" / ".catalog.sqlite3.tmp").exists())


if __name__ == "__main__":
    unittest.main()
