"""Knowledge OS Reader: a local, read-only, server-rendered web reader.

This package is an optional extra (``pip install -e ".[reader]"``). It never
writes to the workspace it serves. ``knowledge_os/reader/library.py`` is the
only module in this package permitted to import ``knowledge_os.*``; every
other module consumes its plain dataclasses.
"""

from __future__ import annotations

__version__ = "0.0.1"
