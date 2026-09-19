"""View modules, one per route in ``knowledge_os/reader/app.py``.

Every module here exposes exactly one handler, ``async def view(request:
Request) -> Response``, matching the route table in ``app.py``. Unit 0 ships
every module as a stub that renders the shared shell through
``templates/stub.html`` (itself an extension of ``templates/base.html``) so
each route already returns 200 with the three-column shell visible; a
stage-B unit replaces the body of its one module's ``view()`` function and
adds its own template(s), without needing to touch ``app.py`` or any other
view module.
"""

from __future__ import annotations
