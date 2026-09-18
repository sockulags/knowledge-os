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

import re
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

_HEADING_OPEN = re.compile(r"<h([1-6])>")


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


def render_document(text: str) -> tuple[str, tuple[tuple[int, str, str], ...]]:
    """Render one document's Markdown body together with its table of
    contents.

    ``markdown.render`` does not emit ``id`` attributes on headings (see its
    module docstring); this pairs its output with ``markdown.headings`` by
    injecting the Nth heading's anchor onto the Nth ``<hN>`` opening tag in
    document order. That pairing is safe because both functions parse the
    same text through the same commonmark parser in a single pass, so the
    heading-tag order in the rendered HTML and the heading order
    ``headings()`` returns always agree (verified against both
    ``docs/architecture.md``, 10 headings, and
    ``docs/architecture-audit-v0.1.md``, 52 headings). If that invariant is
    ever violated by a future markdown.py change, the injection falls back
    to the plain, unannotated HTML rather than raising, so a rendering
    mismatch degrades to "no anchor links" instead of a 500.
    """

    toc = tuple(markdown.headings(text))
    html = markdown.render(text)
    if not toc:
        return html, toc

    remaining = iter(toc)

    def _inject(match: re.Match[str]) -> str:
        _level, _text, anchor = next(remaining)
        return f'<h{match.group(1)} id="{anchor}">'

    try:
        annotated = _HEADING_OPEN.sub(_inject, html)
    except StopIteration:
        return html, toc
    return annotated, toc
