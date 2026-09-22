# Knowledge OS desktop shell

An Electron window around the existing Knowledge OS reader. The main process
runs the Python core (`python -m knowledge_os.reader`, the same server as
`kos-read`) on a free local port and loads the React UI that the core serves.
There is no second UI: the only page of its own is a small start page for
opening or creating a knowledge base and for showing errors.

Packaging and an installer are not part of this folder yet.

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

## Which Python runs the core

The shell tries these in order and uses the first one that is Python 3.11+ and
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

An error screen explains a missing Python, a folder that is not a knowledge
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

## Development hooks

- `KOS_DESKTOP_WORKSPACE=PATH` opens that knowledge base at startup.
- `KOS_DESKTOP_USER_DATA=PATH` uses a separate user-data folder, so a test run
  does not touch your recent list.
