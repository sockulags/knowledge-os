# Knowledge OS desktop shell

An Electron window around the existing Knowledge OS reader. The main process
runs the Python core (`python -m knowledge_os.reader`, the same server as
`kos-read`) on a free local port and loads the React UI that the core serves.
There is no second UI: the only pages of its own are a small start page for
opening or creating a knowledge base and for showing errors, and the
[Referat plugin](#referat-plugin)'s import window.

`npm run dist` builds a Windows installer that bundles the core, so the
installed app needs no Python (see [Building the Windows installer](#building-the-windows-installer)).

## Requirements

- Node.js 22 or newer and npm.
- Python 3.11 or newer with Knowledge OS and its reader dependencies (add the
  `mcp` extra to run `kos mcp` for agents). From the repository root:

  ```powershell
  py -3.11 -m venv .venv
  .\.venv\Scripts\python -m pip install -e ".[reader,mcp]"
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
| `npm run dist:test` | Builds the isolated **test variant** for installer/update testing; writes `dist-test/knowledge-os-test-setup.exe`. Never use `npm run dist` for testing installs — see [Testing the installer](#testing-the-installer). |
| `npm run test:installer` | Builds the test variant and runs the guarded install/PATH/uninstall check described below. |

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
(including the `reader` and `mcp` extras) and a pinned PyInstaller into it,
and freezes Knowledge OS from this checkout with `core\kos-core.spec`. It then
runs the frozen core once as a smoke test, including starting `kos mcp`.
`build-core\` and `dist\` are git-ignored.

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
  with the one that actually runs listed first. `kos --version` reports which
  one you are running (the bundled core's path, or the Python interpreter and
  package path). To make that shadowing visible instead of silent, the shim
  sets `KOS_LAUNCHED_BY_SHIM` to its own path before starting the core; the
  core (`knowledge_os/version_info.py`) checks `shutil.which("kos")` against
  that path and, if a bare `kos` would resolve elsewhere, prints a one-line
  warning to stderr — never stdout, so `--json` output and `kos mcp`'s stdio
  protocol stay clean. The same module warns from the pip-installed `kos` side
  too, when it runs while the app is also installed (it does not compare
  versions, only that both exist, which is enough to point at the fix).
  `KOS_NO_PATH_WARNING=1` silences it.

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

## Agents and the runtime file

Agents reach the open knowledge base through `kos mcp`, the MCP server in the
core (see "Agent access over MCP" in
[`docs/architecture.md`](../docs/architecture.md)). It finds the running core
through `runtime.json` in the user-data folder
(`%APPDATA%\knowledge-os-desktop\runtime.json` for the installed app, or
under `KOS_DESKTOP_USER_DATA`):

```json
{
  "version": 1,
  "app_version": "0.2.0",
  "port": 51234,
  "url": "http://127.0.0.1:51234",
  "write_token": "...",
  "workspace": { "root": "D:\\notes\\my-kb", "name": "my-kb" },
  "core_pid": 1234,
  "shell_pid": 999,
  "written_at": "2026-09-23T20:00:00.000Z"
}
```

Once the core answers, the shell reads the write token from `GET /api/session`
and writes the file (`src/main/runtimeFile.ts`). Opening another knowledge
base rewrites it; closing the knowledge base, closing the window, quitting, and
a core that stops unexpectedly remove it. It is removed only while it still
names this app's core, so a second app instance's file is left alone. A crash
can leave a file behind; `kos mcp` uses a file only when `core_pid` is alive and
the port hands out the same write token, and otherwise tells the agent the app
is not answering.

The file holds the write token, so only the current user may read it. On
Windows it is written to a temporary file first, whose access list is then set
with `icacls FILE /inheritance:r /grant:r *<your SID>:F` (the SID comes from
`whoami /user`): inherited entries are removed, so Administrators and SYSTEM
lose their inherited access and the current user is the only entry. Only then
is it renamed to `runtime.json`. If that fails, no file is written and agents
report that the app is not open. On macOS and Linux the file is created with
mode `0600`. Run `icacls "%APPDATA%\knowledge-os-desktop\runtime.json"` to see
its access list.

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
including `resources\core\` and the `kos` shim in `bin\`, and runs the same
PATH step as a fresh install, which does not add a second entry. The recent
list and the settings live in the user-data folder, which the installer does
not touch.

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
   `knowledge_os/reader/__init__.py`, the plugin manifests
   (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
   `.codex-plugin/plugin.json`; `tests/test_plugin_packaging.py` checks they
   match `pyproject.toml`), and `desktop/package.json` with its lock
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

## Testing the installer

**Never run `npm run dist`'s installer or uninstaller to test anything.** An
earlier round of installer and update testing installed into and then
silently uninstalled `%LOCALAPPDATA%\Programs\knowledge-os-desktop` — the same
folder a real install uses — which deleted a real installation and its `kos`
PATH entry. Installer and update tests must always use the **test build
variant** instead, built by `npm run dist:test`
(`electron-builder.test.yml`, which extends `electron-builder.yml`). It
changes every identifier that could make a test run collide with a real
install:

| | Real (`npm run dist`) | Test (`npm run dist:test`) |
| --- | --- | --- |
| `appId` | `se.lucasskog.knowledgeos` | `se.lucasskog.knowledgeostest` |
| `productName` | Knowledge OS | Knowledge OS Test |
| app name / install dir / userData dir | `knowledge-os-desktop` | `knowledge-os-desktop-test` |
| installer/uninstaller `.exe` | `knowledge-os-setup.exe` / `knowledge-os.exe` | `knowledge-os-test-setup.exe` / `knowledge-os-test.exe` |
| PATH entry | `...\Programs\knowledge-os-desktop\bin` | `...\Programs\knowledge-os-desktop-test\bin` |
| updater cache dir | `knowledge-os-desktop-updater` | `knowledge-os-desktop-test-updater` |
| update feed | GitHub releases (`app-update.yml`) | none (`publish: null`, no `app-update.yml` is written) |
| build output | `dist/` | `dist-test/` |

The install directory and userData folder are named after the app's
`name` (electron-builder names the NSIS install folder and Electron names the
default userData folder after the packaged `package.json`'s `name`, not
`productName`), so `electron-builder.test.yml` overrides it with
`extraMetadata.name`. `build/installer.nsh` and `build/manage-path.ps1` need
no change: they already add/remove `$INSTDIR\bin` for whatever install
directory the running installer was given, so the different install
directory alone gives the test variant its own PATH entry. Because the test
build has no `publish` config, it never gets an `app-update.yml`, so it can
never find or install an update from a real GitHub release, however it is
started.

`npm run test:installer` runs the guarded flow: it re-derives the real and
test identifiers from `electron-builder.yml`, `electron-builder.test.yml`,
and `package.json`, and **refuses to run** if any of them are not cleanly
separate from the real app's (same install dir, same PATH entry, same
`appId`, or same `productName`). Only once that guard passes does it build
the test variant, record the current user PATH exactly as stored in the
registry, install the test variant silently, run `kos --help` through the
test variant's shim from a new process (with PATH rebuilt from the registry,
the way a newly opened terminal would see it), uninstall the test variant
silently, and verify the user PATH is byte-identical to what it recorded
before the run — restoring that exact value immediately if it is not. It
also snapshots the real install folder and its userData folder, if present,
before and after, and fails loudly if either changed. The real app is never
installed, updated, or uninstalled by this script.

## Testing an update locally

An update can be tested end to end without publishing a release, using the
test variant so it can never reach a real GitHub release. The feed is
switched to electron-updater's `generic` provider on a local HTTP server by
setting `MAIN_VITE_KOS_UPDATE_TEST_FEED` while building the app that should
find the update:

```powershell
# Version A, which looks for updates on the local server.
npm version 0.1.90 --no-git-tag-version
$env:MAIN_VITE_KOS_UPDATE_TEST_FEED = 'http://127.0.0.1:8765/'
npm run dist:test        # copy dist-test\ away as version A
Remove-Item Env:\MAIN_VITE_KOS_UPDATE_TEST_FEED

# Version B, served as the update.
npm version 0.1.91 --no-git-tag-version
npm run dist:test
python -m http.server 8765 --bind 127.0.0.1 --directory dist-test
```

Install A silently (`knowledge-os-test-setup.exe /S`), start it, and Help →
Check for Updates… finds B, downloads it, and offers the restart. Undo the
version bumps afterwards, and uninstall the test variant
(`Uninstall Knowledge OS Test.exe /S`, in the test install dir under
`%LOCALAPPDATA%\Programs\knowledge-os-desktop-test`) when done.

On the local server both versions' installers have the same file name, so
electron-updater's differential download compares B's blockmap with itself,
fails its checksum, and falls back to a full download (logged as "Cannot
download differentially"). On GitHub the release tag is part of each download
URL, so the old version's blockmap is a different file.

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
are denied. The Referat import window runs with the same settings, its own
preload script, and no navigation beyond its own page (see
[Referat plugin](#referat-plugin)).

The core's write endpoints need a per-process token. The shell passes nothing:
the UI, served from the core's own origin, reads the token from
`GET /api/session` and sends it back in the `X-KOS-Write-Token` header. The
shell reads the same token for the runtime file that `kos mcp` uses (see
[Agents and the runtime file](#agents-and-the-runtime-file)). See
"Local interface write API" in [`docs/architecture.md`](../docs/architecture.md).

## Referat plugin

[Referat](https://github.com/sockulags/referat) records meetings and writes
their minutes on this computer. The Referat menu, enabled while a knowledge
base is open, has two items:

- **Record Meeting with Referat** starts the installed Referat, or does
  nothing when it is already running (Referat has no single-instance lock).
- **Import Meeting from Referat…** opens the import window.

The import window lists Referat's meetings, newest first. Meetings Referat is
still recording or processing are shown but cannot be imported, and meeting
folders Referat's files could not be read from are listed with the reason.
Choosing a finished meeting shows a preview: which minutes to import when
Referat wrote several (the newest "Protokoll" is the default), the decisions
found in them with a checkbox each, the target project (the one shown in the
main window, else the one Referat was last started from) and folder (default
`meeting-notes`), and a checkbox for the full transcript, which is off by
default. Importing creates:

- One active note titled after the meeting, with the date, duration, and
  meeting reference, then the minutes' sections under Summary, Decisions,
  Action items, and Open questions. Sections with other headings are kept
  under their own heading; the transcript is added only when ticked. Voice
  embeddings are never read.
- One draft decision per ticked item under the decisions heading, linked to
  the note with `related`. Decisions are drafts because of the approval
  policy; they govern nothing until someone accepts them.

The minutes are Markdown written by a language model, so sections are found
by heading name at any heading level (or a line that is only bold text):
Sammanfattning/Summary, Beslut/Decisions, Actionpunkter/Action items, and
Öppna frågor/Open questions, plus a few common variants. Each top-level list
item under the decisions heading is one decision, with nested items kept in
its body; without a list, each sub-heading or paragraph is one. A placeholder
such as "Inga beslut fattades." gives no decisions, and minutes without a
decisions heading import no decisions; the preview says which case applies.

Every record carries provenance `referat-meeting` with reference
`referat:<meeting id>` (see "Local interface write API" in
[`docs/architecture.md`](../docs/architecture.md)). Ids are the meeting's
local date plus words from the title or decision text, such as
`2026-09-21-planeringsmote-vecka-39`. An id that is taken gets a `-2`, `-3`,
... suffix, both when checked beforehand and when the core answers
`duplicate`; nothing is overwritten. Before previewing and again before
writing, the plugin looks for records that already carry the meeting's
reference; a meeting imported before is offered as "Already imported" with
links to the records instead of being imported twice.

All writes go through `POST /api/records` of the running core, one record at
a time, so each is validated like any interface write and auto-committed
when the knowledge base is a Git repository. The note is written first; if it
fails, nothing else is written. If a decision fails, the result lists exactly
which records were created, which were not and why, and offers to retry the
failed decisions against the same note.

The plugin lives in `src/main/plugins/referat/`, with its page
`src/renderer/referat.html` and preload script `src/preload/referat.ts`. It
uses [referat-sdk](https://github.com/sockulags/referat-sdk), pinned to
`v0.1.0` and bundled into the main process. The SDK only reads Referat's
data folder and runs in the main process; the import window's preload
exposes eight calls (context, list meetings, preview, import, retry, launch,
open a record, close), which the main process answers only for that window.
Nothing passed to the window names a file path. The core and the reader have
no Referat code. When Referat is not installed, the window says so and the
rest of the app is unchanged.

## Development hooks

- `KOS_DESKTOP_WORKSPACE=PATH` opens that knowledge base at startup.
- `KOS_DESKTOP_USER_DATA=PATH` uses a separate user-data folder, so a test run
  does not touch your recent list or settings.
- `MAIN_VITE_KOS_UPDATE_TEST_FEED=URL`, set at build time, points the updater
  at a local test server (see [Testing an update locally](#testing-an-update-locally)).
- `REFERAT_USER_DATA=PATH` makes the Referat plugin read meetings from that
  folder (it holds `meetings/`) instead of the installed Referat's, for
  example a synthetic data folder. Referat itself honours the same variable.
