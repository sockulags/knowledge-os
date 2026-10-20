"""The frozen core's lock file still covers what pyproject.toml asks for.

desktop/scripts/build-core.ps1 installs the build venv only from
desktop/core/requirements-core.txt (with --require-hashes), so a dependency
added to pyproject.toml without regenerating the lock (desktop/scripts/
lock-core.ps1) would be missing from the packaged app.
"""

import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "desktop" / "core"
# The extras build-core.ps1 freezes into kos-core.exe (see lock-core.ps1).
CORE_EXTRAS = ("reader", "mcp", "search")

PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)")
NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(requirement: str) -> str:
    match = NAME.match(requirement)
    assert match, requirement
    return normalize(match.group(1))


def locked() -> dict[str, tuple[str, list[str]]]:
    """Each locked package's version and the lines that carry its hashes."""
    packages: dict[str, tuple[str, list[str]]] = {}
    current: list[str] = []
    for line in (CORE / "requirements-core.txt").read_text(encoding="utf-8").splitlines():
        match = PIN.match(line)
        if match:
            current = []
            packages[normalize(match.group(1))] = (match.group(2), current)
        elif line.strip().startswith("--hash=sha256:"):
            current.append(line.strip())
    return packages


class CoreLockTests(unittest.TestCase):
    def test_lock_covers_the_core_dependencies(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        wanted = list(project["dependencies"])
        for extra in CORE_EXTRAS:
            wanted += project["optional-dependencies"][extra]
        packages = locked()
        missing = sorted({requirement_name(item) for item in wanted} - packages.keys())
        self.assertEqual(missing, [], "run desktop/scripts/lock-core.ps1 to update the lock")

    def test_lock_pins_the_build_tools_exactly(self) -> None:
        packages = locked()
        lines = (CORE / "build-requirements.in").read_text(encoding="utf-8").splitlines()
        pins = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
        self.assertTrue(pins)
        for pin in pins:
            match = PIN.match(pin)
            self.assertIsNotNone(match, f"{pin} must be an exact == pin")
            assert match
            self.assertEqual(packages.get(normalize(match.group(1)), ("",))[0], match.group(2))

    def test_every_locked_package_has_a_hash(self) -> None:
        packages = locked()
        self.assertTrue(packages)
        for name, (_, hashes) in packages.items():
            self.assertTrue(hashes, f"{name} has no --hash in requirements-core.txt")


if __name__ == "__main__":
    unittest.main()
