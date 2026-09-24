// Runs `kos clone URL PATH --json --cancel-on-stdin-eof` in the Python core,
// so cloning uses the same Git runner as sync (Git from PATH, no prompts,
// timeouts, process-tree kill, redacted messages). Only Node built-ins are
// imported, never 'electron', so the parsing is unit-testable.
//
// Cancelling closes the core's stdin: the core then stops Git and removes
// what the clone wrote. If it has not exited within CANCEL_GRACE_MS, the
// whole process tree is killed.

import { spawn, type ChildProcess } from 'child_process'
import { tmpdir } from 'os'
import type { CloneProgress, CloneResult } from '../shared/clone'
import { killProcessTree } from './pythonCore'

const CANCEL_GRACE_MS = 20_000
const OUTPUT_LIMIT = 16_000

/** One line of `kos clone --json` output, or null when it is not one. */
export type CloneEvent =
  | { event: 'progress'; progress: CloneProgress }
  | { event: 'done'; result: Extract<CloneResult, { ok: true }> }
  | { event: 'error'; result: Extract<CloneResult, { ok: false }> }

export function parseCloneLine(line: string): CloneEvent | null {
  let data: unknown
  try {
    data = JSON.parse(line)
  } catch {
    return null
  }
  if (data === null || typeof data !== 'object') return null
  const value = data as Record<string, unknown>
  if (value.event === 'progress') {
    const phase = value.phase
    if (phase !== 'clone' && phase !== 'check' && phase !== 'index') return null
    return {
      event: 'progress',
      progress: {
        phase,
        line: typeof value.line === 'string' ? value.line : null,
        percent: typeof value.percent === 'number' ? value.percent : null
      }
    }
  }
  if (value.event === 'done' && typeof value.root === 'string') {
    const issues = Array.isArray(value.issues)
      ? value.issues.filter(
          (issue): issue is { path: string; message: string } =>
            issue !== null &&
            typeof issue === 'object' &&
            typeof (issue as { path?: unknown }).path === 'string' &&
            typeof (issue as { message?: unknown }).message === 'string'
        )
      : []
    return {
      event: 'done',
      result: {
        ok: true,
        root: value.root,
        name: typeof value.name === 'string' ? value.name : null,
        issues,
        indexError: typeof value.index_error === 'string' ? value.index_error : null
      }
    }
  }
  if (value.event === 'error' && typeof value.error === 'string') {
    return {
      event: 'error',
      result: {
        ok: false,
        error: value.error,
        detail: typeof value.detail === 'string' ? value.detail : ''
      }
    }
  }
  return null
}

export interface CloneRun {
  result: Promise<CloneResult>
  /** Ask the core to stop; resolves once the clone has ended one way or another. */
  cancel: () => Promise<CloneResult>
}

export function startClone(
  executable: string,
  url: string,
  target: string,
  env: NodeJS.ProcessEnv,
  onProgress: (progress: CloneProgress) => void
): CloneRun {
  let child: ChildProcess
  let settled: CloneResult | null = null
  let finalEvent: CloneResult | null = null
  let stderr = ''
  let pending = ''
  let resolveResult: (result: CloneResult) => void = () => undefined
  const result = new Promise<CloneResult>((resolve) => {
    resolveResult = (value) => {
      if (settled !== null) return
      settled = value
      resolve(value)
    }
  })

  try {
    child = spawn(
      executable,
      ['-m', 'knowledge_os', 'clone', url, target, '--json', '--cancel-on-stdin-eof'],
      {
        cwd: tmpdir(),
        env,
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true
      }
    )
  } catch (error) {
    resolveResult({ ok: false, error: 'core', detail: String(error) })
    return { result, cancel: () => result }
  }

  child.stdin?.on('error', () => undefined)
  child.stdout?.setEncoding('utf8')
  child.stdout?.on('data', (chunk: string) => {
    pending += chunk
    const lines = pending.split(/\r?\n/)
    pending = lines.pop() ?? ''
    for (const line of lines) {
      const event = parseCloneLine(line)
      if (event === null) continue
      if (event.event === 'progress') onProgress(event.progress)
      else finalEvent = event.result
    }
  })
  child.stderr?.on('data', (chunk: Buffer | string) => {
    stderr = (stderr + chunk.toString()).slice(-OUTPUT_LIMIT)
  })
  child.on('error', (error) => {
    resolveResult({ ok: false, error: 'core', detail: error.message })
  })
  child.on('close', (code) => {
    const last = parseCloneLine(pending)
    if (last !== null && last.event !== 'progress') finalEvent = last.result
    resolveResult(
      finalEvent ?? {
        ok: false,
        error: 'core',
        detail: stderr.trim() || `The core stopped with exit code ${code ?? 'unknown'}.`
      }
    )
  })

  const cancel = (): Promise<CloneResult> => {
    if (settled === null) {
      child.stdin?.end()
      const timer = setTimeout(() => {
        if (child.pid !== undefined) killProcessTree(child.pid)
      }, CANCEL_GRACE_MS)
      void result.then(() => clearTimeout(timer))
    }
    return result
  }
  return { result, cancel }
}
