"""``GET /f/{path:path}`` — one file from the unmanaged tier (``docs/``,
``SYSTEM.md``, ``README.md``, and similar): outside the record contract,
read-only, always labelled as such.

Stub only (unit 0). A later unit replaces the body of ``view()`` with the
real repo-document view. Use ``library.read_repo_document(workspace,
rel_path)`` for the title/text pair; it raises ``library.LibraryError`` (a
``ValueError`` subclass) for a missing file, non-UTF-8 content, or a path
``Workspace.assert_safe_path`` rejects (symlink, reparse point, or escape
from the workspace root) — catch it and show why the entry cannot be read
rather than letting it propagate (Sec.6 "Unreadable content"). Every page
this tier appears on must show ``strings.UNMANAGED_TIER_LABEL`` (acceptance
criterion 11). Keep this module's public name ``view`` and its ``(request)
-> Response`` signature so ``app.py`` never needs to change.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from .. import strings
from ..app import get_library, render


async def view(request: Request) -> Response:
    library = get_library(request)
    return render(
        request,
        "stub.html",
        page_title=strings.PAGE_TITLES["repodoc"],
        message=strings.STUB_NOT_IMPLEMENTED,
        library=library,
        path_params=dict(request.path_params),
    )
