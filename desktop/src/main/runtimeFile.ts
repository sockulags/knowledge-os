// The runtime file that lets `kos mcp` (the MCP server for agents) find the
// running core: while a knowledge base is open, `runtime.json` in the
// user-data folder names the core's port, its per-process write token, the
// open knowledge base, the app version, and the core's process id. It is
// rewritten when another knowledge base is opened and removed when the core
// stops. Only Node built-ins are imported, never 'electron', so the module is
// unit-testable.
//
// The file holds the write token, so only the current user may read it: on
// Windows it gets an access list with the current user as its only entry
// (inheritance removed, set with icacls before the file is moved into
// place); elsewhere it is created with mode 0600. If the access list cannot
// be set, the file is not written at all and agents report that the app is
// not open.

import { spawnSync } from 'child_process'
import {
  chmodSync,
  mkdirSync,
  readFileSync,
  renameSync,
  rmSync,
  unlinkSync,
  writeFileSync
} from 'fs'
import { dirname, join } from 'path'

export const RUNTIME_FILE_NAME = 'runtime.json'

export interface RuntimeInfo {
  port: number
  writeToken: string
  workspaceRoot: string
  workspaceName: string
  appVersion: string
  corePid: number
}

export function runtimeFilePath(userData: string): string {
  return join(userData, RUNTIME_FILE_NAME)
}

/** The file's JSON; `kos mcp` reads exactly these fields (knowledge_os/agent_access/runtime.py). */
export function runtimeJson(info: RuntimeInfo, now: Date = new Date()): Record<string, unknown> {
  return {
    version: 1,
    app_version: info.appVersion,
    port: info.port,
    url: `http://127.0.0.1:${info.port}`,
    write_token: info.writeToken,
    workspace: { root: info.workspaceRoot, name: info.workspaceName },
    core_pid: info.corePid,
    shell_pid: process.pid,
    written_at: now.toISOString()
  }
}

let cachedSid: string | null = null

/** The current user's SID, from `whoami /user`. */
export function currentUserSid(): string {
  if (cachedSid !== null) return cachedSid
  const result = spawnSync('whoami', ['/user', '/fo', 'csv', '/nh'], {
    encoding: 'utf-8',
    windowsHide: true
  })
  const match = /"(S-1-[0-9-]+)"/.exec(result.stdout ?? '')
  if (result.status !== 0 || match === null) {
    throw new Error(`could not read the current user's SID: ${result.stderr || result.stdout}`)
  }
  cachedSid = match[1]
  return cachedSid
}

/** Remove inherited access and grant full control to the current user only. */
export function restrictToCurrentUser(file: string): void {
  const result = spawnSync(
    'icacls',
    [file, '/inheritance:r', '/grant:r', `*${currentUserSid()}:F`],
    { encoding: 'utf-8', windowsHide: true }
  )
  if (result.status !== 0) {
    throw new Error(`icacls failed: ${(result.stdout ?? '') + (result.stderr ?? '')}`.trim())
  }
}

export interface WriteOptions {
  platform?: NodeJS.Platform
  restrict?: (file: string) => void
  now?: Date
}

/** Write the file through a private temporary file, so no reader ever sees it half written or readable by others. */
export function writeRuntimeFile(
  file: string,
  info: RuntimeInfo,
  options: WriteOptions = {}
): void {
  const platform = options.platform ?? process.platform
  const restrict = options.restrict ?? restrictToCurrentUser
  mkdirSync(dirname(file), { recursive: true })
  const temporary = `${file}.${process.pid}.tmp`
  rmSync(temporary, { force: true })
  try {
    writeFileSync(temporary, JSON.stringify(runtimeJson(info, options.now), null, 2), {
      encoding: 'utf-8',
      mode: 0o600,
      flag: 'wx'
    })
    if (platform === 'win32') restrict(temporary)
    else chmodSync(temporary, 0o600)
    renameSync(temporary, file)
  } catch (error) {
    rmSync(temporary, { force: true })
    throw error
  }
}

/**
 * Remove the file if it still describes the core with `corePid`. A file that
 * another app instance has since rewritten for its own core is left alone; an
 * unreadable or damaged one is removed.
 */
export function removeRuntimeFile(file: string, corePid: number): boolean {
  let parsed: unknown
  try {
    parsed = JSON.parse(readFileSync(file, 'utf-8'))
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return false
    parsed = null
  }
  const owner =
    typeof parsed === 'object' && parsed !== null
      ? (parsed as Record<string, unknown>)['core_pid']
      : undefined
  if (typeof owner === 'number' && owner !== corePid) return false
  try {
    unlinkSync(file)
    return true
  } catch {
    return false
  }
}

/** The core's write token, read the way the UI reads it: `GET /api/session` from loopback. */
export async function fetchWriteToken(url: string): Promise<string> {
  const response = await fetch(`${url}/api/session`, { signal: AbortSignal.timeout(5_000) })
  if (!response.ok) throw new Error(`GET /api/session answered ${response.status}`)
  const body = (await response.json()) as { write_token?: unknown }
  if (typeof body.write_token !== 'string' || body.write_token === '') {
    throw new Error('GET /api/session returned no write token')
  }
  return body.write_token
}
