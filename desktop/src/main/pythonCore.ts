// Runs the Knowledge OS Python core: finds a working interpreter, creates
// workspaces with `kos init`, and starts and stops the read-only reader server
// (`python -m knowledge_os.reader`). Only Node built-ins are imported, never
// 'electron', so the pure parts are unit-testable.
//
// No orphans: the core is spawned with --exit-on-stdin-eof and its stdin is a
// pipe this process keeps open, so the core exits by itself when this process
// dies in any way, including a crash that skips every cleanup handler. Normal
// stops kill the whole process tree, because on Windows a venv's python.exe
// and the `py` launcher each run the real interpreter as a child process.

import { spawn, spawnSync, type ChildProcess } from 'child_process'
import { tmpdir } from 'os'
import { delimiter } from 'path'
import type { ErrorKind } from '../shared/types'
import { findFreePort } from './portFinder'
import type { InterpreterCandidate } from './pythonInterpreter'

const HOST = '127.0.0.1'
const OUTPUT_LIMIT = 16_000
const PROBE_TIMEOUT_MS = 30_000
const HEALTH_TIMEOUT_MS = 30_000
const PORT_ATTEMPTS = 3

const PROBE_SCRIPT = [
  'import sys',
  'if sys.version_info < (3, 11): sys.exit("Python 3.11 or newer is required, found " + sys.version.split()[0])',
  'import knowledge_os.reader.app, uvicorn',
  'print(sys.executable)'
].join('\n')

export interface CoreFailure {
  error: ErrorKind
  message: string
  detail: string
}

/** Environment for every Python child: the checkout (if any) on PYTHONPATH, UTF-8 I/O. */
export function pythonEnvironment(
  base: NodeJS.ProcessEnv,
  repoRoot: string | null
): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {
    ...base,
    PYTHONUNBUFFERED: '1',
    PYTHONIOENCODING: 'utf-8',
    PYTHONUTF8: '1'
  }
  if (repoRoot !== null) {
    env['PYTHONPATH'] = base['PYTHONPATH']
      ? `${repoRoot}${delimiter}${base['PYTHONPATH']}`
      : repoRoot
  }
  return env
}

class OutputTail {
  private text = ''
  append(chunk: Buffer | string): void {
    this.text = (this.text + chunk.toString()).slice(-OUTPUT_LIMIT)
  }
  toString(): string {
    return this.text.trim()
  }
}

interface RunResult {
  code: number | null
  stdout: string
  stderr: string
  spawnError: string | null
}

function run(
  command: string,
  args: string[],
  env: NodeJS.ProcessEnv,
  timeoutMs: number
): Promise<RunResult> {
  return new Promise((resolve) => {
    const stdout = new OutputTail()
    const stderr = new OutputTail()
    let child: ChildProcess
    try {
      child = spawn(command, args, { cwd: tmpdir(), env, windowsHide: true })
    } catch (error) {
      resolve({ code: null, stdout: '', stderr: '', spawnError: String(error) })
      return
    }
    const timer = setTimeout(() => {
      if (child.pid !== undefined) killProcessTree(child.pid)
    }, timeoutMs)
    child.stdout?.on('data', (chunk) => stdout.append(chunk))
    child.stderr?.on('data', (chunk) => stderr.append(chunk))
    child.on('error', (error) => {
      clearTimeout(timer)
      resolve({ code: null, stdout: '', stderr: '', spawnError: error.message })
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      resolve({ code, stdout: stdout.toString(), stderr: stderr.toString(), spawnError: null })
    })
  })
}

function lastLine(text: string): string {
  const lines = text.split(/\r?\n/).filter((line) => line.trim() !== '')
  return lines.length > 0 ? lines[lines.length - 1].trim() : ''
}

export type ResolveResult = { ok: true; executable: string } | { ok: false; failure: CoreFailure }

/**
 * Try each candidate in order and return the absolute path of the first
 * interpreter that is Python 3.11+ and can import the reader and its
 * dependencies. The core is then spawned through that path directly.
 */
export async function resolvePython(
  candidates: InterpreterCandidate[],
  env: NodeJS.ProcessEnv
): Promise<ResolveResult> {
  const attempts: string[] = []
  for (const candidate of candidates) {
    const label = [candidate.command, ...candidate.args].join(' ')
    const result = await run(
      candidate.command,
      [...candidate.args, '-c', PROBE_SCRIPT],
      env,
      PROBE_TIMEOUT_MS
    )
    if (result.code === 0 && lastLine(result.stdout) !== '') {
      return { ok: true, executable: lastLine(result.stdout) }
    }
    const reason =
      result.spawnError ??
      (lastLine(result.stderr) || `exited with code ${result.code ?? 'unknown'}`)
    attempts.push(`${candidate.source} (${label}): ${reason}`)
  }
  return {
    ok: false,
    failure: {
      error: 'python-missing',
      message:
        'No usable Python was found. Knowledge OS needs Python 3.11 or newer with the reader ' +
        'dependencies: run `pip install -e ".[reader]"` in the repository\'s .venv, or set ' +
        'KOS_PYTHON to an interpreter that has them.',
      detail: attempts.join('\n')
    }
  }
}

export type InitResult = { ok: true; root: string } | { ok: false; failure: CoreFailure }

/** Create a workspace with `kos init FOLDER --json`. */
export async function initWorkspace(
  executable: string,
  folder: string,
  env: NodeJS.ProcessEnv
): Promise<InitResult> {
  const result = await run(
    executable,
    ['-m', 'knowledge_os', 'init', folder, '--json'],
    env,
    PROBE_TIMEOUT_MS
  )
  if (result.code === 0) {
    try {
      const parsed = JSON.parse(result.stdout) as { root?: unknown }
      if (typeof parsed.root === 'string') return { ok: true, root: parsed.root }
    } catch {
      // Reported below.
    }
  }
  const message = lastLine(result.stderr).replace(/^ERROR:\s*/, '') || 'kos init failed.'
  return {
    ok: false,
    failure: {
      error: 'create-failed',
      message: `Could not create a knowledge base in ${folder}: ${message}`,
      detail: [result.spawnError, result.stderr, result.stdout].filter(Boolean).join('\n')
    }
  }
}

/** Why a core that exited before becoming healthy failed, from its output. */
export function classifyEarlyExit(
  output: string,
  code: number | null
): CoreFailure & { retryPort: boolean } {
  if (/errno (10048|98|48)\b|address already in use/i.test(output)) {
    return {
      error: 'early-exit',
      message: 'The Python core could not bind its local port.',
      detail: output,
      retryPort: true
    }
  }
  const errors = output
    .split(/\r?\n/)
    .filter((line) => line.startsWith('ERROR: '))
    .map((line) => line.slice('ERROR: '.length).trim())
  if (errors.length > 0) {
    return {
      error: 'invalid-workspace',
      message: `This folder cannot be opened as a knowledge base: ${errors.join(' ')}`,
      detail: output,
      retryPort: false
    }
  }
  return {
    error: 'early-exit',
    message: `The Python core stopped while starting (exit code ${code ?? 'unknown'}).`,
    detail: output,
    retryPort: false
  }
}

/** Kill a process and all of its descendants, synchronously. Safe on an exited pid. */
export function killProcessTree(pid: number, platform: NodeJS.Platform = process.platform): void {
  if (platform === 'win32') {
    spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' })
    return
  }
  try {
    // The core is spawned as a process-group leader on POSIX.
    process.kill(-pid, 'SIGTERM')
  } catch {
    try {
      process.kill(pid, 'SIGTERM')
    } catch {
      // Already gone.
    }
  }
}

export type StartResult = { ok: true; core: CoreProcess } | { ok: false; failure: CoreFailure }

export class CoreProcess {
  private exited = false
  private stopping = false
  private readonly exitPromise: Promise<void>

  private constructor(
    private readonly child: ChildProcess,
    private readonly output: OutputTail,
    readonly url: string,
    readonly name: string
  ) {
    this.exitPromise = new Promise((resolve) => {
      if (child.exitCode !== null || child.signalCode !== null) {
        this.exited = true
        resolve()
        return
      }
      child.once('exit', () => {
        this.exited = true
        resolve()
      })
    })
  }

  get pid(): number | undefined {
    return this.child.pid
  }

  /** Called once if the core exits while it is still in use. */
  onUnexpectedExit(callback: (detail: string) => void): void {
    this.child.once('exit', (code) => {
      if (!this.stopping) callback(`exit code ${code ?? 'unknown'}\n${this.output.toString()}`)
    })
  }

  /** Kill the process tree synchronously; used from quit and crash handlers. */
  stopSync(): void {
    this.stopping = true
    if (this.exited || this.child.pid === undefined) return
    this.child.stdin?.destroy()
    killProcessTree(this.child.pid)
  }

  async stop(): Promise<void> {
    this.stopSync()
    await Promise.race([this.exitPromise, new Promise((resolve) => setTimeout(resolve, 5_000))])
  }

  static async start(
    executable: string,
    root: string,
    env: NodeJS.ProcessEnv,
    platform: NodeJS.Platform = process.platform
  ): Promise<StartResult> {
    let failure: CoreFailure | null = null
    for (let attempt = 0; attempt < PORT_ATTEMPTS; attempt++) {
      const port = await findFreePort(HOST)
      const url = `http://${HOST}:${port}`
      const output = new OutputTail()
      const child = spawn(
        executable,
        [
          '-m',
          'knowledge_os.reader',
          '--root',
          root,
          '--host',
          HOST,
          '--port',
          String(port),
          '--exit-on-stdin-eof'
        ],
        {
          // Never the workspace or the checkout: the core must not depend on cwd,
          // and on Windows a child's cwd holds that folder open.
          cwd: tmpdir(),
          env,
          stdio: ['pipe', 'pipe', 'pipe'],
          windowsHide: true,
          detached: platform !== 'win32'
        }
      )
      child.stdout?.on('data', (chunk) => output.append(chunk))
      child.stderr?.on('data', (chunk) => output.append(chunk))
      // A closed stdin pipe raises EPIPE on the (unused) write side; ignore it.
      child.stdin?.on('error', () => undefined)

      const health = await waitForHealth(url, child)
      if (health.ok) {
        return { ok: true, core: new CoreProcess(child, output, url, health.name) }
      }
      if (child.pid !== undefined) killProcessTree(child.pid, platform)
      if (health.timedOut) {
        failure = {
          error: 'early-exit',
          message: `The Python core did not answer on ${url} within ${HEALTH_TIMEOUT_MS / 1000} seconds.`,
          detail: output.toString()
        }
        break
      }
      const classified = classifyEarlyExit(output.toString(), health.code)
      failure = { error: classified.error, message: classified.message, detail: classified.detail }
      if (!classified.retryPort) break
    }
    return { ok: false, failure: failure as CoreFailure }
  }
}

type HealthResult =
  { ok: true; name: string } | { ok: false; timedOut: boolean; code: number | null }

async function waitForHealth(url: string, child: ChildProcess): Promise<HealthResult> {
  let exit: { code: number | null } | null = null
  const exited = new Promise<void>((resolve) => {
    child.once('exit', (code) => {
      exit = { code }
      resolve()
    })
    child.once('error', () => {
      exit = { code: null }
      resolve()
    })
  })
  // Wait for 'close' as well so the output of an early exit is complete.
  const closed = new Promise<void>((resolve) => child.once('close', () => resolve()))

  const deadline = Date.now() + HEALTH_TIMEOUT_MS
  while (Date.now() < deadline) {
    if (exit !== null) {
      await Promise.race([closed, new Promise((resolve) => setTimeout(resolve, 1_000))])
      return { ok: false, timedOut: false, code: (exit as { code: number | null }).code }
    }
    try {
      const response = await fetch(`${url}/api/workspace`, { signal: AbortSignal.timeout(1_000) })
      if (response.ok) {
        const body = (await response.json()) as { name?: unknown }
        return { ok: true, name: typeof body.name === 'string' ? body.name : '' }
      }
    } catch {
      // Not listening yet.
    }
    await Promise.race([exited, new Promise((resolve) => setTimeout(resolve, 150))])
  }
  return { ok: false, timedOut: true, code: null }
}
