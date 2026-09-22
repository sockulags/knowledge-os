"""The ``kos-read`` command line interface.

A separate console script from ``kos`` (not a subcommand), so the frozen
``kos`` CLI contract stays untouched and the reader remains physically
detachable. ``--root`` mirrors ``knowledge_os.cli``'s option verbatim,
including ``default=argparse.SUPPRESS``: that is load-bearing, since it is
what lets ``getattr(args, "root", None)`` trigger workspace discovery
starting from the current working directory when ``--root`` is omitted,
exactly like ``kos``.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path

from knowledge_os.workspace import Workspace, WorkspaceError

MISSING_EXTRA = (
    "the reader needs its optional dependencies; "
    'install them with: pip install "knowledge-os[reader]"'
)


def _root_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=argparse.SUPPRESS,
        help="workspace root (default: discover from cwd)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kos-read",
        description="Local, read-only web reader for a Knowledge OS workspace",
    )
    _root_option(parser)
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8800, help="bind port (default: 8800)")
    parser.add_argument(
        "--exit-on-stdin-eof",
        action="store_true",
        help="exit as soon as standard input closes (lets a parent process that dies take this server with it)",
    )
    return parser


def _exit_when_stdin_closes() -> None:
    """Exit the whole process once standard input reaches end-of-file.

    A launching parent (the desktop shell) keeps this process's stdin pipe
    open and never writes to it. When the parent exits for any reason,
    including a crash that skips its own cleanup, the operating system
    closes the pipe and this server stops instead of being orphaned.
    """

    if sys.stdin is None:
        return

    def watch() -> None:
        stream = sys.stdin.buffer
        while stream.read(4096):
            pass
        os._exit(0)

    threading.Thread(target=watch, name="kos-read-stdin-lifeline", daemon=True).start()


def _workspace(args: argparse.Namespace) -> Workspace:
    return Workspace.discover(getattr(args, "root", None))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # ``[project.scripts]`` installs this command unconditionally, so a plain
    # ``pip install knowledge-os`` yields a ``kos-read`` with no reader
    # dependencies behind it. Import them here rather than at module scope so
    # that case reports what to install instead of raising ImportError.
    try:
        import uvicorn

        from .app import create_app
    except ImportError as exc:
        print(f"ERROR: {MISSING_EXTRA} ({exc})", file=sys.stderr)
        return 1
    try:
        workspace = _workspace(args)
        app = create_app(workspace)
    except (WorkspaceError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.exit_on_stdin_eof:
        _exit_when_stdin_closes()
    uvicorn.run(app, host=args.host, port=args.port)
    return 0
