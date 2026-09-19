"""``GET /f/{path:path}`` — one file from the unmanaged tier (``docs/``,
``SYSTEM.md``, ``README.md``, and their handful of neighbours): outside the
record contract, read-only, always labelled as such.

The path parameter is caller-supplied, so this route is refused-by-default:
a request only reaches ``repodocs.read_text_entry`` (and, through it,
``library.read_repo_document`` and ``Workspace.assert_safe_path``) at all
when the normalized path exactly matches one of
``repodocs.REPO_DOCUMENT_PATHS`` — the fixed, closed list this tier
actually contains. Anything else, including every path-traversal shape, an
absolute path, or a path into the managed corpus itself, is refused before
touching the filesystem. ``assert_safe_path`` is still the layer of last
resort underneath that allowlist (it also catches a symlink swapped in
after the server started), never re-implemented here.

A missing file, a file deleted mid-session, and non-UTF-8 content are all
caught by ``read_text_entry`` (which never raises) and render the same
clean explanation page instead of a traceback, per Sec.6 "Unreadable
content".
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from .. import strings
from ..app import get_library, render
from ..library import path_index
from ..repodocs import REPO_DOCUMENT_PATHS, read_text_entry, render_document

#: Every refusal (not in the tier, not found, not UTF-8, or rejected by
#: assert_safe_path) answers the same status code and the same template
#: shape, deliberately: telling a caller *which* reason applied would leak
#: information about a path it should not be probing in the first place.
_REFUSED_STATUS = 404


def _refused(request: Request, error: str) -> Response:
    templates = request.app.state.templates
    context = {
        "page_title": strings.PAGE_TITLES["repodoc"],
        "document": None,
        "document_html": None,
        "toc": (),
        "error": error,
        "unmanaged_entries": (),
    }
    return templates.TemplateResponse(request, "repodoc.html", context, status_code=_REFUSED_STATUS)


async def view(request: Request) -> Response:
    workspace = request.app.state.workspace
    library = get_library(request)
    raw_path = request.path_params["path"]
    # A request like `/f//etc/passwd` carries a leading slash in the path
    # parameter; strip it before comparing so the message names the same
    # relative form the tier list uses. This has no security role — the
    # exact-match check below refuses the path either way.
    rel_path = raw_path.lstrip("/")

    if rel_path not in REPO_DOCUMENT_PATHS:
        return _refused(request, strings.REPODOC_NOT_IN_TIER.format(path=raw_path))

    document, text = read_text_entry(workspace, rel_path)
    if not document.readable:
        # RepoDocumentEntry guarantees `detail` is set exactly when
        # `readable` is False.
        assert document.detail is not None
        return _refused(request, document.detail)

    # A repo document can itself link to another repo document by relative
    # path (e.g. docs/architecture.md linking to another docs/ file); resolve
    # against the corpus the same way a managed record's body does (task 4),
    # via the same path-to-id lookup views/document.py builds.
    html, toc = render_document(text, source_path=rel_path, resolve_link=path_index(library).get)
    return render(
        request,
        "repodoc.html",
        page_title=document.title,
        document=document,
        document_html=html,
        toc=toc,
        error=None,
        unmanaged_entries=(),
    )
