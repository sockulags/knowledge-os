"""``GET /search`` — a view, not a modal: filters on type, status, scope,
``record_kind``, and trust; filter state survives navigating into a
document and back.

Stub only (unit 0). A later unit replaces the body of ``view()`` with the
real search view. Use ``library.search(workspace, query, limit=...)`` for
results (it never raises: a blank query, a missing index, or an unparseable
FTS expression all come back as a clean empty list — see that function's
docstring); use ``Library.index`` (``get_library(request).index``) to decide
whether to show ``strings.INDEX_HEALTH["stale"]`` /
``strings.INDEX_HEALTH["absent"]`` instead of attempting a search at all
(Sec.6 "Stale index" / "Missing index"). Keep this module's public name
``view`` and its ``(request) -> Response`` signature so ``app.py`` never
needs to change.
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
        page_title=strings.PAGE_TITLES["search"],
        message=strings.STUB_NOT_IMPLEMENTED,
        library=library,
        path_params={},
    )
