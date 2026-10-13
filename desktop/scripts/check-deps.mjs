// Fails fast, with a readable message, when a dependency that package.json
// declares is not installed in node_modules or does not match package-lock.json.
// Without it, a missing package surfaces later as a bundler error such as
// Rollup's `failed to resolve import "referat-sdk"`.
//
// Runs as the `predev`, `prestart`, and `prebuild` npm scripts. It reads three
// small JSON files per dependency and never touches the network, so it takes a
// few milliseconds. It is not hooked into any install lifecycle script, so
// `npm install` and `npm ci` never run it.
//
// What counts as a problem, for every name under `dependencies` and
// `devDependencies` in package.json:
// - missing: `node_modules/<name>/package.json` does not exist;
// - wrong version: package-lock.json records a different version than the
//   installed package.json;
// - wrong commit (git dependencies such as `github:owner/repo#tag`): the
//   commit package-lock.json resolves to differs from the commit npm recorded
//   in `node_modules/.package-lock.json` when it installed the package. That
//   hidden lockfile is npm's own; when it is absent the commit is not checked.

/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain JavaScript, no types to declare */

import { readFileSync } from 'fs'
import { dirname, join, resolve } from 'path'
import { fileURLToPath, pathToFileURL } from 'url'

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, 'utf8'))
  } catch {
    return null
  }
}

/**
 * The declared dependencies of the package in `dir` that are not installed as
 * package-lock.json says. Each problem is `{ name, reason }`.
 */
export function findDependencyProblems(dir) {
  const manifest = readJson(join(dir, 'package.json'))
  if (manifest === null) throw new Error(`cannot read ${join(dir, 'package.json')}`)
  const lockPackages = readJson(join(dir, 'package-lock.json'))?.packages ?? {}
  const installedPackages = readJson(join(dir, 'node_modules', '.package-lock.json'))?.packages
  const names = Object.keys({ ...manifest.dependencies, ...manifest.devDependencies }).sort()
  const problems = []
  for (const name of names) {
    const key = `node_modules/${name}`
    const installed = readJson(join(dir, key, 'package.json'))
    if (installed === null) {
      problems.push({ name, reason: 'not installed' })
      continue
    }
    const locked = lockPackages[key]
    if (locked === undefined) continue
    if (locked.version !== undefined && installed.version !== locked.version) {
      problems.push({
        name,
        reason: `installed ${installed.version}, package-lock.json wants ${locked.version}`
      })
      continue
    }
    const wanted = locked.resolved
    if (typeof wanted === 'string' && wanted.startsWith('git+') && installedPackages) {
      const have = installedPackages[key]?.resolved
      if (have !== undefined && have !== wanted) {
        problems.push({
          name,
          reason: `installed from ${have}, package-lock.json wants ${wanted}`
        })
      }
    }
  }
  return problems
}

/** The message printed when `problems` is not empty. */
export function formatProblems(problems) {
  const lines = problems.map((problem) => `  - ${problem.name}: ${problem.reason}`)
  return [
    'Some dependencies of the desktop app are missing or out of date:',
    ...lines,
    '',
    'Run `npm install` in desktop/ and try again.'
  ].join('\n')
}

const invokedDirectly =
  process.argv[1] !== undefined && import.meta.url === pathToFileURL(resolve(process.argv[1])).href

if (invokedDirectly) {
  const desktop = join(dirname(fileURLToPath(import.meta.url)), '..')
  const problems = findDependencyProblems(desktop)
  if (problems.length > 0) {
    console.error(formatProblems(problems))
    process.exit(1)
  }
}
