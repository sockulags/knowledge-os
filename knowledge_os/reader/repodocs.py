"""The unmanaged repo-document tier: the closed list of plain Markdown files
that sit outside the record contract (``docs/plans/reader-v1.md`` Sec.3,
"Repo documents"), plus the shared lookup and rendering helpers other units
use to surface an entry from it.

Every path here is served at ``GET /f/{path:path}`` (``views/repodoc.py``,
this unit) and must never be mistaken for a managed record: this module
reads only through ``library.read_repo_document``, which itself never
leaves ``Workspace.assert_safe_path`` (a resolved-path containment check, a
lexical containment check, and a per-component symlink/reparse-point walk).
Nothing here re-implements or bypasses that check, parses YAML, or writes
to the workspace.

Other units surface this tier on their own page by importing
``REPO_DOCUMENT_PATHS`` and/or ``list_repo_documents`` from here, and by
including ``templates/partials/unmanaged.html`` in their own template with
``unmanaged_entries`` set in their ``render()`` context — see that
partial's own header comment for its exact contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import library, markdown

#: The fixed, closed list of paths in the unmanaged tier, workspace-relative
#: POSIX, in the order the plan lists them (Sec.3). Not derived from a
#: filesystem walk on purpose: this tier is a small, enumerated, shrinking
#: set of files the plan names explicitly, not "every .md file outside the
#: corpus" — walking the filesystem would also pick up ordinary repository
#: clutter that was never meant to belong to this tier, and would turn
#: ``/f/{path:path}`` into a way to browse the whole repository.
#: ``views/repodoc.py`` refuses any path that is not exactly one of these
#: before it ever touches the filesystem, which is also what makes every
#: path-traversal shape (``../../etc/passwd``, an absolute path, an encoded
#: variant) a clean refusal: none of them can equal one of these literals.
REPO_DOCUMENT_PATHS: tuple[str, ...] = (
    "SYSTEM.md",
    "README.md",
    "AGENTS.md",
    "docs/architecture.md",
    "docs/architecture-audit-v0.1.md",
    "docs/openknowledge-governance-compatibility.md",
    "docs/decisions/0001-stack-and-index.md",
    "docs/plans/reader-v1.md",
)


@dataclass(frozen=True)
class RepoDocumentEntry:
    """One unmanaged-tier file, read (or attempted) for display.

    ``readable`` is False for exactly the states Sec.6 "Unreadable content"
    names: a path rejected by ``assert_safe_path``, a file deleted while the
    server runs, or non-UTF-8 content. ``title`` is always set (falling back
    to the bare path when unreadable) so a listing always has something to
    show; ``detail`` carries the human-facing reason and is ``None`` exactly
    when ``readable`` is True.
    """

    path: str
    title: str
    readable: bool
    detail: str | None


def read_text_entry(workspace: Any, rel_path: str) -> tuple[RepoDocumentEntry, str | None]:
    """Read one tier entry's display metadata and its body together, in one
    pass, never raising.

    Returns ``(entry, text)``; ``text`` is ``None`` exactly when
    ``entry.readable`` is False. The one place that calls
    ``library.read_repo_document`` and catches ``library.LibraryError`` for
    this whole module, so a listing (which only wants ``entry``) and the
    single-document page (which also wants ``text`` to render) never
    duplicate that try/except or read the same file twice.

    ``workspace`` is a ``knowledge_os.workspace.Workspace`` instance, typed
    as ``Any`` here because only ``library.py`` is permitted to import
    ``knowledge_os.*`` (see the module docstring); every caller already
    holds one via ``request.app.state.workspace``.
    """

    try:
        title, text = library.read_repo_document(workspace, rel_path)
    except library.LibraryError as exc:
        return RepoDocumentEntry(path=rel_path, title=rel_path, readable=False, detail=str(exc)), None
    return RepoDocumentEntry(path=rel_path, title=title, readable=True, detail=None), text


def read_entry(workspace: Any, rel_path: str) -> RepoDocumentEntry:
    """Read one tier entry for display, discarding its body.

    For a caller that only needs the listing metadata (``list_repo_documents``
    below); ``views/repodoc.py`` calls ``read_text_entry`` directly instead,
    since it also needs the body to render.
    """

    entry, _text = read_text_entry(workspace, rel_path)
    return entry


def list_repo_documents(workspace: Any) -> tuple[RepoDocumentEntry, ...]:
    """Read every entry in the fixed tier, in ``REPO_DOCUMENT_PATHS`` order.

    For a project or start page that wants to list this tier alongside a
    validated group. This unit's own page (``views/repodoc.py``) reads one
    entry directly through ``read_text_entry`` instead, since it already
    knows which single path it was asked for and also needs the body.
    """

    return tuple(read_entry(workspace, path) for path in REPO_DOCUMENT_PATHS)


def render_document(
    text: str,
    *,
    source_path: str | None = None,
    resolve_link: markdown.ResolveLink | None = None,
) -> tuple[str, tuple[tuple[int, str, str], ...]]:
    """Render one document's Markdown body together with its table of
    contents.

    ``markdown.render`` assigns every heading a stable, unique ``id`` itself
    (one pass, one place: see that module's docstring), and
    ``markdown.headings`` derives the same anchors from the same parse, so
    the two always agree without this module re-deriving or re-pairing
    anchors of its own. ``source_path`` and ``resolve_link`` are optional
    and forwarded as-is to ``markdown.render``; passing both rewrites a
    relative record-to-record link inside this document into a ``/r/<id>``
    permalink (``views/repodoc.py`` passes the requested path and a lookup
    built from ``library.path_index``).
    """

    toc = tuple(markdown.headings(text))
    html = markdown.render(text, source_path=source_path, resolve_link=resolve_link)
    return html, toc
