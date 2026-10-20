// The main process's diagnostics, written to `main.log` in the logs folder
// under Electron's user-data folder so the installed app, which has no
// console, still leaves a trace (Help → Open Log Folder). The file is rotated
// at about 1 MB and three files are kept: main.log, main.log.1, main.log.2.
// Every line also goes to the console, as before. Only Node built-ins are
// used so the module is unit-testable.

import { appendFileSync, existsSync, mkdirSync, renameSync, rmSync, statSync } from 'fs'
import { join } from 'path'
import { format } from 'util'

export const LOG_FILE = 'main.log'
export const MAX_LOG_BYTES = 1024 * 1024
/** main.log plus this many older files. */
export const KEPT_OLD_LOGS = 2

export type LogLevel = 'info' | 'warn' | 'error'

export interface LogFileOptions {
  dir: string
  maxBytes?: number
  keptOld?: number
}

/** A log file that starts over in a fresh file once it would pass `maxBytes`. */
export class RotatingLogFile {
  readonly dir: string
  readonly path: string
  private readonly maxBytes: number
  private readonly keptOld: number

  constructor(options: LogFileOptions) {
    this.dir = options.dir
    this.path = join(options.dir, LOG_FILE)
    this.maxBytes = options.maxBytes ?? MAX_LOG_BYTES
    this.keptOld = options.keptOld ?? KEPT_OLD_LOGS
  }

  /** Appends one line. Synchronous, so a line written just before a crash is kept. */
  write(line: string): void {
    mkdirSync(this.dir, { recursive: true })
    const text = line.endsWith('\n') ? line : `${line}\n`
    const size = this.size()
    if (size > 0 && size + Buffer.byteLength(text) > this.maxBytes) this.rotate()
    appendFileSync(this.path, text, 'utf-8')
  }

  private size(): number {
    try {
      return statSync(this.path).size
    } catch {
      return 0
    }
  }

  /** main.log becomes main.log.1, main.log.1 becomes main.log.2, and the oldest is dropped. */
  private rotate(): void {
    const old = (index: number): string => `${this.path}.${index}`
    if (this.keptOld === 0) {
      rmSync(this.path, { force: true })
      return
    }
    rmSync(old(this.keptOld), { force: true })
    for (let index = this.keptOld - 1; index >= 1; index--) {
      if (existsSync(old(index))) renameSync(old(index), old(index + 1))
    }
    renameSync(this.path, old(1))
  }
}

/** One log line: time, level, and the arguments formatted as console.log would. */
export function formatLine(level: LogLevel, args: unknown[], now = new Date()): string {
  return `${now.toISOString()} ${level.toUpperCase().padEnd(5)} ${format(...args)}`
}

let file: RotatingLogFile | null = null

/** Starts writing to `dir`; before this, lines only go to the console. */
export function initLog(dir: string): void {
  file = new RotatingLogFile({ dir })
}

/** The folder the log is written to, or null before `initLog`. */
export function logDir(): string | null {
  return file?.dir ?? null
}

function write(level: LogLevel, args: unknown[]): void {
  if (level === 'info') console.log(...args)
  else if (level === 'warn') console.warn(...args)
  else console.error(...args)
  if (file === null) return
  try {
    file.write(formatLine(level, args))
  } catch (error) {
    // A full disk or a locked file must never take the app down.
    console.error('could not write the log file', error)
  }
}

export const log = {
  info: (...args: unknown[]): void => write('info', args),
  warn: (...args: unknown[]): void => write('warn', args),
  error: (...args: unknown[]): void => write('error', args)
}
