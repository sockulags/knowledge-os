"""Shared parsing and validation for operational skills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import yaml

from .model import ID_PATTERN
from .workspace import is_managed_link


SKILL_FRONTMATTER_FIELDS = {"name", "description", "tags"}
SKILL_TAG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SkillError(ValueError):
    """A user-actionable skill format or path error."""


@dataclass(frozen=True)
class Skill:
    path: Path
    name: str
    description: str
    tags: tuple[str, ...]
    body: str


def _safe_relative(root: Path, path: Path) -> str:
    root = root.expanduser().resolve()
    candidate = path.expanduser()
    try:
        relative = candidate.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise SkillError(f"skill path {path} resolves outside workspace root {root}") from exc

    cursor = root
    for part in relative.parts:
        cursor /= part
        if is_managed_link(cursor):
            raise SkillError(f"managed skill path {path} must not contain symlinks")
    return relative.as_posix()


def _parse_skill_text(path: Path, raw: str, *, root: Path | None = None) -> Skill:
    relative = _safe_relative(root, path) if root is not None else str(path)
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\n") != "---":
        raise SkillError(f"skill {relative} is missing YAML frontmatter")
    closing = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.rstrip("\n") == "---"),
        None,
    )
    if closing is None:
        raise SkillError(f"skill {relative} is missing YAML frontmatter closing delimiter")
    try:
        metadata = yaml.safe_load("".join(lines[1:closing]))
    except yaml.YAMLError as exc:
        raise SkillError(f"skill {relative} has invalid YAML frontmatter: {exc}") from exc
    if not isinstance(metadata, dict):
        raise SkillError(f"skill {relative} frontmatter must be an object")
    unknown = sorted(set(metadata) - SKILL_FRONTMATTER_FIELDS, key=str)
    if unknown:
        raise SkillError(f"skill {relative} has unknown frontmatter field(s): {', '.join(map(str, unknown))}")

    name = metadata.get("name")
    if not isinstance(name, str) or not name.strip():
        raise SkillError(f"skill {relative} requires a non-empty name")
    name = name.strip()
    if not ID_PATTERN.fullmatch(name):
        raise SkillError(f"skill {relative} name must be lowercase kebab-case")

    description = metadata.get("description")
    if not isinstance(description, str) or not description.strip():
        raise SkillError(f"skill {relative} requires a non-empty description")
    description = description.strip()

    tags = metadata.get("tags", [])
    if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
        raise SkillError(f"skill {relative} tags must be a list of non-empty strings")
    normalized_tags: list[str] = []
    for tag in tags:
        normalized_tag = tag.strip()
        if not SKILL_TAG_PATTERN.fullmatch(normalized_tag):
            raise SkillError(f"skill {relative} tag {normalized_tag!r} must be lowercase kebab-case")
        if normalized_tag not in normalized_tags:
            normalized_tags.append(normalized_tag)

    body = "".join(lines[closing + 1 :])
    if body.startswith("\n"):
        body = body[1:]
    if not body.strip():
        raise SkillError(f"skill {relative} body must be non-empty")

    directory_name = path.parent.name
    if directory_name != name:
        raise SkillError(
            f"skill {relative} directory name {directory_name!r} must match name {name!r}"
        )
    return Skill(path=path, name=name, description=description, tags=tuple(normalized_tags), body=body)


def parse_skill(path: Path, *, root: Path | None = None) -> Skill:
    """Parse one UTF-8 skill and apply the shared skill contract."""

    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        relative = _safe_relative(root, path) if root is not None else str(path)
        raise SkillError(f"skill file must be UTF-8 text: {relative}") from exc
    except OSError as exc:
        relative = _safe_relative(root, path) if root is not None else str(path)
        raise SkillError(f"skill file could not be read: {relative}: {exc}") from exc
    return _parse_skill_text(path, raw, root=root)


def _walk_skill_paths(root: Path) -> tuple[list[Path], list[tuple[Path, str]]]:
    root = root.expanduser().resolve()
    skills_root = root / "skills"
    if not skills_root.exists() and not is_managed_link(skills_root):
        return [], []
    if is_managed_link(skills_root):
        return [], [(skills_root, "managed skill directory must not be a symlink")]
    if not skills_root.is_dir():
        return [], [(skills_root, "managed skill path must be a directory")]

    paths: list[Path] = []
    issues: list[tuple[Path, str]] = []
    for current, directories, files in os.walk(skills_root, topdown=True, followlinks=False):
        current_path = Path(current)
        for directory in sorted(tuple(directories)):
            path = current_path / directory
            if is_managed_link(path):
                issues.append((path, "managed skill directory must not be a symlink"))
                directories.remove(directory)
        for filename in sorted(files):
            path = current_path / filename
            if is_managed_link(path):
                issues.append((path, "managed skill file must not be a symlink"))
                continue
            if filename == "SKILL.md":
                paths.append(path)
    return sorted(paths, key=lambda path: path.as_posix()), issues


def load_skills(root: Path) -> tuple[list[Skill], list[tuple[Path, str]]]:
    """Load every skill and return parsed skills plus deterministic issues."""

    root = root.expanduser().resolve()
    paths, issues = _walk_skill_paths(root)
    skills: list[Skill] = []
    names: dict[str, Path] = {}
    for path in paths:
        try:
            skill = parse_skill(path, root=root)
        except SkillError as exc:
            issues.append((path, str(exc)))
            continue
        previous = names.get(skill.name)
        if previous is not None:
            issues.append(
                (
                    path,
                    f"duplicate skill name {skill.name!r}; already defined at "
                    f"{previous.resolve().relative_to(root.resolve()).as_posix()}",
                )
            )
            continue
        names[skill.name] = path
        skills.append(skill)
    return sorted(skills, key=lambda skill: skill.path.as_posix()), sorted(
        issues,
        key=lambda item: (str(item[0]), item[1]),
    )


def skill_search_terms(skill: Skill) -> tuple[str, ...]:
    """Return metadata used by context discovery; skill bodies are excluded."""

    return (skill.name, skill.description, *skill.tags)
