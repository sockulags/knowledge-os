"""``GET /everything`` — flat catalog of the whole corpus, including raw
sources and rejected discoveries, each carrying its trust label.

Stub only (unit 0). A later unit replaces the body of ``view()`` with the
real everything view. Sources and rejected discoveries must be reachable
here and must never appear inside a governing group (acceptance criterion
10); ``Library.broken`` entries belong here too, rendered in place as broken
(Sec.6 "Broken record"). Keep this module's public name ``view`` and its
``(request) -> Response`` signature so ``app.py`` never needs to change.
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
        page_title=strings.PAGE_TITLES["everything"],
        message=strings.STUB_NOT_IMPLEMENTED,
        library=library,
        path_params={},
    )
