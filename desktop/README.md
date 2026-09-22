# Knowledge OS desktop shell

An Electron window around the existing Knowledge OS reader. The main process
runs the Python core (`python -m knowledge_os.reader`, the same server as
`kos-read`) on a free local port and loads the React UI that the core serves.
There is no second UI: the only page of its own is a small start page for
opening or creating a knowledge base and for showing errors.

`npm run dist` builds a Windows installer that bundles the core, so the
installed app needs no Python (see [Building the Windows installer](#building-the-windows-installer)).

## Requirements

- Node.js 22 or newer and npm.
- Python 3.11 or newer with Knowledge OS and its reader dependencies. From the
  repository root:

  ```powershell
  py -3.11 -m venv .venv
  .\.venv\Scripts\python -m pip install -e ".[reader]"
  ```

## Scripts

Run these in `desktop/`:

| Command | What it does |
| --- | --- |
| `npm install` | Installs dependencies and downloads Electron. |
| `npm run dev` | Starts the app with the start page served by Vite. |
| `npm run typecheck` | Type-checks the main, preload, and start-page code. |
| `npm run lint` | Runs ESLint with the Prettier rules. |
| `npm test` | Runs the Vitest unit tests. |
| `npm run build` | Type-checks and builds into `out/`; `npm start` runs that build. |
| `npm run build:ui` | Installs `reader-ui/` dependencies and rebuilds the reader UI into `knowledge_os/reader/static/app/`. |
| `npm run build:core` | Builds the frozen core into `build-core/dist/kos-core/`. |
| `npm run dist` | Runs the three builds above, then writes the installer to `dist/knowledge-os-setup.exe`. |

## Building the Windows installer

From a clean checkout, in `desktop/`:

```powershell
npm ci
npm run dist
```

This needs Windows, Node.js 22 or newer, and Python 3.11 reachable as
`py -3.11` (the Python launcher from the python.org installer). No virtual
environment has to be prepared: `build:core` creates its own in
`build-core\venv`, installs the dependencies listed in `pyproject.toml`
(including the `reader` extra) and a pinned PyInstaller into it, and freezes
Knowledge OS from this checkout with `core\kos-core.spec`. It then runs the
frozen core once as a smoke test. `build-core\` and `dist\` are git-ignored.

The installer is an unsigned, per-user NSIS installer (no administrator
prompt) for the app "Knowledge OS". It installs to
`%LOCALAPPDATA%\Programs\knowledge-os-desktop` (electron-builder names the
folder after the npm package), adds Start menu and desktop shortcuts, and
registers an uninstaller under Installed apps. `knowledge-os-setup.exe /S`
installs silently. Windows SmartScreen warns about
the unsigned installer on first run. There is no auto-update.

The core is a PyInstaller one-folder build (`resources\core\kos-core.exe`
next to its `_internal\` folder), not a one-file build: it starts without
unpacking itself to a temp folder, and it runs as a single process, so the
process-tree kill and the stdin lifeline below apply to it unchanged.
`kos-core.exe` accepts the same `-m knowledge_os ARGS` and
`-m knowledge_os.reader ARGS` forms as Python, so the shell starts it with the
same arguments in development and in the installed app.

## Which Python runs the core

The installed app runs its bundled `kos-core.exe` and never looks for Python.
Setting `KOS_PYTHON` makes an installed app use that interpreter instead,
which is useful for debugging; the interpreter then needs Knowledge OS
installed, since an installed app has no checkout to put on `PYTHONPATH`.

When the shell runs from a checkout (`npm run dev` or `npm start`), it tries
these in order and uses the first one that is Python 3.11+ and
can import the reader and its dependencies:

1. `KOS_PYTHON`, when set. It is then the only candidate, so a wrong value is
   reported instead of silently replaced.
2. The repository's `.venv` (`.venv\Scripts\python.exe` on Windows).
3. `py -3.11` on Windows (`python3.11`, then `python3`, elsewhere).
4. `python` on PATH.

When the shell runs from a checkout, the checkout is put first on
`PYTHONPATH`, so the core always runs this repository's code. The core's
working directory is the system temp folder, never the workspace or the
checkout.

## How the core is started and stopped

Opening a knowledge base starts
`python -m knowledge_os.reader --root PATH --host 127.0.0.1 --port N --exit-on-stdin-eof`
on a port the operating system reports as free, then polls `/api/workspace`
until it answers and loads `http://127.0.0.1:N/` in the window. Switching to
another knowledge base stops the running core first.

The core is stopped when the window closes, when the app quits, on SIGINT,
SIGTERM, and an uncaught exception in the main process. Each stop kills the
whole process tree (`taskkill /T /F` on Windows), because a venv's `python.exe`
and the `py` launcher each run the real interpreter as a child process. If the
main process dies without running any handler, the core still exits: its stdin
is a pipe held by the main process, and `--exit-on-stdin-eof` makes it exit
when that pipe closes.

## Start page and errors

The start page opens a folder, creates a new knowledge base in an empty folder
with `kos init`, and lists the ten most recently opened knowledge bases. The
list is stored in `recent-workspaces.json` in Electron's user-data folder. The
File menu has the same actions plus Close Knowledge Base.

An error screen explains a missing Python (or, in the installed app, a missing
bundled core), a folder that is not a knowledge
base, a core that stopped while starting or later, and a refused `kos init`,
and shows the core's own output. A knowledge base with lint issues still opens;
the reader shows those issues itself.

## Security

The window runs with `contextIsolation`, `sandbox`, and no `nodeIntegration`.
The preload script exposes only the workspace actions, and the main process
refuses those calls from any page other than the start page. Navigation is
limited to the start page and the running core's origin; web links open in
the system browser, and every other scheme is blocked. Permission requests
are denied.

The core's write endpoints need a per-process token. The shell passes nothing:
the UI, served from the core's own origin, reads the token from
`GET /api/session` and sends it back in the `X-KOS-Write-Token` header. See
"Local interface write API" in [`docs/architecture.md`](../docs/architecture.md).

## Development hooks

- `KOS_DESKTOP_WORKSPACE=PATH` opens that knowledge base at startup.
- `KOS_DESKTOP_USER_DATA=PATH` uses a separate user-data folder, so a test run
  does not touch your recent list.
