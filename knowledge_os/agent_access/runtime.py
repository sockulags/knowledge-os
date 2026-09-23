"""Find the running desktop app from its runtime file.

While a knowledge base is open, the desktop shell writes ``runtime.json`` in
its user-data folder (see ``desktop/src/main/runtimeFile.ts``):

    {"version": 1, "app_version": "0.2.0", "port": 51234,
     "url": "http://127.0.0.1:51234", "write_token": "...",
     "workspace": {"root": "D:\\\\notes\\\\kb", "name": "kb"},
     "core_pid": 1234, "shell_pid": 999, "written_at": "2026-09-23T20:00:00Z"}

The shell rewrites it when another knowledge base is opened and removes it
when the core stops. A crash can leave it behind, so a file is used only when
its core process is still alive and the server on its port hands out the same
write token; anything else is reported as stale and nothing is written.

The user-data folder is Electron's ``userData`` for the app
``knowledge-os-desktop``: ``%APPDATA%\\knowledge-os-desktop`` on Windows,
``~/Library/Application Support/knowledge-os-desktop`` on macOS, and
``$XDG_CONFIG_HOME/knowledge-os-desktop`` (``~/.config``) elsewhere.
``KOS_DESKTOP_USER_DATA`` overrides it, as it does for the app, and
``KOS_RUNTIME_FILE`` names the file directly.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

RUNTIME_FILE_NAME = "runtime.json"
APP_FOLDER_NAME = "knowledge-os-desktop"
_LOOPBACK = "127.0.0.1"
_PROBE_TIMEOUT = 3.0


class AppUnavailable(Exception):
    """The app cannot be used right now. ``kind`` is ``app_not_open`` (no
    runtime file: the app is closed or no knowledge base is open) or
    ``app_not_responding`` (a file that no running core answers for)."""

    def __init__(self, kind: str, detail: str):
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


@dataclass(frozen=True)
class RuntimeInfo:
    port: int
    write_token: str
    workspace_root: str
    workspace_name: str
    app_version: str
    core_pid: int

    @property
    def base_url(self) -> str:
        return f"http://{_LOOPBACK}:{self.port}"


def user_data_dir(env: Mapping[str, str] | None = None, platform: str | None = None) -> Path:
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    override = env.get("KOS_DESKTOP_USER_DATA")
    if override:
        return Path(override)
    if platform == "win32":
        appdata = env.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / APP_FOLDER_NAME
    if platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_FOLDER_NAME
    config = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config) / APP_FOLDER_NAME


def runtime_file(env: Mapping[str, str] | None = None, platform: str | None = None) -> Path:
    env = os.environ if env is None else env
    explicit = env.get("KOS_RUNTIME_FILE")
    if explicit:
        return Path(explicit)
    return user_data_dir(env, platform) / RUNTIME_FILE_NAME


def parse_runtime(text: str) -> RuntimeInfo:
    """Validate the file's fields. Raises ``ValueError`` for anything else."""

    data = json.loads(text)
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("unsupported runtime file version")
    workspace = data.get("workspace")
    port = data.get("port")
    pid = data.get("core_pid")
    token = data.get("write_token")
    if not isinstance(workspace, dict) or not isinstance(workspace.get("root"), str):
        raise ValueError("runtime file has no workspace")
    if not isinstance(port, int) or isinstance(port, bool) or not 0 < port < 65536:
        raise ValueError("runtime file has no valid port")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        raise ValueError("runtime file has no valid core_pid")
    if not isinstance(token, str) or not token:
        raise ValueError("runtime file has no write token")
    name = workspace.get("name")
    version = data.get("app_version")
    return RuntimeInfo(
        port=port,
        write_token=token,
        workspace_root=workspace["root"],
        workspace_name=name if isinstance(name, str) and name else Path(workspace["root"]).name,
        app_version=version if isinstance(version, str) else "",
        core_pid=pid,
    )


def pid_alive(pid: int) -> bool:
    """Whether a process with this id is running (best effort)."""

    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        process_query_limited_information = 0x1000
        still_active = 259
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            # Access denied still means the process exists.
            return ctypes.get_last_error() == 5
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _session_token(info: RuntimeInfo) -> str | None:
    request = urllib.request.Request(info.base_url + "/api/session", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=_PROBE_TIMEOUT) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None
    token = payload.get("write_token") if isinstance(payload, dict) else None
    return token if isinstance(token, str) else None


def connect(env: Mapping[str, str] | None = None) -> RuntimeInfo:
    """Read the runtime file and confirm that its core is the one answering.

    Raises ``AppUnavailable`` when there is no usable file, the core process
    is gone, or the port does not answer with the same write token.
    """

    path = runtime_file(env)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise AppUnavailable(
            "app_not_open",
            "The Knowledge OS app is not running with a knowledge base open.",
        ) from None
    except OSError as exc:
        raise AppUnavailable("app_not_open", f"The Knowledge OS runtime file could not be read: {exc}") from None
    try:
        info = parse_runtime(text)
    except ValueError as exc:
        raise AppUnavailable("app_not_responding", f"The Knowledge OS runtime file is not usable: {exc}.") from None
    stale = (
        "The Knowledge OS app left a runtime file behind but is no longer answering; "
        "it probably closed without cleaning up."
    )
    if not pid_alive(info.core_pid):
        raise AppUnavailable("app_not_responding", stale)
    if _session_token(info) != info.write_token:
        raise AppUnavailable("app_not_responding", stale)
    return info
