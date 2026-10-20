// Stopping a process together with everything it started. On Windows a
// launcher (a venv's python.exe, the `py` launcher, an agent's Node adapter)
// runs the real work as child processes that outlive a plain kill and keep
// their working folder locked. Only Node built-ins, so it is unit-testable.

import { spawnSync } from 'child_process'

/**
 * Kill a process and all of its descendants, synchronously. Safe on an exited
 * pid. On POSIX the process must have been spawned `detached`, so it leads its
 * own process group; otherwise only the process itself is stopped.
 */
export function killProcessTree(pid: number, platform: NodeJS.Platform = process.platform): void {
  if (platform === 'win32') {
    spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' })
    return
  }
  try {
    process.kill(-pid, 'SIGTERM')
  } catch {
    try {
      process.kill(pid, 'SIGTERM')
    } catch {
      // Already gone.
    }
  }
}
