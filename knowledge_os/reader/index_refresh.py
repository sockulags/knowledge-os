"""Keep the search index current while the reader runs.

The search index is disposable: canonical Markdown is authoritative, and
``kos index`` rebuilds the index from it at any time. A desktop user has no
terminal to run that command in, so when a request finds the index stale,
absent, or unreadable, the reader rebuilds it itself, in a background thread,
through the exact code path ``kos index`` uses (``index.rebuild_indexes``,
reached through the adapter's ``library.rebuild_search_index``, which holds
the workspace advisory lock that ingest, discovery, and every other index
replacement share).

Requests never wait for the rebuild. While it runs, every request reports the
index as refreshing (search stays off, with a neutral notice); the first
request after it finishes sees a healthy index again.

No loops and no concurrent rebuilds: at most one rebuild runs per process, and
the reader attempts at most one rebuild per state of the corpus (a fingerprint
of the records and lint issues it just loaded). A rebuild that failed, or that
succeeded and still left the index unhealthy, is not repeated until the
corpus changes or the reader restarts; until then the request reports why.
A corpus with lint issues is never handed to the rebuild at all, since
``kos index`` refuses an invalid corpus.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import replace
from typing import Callable

from knowledge_os.workspace import Workspace

from . import strings
from .library import IndexHealth, Library, rebuild_search_index


def corpus_fingerprint(library: Library) -> str:
    """Everything that decides what the index should contain, or whether it
    can be built at all: each record's indexed fields and every lint issue."""

    digest = hashlib.sha256()
    for record in sorted(library.records, key=lambda entry: entry.path):
        fields = (
            record.path,
            record.id,
            record.title,
            record.type,
            record.record_kind or "",
            record.status,
            record.scope,
            " ".join(record.tags),
            record.body,
        )
        digest.update(repr(fields).encode("utf-8"))
    for issue in sorted(library.issues, key=lambda entry: (entry.path, entry.message)):
        digest.update(repr(("issue", issue.path, issue.message)).encode("utf-8"))
    return digest.hexdigest()


class IndexRefresher:
    """One per app. ``observe`` is called on every freshly loaded library and
    returns it with ``index`` describing what the reader is doing about it."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        enabled: bool = True,
        rebuild: Callable[[Workspace], int] = rebuild_search_index,
    ) -> None:
        self._workspace = workspace
        self._enabled = enabled
        self._rebuild = rebuild
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        #: Fingerprint of the corpus the last rebuild was started for, and
        #: the user-facing reason it did not help (``None`` while running or
        #: after a rebuild that succeeded).
        self._attempted: str | None = None
        self._failure: str | None = None

    def wait(self, timeout: float | None = None) -> None:
        """Block until a running rebuild finishes (for tests and shutdown)."""

        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def observe(self, library: Library) -> Library:
        index = library.index
        if not self._enabled or (index.available and not index.stale):
            return library
        if library.issues:
            return _with_index(library, index, strings.INDEX_HEALTH["refresh_blocked"])

        fingerprint = corpus_fingerprint(library)
        with self._lock:
            if self._thread is not None:
                return _with_index(library, index, strings.INDEX_HEALTH["refreshing"], refreshing=True)
            if fingerprint == self._attempted:
                reason = self._failure or strings.INDEX_HEALTH["refresh_failed"].format(
                    detail=strings.INDEX_REFRESH_STILL_STALE
                )
                return _with_index(library, index, reason)
            self._attempted = fingerprint
            self._failure = None
            self._thread = threading.Thread(target=self._run, name="kos-read-index-refresh", daemon=True)
            self._thread.start()
        return _with_index(library, index, strings.INDEX_HEALTH["refreshing"], refreshing=True)

    def _run(self) -> None:
        failure: str | None = None
        try:
            self._rebuild(self._workspace)
        except Exception as exc:  # any failure is reported, never raised into a request
            failure = strings.INDEX_HEALTH["refresh_failed"].format(detail=_first_line(exc))
        with self._lock:
            self._failure = failure
            self._thread = None


def _first_line(exc: Exception) -> str:
    text = str(exc).strip()
    return text.splitlines()[0] if text else type(exc).__name__


def _with_index(library: Library, index: IndexHealth, message: str, *, refreshing: bool = False) -> Library:
    return replace(library, index=replace(index, refreshing=refreshing, message=message))
