"""Shared scaffolding for the reader test suite.

Follows the repository's existing test convention exactly (see
tests/test_vertical_slice.py): unittest only, no pytest, no fixtures, no
conftest.py. A test builds its own workspace on disk inside a
tempfile.TemporaryDirectory() and calls the helpers below to populate and
optionally serve it. Stage-B units build all of their end-to-end tests on
``serve``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import yaml

from knowledge_os.index import rebuild_indexes
from knowledge_os.workspace import Workspace

REPOSITORY = Path(__file__).resolve().parents[1]

#: Fixed ids for :func:`write_decision_fixture`'s isolated project. Reader
#: API tests that assert on "the one open proposal" or "N decisions govern
#: this workspace" behavior must not depend on which draft decision happens
#: to be live in the real corpus -- the real corpus's draft decisions change
#: over time as Lucas accepts or withdraws them (the openknowledge-pivot
#: decision, for example, was withdrawn and replaced by a new draft that
#: Lucas is expected to accept soon). Those assertions get this isolated,
#: never-changing fixture instead.
FIXTURE_PROJECT_ID = "fixture-decisions-project"
FIXTURE_GOVERNING_IDS = (
    "fixture-governing-alpha",
    "fixture-governing-beta",
    "fixture-governing-gamma",
)
FIXTURE_PROPOSED_ID = "fixture-proposed-decision"

MANAGED_DIRECTORIES = (
    "inbox",
    "knowledge",
    "projects",
    "sources",
    "memory",
    "syntheses",
    "discoveries",
    "skills",
    "indexes",
    "tooling",
)


def create_workspace(root: Path, *, name: str = "reader-test") -> None:
    """Write a minimal, valid knowledge-os.toml and every managed directory."""

    (root / "knowledge-os.toml").write_text(f'[workspace]\nname = "{name}"\nversion = 1\n', encoding="utf-8")
    for directory in MANAGED_DIRECTORIES:
        (root / directory).mkdir(parents=True, exist_ok=True)


def write_record(root: Path, rel_path: str, metadata: dict, body: str = "Body.\n") -> Path:
    """Write one managed record at a workspace-relative path.

    ``rel_path`` is relative to the workspace root, e.g.
    ``"knowledge/some-id.md"`` or ``"projects/demo/README.md"`` for a
    project overview. Frontmatter is rendered the same way the rest of the
    test suite renders it: ``yaml.safe_dump(metadata, sort_keys=False)``.
    """

    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.safe_dump(metadata, sort_keys=False)
    path.write_text(f"---\n{rendered}---\n\n{body}", encoding="utf-8")
    return path


def write_decision_fixture(root: Path) -> None:
    """Build a small, self-contained, indexed workspace with one project
    overview, three active ("in force") decisions, and one draft decision
    waiting on approval ("proposed" / "waiting on you"). See
    ``FIXTURE_PROJECT_ID`` for why this exists instead of asserting against
    the real corpus's own draft decisions.
    """

    create_workspace(root)
    write_record(
        root,
        f"projects/{FIXTURE_PROJECT_ID}/README.md",
        {
            "id": FIXTURE_PROJECT_ID,
            "title": "Fixture decisions project overview",
            "type": "project",
            "status": "active",
            "scope": f"project:{FIXTURE_PROJECT_ID}",
            "created": "2026-08-29",
            "updated": "2026-08-29",
            "provenance": [{"kind": "fixture", "reference": FIXTURE_PROJECT_ID}],
        },
        "Fixture decisions project overview.\n",
    )
    for governing_id in FIXTURE_GOVERNING_IDS:
        write_record(
            root,
            f"projects/{FIXTURE_PROJECT_ID}/{governing_id}.md",
            {
                "id": governing_id,
                "title": governing_id.replace("-", " ").title(),
                "type": "project",
                "record_kind": "decision",
                "status": "active",
                "scope": f"project:{FIXTURE_PROJECT_ID}",
                "created": "2026-08-29",
                "updated": "2026-08-29",
                "provenance": [
                    {
                        "kind": "decision-acceptance",
                        "reference": f"conversation:2026-08-29:{governing_id}",
                        "captured": "2026-08-29T12:00:00Z",
                    }
                ],
            },
            f"{governing_id} governing body.\n",
        )
    write_record(
        root,
        f"projects/{FIXTURE_PROJECT_ID}/{FIXTURE_PROPOSED_ID}.md",
        {
            "id": FIXTURE_PROPOSED_ID,
            "title": "Fixture proposed decision",
            "type": "project",
            "record_kind": "decision",
            "status": "draft",
            "scope": f"project:{FIXTURE_PROJECT_ID}",
            "created": "2026-08-30",
            "updated": "2026-08-30",
            "provenance": [
                {
                    "kind": "user-approved-conversation",
                    "reference": "conversation:2026-08-30:fixture-proposed-decision-approval",
                }
            ],
        },
        "Fixture proposed decision body.\n",
    )
    rebuild_indexes(Workspace(root))


def _poll_until_serving(base_url: str, process: subprocess.Popen, timeout: float) -> None:
    """Poll ``/api/workspace``, not ``/``: the bare root serves the built
    React app's ``index.html`` and answers 503 before ``npm run build`` has
    ever run (see ``app.py``'s SPA fallback), which would make every test
    that only needs the JSON API wait out the full timeout in a checkout
    with no frontend build. The API route is always live once the process
    accepts connections at all."""

    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(f"kos-read exited early with code {exit_code} before serving {base_url}")
        try:
            with urllib.request.urlopen(base_url + "/api/workspace", timeout=1):
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            last_error = exc
            time.sleep(0.1)
    raise RuntimeError(f"kos-read did not start serving {base_url} within {timeout}s") from last_error


@contextmanager
def serve(root: Path, port: int, *, timeout: float = 15.0) -> Iterator[str]:
    """Start ``kos-read --root root --port port`` and yield its base URL.

    Polls until the port answers an HTTP request before yielding, and
    always terminates the subprocess in a ``finally``, even if the caller's
    test raises. Output is captured to a temporary file (not a pipe) so a
    long test session issuing many requests cannot deadlock the child on a
    full pipe buffer; the file is surfaced in the error message if the
    server never comes up.
    """

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPOSITORY) + os.pathsep + environment.get("PYTHONPATH", "")
    base_url = f"http://127.0.0.1:{port}"
    log = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    # No `cwd=root`: `--root` is always passed explicitly above, so
    # Workspace.discover() never falls back to the process's current
    # directory (see workspace.py) and the subprocess has no need to run
    # with `root` as its working directory. On Windows, a child process's
    # current directory is held open as a live directory handle for as
    # long as the process runs it; setting it to the caller's own
    # tempfile.TemporaryDirectory() raced that directory's cleanup against
    # the OS finishing release of the handle after `process.wait()`
    # returned, intermittently raising PermissionError: [WinError 32] from
    # the temp directory's own removal. Leaving `cwd` at the parent's
    # default avoids taking that handle on `root` at all.
    process = subprocess.Popen(
        [sys.executable, "-m", "knowledge_os.reader", "--root", str(root), "--port", str(port)],
        env=environment,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        try:
            _poll_until_serving(base_url, process, timeout)
        except RuntimeError as exc:
            log.seek(0)
            raise RuntimeError(f"{exc}\n--- kos-read output ---\n{log.read()}") from None
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log.close()
