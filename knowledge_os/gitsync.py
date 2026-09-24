"""Git versioning and sync for a workspace that is its own Git repository.

Everything here calls the ``git`` executable found on ``PATH``; there is no
Git library dependency. Every call runs with a timeout, without a terminal,
and with interactive credential prompts disabled, so a missing credential is
reported as an authentication error instead of blocking the caller. Existing
credential helpers and SSH agents keep working; nothing here reads, stores,
or logs credentials, and URLs in Git's messages are redacted.

The workspace root must be the top level of its repository. A workspace
nested inside another repository (for example an example workspace inside an
application's source tree) is treated as "not its own Git repository", so the
interface never commits into someone else's project by accident.

Operations:

* :func:`auto_commit` commits exactly the paths one interface write touched,
  never ``indexes/`` and never unrelated changes the user made elsewhere.
* :func:`sync` fetches, merges the upstream branch into the current branch,
  rebuilds the indexes when files changed, and pushes. A merge (rather than a
  rebase) is used because it stops at most once, leaves the standard
  recoverable ``MERGE_HEAD`` state (``git merge --abort`` undoes it), never
  rewrites local commits, and refuses to start when uncommitted local changes
  would be overwritten or when the index holds staged changes.
* :func:`list_conflicts`, :func:`resolve_conflict`, and :func:`abort_merge`
  drive conflict resolution; calling :func:`sync` again once no conflicted
  files remain lints the corpus, records the merge commit, and pushes.

Every operation that reads or changes the repository's files holds the
workspace mutation lock, so Git operations never interleave with record
writes or index rebuilds.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from .workspace import Workspace, WorkspaceError, refresh_derived_indexes, validate_workspace, workspace_mutation_lock

#: Seconds allowed for one network operation (fetch or push).
NETWORK_TIMEOUT = 45.0
#: Seconds allowed for one local Git operation.
LOCAL_TIMEOUT = 30.0

#: The generated index directory is never committed by the interface.
INDEX_DIRECTORY = "indexes/"
_INDEX_TRACKING_ALLOWED = {"indexes/README.md"}

_LAST_SYNC_FILE = "kos-last-sync"

_URL_CREDENTIALS = re.compile(r"(\b[a-zA-Z][a-zA-Z0-9+.-]*://)[^/\s@]+@")

_AUTH_MARKERS = (
    "terminal prompts disabled",
    "could not read username",
    "could not read password",
    "authentication failed",
    "permission denied (publickey",
    "permission denied, please try again",
    "host key verification failed",
    "http basic: access denied",
    "requested url returned error: 401",
    "requested url returned error: 403",
    "invalid username or password",
)
_NETWORK_MARKERS = (
    "could not resolve host",
    "connection refused",
    "failed to connect",
    "connection timed out",
    "network is unreachable",
    "unable to access",
    "could not read from remote repository",
    "connection reset",
    "operation timed out",
    "no route to host",
)


class GitSyncError(Exception):
    """A Git operation that could not be done, with a stable ``kind``.

    Kinds: ``git_missing``, ``not_a_repo``, ``source_repo`` (the workspace is
    the Knowledge OS source repository itself), ``no_branch``,
    ``no_identity``, ``no_upstream``, ``auth``, ``network``, ``timeout``,
    ``rejected`` (the remote refused the push), ``blocked`` (Git refused to
    merge over local changes), ``conflict`` (the merge stopped on
    conflicts), ``not_conflicted`` (a resolve named a file that is not in
    conflict), ``lint`` (resolved files leave the corpus invalid),
    ``no_merge``, and ``failed`` (any other Git failure).
    """

    def __init__(
        self,
        kind: str,
        message: str,
        *,
        issues: tuple[tuple[str, str], ...] = (),
        conflicts: tuple[str, ...] = (),
    ):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.issues = issues
        self.conflicts = conflicts


@dataclass(frozen=True)
class Repository:
    workspace: Workspace
    git: str
    git_dir: Path


@dataclass(frozen=True)
class CommitOutcome:
    """What happened to the Git history after one interface write."""

    committed: bool
    sha: str | None = None
    message: str | None = None
    skipped: str | None = None  # a GitSyncError kind, or "nothing_to_commit" / "merge_in_progress"
    detail: str | None = None


@dataclass(frozen=True)
class SyncStatus:
    available: bool
    reason: str | None = None  # a GitSyncError kind when not available
    detail: str | None = None
    branch: str | None = None
    upstream: str | None = None
    remotes: tuple[str, ...] = ()
    ahead: int = 0
    behind: int = 0
    uncommitted: int = 0
    merging: bool = False
    conflicts: int = 0
    last_sync: str | None = None
    identity: dict[str, str] | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SyncOutcome:
    state: str  # "synced" or "conflict"
    pulled: int = 0
    pushed: int = 0
    reindexed: bool = False
    index_error: str | None = None
    conflicts: tuple[str, ...] = ()
    detail: str | None = None


@dataclass(frozen=True)
class ConflictFile:
    path: str
    ours: str | None  # None when this side deleted the file
    theirs: str | None
    working: str | None  # the working-tree text: conflict markers, or the chosen resolution
    binary: bool = False
    resolved: bool = False  # a version was already chosen; choosing again reopens the conflict


@dataclass(frozen=True)
class ResolveOutcome:
    path: str
    remaining: tuple[str, ...]
    issues: tuple[tuple[str, str], ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Running git
# ---------------------------------------------------------------------------


def redact(text: str) -> str:
    """Remove ``user:password@`` from any URL in a Git message."""

    return _URL_CREDENTIALS.sub(r"\1***@", text)


def find_git() -> str | None:
    return shutil.which("git")


def _environment(ssh_batch: bool) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            # Never wait on a terminal or a GUI prompt; missing credentials
            # fail fast and are reported as an authentication error.
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "",
            "SSH_ASKPASS_REQUIRE": "never",
            "GCM_INTERACTIVE": "never",
            "GIT_EDITOR": "true",
            "GIT_MERGE_AUTOEDIT": "no",
            "LC_ALL": "C",
            "LANG": "C",
        }
    )
    env.pop("SSH_ASKPASS", None)
    if ssh_batch:
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
    return env


def _kill_tree(process: subprocess.Popen[bytes]) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    else:
        import signal

        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
    process.kill()


def _run_git(
    git: str,
    cwd: Path,
    args: Iterable[str],
    *,
    timeout: float = LOCAL_TIMEOUT,
    ssh_batch: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    command = [git, "-c", "core.quotepath=false", *args]
    options: dict[str, object] = {}
    if os.name == "nt":
        options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0) | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_environment(ssh_batch),
            **options,  # type: ignore[arg-type]
        )
    except OSError as exc:
        raise GitSyncError("git_missing", f"could not run git: {exc}") from exc
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        verb = next((arg for arg in args if not arg.startswith("-")), "git")
        raise GitSyncError(
            "timeout",
            f"git {verb} did not finish within {timeout:g} seconds and was stopped; "
            "check the network connection and that the remote answers",
        ) from None
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").strip()


def _message(result: subprocess.CompletedProcess[bytes]) -> str:
    return redact(_text(result.stderr) or _text(result.stdout) or f"git exited with status {result.returncode}")


def _git(repo: Repository, *args: str, timeout: float = LOCAL_TIMEOUT, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = _run_git(repo.git, repo.workspace.root, args, timeout=timeout)
    if check and result.returncode != 0:
        raise GitSyncError("failed", f"git {args[0]} failed: {_message(result)}")
    return result


def _out(repo: Repository, *args: str) -> str:
    return _text(_git(repo, *args).stdout)


def _classify_network_failure(result: subprocess.CompletedProcess[bytes], action: str) -> GitSyncError:
    message = _message(result)
    lowered = message.lower()
    if any(marker in lowered for marker in _AUTH_MARKERS):
        return GitSyncError(
            "auth",
            f"{action} failed because the remote needs credentials that Git could not get without asking. "
            "Set up a credential helper or an SSH key for this remote, then sync again. Git said: " + message,
        )
    if "[rejected]" in lowered or "non-fast-forward" in lowered or "fetch first" in lowered:
        return GitSyncError(
            "rejected",
            f"{action} was rejected because the remote changed in the meantime; sync again. Git said: {message}",
        )
    if any(marker in lowered for marker in _NETWORK_MARKERS):
        return GitSyncError("network", f"{action} failed: the remote could not be reached. Git said: {message}")
    return GitSyncError("failed", f"{action} failed: {message}")


def _same_path(left: Path, right: Path) -> bool:
    a, b = os.path.normcase(str(left.resolve())), os.path.normcase(str(right.resolve()))
    return a == b


def _is_knowledge_os_source_repository(root: Path) -> bool:
    """Whether ``root`` is the Knowledge OS source repository's own top level.

    Detected without relying on remote URLs (a clone or fork must be caught
    too): the root declares the ``knowledge-os`` project in ``pyproject.toml``
    and has the ``knowledge_os/`` package directory next to it. A workspace
    can otherwise legitimately be pointed at this repository's top level (it
    is a valid workspace, with its own ``knowledge-os.toml`` marker), so this
    check exists to stop the app from committing records into the code
    repository on whatever branch happens to be checked out, or pushing them
    with the sync button.
    """

    pyproject = root / "pyproject.toml"
    if not (pyproject.is_file() and (root / "knowledge_os").is_dir()):
        return False
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return data.get("project", {}).get("name") == "knowledge-os"


def open_repository(workspace: Workspace) -> Repository:
    """Return the repository whose top level is this workspace, or raise."""

    git = find_git()
    if git is None:
        raise GitSyncError(
            "git_missing",
            "Git was not found on PATH. Install Git (https://git-scm.com) and restart the app to version and sync "
            "this knowledge base.",
        )
    result = _run_git(git, workspace.root, ["rev-parse", "--show-toplevel", "--absolute-git-dir"])
    if result.returncode != 0:
        raise GitSyncError(
            "not_a_repo",
            "This knowledge base is not a Git repository, so changes are not committed or synced. "
            f"Run `git init` in {workspace.root} to start versioning it.",
        )
    lines = _text(result.stdout).splitlines()
    toplevel, git_dir = Path(lines[0]), Path(lines[1])
    if not _same_path(toplevel, workspace.root):
        raise GitSyncError(
            "not_a_repo",
            f"This knowledge base lies inside the Git repository at {toplevel} instead of being its own repository, "
            "so the app does not commit or sync it.",
        )
    if _is_knowledge_os_source_repository(workspace.root):
        raise GitSyncError(
            "source_repo",
            "This is the Knowledge OS source repository; the app does not commit or sync here. Point it at a "
            "different workspace to version and sync your records with Git.",
        )
    return Repository(workspace, git, git_dir)


# ---------------------------------------------------------------------------
# Small repository queries
# ---------------------------------------------------------------------------


def _branch(repo: Repository) -> str | None:
    result = _git(repo, "symbolic-ref", "--short", "-q", "HEAD", check=False)
    return _text(result.stdout) or None


def _has_head(repo: Repository) -> bool:
    return _git(repo, "rev-parse", "-q", "--verify", "HEAD", check=False).returncode == 0


def _head(repo: Repository) -> str | None:
    result = _git(repo, "rev-parse", "-q", "--verify", "HEAD", check=False)
    return _text(result.stdout) if result.returncode == 0 else None


def _config(repo: Repository, key: str) -> str | None:
    result = _git(repo, "config", "--get", key, check=False)
    if result.returncode != 0:
        return None
    return _text(result.stdout) or None


def _remotes(repo: Repository) -> tuple[str, ...]:
    return tuple(line for line in _out(repo, "remote").splitlines() if line)


def _merging(repo: Repository) -> bool:
    return _git(repo, "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False).returncode == 0


def _unmerged(repo: Repository) -> tuple[str, ...]:
    output = _git(repo, "diff", "--name-only", "--diff-filter=U", "-z").stdout
    return tuple(sorted({item.decode("utf-8", errors="replace") for item in output.split(b"\0") if item}))


def _identity(repo: Repository) -> dict[str, str] | None:
    name = os.environ.get("GIT_AUTHOR_NAME") or _config(repo, "user.name")
    email = os.environ.get("GIT_AUTHOR_EMAIL") or _config(repo, "user.email")
    if not name or not email:
        return None
    return {"name": name, "email": email}


def _require_identity(repo: Repository) -> None:
    if _identity(repo) is None:
        raise GitSyncError(
            "no_identity",
            "Git has no author identity for this repository, so nothing was committed. Set one with "
            '`git config user.name "Your Name"` and `git config user.email you@example.com` '
            f"in {repo.workspace.root} (or add --global).",
        )


def _changed_paths(repo: Repository, pathspec: Iterable[str] = ()) -> list[str]:
    args = ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
    spec = list(pathspec)
    if spec:
        args += ["--", *spec]
    entries = _git(repo, *args).stdout.split(b"\0")
    paths: list[str] = []
    skip_next = False
    for entry in entries:
        if skip_next:
            skip_next = False
            continue
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:].decode("utf-8", errors="replace")
        if status[:1] in (b"R", b"C"):
            skip_next = True  # the rename's source path follows
        paths.append(path)
    return paths


@dataclass(frozen=True)
class _Upstream:
    remote: str
    branch_ref: str  # refs/heads/<name> on the remote
    tracking: str | None  # local remote-tracking ref when it exists


def _upstream(repo: Repository, branch: str) -> _Upstream | None:
    remote = _config(repo, f"branch.{branch}.remote")
    merge = _config(repo, f"branch.{branch}.merge")
    if not remote or not merge:
        return None
    result = _git(repo, "rev-parse", "--symbolic-full-name", f"{branch}@{{upstream}}", check=False)
    tracking = _text(result.stdout) if result.returncode == 0 else None
    return _Upstream(remote, merge, tracking or None)


def _short_ref(ref: str) -> str:
    for prefix in ("refs/remotes/", "refs/heads/"):
        if ref.startswith(prefix):
            return ref[len(prefix) :]
    return ref


def _ahead_behind(repo: Repository, tracking: str | None) -> tuple[int, int]:
    if not _has_head(repo):
        return 0, (int(_out(repo, "rev-list", "--count", tracking) or 0) if tracking else 0)
    if tracking is None:
        return int(_out(repo, "rev-list", "--count", "HEAD") or 0), 0
    counts = _out(repo, "rev-list", "--left-right", "--count", f"HEAD...{tracking}").split()
    return int(counts[0]), int(counts[1])


def _last_sync(repo: Repository) -> str | None:
    try:
        return (repo.git_dir / _LAST_SYNC_FILE).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _record_sync(repo: Repository) -> None:
    stamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        (repo.git_dir / _LAST_SYNC_FILE).write_text(stamp + "\n", encoding="utf-8")
    except OSError:
        pass


def _no_upstream_error(repo: Repository, branch: str) -> GitSyncError:
    remotes = _remotes(repo)
    if not remotes:
        return GitSyncError(
            "no_upstream",
            "This repository has no remote to sync with. Add one and publish this branch with "
            f"`git remote add origin <url>` and `git push -u origin {branch}` in {repo.workspace.root}.",
        )
    return GitSyncError(
        "no_upstream",
        f"The branch {branch} has no upstream branch to sync with. Set one with "
        f"`git push -u {remotes[0]} {branch}` in {repo.workspace.root}.",
    )


def _ssh_batch(repo: Repository) -> bool:
    """Use SSH batch mode unless the user configured their own SSH command."""

    if os.environ.get("GIT_SSH_COMMAND") or os.environ.get("GIT_SSH"):
        return False
    return _config(repo, "core.sshCommand") is None


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def status(workspace: Workspace) -> SyncStatus:
    """Describe the repository without contacting the remote."""

    try:
        repo = open_repository(workspace)
    except GitSyncError as exc:
        return SyncStatus(available=False, reason=exc.kind, detail=exc.message)
    try:
        branch = _branch(repo)
        upstream = _upstream(repo, branch) if branch else None
        ahead, behind = _ahead_behind(repo, upstream.tracking if upstream else None)
        changed = [path for path in _changed_paths(repo) if not path.startswith(INDEX_DIRECTORY)]
        merging = _merging(repo)
        tracked_indexes = [
            path
            for path in _out(repo, "ls-files", "--", "indexes").splitlines()
            if path and path not in _INDEX_TRACKING_ALLOWED
        ]
    except GitSyncError as exc:
        return SyncStatus(available=False, reason=exc.kind, detail=exc.message)
    warnings: list[str] = []
    if tracked_indexes:
        warnings.append(
            "Generated index files are tracked by Git ("
            + ", ".join(tracked_indexes)
            + "). They are rebuilt on every change and can conflict on sync; stop tracking them with "
            "`git rm --cached " + " ".join(tracked_indexes) + "` and add them to .gitignore."
        )
    upstream_name = None
    if upstream is not None:
        upstream_name = _short_ref(upstream.tracking) if upstream.tracking else f"{upstream.remote}/{_short_ref(upstream.branch_ref)}"
    return SyncStatus(
        available=True,
        branch=branch,
        upstream=upstream_name,
        remotes=_remotes(repo),
        ahead=ahead,
        behind=behind,
        uncommitted=len(changed),
        merging=merging,
        conflicts=len(_unmerged(repo)) if merging else 0,
        last_sync=_last_sync(repo),
        identity=_identity(repo),
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# Auto-commit
# ---------------------------------------------------------------------------


def auto_commit(workspace: Workspace, paths: Iterable[str], message: str) -> CommitOutcome:
    """Commit exactly ``paths`` (workspace-relative POSIX) with ``message``.

    Never raises: a workspace that is not its own repository, a missing Git
    or identity, or a merge in progress is reported as ``skipped`` with a
    readable ``detail``. Paths under ``indexes/`` are never committed, and
    other changes in the working tree or index are left untouched.
    """

    selected = sorted({path for path in paths if path and not path.startswith(INDEX_DIRECTORY)})
    try:
        repo = open_repository(workspace)
        with workspace_mutation_lock(workspace):
            if _merging(repo):
                return CommitOutcome(
                    False,
                    skipped="merge_in_progress",
                    detail="A sync is waiting for conflicts to be resolved, so this change was not committed yet.",
                )
            _require_identity(repo)
            if selected:
                # A move removes paths. Git refuses a pathspec that is neither
                # on disk nor tracked (a file removed before it was ever
                # committed), so keep only paths Git can stage.
                listed = _git(repo, "ls-files", "-z", "--", *selected).stdout.split(b"\0")
                tracked = {entry.decode("utf-8", errors="replace") for entry in listed if entry}
                selected = [path for path in selected if path in tracked or (workspace.root / path).exists()]
            if not selected or not _changed_paths(repo, selected):
                return CommitOutcome(False, skipped="nothing_to_commit", detail="Nothing changed in Git.")
            _git(repo, "add", "--all", "--", *selected)
            # With paths, commit records only those paths ("--only"),
            # whatever else the user staged or changed.
            _git(repo, "commit", "--quiet", "-m", message, "--only", "--", *selected)
            sha = _out(repo, "rev-parse", "HEAD")
    except GitSyncError as exc:
        return CommitOutcome(False, skipped=exc.kind, detail=exc.message)
    except WorkspaceError as exc:
        return CommitOutcome(False, skipped="failed", detail=str(exc))
    return CommitOutcome(True, sha=sha, message=message)


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


def _reindex(workspace: Workspace) -> tuple[bool, str | None]:
    try:
        refresh_derived_indexes(workspace)
    except WorkspaceError as exc:
        return False, str(exc)
    return True, None


def _push(repo: Repository, upstream: _Upstream, timeout: float) -> None:
    result = _run_git(
        repo.git,
        repo.workspace.root,
        ["push", "--porcelain", upstream.remote, f"HEAD:{upstream.branch_ref}"],
        timeout=timeout,
        ssh_batch=_ssh_batch(repo),
    )
    if result.returncode != 0:
        raise _classify_network_failure(result, "Push")


def _lint_issues(workspace: Workspace) -> tuple[tuple[str, str], ...]:
    _documents, issues = validate_workspace(workspace)
    found: list[tuple[str, str]] = []
    for issue in issues:
        try:
            location = workspace.relative(issue.path)
        except WorkspaceError:
            location = str(issue.path)
        found.append((location, issue.message))
    return tuple(found)


def sync(workspace: Workspace, *, timeout: float = NETWORK_TIMEOUT) -> SyncOutcome:
    """Pull (fetch + merge) the upstream branch, then push.

    When a merge from an earlier sync is waiting and every conflict has been
    resolved, this completes it instead: the corpus must pass lint, then the
    merge is committed, the indexes rebuilt, and the result pushed.
    """

    repo = open_repository(workspace)
    with workspace_mutation_lock(workspace):
        branch = _branch(repo)
        if branch is None:
            raise GitSyncError("no_branch", "The repository is not on a branch (detached HEAD), so it cannot sync.")
        upstream = _upstream(repo, branch)
        if upstream is None:
            raise _no_upstream_error(repo, branch)

        if _merging(repo):
            return _complete_merge(repo, upstream, timeout)

        before = _head(repo)
        result = _run_git(
            repo.git,
            workspace.root,
            ["fetch", "--quiet", upstream.remote],
            timeout=timeout,
            ssh_batch=_ssh_batch(repo),
        )
        if result.returncode != 0:
            raise _classify_network_failure(result, "Fetching from the remote")
        upstream = _upstream(repo, branch) or upstream

        pulled = 0
        if upstream.tracking is not None:
            _ahead, behind = _ahead_behind(repo, upstream.tracking)
            if behind:
                _require_identity(repo)
                pulled = behind
                label = _short_ref(upstream.tracking)
                merge = _git(repo, "merge", "--no-edit", "-m", f"Sync with {label}", upstream.tracking, check=False)
                if merge.returncode != 0:
                    conflicts = _unmerged(repo) if _merging(repo) else ()
                    if conflicts:
                        return SyncOutcome(
                            "conflict",
                            pulled=pulled,
                            conflicts=conflicts,
                            detail=f"{len(conflicts)} file(s) changed both here and on {label}. Choose a version "
                            "for each, then finish the sync.",
                        )
                    said = _message(merge)
                    if any(marker in said for marker in ("overwritten", "uncommitted changes", "not uptodate")):
                        raise GitSyncError(
                            "blocked",
                            "The pull was stopped before changing anything because it would overwrite uncommitted "
                            "local changes. Commit or undo them in Git, then sync again. Git said: " + said,
                        )
                    raise GitSyncError("failed", f"Merging {label} failed: {said}")

        reindexed, index_error = False, None
        if pulled and _head(repo) != before:
            reindexed, index_error = _reindex(workspace)

        ahead, _behind = _ahead_behind(repo, upstream.tracking)
        pushed = 0
        if ahead and _has_head(repo):
            _push(repo, upstream, timeout)
            pushed = ahead
        _record_sync(repo)
        return SyncOutcome("synced", pulled=pulled, pushed=pushed, reindexed=reindexed, index_error=index_error)


def _complete_merge(repo: Repository, upstream: _Upstream, timeout: float) -> SyncOutcome:
    remaining = _unmerged(repo)
    if remaining:
        raise GitSyncError(
            "conflict",
            f"{len(remaining)} file(s) still need a chosen version before the sync can finish.",
            conflicts=remaining,
        )
    issues = _lint_issues(repo.workspace)
    if issues:
        raise GitSyncError(
            "lint",
            "The resolved files do not pass kos lint, so the sync was not finished. Fix the issues and try again.",
            issues=issues,
        )
    _require_identity(repo)
    label = _short_ref(upstream.tracking) if upstream.tracking else upstream.remote
    _git(repo, "commit", "--quiet", "-m", f"Sync with {label} (resolved conflicts)")
    reindexed, index_error = _reindex(repo.workspace)
    ahead, _behind = _ahead_behind(repo, upstream.tracking)
    pushed = 0
    if ahead:
        _push(repo, upstream, timeout)
        pushed = ahead
    _record_sync(repo)
    return SyncOutcome("synced", pushed=pushed, reindexed=reindexed, index_error=index_error)


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------


def _decode(data: bytes) -> tuple[str | None, bool]:
    try:
        return data.decode("utf-8"), False
    except UnicodeDecodeError:
        return None, True


def _stage_text(repo: Repository, stage: int, path: str) -> tuple[str | None, bool]:
    result = _git(repo, "show", f":{stage}:{path}", check=False)
    if result.returncode != 0:
        return None, False
    return _decode(result.stdout)


def _resolve_undo(repo: Repository) -> dict[str, dict[int, str]]:
    """Files this merge had in conflict that were resolved since: path -> stage -> blob."""

    found: dict[str, dict[int, str]] = {}
    for entry in _git(repo, "ls-files", "--resolve-undo", "-z").stdout.split(b"\0"):
        if b"\t" not in entry:
            continue
        meta, raw_path = entry.split(b"\t", 1)
        _mode, blob, stage = meta.decode("ascii").split()
        found.setdefault(raw_path.decode("utf-8", errors="replace"), {})[int(stage)] = blob
    return found


def _blob_text(repo: Repository, blob: str | None) -> tuple[str | None, bool]:
    if blob is None:
        return None, False
    return _decode(_git(repo, "cat-file", "blob", blob).stdout)


def list_conflicts(workspace: Workspace) -> tuple[ConflictFile, ...]:
    """Every file this merge put in conflict, including ones already resolved."""

    repo = open_repository(workspace)
    with workspace_mutation_lock(workspace):
        if not _merging(repo):
            return ()
        unmerged = set(_unmerged(repo))
        undo = _resolve_undo(repo)
        files: list[ConflictFile] = []
        for path in sorted(unmerged | set(undo)):
            if path in unmerged:
                ours, ours_binary = _stage_text(repo, 2, path)
                theirs, theirs_binary = _stage_text(repo, 3, path)
            else:
                ours, ours_binary = _blob_text(repo, undo[path].get(2))
                theirs, theirs_binary = _blob_text(repo, undo[path].get(3))
            working: str | None = None
            binary = ours_binary or theirs_binary
            target = workspace.root / path
            if target.is_file():
                working, working_binary = _decode(target.read_bytes())
                binary = binary or working_binary
            files.append(ConflictFile(path, ours, theirs, working, binary, resolved=path not in unmerged))
        return tuple(files)


def resolve_conflict(workspace: Workspace, path: str, choice: str, content: str | None = None) -> ResolveOutcome:
    """Resolve one conflicted file with ``ours``, ``theirs``, or ``merged`` text.

    Only a path this merge put in conflict can be written. A file resolved
    earlier in the same merge is first put back in conflict (``git checkout
    -m``), so a person can change their mind before the sync finishes. The
    returned ``issues`` are the lint findings for this file alone; the sync
    cannot finish until the whole corpus passes lint.
    """

    if choice not in {"ours", "theirs", "merged"}:
        raise GitSyncError("failed", "choice must be one of ours, theirs, or merged")
    if choice == "merged" and content is None:
        raise GitSyncError("failed", "a merged resolution needs the merged text")
    repo = open_repository(workspace)
    with workspace_mutation_lock(workspace):
        if not _merging(repo):
            raise GitSyncError("no_merge", "There is no sync waiting for conflicts to be resolved.")
        conflicted = _unmerged(repo)
        target = workspace.root / path
        if path not in conflicted:
            if path not in _resolve_undo(repo):
                raise GitSyncError("not_conflicted", f"{path} is not a conflicted file.", conflicts=conflicted)
            workspace.assert_safe_path(target)
            _git(repo, "checkout", "-m", "--", path)
        workspace.assert_safe_path(target)
        if choice == "merged":
            assert content is not None
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content.encode("utf-8"))
            _git(repo, "add", "--", path)
        else:
            stage = 2 if choice == "ours" else 3
            if _git(repo, "cat-file", "-e", f":{stage}:{path}", check=False).returncode == 0:
                _git(repo, "checkout", f"--{choice}", "--", path)
                _git(repo, "add", "--", path)
            else:
                # That side deleted the file; resolving to it deletes it.
                _git(repo, "rm", "--quiet", "--force", "--", path)
        issues = tuple((p, m) for p, m in _lint_issues(workspace) if p == path)
        return ResolveOutcome(path, _unmerged(repo), issues)


def abort_merge(workspace: Workspace) -> None:
    """Undo a sync that stopped on conflicts, restoring the pre-merge state."""

    repo = open_repository(workspace)
    with workspace_mutation_lock(workspace):
        if not _merging(repo):
            raise GitSyncError("no_merge", "There is no sync waiting for conflicts to be resolved.")
        _git(repo, "merge", "--abort")
        _reindex(workspace)
