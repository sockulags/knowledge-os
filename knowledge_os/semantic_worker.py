"""The search model in its own process (issue #102).

Loading the native runtime (onnxruntime, numpy) has hung a whole process on a
Windows work computer: a thread stuck loading their libraries blocked the
reader's other requests and then its start. So no long-lived process of the
app loads it. ``kos model serve`` (``serve`` below) loads the model and
answers JSON lines on stdin/stdout; ``Worker`` starts it, gives it a time
limit to load, and talks to it. If it hangs or dies, the worker is stopped
and search by meaning reports ``failed`` with the reason, while full-text
search and the rest of the app carry on.

Requests are ``{"id", "op", ...}`` and answers ``{"id", ...}`` or
``{"id", "error"}``; the first line the process writes is ``{"ready": true}``
or ``{"error"}``. Operations:

- ``search`` (``root``, ``query``, ``limit``): matches from
  ``semantic.search``.
- ``refresh`` (``root``): brings ``indexes/semantic.sqlite3`` in line with
  the catalog, embedding only changed passages; ``counts`` is null when it
  was already current.

The process reads requests in one thread and answers each in its own, so a
search is not stuck behind a long refresh (the model itself runs one batch
at a time). It exits when its stdin closes, that is, when the app does.
"""

from __future__ import annotations

import atexit
import itertools
import json
import os
import subprocess
import sys
import threading
from collections import deque
from dataclasses import asdict
from pathlib import Path
from typing import IO, Any, Callable

from . import semantic
from .workspace import Workspace, validate_workspace

#: How long the model may take to load (a first load while an antivirus scans
#: a 570 MB file can take a while) before the worker is stopped.
LOAD_TIMEOUT = 180.0
#: How long a search waits for the worker before answering without meaning.
SEARCH_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# The worker process
# ---------------------------------------------------------------------------


def _handle(request: dict[str, Any], embedder: semantic.Embedder) -> dict[str, Any]:
    workspace = Workspace(Path(str(request["root"])))
    op = request.get("op")
    if op == "search":
        matches = semantic.search(workspace, str(request["query"]), embedder, int(request.get("limit", 20)))
        return {"matches": [asdict(match) for match in matches]}
    if op == "refresh":
        if semantic.is_current(workspace, embedder.spec):
            return {"counts": None}
        stamp = semantic.catalog_stamp(workspace)  # before reading, so a later write is caught next time
        documents, _issues = validate_workspace(workspace)
        return {"counts": semantic.update_index(workspace, documents, embedder, source_stamp=stamp)}
    raise semantic.SemanticError(f"unknown operation {op!r}")


def serve(stdin: IO[str] | None = None, stdout: IO[str] | None = None, *, embedder: Any = None) -> int:
    """Run as the worker process: load the model, then answer requests until
    stdin closes."""

    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    write_lock = threading.Lock()

    def send(message: dict[str, Any]) -> None:
        with write_lock:
            stdout.write(json.dumps(message) + "\n")
            stdout.flush()

    try:
        embedder = embedder or semantic.Embedder()
    except Exception as exc:
        send({"error": str(exc) or type(exc).__name__})
        return 1
    send({"ready": True})

    def answer(request: dict[str, Any]) -> None:
        try:
            send({"id": request.get("id"), **_handle(request, embedder)})
        except Exception as exc:
            send({"id": request.get("id"), "error": str(exc) or type(exc).__name__})

    threads = []
    for line in stdin:
        try:
            request = json.loads(line)
        except ValueError:
            continue
        thread = threading.Thread(target=answer, args=(request,), daemon=True)
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()
    return 0


# ---------------------------------------------------------------------------
# The app's side
# ---------------------------------------------------------------------------


def default_command() -> list[str]:
    """This same program with ``-m knowledge_os model serve``: the frozen
    desktop core (``kos-core.exe``) accepts ``-m`` like Python does."""

    return [sys.executable, "-m", "knowledge_os", "model", "serve"]


def _environment() -> dict[str, str]:
    env = dict(os.environ)
    if not getattr(sys, "frozen", False):
        # A Python install: make sure the child imports this same package.
        package_parent = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [package_parent, env.get("PYTHONPATH")]))
    env["PYTHONUNBUFFERED"] = "1"
    return env


class Worker:
    """Starts and talks to one worker process. ``state`` is ``"idle"``,
    ``"starting"``, ``"ready"``, or ``"failed"`` (``error`` says why)."""

    def __init__(
        self,
        command: list[str] | None = None,
        *,
        load_timeout: float = LOAD_TIMEOUT,
        env: dict[str, str] | None = None,
    ) -> None:
        self._command = command or default_command()
        self._load_timeout = load_timeout
        self._env = env
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._ready = threading.Event()
        self._ids = itertools.count(1)
        self._pending: dict[int, tuple[threading.Event, list[dict[str, Any]]]] = {}
        self._stderr: deque[str] = deque(maxlen=20)
        self.state = "idle"
        self.error: str | None = None

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Start the process unless it is starting or ready; returns at once."""

        with self._lock:
            if self.state in ("starting", "ready"):
                return
            self.state, self.error = "starting", None
            self._ready.clear()
            try:
                self._process = subprocess.Popen(
                    self._command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=self._env or _environment(),
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError as exc:
                self.state, self.error = "failed", f"could not start the search process: {exc}"
                return
            process = self._process
        threading.Thread(target=self._read, args=(process,), name="kos-semantic-read", daemon=True).start()
        threading.Thread(target=self._read_stderr, args=(process,), name="kos-semantic-log", daemon=True).start()
        threading.Thread(target=self._watch_load, args=(process,), name="kos-semantic-load", daemon=True).start()

    def wait_ready(self, timeout: float | None = None) -> bool:
        return self._ready.wait(timeout) and self.state == "ready"

    def stop(self) -> None:
        with self._lock:
            process, self._process = self._process, None
            if self.state != "failed":
                self.state = "idle"
        if process is not None:
            _kill(process)
        self._fail_pending("the search process was stopped")

    # -- requests -----------------------------------------------------------

    def request(self, op: str, timeout: float | None, **fields: Any) -> dict[str, Any]:
        """Send one request and wait for its answer; raises SemanticError when
        the worker is not ready, fails, or does not answer in time."""

        with self._lock:
            process = self._process
            if self.state != "ready" or process is None or process.stdin is None:
                raise semantic.SemanticError(self.error or "the search model is not loaded")
            request_id = next(self._ids)
            done = threading.Event()
            box: list[dict[str, Any]] = []
            self._pending[request_id] = (done, box)
            try:
                process.stdin.write((json.dumps({"id": request_id, "op": op, **fields}) + "\n").encode("utf-8"))
                process.stdin.flush()
            except OSError as exc:
                self._pending.pop(request_id, None)
                raise semantic.SemanticError(f"the search process stopped: {exc}") from exc
        if not done.wait(timeout):
            with self._lock:
                self._pending.pop(request_id, None)
            raise semantic.SemanticError(f"the search process did not answer within {timeout:.0f} seconds")
        answer = box[0]
        if "error" in answer:
            raise semantic.SemanticError(str(answer["error"]))
        return answer

    # -- threads ------------------------------------------------------------

    def _watch_load(self, process: subprocess.Popen[bytes]) -> None:
        if self._ready.wait(self._load_timeout):
            return
        with self._lock:
            if self._process is not process or self.state != "starting":
                return
            self._process = None
            self.state = "failed"
            self.error = f"the search model did not load within {self._load_timeout:.0f} seconds"
            self._ready.set()
        _kill(process)

    def _read(self, process: subprocess.Popen[bytes]) -> None:
        assert process.stdout is not None
        for raw in process.stdout:
            try:
                message = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(message, dict):
                continue
            if "id" not in message:
                with self._lock:
                    if self._process is not process:
                        return
                    if message.get("ready"):
                        self.state = "ready"
                    else:
                        self.state, self.error = "failed", str(message.get("error") or "the search model did not load")
                        self._process = None
                    self._ready.set()
                if self.state == "failed":
                    _kill(process)
                    process.stdout.close()
                    return
                continue
            with self._lock:
                entry = self._pending.pop(message["id"], None)
            if entry is not None:
                entry[1].append(message)
                entry[0].set()
        # The process ended.
        process.stdout.close()
        process.wait()
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        with self._lock:
            if self._process is process:
                self._process = None
                self.state = "failed"
                tail = " ".join(line.strip() for line in list(self._stderr)[-3:] if line.strip())
                self.error = f"the search process stopped (exit code {process.returncode})" + (f": {tail}" if tail else "")
                self._ready.set()
        self._fail_pending(self.error or "the search process stopped")

    def _read_stderr(self, process: subprocess.Popen[bytes]) -> None:
        assert process.stderr is not None
        for raw in process.stderr:
            self._stderr.append(raw.decode("utf-8", "replace"))
        process.stderr.close()

    def _fail_pending(self, reason: str) -> None:
        with self._lock:
            pending, self._pending = self._pending, {}
        for done, box in pending.values():
            box.append({"error": reason})
            done.set()


def _kill(process: subprocess.Popen[bytes]) -> None:
    try:
        process.kill()
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass
    if process.stdin is not None:
        try:
            process.stdin.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# The process's one worker (the reader and the CLI)
# ---------------------------------------------------------------------------

_worker: Worker | None = None
_worker_lock = threading.Lock()
_refreshing: set[str] = set()
_refresh_lock = threading.Lock()


def shared() -> Worker:
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = Worker()
            atexit.register(_worker.stop)
        return _worker


def usable() -> bool:
    return semantic.is_installed() and semantic.runtime_available()


def start_in_background(*, retry: bool = False) -> None:
    """Start the worker when the model is installed; ``retry`` also restarts
    one that failed (a person asked for it again)."""

    if not usable():
        return
    worker = shared()
    if worker.state == "failed" and not retry:
        return
    worker.start()


def status() -> tuple[str, str | None]:
    """The worker's state and error, without starting it."""

    worker = _worker
    return ("idle", None) if worker is None else (worker.state, worker.error)


def search(workspace: Workspace, query: str, limit: int, timeout: float = SEARCH_TIMEOUT) -> list[semantic.Match]:
    """Matches by meaning, or none when the worker is not ready or slow."""

    worker = _worker
    if worker is None or worker.state != "ready" or not query.strip():
        return []
    try:
        answer = worker.request("search", timeout, root=str(workspace.root), query=query, limit=limit)
    except semantic.SemanticError:
        return []
    return [semantic.Match(**match) for match in answer.get("matches", [])]


def refresh_in_background(workspace: Workspace, *, retry: bool = False) -> bool:
    """Start bringing the workspace's semantic index up to date through the
    worker (starting it if needed); returns whether a refresh is running."""

    if not usable() or semantic.is_current(workspace):
        return False
    key = str(workspace.root)
    with _refresh_lock:
        if key in _refreshing:
            return True
        _refreshing.add(key)
    start_in_background(retry=retry)
    worker = shared()

    def run() -> None:
        try:
            if worker.wait_ready(LOAD_TIMEOUT + 5):
                worker.request("refresh", None, root=key)
        except semantic.SemanticError:
            pass  # the previous index stays; status shows a failed worker
        finally:
            with _refresh_lock:
                _refreshing.discard(key)

    threading.Thread(target=run, name="kos-semantic-index", daemon=True).start()
    return True


def refreshing(workspace: Workspace) -> bool:
    with _refresh_lock:
        return str(workspace.root) in _refreshing


def refresh_now(workspace: Workspace, report: Callable[[str], None] = print) -> None:
    """``kos index``: update the index through a worker of its own, then stop it."""

    worker = Worker()
    worker.start()
    try:
        if not worker.wait_ready(LOAD_TIMEOUT + 5):
            report(f"Search by meaning: skipped; {worker.error or 'the search model did not load'}")
            return
        counts = worker.request("refresh", None, root=str(workspace.root)).get("counts")
    except semantic.SemanticError as exc:
        report(f"Search by meaning: skipped; {exc}")
        return
    finally:
        worker.stop()
    if counts is None:
        report("Search by meaning: already up to date")
    else:
        report(
            f"Search by meaning: {counts['passages']} passage(s), {counts['embedded']} newly read; semantic.sqlite3 rebuilt"
        )
