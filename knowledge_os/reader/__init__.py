"""Knowledge OS Reader: the local JSON API and web interface for one workspace.

This package is an optional extra (``pip install -e ".[reader]"``). Reads
never write to the workspace it serves; the write endpoints in ``api/write.py``
create and edit records only through the core's capture and update mutations.
``knowledge_os/reader/library.py`` is the only module in this package
permitted to import ``knowledge_os.*``; every other module consumes its plain
dataclasses and functions.
"""

from __future__ import annotations

__version__ = "0.1.0"
