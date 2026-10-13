// Checks that a packaged app can load everything its main process requires
// at run time. `node scripts/check-packaged.mjs [app.asar]` (default: the
// asar in dist/win-unpacked) extracts the archive to a temporary folder,
// finds every bare `require("…")` in out/main, and loads each one from inside
// the extracted app, the way the packaged main process resolves it.
//
// Run by the Release workflow after `npm run dist` and before anything is
// published: 0.8.0 shipped a main process that required the ACP SDK, whose
// peer dependency zod electron-builder left out, so the app did not start.

import { extractAll } from '@electron/asar'
import { mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from 'fs'
import { builtinModules, createRequire } from 'module'
import { tmpdir } from 'os'
import { join, resolve } from 'path'
import { pathToFileURL } from 'url'

const asar = resolve(process.argv[2] ?? 'dist/win-unpacked/resources/app.asar')
const root = mkdtempSync(join(tmpdir(), 'kos-packaged-'))

let failed = 0
try {
  extractAll(asar, root)
  const main = join(root, 'out', 'main')
  const wanted = new Set()
  const scripts = readdirSync(main, { recursive: true })
    .map((name) => join(main, String(name)))
    .filter((path) => path.endsWith('.js') && statSync(path).isFile())
  for (const file of scripts) {
    for (const match of readFileSync(file, 'utf8').matchAll(
      /\brequire\(\s*["']([^"'.][^"']*)["']\s*\)/g
    )) {
      wanted.add(match[1])
    }
  }
  const builtins = new Set(builtinModules)
  const load = createRequire(join(main, 'index.js'))
  for (const name of [...wanted].sort()) {
    if (name === 'electron' || name.startsWith('node:') || builtins.has(name)) continue
    try {
      try {
        load(name)
      } catch (error) {
        if (error?.code !== 'ERR_REQUIRE_ESM') throw error
        await import(pathToFileURL(load.resolve(name)).href)
      }
      console.log(`ok       ${name}`)
    } catch (error) {
      failed += 1
      console.error(`MISSING  ${name}: ${String(error?.message ?? error).split('\n')[0]}`)
    }
  }
} finally {
  rmSync(root, { recursive: true, force: true })
}

if (failed > 0) {
  console.error(
    `${failed} run-time dependenc${failed === 1 ? 'y' : 'ies'} of the main process cannot be loaded from ${asar}.`
  )
  process.exit(1)
}
console.log(`Every run-time dependency of the main process loads from ${asar}.`)
