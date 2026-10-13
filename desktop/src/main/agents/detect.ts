// Finding an agent's own program on this computer, for providers' detect().
// Pure apart from the injected file checks and the version probe, so it is
// unit-testable.

import { execFile } from 'child_process'
import { existsSync, statSync } from 'fs'
import { delimiter, join } from 'path'

const VERSION_TIMEOUT_MS = 10_000

export interface PathLookup {
  env: NodeJS.ProcessEnv
  platform: NodeJS.Platform
  isFile?: (path: string) => boolean
}

function defaultIsFile(path: string): boolean {
  try {
    return existsSync(path) && statSync(path).isFile()
  } catch {
    return false
  }
}

/**
 * The first executable called `name` on PATH, trying Windows' extensions in
 * `preferredExtensions` order (a native `.exe` before an npm `.cmd` shim).
 */
export function findOnPath(
  name: string,
  { env, platform, isFile = defaultIsFile }: PathLookup,
  preferredExtensions: readonly string[] = ['.exe', '.cmd', '.bat']
): string | null {
  const path = env['PATH'] ?? env['Path'] ?? ''
  const directories = path
    .split(platform === 'win32' ? ';' : delimiter)
    .filter((entry) => entry.trim() !== '')
  const names =
    platform === 'win32' ? preferredExtensions.map((extension) => name + extension) : [name]
  // Every extension in one directory before the next directory, as Windows does.
  for (const directory of directories) {
    for (const candidate of names) {
      const full = join(directory.replace(/^"|"$/g, ''), candidate)
      if (isFile(full)) return full
    }
  }
  return null
}

/** `<executable> --version`'s first line, or null when it does not answer. */
export function probeVersion(executable: string, env: NodeJS.ProcessEnv): Promise<string | null> {
  return new Promise((resolve) => {
    // A .cmd shim can only run through the shell on Windows.
    const shell = /\.(cmd|bat)$/i.test(executable)
    execFile(
      shell ? `"${executable}"` : executable,
      ['--version'],
      { env, timeout: VERSION_TIMEOUT_MS, windowsHide: true, shell },
      (error, stdout) => {
        if (error) {
          resolve(null)
          return
        }
        const line = stdout.toString().trim().split(/\r?\n/)[0]?.trim()
        resolve(line ? line : null)
      }
    )
  })
}
