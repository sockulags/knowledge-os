"""Answers "which ``kos`` is this, and is it the right one" (issue #60).

Two things can go wrong on a machine with more than one ``kos`` on PATH:

- The desktop app's shim (``<install dir>\\bin\\kos.cmd``) runs, but a bare
  ``kos`` invocation elsewhere (an agent config, another terminal, ...) would
  resolve to a different, earlier ``kos`` on PATH instead.
- A Python-installed ``kos`` runs while the desktop app is also installed,
  so its bundled ``kos`` exists too and may be the one people expect.

``kos --version`` reports where the running process's code came from, and a
one-line warning is printed to stderr (never stdout, so ``--json`` output and
the ``kos mcp`` stdio protocol stay clean) when one of those looks likely.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import __version__

#: Set by the desktop app's ``kos.cmd`` shim to its own full path before it
#: launches the bundled frozen core, so the core can tell whether a bare
#: ``kos`` on PATH would actually reach that same shim.
KOS_LAUNCHED_BY_SHIM_ENV = "KOS_LAUNCHED_BY_SHIM"

#: Set to silence the PATH-shadowing warning entirely.
KOS_NO_PATH_WARNING_ENV = "KOS_NO_PATH_WARNING"

_APP_DIR_NAME = "knowledge-os-desktop"


def _is_editable_install() -> bool:
    """Cheaply guess whether this package was installed with ``pip install -e``.

    Not a guarantee: it only checks whether the package directory sits next
    to a ``pyproject.toml`` outside of a ``site-packages``/``dist-packages``
    tree, which is true for an editable install from a checkout and false for
    a normal (non-editable) install or the frozen core.
    """
    package_dir = Path(__file__).resolve().parent
    if "site-packages" in package_dir.parts or "dist-packages" in package_dir.parts:
        return False
    return (package_dir.parent / "pyproject.toml").is_file()


def runtime_description() -> str:
    """Describe where this running ``kos`` process's code came from."""
    if getattr(sys, "frozen", False):
        bundled_core = Path(sys.executable).resolve()
        return f"installed app (bundled core at {bundled_core})"
    package_dir = Path(__file__).resolve().parent
    python_version = ".".join(str(part) for part in sys.version_info[:3])
    description = f"Python {python_version} at {sys.executable}, package at {package_dir}"
    if _is_editable_install():
        description += " (editable install)"
    return description


def version_lines() -> list[str]:
    """The lines ``kos --version`` prints on stdout."""
    return [f"kos {__version__}", runtime_description()]


def _installed_app_core_exe() -> Path | None:
    """The bundled core's path if the desktop app is installed for this user."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    candidate = Path(local_app_data) / "Programs" / _APP_DIR_NAME / "resources" / "core" / "kos-core.exe"
    return candidate if candidate.is_file() else None


def _shim_shadowed_warning() -> str | None:
    shim_path = os.environ.get(KOS_LAUNCHED_BY_SHIM_ENV)
    if not shim_path:
        return None
    which_kos = shutil.which("kos")
    if not which_kos:
        return None
    try:
        if Path(which_kos).resolve() == Path(shim_path).resolve():
            return None
    except OSError:
        return None
    return (
        f"kos: this is the installed app's kos, but a plain 'kos' on PATH resolves to "
        f"{which_kos} instead. Run 'py -3.11 -m pip uninstall knowledge-os', or put "
        f"{Path(shim_path).resolve().parent} first on PATH."
    )


def _python_shadowed_by_app_warning() -> str | None:
    installed_core = _installed_app_core_exe()
    if installed_core is None:
        return None
    # Reading the bundled core's own version cheaply (without starting it)
    # needs a platform-specific file-version helper; we skip that comparison
    # and simply flag that both exist, which is enough to unblock the fix.
    bin_dir = installed_core.parents[2] / "bin"
    return (
        f"kos: running a Python-installed kos while the desktop app is also installed "
        f"({installed_core}); run 'py -3.11 -m pip uninstall knowledge-os', or put "
        f"{bin_dir} first on PATH."
    )


def path_warning() -> str | None:
    """A one-line PATH-shadowing warning, or ``None`` if nothing looks wrong."""
    if os.environ.get(KOS_NO_PATH_WARNING_ENV):
        return None
    if getattr(sys, "frozen", False):
        return _shim_shadowed_warning()
    return _python_shadowed_by_app_warning()
