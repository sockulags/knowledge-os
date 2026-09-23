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
| `npm run dist` | Runs the three builds above, then writes the installer to `dist/knowledge-os-setup.exe`, with `latest.yml` and `knowledge-os-setup.exe.blockmap` for updates. |

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
the unsigned installer on first run. The installed app updates itself from
GitHub releases (see [Updates](#updates)).

### The `kos` command

The installer also puts a `kos` command on PATH, backed by the bundled core
(no separate Python install needed):

- `<install dir>\bin\kos.cmd` is a small shim
  (`resources/bin/kos.cmd` in this checkout) that forwards every argument to
  `<install dir>\resources\core\kos-core.exe -m knowledge_os`, preserving the
  exit code and stdin/stdout, so `kos --root PATH lint --json` and piping
  both work the same as running the Python CLI directly. `kos-read.cmd`
  ships alongside it the same way, forwarding to `-m knowledge_os.reader`
  (the standalone reader server; the shell starts the bundled core the same
  way itself, see below).
- The installer adds `<install dir>\bin` to the **current user's** PATH
  (`HKCU\Environment`, not a machine-wide change, so no administrator rights
  are needed) and broadcasts the PATH change so newly opened terminals see
  `kos` immediately, with no reboot or sign-out required. A terminal that was
  already open needs to be restarted to pick it up. Reinstalling or
  upgrading does not add a second PATH entry. Uninstalling removes exactly
  that one entry and leaves the rest of PATH untouched.
- The PATH update runs `build/installer.nsh`'s custom NSIS install/uninstall
  steps, which hand the actual registry edit to `build/manage-path.ps1`
  instead of doing it in NSIS itself. NSIS's default string build caps
  strings at 1024 characters, and a real PATH can be longer than that;
  reading a long `HKCU\Environment\Path` into such a string and writing it
  back would silently truncate everything past the limit. The PowerShell
  script reads and writes that registry value through .NET's Registry API,
  which has no such limit, so long PATH values are never touched.
- If a pip-installed `kos` is already on PATH, both can coexist; whichever
  directory comes first on PATH wins for a bare `kos` invocation. Run
  `where kos` to see every `kos` on PATH in the order Windows will try them,
  with the one that actually runs listed first.

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

## Updates

The installed app updates itself from the
[GitHub releases](https://github.com/sockulags/knowledge-os/releases) of this
repository with electron-updater. It checks 10 seconds after startup and every
4 hours after that, and whenever you choose Help → Check for Updates…. A newer
release downloads in the background. When the download is finished the app
asks whether to restart now; Help → Restart to Update does the same later, and
a downloaded update is also installed silently the next time you quit. The app
never restarts on its own.

Restarting to update closes the window first, so unsaved changes in the editor
get the same "Discard changes / Keep editing" question as closing the window;
keeping the edits cancels the restart. Closing the window stops the core the
same way quitting does (the whole process tree), and only then does the
installer start, so no `kos-core.exe` from the old version keeps running and
nothing is mid-write. The installer replaces the whole installation folder,
including `resources\core\`. The recent list and the settings live in the
user-data folder, which the installer does not touch.

Help → Check for Updates Automatically turns the scheduled checks off; the
choice is stored as `checkForUpdates` in `settings.json` in the user-data
folder, next to `recent-workspaces.json`. Manual checks always work.

When the computer is offline or GitHub cannot be reached, an automatic check
fails quietly: the failure is written to the log (the main process's standard
output) and the app keeps working. A manual check then says that it could not
check for updates. Running from a checkout (`npm run dev`, `npm start`), the
updater is off and Check for Updates… says so.

### Updates without code signing

The installer is not signed. For updates this means:

- electron-updater checks the Authenticode publisher of a downloaded installer
  only when `app-update.yml` (written into the app by electron-builder) names a
  `publisherName`. electron-builder writes one only for signed builds, so there
  is no publisher check. What protects the download is the sha512 in
  `latest.yml`, fetched over HTTPS from the GitHub release: the installer must
  match it before it runs. Anyone who can publish a release on the repository
  can therefore ship an update.
- The update runs the downloaded installer silently from the app, so the
  SmartScreen warning for an unsigned download usually does not appear for
  updates; it still appears for a first install from a browser download.
- To add signing later, configure `win.signtoolOptions` (with `publisherName`)
  in `electron-builder.yml`. Updates then verify the publisher with no code
  change. A release signed with a new certificate can be installed over an
  unsigned one, but after that, every update must be signed by that publisher.

## Releasing a new version

Nothing is uploaded by `npm run dist` (it passes `--publish never`); the
release is made by hand:

1. Bump the version everywhere it is written: `version` in `pyproject.toml`,
   `__version__` in `knowledge_os/__init__.py` and
   `knowledge_os/reader/__init__.py`, and `desktop/package.json` with its lock
   file (`npm version X.Y.Z --no-git-tag-version` in `desktop/` updates both).
   The app's version, which the updater compares, is the one in
   `desktop/package.json`.
2. Commit, merge, and build from a clean checkout of that commit in a shell
   where `MAIN_VITE_KOS_UPDATE_TEST_FEED` is not set: `npm ci`, then
   `npm run dist`.
3. Create a GitHub release with the tag `vX.Y.Z` (for example
   `gh release create vX.Y.Z --title "X.Y.Z" --notes "…"`) and attach these
   three files from `desktop/dist/`:
   - `knowledge-os-setup.exe`
   - `latest.yml`
   - `knowledge-os-setup.exe.blockmap`

   The release must be published, not a draft or a pre-release: installed apps
   read `latest.yml` from the latest published release. `latest.yml` names
   the installer by its file name and pins its size and sha512, so upload the
   three files from the same build. Installed apps find the update at their
   next check.

## Testing an update locally

An update can be tested end to end without publishing a release. The feed is
switched to electron-updater's `generic` provider on a local HTTP server by
setting `MAIN_VITE_KOS_UPDATE_TEST_FEED` while building the app that should
find the update:

```powershell
# Version A, which looks for updates on the local server.
npm version 0.1.90 --no-git-tag-version
$env:MAIN_VITE_KOS_UPDATE_TEST_FEED = 'http://127.0.0.1:8765/'
npm run dist            # copy dist\ away as version A
Remove-Item Env:\MAIN_VITE_KOS_UPDATE_TEST_FEED

# Version B, served as the update.
npm version 0.1.91 --no-git-tag-version
npm run dist
python -m http.server 8765 --bind 127.0.0.1 --directory dist
```

Install A silently (`knowledge-os-setup.exe /S`), start it, and Help → Check
for Updates… finds B, downloads it, and offers the restart. Undo the version
bumps afterwards.

electron-vite bakes the variable into the main-process bundle at build time;
the installed app never reads it from its environment. Only a loopback
`http`/`https` URL (`127.0.0.1`, `localhost`, `[::1]`) is accepted and
anything else is ignored, so a build made with the variable set by mistake can
only look for updates on the same computer. Release builds are made without
it, and their updater reads the GitHub feed from `app-update.yml`.

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
  does not touch your recent list or settings.
- `MAIN_VITE_KOS_UPDATE_TEST_FEED=URL`, set at build time, points the updater
  at a local test server (see [Testing an update locally](#testing-an-update-locally)).
