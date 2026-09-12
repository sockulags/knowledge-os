"""``GET /r/{record_id}`` — read one record: reading column, provenance and
relations in the metadata rail, collapsible for deep reading; a table of
contents for long documents.

Stub only (unit 0). A later unit replaces the body of ``view()`` with the
real document view described in ``docs/plans/reader-v1.md`` Sec.4. A broken
record (present in ``Library.broken``, not ``Library.records_by_id``) must
still render in place with its exact lint message (Sec.6 "Broken record");
an unresolved relation must render as "points at unknown id X"
(``strings.BROKEN_RELATION``), never silently dropped. ``markdown.render``
and ``markdown.headings`` (or the ``|markdown`` Jinja filter registered in
``app.py``) are available for rendering ``Record.body``. Keep this module's
public name ``view`` and its ``(request) -> Response`` signature so
``app.py`` never needs to change.
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
        page_title=strings.PAGE_TITLES["document"],
        message=strings.STUB_NOT_IMPLEMENTED,
        library=library,
        path_params=dict(request.path_params),
    )
