"""``GET /`` — "back in": recently changed, open decisions, entry points.

Stub only (unit 0). A later unit replaces the body of ``view()`` with the
real start page described in ``docs/plans/reader-v1.md`` Sec.4: recently
changed records, open decisions awaiting a position, one entry point per
project, and a health line, or (Sec.6 "Empty workspace") an explanation of
what a record is plus a pointer at ``kos capture`` when the library is
empty. Keep this module's public name ``view`` and its ``(request) ->
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
        page_title=strings.PAGE_TITLES["start"],
        message=strings.STUB_NOT_IMPLEMENTED,
        library=library,
        path_params={},
    )
