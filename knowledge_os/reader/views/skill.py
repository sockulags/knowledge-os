"""``GET /s/{skill_name}`` — one operational-guidance skill by permalink.

Stub only (unit 0). A later unit replaces the body of ``view()`` with the
real skill view. Skills are ``Library.skills`` (a tuple of
``library.SkillEntry``, matched by ``.name`` against the ``skill_name`` path
parameter); they carry the trust label ``strings.SKILL_TRUST_LABEL``
("operational guidance", assigned by ``library.py`` since
``context_policy.trust_label()`` never returns it for a skill). Keep this
module's public name ``view`` and its ``(request) -> Response`` signature so
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
        page_title=strings.PAGE_TITLES["skill"],
        message=strings.STUB_NOT_IMPLEMENTED,
        library=library,
        path_params=dict(request.path_params),
    )
