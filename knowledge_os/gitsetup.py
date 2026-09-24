"""Connect a knowledge base to a Git remote, and clone one from a URL.

This module adds the two ways into sync that used to need the command line:

* :func:`clone_workspace` clones a knowledge base from a Git URL into a new
  folder, checks that the result is a knowledge base (its marker file and
  ``kos lint``), and rebuilds its indexes.
* The guided setup: :func:`setup_status` says which step a knowledge base is
  at (not versioned, no remote, no upstream, or ready), and
  :func:`init_repository`, :func:`set_identity`, :func:`check_remote`, and
  :func:`connect_remote` take it through those steps.

Every Git call goes through the same runner as sync (``gitsync._run_git`` and
its streaming variant): Git from ``PATH``, no terminal, prompts disabled,
the user's own credential helpers and SSH agents, timeouts that kill the
process tree, and ``user:password@`` redacted from every message. Nothing
here asks for, stores, or logs a credential, and a URL that carries a
password is refused rather than written into ``.git/config``.

A remote that already has commits is never overwritten. When its history
shares a commit with this knowledge base, connecting to it is an ordinary
sync (a merge that can stop on conflicts but never loses data); when the
histories are unrelated, nothing is changed and the error says to clone the
remote instead.

The Knowledge OS source repository is never offered any of this (the
``source_repo`` guard of :mod:`knowledge_os.gitsync`).
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from . import gitsync
from .gitsync import (
    NETWORK_TIMEOUT,
    GitSyncError,
    Repository,
    SyncOutcome,
    _classify_network_failure,
    _is_knowledge_os_source_repository,
    _message,
    _run_git,
    _run_git_streaming,
    _same_path,
    _text,
    find_git,
    open_repository,
    redact,
)
from .init_workspace import GITIGNORE_CONTENT
from .workspace import Workspace, WorkspaceError, workspace_mutation_lock

#: A clone may take long on a slow link; it is stopped after this many
#: seconds in total, or after :data:`CLONE_IDLE_TIMEOUT` seconds in which Git
#: reported nothing.
CLONE_TIMEOUT = 1800.0
CLONE_IDLE_TIMEOUT = 60.0

#: The commit message of the first commit the guided setup makes.
FIRST_COMMIT_MESSAGE = "Start versioning this knowledge base"

_SETUP_REF = "refs/kos-setup/remote"
_SCHEMES = {"https", "http", "ssh", "git", "file"}
_MARKER = "knowledge-os.toml"


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------


def validate_remote_url(url: str) -> str:
    """Return ``url`` trimmed if it is a Git URL the app accepts, or raise ``bad_url``.

    Accepted: ``https://``, ``http://``, ``ssh://``, ``git://``, and
    ``file://`` URLs, the scp-like ``git@host:owner/repo.git``, and an
    absolute local path. A URL with a password or token in it is refused so
    the credential never lands in the repository's configuration.
    """

    text = url.strip()
    if not text:
        raise GitSyncError("bad_url", "Enter the address of a Git repository.")
    if any(character.isspace() or ord(character) < 32 for character in text):
        raise GitSyncError("bad_url", "A Git URL cannot contain spaces or line breaks.")
    if text.startswith("-"):
        raise GitSyncError("bad_url", "A Git URL cannot start with a dash.")
    scheme = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*)://", text)
    if scheme:
        name = scheme.group(1).lower()
        if name not in _SCHEMES:
            raise GitSyncError(
                "bad_url",
                f"{name}:// is not supported. Use an https://, ssh://, git://, or file:// address, "
                "or git@host:owner/repository.git.",
            )
        try:
            parts = urlsplit(text)
            host = parts.hostname
            password = parts.password
        except ValueError as exc:
            raise GitSyncError("bad_url", f"This URL cannot be read: {exc}.") from exc
        if name != "file" and not host:
            raise GitSyncError("bad_url", "The URL has no host name.")
        if password is not None:
            raise GitSyncError(
                "bad_url",
                "Remove the password or token from the URL. The app never stores credentials: sign in once "
                "with Git outside the app (a credential helper or an SSH key) and use the plain address.",
            )
        return text
    if re.match(r"^[A-Za-z]:[\\/]", text) or text.startswith(("\\\\", "/")):
        return text  # an absolute local path, such as a folder on a network share
    if re.match(r"^(?:[^@/\\:]+@)?[^@/\\:]{2,}:[^\\].*$", text):
        return text  # scp-like: [user@]host:path
    raise GitSyncError(
        "bad_url",
        "This does not look like a Git URL. Use an address such as https://host/owner/repository.git, "
        "git@host:owner/repository.git, or the full path of a folder.",
    )


# ---------------------------------------------------------------------------
# Clone
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CloneProgress:
    """One progress report: ``phase`` is ``clone``, ``check``, or ``index``.

    During ``clone``, ``line`` is Git's own progress line (for example
    ``Receiving objects:  45% (450/1000)``) and ``percent`` its number.
    """

    phase: str
    line: str | None = None
    percent: int | None = None


@dataclass(frozen=True)
class CloneOutcome:
    root: Path
    name: str | None
    reindexed: bool
    index_error: str | None = None
    #: ``kos lint`` findings as (path, message); when there are any, the
    #: indexes were not rebuilt and the reader shows the findings.
    issues: tuple[tuple[str, str], ...] = ()


def _force_remove(function, path, _info) -> None:  # type: ignore[no-untyped-def]
    # Git marks object files read-only on Windows.
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        function(path)
    except OSError:
        pass


def _empty_directory(path: Path, *, remove_itself: bool) -> None:
    """Remove what a failed clone left behind; retry while Windows releases handles."""

    for attempt in range(20):
        if not path.exists():
            return
        if remove_itself:
            shutil.rmtree(path, onerror=_force_remove)
        else:
            for child in path.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child, onerror=_force_remove)
                else:
                    try:
                        os.chmod(child, stat.S_IWRITE | stat.S_IREAD)
                        child.unlink()
                    except OSError:
                        pass
        if (not path.exists()) if remove_itself else not any(path.iterdir()):
            return
        time.sleep(0.25 * (attempt + 1) if attempt < 4 else 1.0)


def _ssh_batch_at(git: str, cwd: Path) -> bool:
    if os.environ.get("GIT_SSH_COMMAND") or os.environ.get("GIT_SSH"):
        return False
    result = _run_git(git, cwd, ["config", "--get", "core.sshCommand"])
    return result.returncode != 0 or not _text(result.stdout)


def _percent(line: str) -> int | None:
    found = re.search(r"(\d{1,3})%", line)
    return int(found.group(1)) if found else None


def clone_workspace(
    url: str,
    destination: Path,
    *,
    timeout: float = CLONE_TIMEOUT,
    idle_timeout: float = CLONE_IDLE_TIMEOUT,
    on_progress: Callable[[CloneProgress], None] | None = None,
    cancel: threading.Event | None = None,
) -> CloneOutcome:
    """Clone the knowledge base at ``url`` into ``destination`` and check it.

    ``destination`` must not exist yet or must be an empty folder. When the
    clone fails, times out, or is cancelled, everything it wrote is removed
    again (an empty folder that existed before stays). A cloned repository
    that is not a knowledge base is left where it is and reported as
    ``not_a_knowledge_base``; nothing is deleted after a successful clone.
    """

    report = on_progress or (lambda _progress: None)
    url = validate_remote_url(url)
    git = find_git()
    if git is None:
        raise GitSyncError(
            "git_missing",
            "Git was not found on PATH. Install Git (https://git-scm.com) and restart the app to clone a "
            "knowledge base.",
        )
    target = Path(os.path.abspath(destination.expanduser()))
    existed = target.exists()
    if existed:
        if not target.is_dir():
            raise GitSyncError("target_not_empty", f"{target} already exists and is not a folder. Choose another name.")
        if any(target.iterdir()):
            raise GitSyncError(
                "target_not_empty",
                f"The folder {target} already exists and is not empty, so nothing was cloned into it. "
                "Choose another folder name.",
            )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise GitSyncError("failed", f"The folder {target.parent} could not be created: {exc}") from exc

    report(CloneProgress("clone"))
    try:
        result = _run_git_streaming(
            git,
            target.parent,
            ["clone", "--progress", "--", url, str(target)],
            timeout=timeout,
            idle_timeout=idle_timeout,
            ssh_batch=_ssh_batch_at(git, target.parent),
            on_line=lambda line: report(CloneProgress("clone", line, _percent(line))),
            cancel=cancel,
        )
    except GitSyncError:
        _empty_directory(target, remove_itself=not existed)
        raise
    if result.returncode != 0:
        _empty_directory(target, remove_itself=not existed)
        raise _classify_network_failure(result, "Cloning")

    report(CloneProgress("check"))
    if not (target / _MARKER).is_file():
        raise GitSyncError(
            "not_a_knowledge_base",
            f"The repository was cloned to {target}, but it is not a knowledge base: it has no {_MARKER} "
            "file at its top level. Nothing was opened, and the folder was left as it is.",
        )
    try:
        workspace = Workspace(target)
    except WorkspaceError as exc:
        raise GitSyncError(
            "not_a_knowledge_base",
            f"The repository was cloned to {target}, but it cannot be opened as a knowledge base: {exc}. "
            "Nothing was opened, and the folder was left as it is.",
        ) from exc
    issues = gitsync._lint_issues(workspace)
    section = workspace.config.get("workspace")
    name = section.get("name") if isinstance(section, dict) and isinstance(section.get("name"), str) else None
    if issues:
        return CloneOutcome(target, name, reindexed=False, issues=issues)
    report(CloneProgress("index"))
    from .index import rebuild_indexes

    try:
        rebuild_indexes(workspace)
    except (WorkspaceError, OSError, ValueError) as exc:
        return CloneOutcome(target, name, reindexed=False, index_error=str(exc))
    return CloneOutcome(target, name, reindexed=True)


# ---------------------------------------------------------------------------
# Guided setup
# ---------------------------------------------------------------------------

#: States that offer a next step, in the order the setup walks through them.
SETUP_STEPS = ("init", "remote", "publish")


@dataclass(frozen=True)
class SetupStatus:
    """Where a knowledge base stands on the way to syncing.

    ``state`` is one of ``init`` (not a Git repository yet, or no commit),
    ``remote`` (no remote), ``publish`` (a remote but no upstream branch),
    ``ready`` (sync works), or a state that the app cannot set up:
    ``git_missing``, ``source_repo``, ``nested`` (inside another
    repository), ``detached`` (not on a branch), or ``repo_error`` (Git
    could not read the repository; ``detail`` has its message).
    """

    state: str
    branch: str | None = None
    remote: str | None = None
    remote_url: str | None = None
    identity: dict[str, str] | None = None
    detail: str | None = None


def _identity_at(git: str, cwd: Path) -> dict[str, str] | None:
    """The author identity Git would use in ``cwd`` (repository, global, or environment)."""

    def value(key: str) -> str | None:
        result = _run_git(git, cwd, ["config", "--get", key])
        return (_text(result.stdout) or None) if result.returncode == 0 else None

    name = os.environ.get("GIT_AUTHOR_NAME") or value("user.name")
    email = os.environ.get("GIT_AUTHOR_EMAIL") or value("user.email")
    if not name or not email:
        return None
    return {"name": name, "email": email}


def _preferred_remote(remotes: tuple[str, ...]) -> str | None:
    if not remotes:
        return None
    return "origin" if "origin" in remotes else remotes[0]


def _remote_url(repo: Repository, remote: str) -> str | None:
    result = gitsync._git(repo, "remote", "get-url", "--", remote, check=False)
    return redact(_text(result.stdout)) if result.returncode == 0 and _text(result.stdout) else None


def setup_status(workspace: Workspace) -> SetupStatus:
    """Say which setup step this knowledge base is at; never contacts a remote."""

    root = workspace.root
    if _is_knowledge_os_source_repository(root):
        return SetupStatus("source_repo")
    git = find_git()
    if git is None:
        return SetupStatus("git_missing")
    identity = _identity_at(git, root)
    located = _run_git(git, root, ["rev-parse", "--show-toplevel"])
    if located.returncode != 0:
        if (root / ".git").exists():
            return SetupStatus("repo_error", identity=identity, detail=_message(located))
        return SetupStatus("init", identity=identity)
    toplevel = Path(_text(located.stdout).splitlines()[0])
    if not _same_path(toplevel, root):
        return SetupStatus("nested", identity=identity, detail=str(toplevel))
    try:
        repo = open_repository(workspace)
    except GitSyncError as exc:
        return SetupStatus("repo_error", identity=identity, detail=exc.message)
    branch = gitsync._branch(repo)
    if branch is None:
        return SetupStatus("detached", identity=identity)
    if not gitsync._has_head(repo):
        return SetupStatus("init", branch=branch, identity=identity)
    remotes = gitsync._remotes(repo)
    remote = _preferred_remote(remotes)
    remote_url = _remote_url(repo, remote) if remote else None
    upstream = gitsync._upstream(repo, branch)
    if upstream is not None:
        return SetupStatus(
            "ready", branch=branch, remote=upstream.remote, remote_url=_remote_url(repo, upstream.remote), identity=identity
        )
    if remote is None:
        return SetupStatus("remote", branch=branch, identity=identity)
    return SetupStatus("publish", branch=branch, remote=remote, remote_url=remote_url, identity=identity)


def _check_identity_fields(name: str, email: str) -> tuple[str, str]:
    name, email = name.strip(), email.strip()
    if not name:
        raise GitSyncError("bad_identity", "Enter the name Git should record as the author of your changes.")
    if not email or not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+", email):
        raise GitSyncError("bad_identity", "Enter an email address such as you@example.com.")
    if any(ord(character) < 32 or character in "<>" for character in name):
        raise GitSyncError("bad_identity", "The name cannot contain line breaks or angle brackets.")
    return name, email


def _require_setup_state(workspace: Workspace, allowed: tuple[str, ...]) -> SetupStatus:
    current = setup_status(workspace)
    if current.state in allowed:
        return current
    if current.state == "source_repo":
        raise GitSyncError(
            "source_repo",
            "This is the Knowledge OS source repository; the app does not set up versioning or sync here.",
        )
    if current.state == "git_missing":
        raise GitSyncError(
            "git_missing",
            "Git was not found on PATH. Install Git (https://git-scm.com) and restart the app.",
        )
    if current.state == "nested":
        raise GitSyncError(
            "not_a_repo",
            f"This knowledge base lies inside the Git repository at {current.detail}, so the app does not set up "
            "a repository of its own here.",
        )
    if current.state == "detached":
        raise GitSyncError("no_branch", "The repository is not on a branch (detached HEAD). Check out a branch first.")
    if current.state == "repo_error":
        raise GitSyncError("failed", f"Git could not read this repository: {current.detail}")
    raise GitSyncError("wrong_step", f"This step does not apply any more: the knowledge base is at step '{current.state}'.")


def _ensure_index_rules(root: Path) -> bool:
    """Add the generated-index ignore rules to ``.gitignore`` when missing."""

    path = root / ".gitignore"
    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    except (OSError, UnicodeDecodeError):
        existing = ""
    present = {line.strip() for line in existing.splitlines()}
    missing = [line for line in GITIGNORE_CONTENT.splitlines() if line.strip() and line.strip() not in present]
    if not missing:
        return False
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(prefix + "\n".join(missing) + "\n")
    return True


@dataclass(frozen=True)
class InitOutcome:
    created_repository: bool
    files: int
    sha: str


def init_repository(workspace: Workspace, *, identity: tuple[str, str] | None = None) -> InitOutcome:
    """Make this knowledge base a Git repository with a first commit of its files.

    Runs ``git init`` (branch ``main`` unless ``init.defaultBranch`` is
    configured) when the folder is not a repository yet, adds the ignore
    rules for the generated indexes, and commits every file Git does not
    ignore. ``identity`` (name, email) is stored in the repository's own
    configuration first; without it, a missing identity stops the step
    before anything changes.
    """

    with workspace_mutation_lock(workspace):
        _require_setup_state(workspace, ("init",))
        git = find_git()
        assert git is not None
        root = workspace.root
        fields = _check_identity_fields(*identity) if identity is not None else None
        if fields is None and _identity_at(git, root) is None:
            raise GitSyncError(
                "no_identity",
                "Git does not know who you are, so it cannot record the first commit. Enter a name and an email "
                "for this knowledge base, or set them for every repository with "
                '`git config --global user.name "Your Name"` and `git config --global user.email you@example.com`.',
            )
        created = not (root / ".git").exists()
        if created:
            default_branch = _run_git(git, root, ["config", "--get", "init.defaultBranch"])
            args = ["init", "--quiet"]
            if default_branch.returncode != 0 or not _text(default_branch.stdout):
                args += ["--initial-branch=main"]
            result = _run_git(git, root, args)
            if result.returncode != 0:
                raise GitSyncError("failed", f"git init failed: {_message(result)}")
        repo = open_repository(workspace)
        if fields is not None:
            gitsync._git(repo, "config", "user.name", fields[0])
            gitsync._git(repo, "config", "user.email", fields[1])
        _ensure_index_rules(root)
        gitsync._git(repo, "add", "--all")
        # Generated index files never go into history, even when a rule
        # was missing before; only the directory's README stays tracked.
        staged = gitsync._out(repo, "diff", "--cached", "--name-only", "--", "indexes")
        generated = [path for path in staged.splitlines() if path and path not in gitsync._INDEX_TRACKING_ALLOWED]
        if generated:
            gitsync._git(repo, "rm", "--cached", "--quiet", "--", *generated)
        files = len([line for line in gitsync._out(repo, "diff", "--cached", "--name-only").splitlines() if line])
        gitsync._git(repo, "commit", "--quiet", "--allow-empty", "-m", FIRST_COMMIT_MESSAGE)
        sha = gitsync._out(repo, "rev-parse", "HEAD")
    return InitOutcome(created_repository=created, files=files, sha=sha)


def set_identity(workspace: Workspace, name: str, email: str) -> dict[str, str]:
    """Store the author identity in this repository's own configuration only."""

    fields = _check_identity_fields(name, email)
    repo = open_repository(workspace)
    with workspace_mutation_lock(workspace):
        gitsync._git(repo, "config", "user.name", fields[0])
        gitsync._git(repo, "config", "user.email", fields[1])
    return {"name": fields[0], "email": fields[1]}


@dataclass(frozen=True)
class RemoteCheck:
    """What ``git ls-remote`` found at a remote.

    ``empty`` means the remote has no branches at all. For a remote with
    branches, ``branch`` is the one this knowledge base would sync with (its
    own branch name if the remote has it, else the remote's default branch)
    and ``related`` says whether that branch shares history with this
    knowledge base, which makes connecting to it a safe, ordinary merge.
    """

    url: str
    empty: bool
    branches: tuple[str, ...] = ()
    branch: str | None = None
    related: bool | None = None


def _ls_remote(repo: Repository, target: str, timeout: float) -> list[tuple[str, str]]:
    result = _run_git(
        repo.git,
        repo.workspace.root,
        ["ls-remote", "--", target],
        timeout=timeout,
        ssh_batch=gitsync._ssh_batch(repo),
    )
    if result.returncode != 0:
        raise _classify_network_failure(result, "Reaching the remote")
    refs: list[tuple[str, str]] = []
    for line in _text(result.stdout).splitlines():
        sha, _, ref = line.partition("\t")
        if sha and ref:
            refs.append((sha.strip(), ref.strip()))
    return refs


def _target_for(repo: Repository, url: str | None) -> tuple[str, str]:
    """Return (what to pass to Git, redacted display URL) for a URL or the existing remote."""

    if url is not None:
        valid = validate_remote_url(url)
        return valid, redact(valid)
    remote = _preferred_remote(gitsync._remotes(repo))
    if remote is None:
        raise GitSyncError("bad_url", "Enter the address of a Git repository.")
    return remote, _remote_url(repo, remote) or remote


def _check(repo: Repository, url: str | None, timeout: float) -> RemoteCheck:
    target, display = _target_for(repo, url)
    refs = _ls_remote(repo, target, timeout)
    heads = {ref[len("refs/heads/") :]: sha for sha, ref in refs if ref.startswith("refs/heads/")}
    if not refs:
        return RemoteCheck(display, empty=True)
    branch_name = gitsync._branch(repo)
    if branch_name in heads:
        branch = branch_name
    else:
        head_sha = next((sha for sha, ref in refs if ref == "HEAD"), None)
        branch = next((name for name, sha in sorted(heads.items()) if sha == head_sha), None)
        if branch is None and heads:
            branch = sorted(heads)[0]
    related = False
    if branch is not None and gitsync._has_head(repo):
        fetched = _run_git(
            repo.git,
            repo.workspace.root,
            ["fetch", "--quiet", "--no-tags", "--", target, f"+refs/heads/{branch}:{_SETUP_REF}"],
            timeout=timeout,
            ssh_batch=gitsync._ssh_batch(repo),
        )
        if fetched.returncode != 0:
            raise _classify_network_failure(fetched, "Reading the remote")
        try:
            related = gitsync._git(repo, "merge-base", "HEAD", _SETUP_REF, check=False).returncode == 0
        finally:
            gitsync._git(repo, "update-ref", "-d", _SETUP_REF, check=False)
    return RemoteCheck(display, empty=False, branches=tuple(sorted(heads)), branch=branch, related=related)


def check_remote(workspace: Workspace, url: str | None = None, *, timeout: float = NETWORK_TIMEOUT) -> RemoteCheck:
    """Test that a remote answers (``git ls-remote``) and whether it is empty.

    ``url`` is the address to test; ``None`` tests the remote already
    configured. Changes nothing but a temporary ref, removed again.
    """

    with workspace_mutation_lock(workspace):
        _require_setup_state(workspace, ("remote", "publish"))
        repo = open_repository(workspace)
        return _check(repo, url, timeout)


@dataclass(frozen=True)
class ConnectOutcome:
    """``published``: this knowledge base was pushed to an empty remote and
    now tracks it. ``synced`` / ``conflict``: the remote shared history, so
    the upstream was set and an ordinary sync ran (``sync`` has its result)."""

    state: str
    remote: str
    branch: str
    pushed: int = 0
    sync: SyncOutcome | None = None


def connect_remote(workspace: Workspace, url: str | None = None, *, timeout: float = NETWORK_TIMEOUT) -> ConnectOutcome:
    """Add (or update) the remote ``origin``, publish this branch, and set its upstream.

    An empty remote gets this branch pushed with ``git push -u``. A remote
    whose branch shares history with this one becomes the upstream, followed
    by an ordinary sync. A remote with unrelated commits is refused with
    ``remote_not_empty`` and nothing is changed.
    """

    run_sync = False
    with workspace_mutation_lock(workspace):
        current = _require_setup_state(workspace, ("remote", "publish"))
        repo = open_repository(workspace)
        branch = current.branch
        assert branch is not None
        check = _check(repo, url, timeout)
        if not check.empty and not check.related:
            raise GitSyncError(
                "remote_not_empty",
                f"The remote {check.url} already has commits that do not share any history with this knowledge "
                "base, so nothing was changed and nothing was overwritten. Use an empty repository, or clone "
                "this one with File → Clone Knowledge Base… and move your records into the clone.",
            )
        remote = current.remote or "origin"
        if url is not None:
            valid = validate_remote_url(url)
            if remote in gitsync._remotes(repo):
                gitsync._git(repo, "remote", "set-url", "--", remote, valid)
            else:
                gitsync._git(repo, "remote", "add", "--", remote, valid)
        if check.empty:
            ahead = int(gitsync._out(repo, "rev-list", "--count", "HEAD") or 0)
            result = _run_git(
                repo.git,
                workspace.root,
                ["push", "--porcelain", "--set-upstream", remote, f"HEAD:refs/heads/{branch}"],
                timeout=timeout,
                ssh_batch=gitsync._ssh_batch(repo),
            )
            if result.returncode != 0:
                raise _classify_network_failure(result, "Publishing to the remote")
            # `push -u HEAD:refs/heads/x` records the upstream; set it
            # explicitly too, so it holds for every Git version.
            gitsync._git(repo, "config", f"branch.{branch}.remote", remote)
            gitsync._git(repo, "config", f"branch.{branch}.merge", f"refs/heads/{branch}")
            gitsync._record_sync(repo)
            return ConnectOutcome("published", remote, branch, pushed=ahead)
        fetched = _run_git(
            repo.git,
            workspace.root,
            ["fetch", "--quiet", remote],
            timeout=timeout,
            ssh_batch=gitsync._ssh_batch(repo),
        )
        if fetched.returncode != 0:
            raise _classify_network_failure(fetched, "Fetching from the remote")
        assert check.branch is not None
        gitsync._git(repo, "config", f"branch.{branch}.remote", remote)
        gitsync._git(repo, "config", f"branch.{branch}.merge", f"refs/heads/{check.branch}")
        run_sync = True
    assert run_sync
    outcome = gitsync.sync(workspace, timeout=timeout)
    return ConnectOutcome(outcome.state, remote, branch, pushed=outcome.pushed, sync=outcome)
