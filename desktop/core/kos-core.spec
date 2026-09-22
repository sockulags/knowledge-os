# PyInstaller spec for kos-core.exe, the frozen Knowledge OS core that the
# packaged desktop app runs instead of a system Python. Built by
# scripts/build-core.ps1; see desktop/README.md.
#
# One-folder build, not one-file: it starts without unpacking to a temp
# folder, and it is a single process, so the shell's process-tree kill and
# the core's stdin-EOF lifeline apply to the process that serves the reader.

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

here = Path(SPECPATH).resolve()
repo = here.parents[1]

a = Analysis(
    [str(here / "kos_core.py")],
    # The package is taken from the checkout, not installed into the build venv.
    pathex=[str(repo)],
    # The reader UI bundle; the reader looks for it next to its own module.
    datas=[
        (str(repo / "knowledge_os" / "reader" / "static" / "app"), "knowledge_os/reader/static/app"),
    ],
    # uvicorn picks its loop, protocol, and lifespan implementations at runtime.
    hiddenimports=collect_submodules("uvicorn"),
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    # UTF-8 mode and unbuffered output, as the shell sets for a dev interpreter.
    [("X utf8", None, "OPTION"), ("u", None, "OPTION")],
    exclude_binaries=True,
    name="kos-core",
    # A console program: the shell keeps its stdin pipe open as a lifeline
    # and hides the window with windowsHide.
    console=True,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="kos-core", upx=False)
