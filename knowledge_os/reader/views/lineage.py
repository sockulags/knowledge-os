"""``GET /r/{record_id}/compare`` — a decision side by side with the prior
decision it supersedes, or the one that superseded it.

Stub only (unit 0). A later unit replaces the body of ``view()`` with the
real compare view described in ``docs/plans/reader-v1.md`` Sec.4 ("decision
to supersedes or superseded-by with a side-by-side comparison"). The
``supersedes`` relation on ``Record.outbound`` (and its inverse on
``Record.inbound``) is already resolved by ``library.py``, including the
unresolved case (``Relation(resolved=False, title=None)``); use
``strings.LINEAGE_NO_COMPARISON`` when a record has no supersession lineage
at all. Keep this module's public name ``view`` and its ``(request) ->
Response`` signature so ``app.py`` never needs to change.
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
        page_title=strings.PAGE_TITLES["lineage"],
        message=strings.STUB_NOT_IMPLEMENTED,
        library=library,
        path_params=dict(request.path_params),
    )
