"""``GET /p/{project_id}`` — a project's overview plus content grouped by
meaning: governing now, proposed, historical, observations, raw material,
and the unmanaged repo-document tier, with relevant general knowledge,
memory, and skills as a side group.

Stub only (unit 0). A later unit replaces the body of ``view()`` with the
real project view described in ``docs/plans/reader-v1.md`` Sec.4 and
``projects/knowledge-os/reader/knowledge-os-reader-design.md``. Group
headers and empty-group sentences already live in ``strings.py``
(``PROJECT_GROUP_HEADERS``, ``PROJECT_GROUP_EMPTY``); every group must stay
visible even when empty (Sec.6 "Empty project group"). Keep this module's
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
        page_title=strings.PAGE_TITLES["project"],
        message=strings.STUB_NOT_IMPLEMENTED,
        library=library,
        path_params=dict(request.path_params),
    )
