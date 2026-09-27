// Writes the install recipe for one ACP adapter version: every npm package in
// its dependency tree with the exact version, tarball URL, and integrity hash
// npm resolves, as src/main/agents/adapters/<name>.lock.json. The app installs
// exactly this list on demand (src/main/agents/installer.ts); nothing else is
// fetched and every tarball is checked against its hash.
//
//   node scripts/lock-adapter.mjs @agentclientprotocol/claude-agent-acp@0.81.2 dist/index.js
//
// Optional dependencies (the agents' platform binaries, hundreds of MB) are
// left out: the adapters run the agent the person installed. Needs npm.

import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const [spec, entry] = process.argv.slice(2)
if (!spec || !entry) {
  console.error('usage: node scripts/lock-adapter.mjs <package>@<version> <entry file>')
  process.exit(2)
}
const at = spec.lastIndexOf('@')
const packageName = spec.slice(0, at)
const version = spec.slice(at + 1)

const work = mkdtempSync(join(tmpdir(), 'kos-adapter-lock-'))
try {
  writeFileSync(join(work, 'package.json'), JSON.stringify({ name: 'adapter-lock', private: true }))
  execFileSync(
    process.platform === 'win32' ? 'npm.cmd' : 'npm',
    [
      'install',
      '--package-lock-only',
      '--ignore-scripts',
      '--no-audit',
      '--no-fund',
      '--save-exact',
      spec
    ],
    { cwd: work, stdio: 'inherit', shell: process.platform === 'win32' }
  )
  const lock = JSON.parse(readFileSync(join(work, 'package-lock.json'), 'utf8'))
  const packages = Object.entries(lock.packages)
    .filter(([path, info]) => path !== '' && !info.optional && !info.link)
    .map(([path, info]) => {
      if (!info.resolved || !info.integrity?.startsWith('sha512-')) {
        throw new Error(`${path} has no tarball or sha512 integrity in the lock`)
      }
      return { path, version: info.version, resolved: info.resolved, integrity: info.integrity }
    })
    .sort((a, b) => a.path.localeCompare(b.path))
  const main = packages.find((item) => item.path === `node_modules/${packageName}`)
  if (!main || main.version !== version) throw new Error(`${spec} is not in the resolved tree`)
  const out = join(
    dirname(fileURLToPath(import.meta.url)),
    '..',
    'src',
    'main',
    'agents',
    'adapters',
    `${packageName.split('/').pop()}.lock.json`
  )
  writeFileSync(out, JSON.stringify({ packageName, version, entry, packages }, null, 2) + '\n')
  console.log(`wrote ${out}: ${packages.length} packages`)
} finally {
  rmSync(work, { recursive: true, force: true })
}
