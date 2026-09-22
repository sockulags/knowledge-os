"""Entry point of kos-core.exe, the frozen Knowledge OS core in the desktop app.

The desktop shell starts the core as ``PYTHON -m knowledge_os.reader ARGS`` and
creates workspaces with ``PYTHON -m knowledge_os init ARGS``. This executable
accepts exactly those two forms, so the shell runs the bundled core with the
same arguments it passes to a Python interpreter in development.
"""

from __future__ import annotations

import sys

USAGE = "usage: kos-core -m {knowledge_os | knowledge_os.reader} [ARGS...]"


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] != "-m":
        print(USAGE, file=sys.stderr)
        return 2
    module, rest = argv[1], argv[2:]
    if module == "knowledge_os":
        from knowledge_os.cli import main as kos_main

        return kos_main(rest)
    if module == "knowledge_os.reader":
        from knowledge_os.reader.cli import main as reader_main

        return reader_main(rest)
    print(f"{USAGE}\nunknown module: {module}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
