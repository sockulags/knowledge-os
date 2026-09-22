// Which Python interpreters may run the Knowledge OS core, in the order they
// are tried. Pure apart from the injected `exists` check so it is unit-testable.

import { join } from 'path'

export interface InterpreterCandidate {
  /** The executable to spawn. */
  command: string
  /** Arguments that precede everything else, e.g. ['-3.11'] for the `py` launcher. */
  args: string[]
  /** Where the candidate came from, for error messages. */
  source: string
}

export interface CandidateOptions {
  env: NodeJS.ProcessEnv
  /** Root of a Knowledge OS checkout, or null when the shell does not run from one. */
  repoRoot: string | null
  platform: NodeJS.Platform
  exists: (path: string) => boolean
}

export function venvPython(repoRoot: string, platform: NodeJS.Platform): string {
  return platform === 'win32'
    ? join(repoRoot, '.venv', 'Scripts', 'python.exe')
    : join(repoRoot, '.venv', 'bin', 'python')
}

/**
 * KOS_PYTHON, when set, is the only candidate: an explicit choice that does not
 * work is reported instead of silently replaced by another interpreter.
 * Otherwise the checkout's .venv (when it exists) comes first, then the
 * interpreters found on PATH.
 */
export function interpreterCandidates(options: CandidateOptions): InterpreterCandidate[] {
  const { env, repoRoot, platform, exists } = options
  const explicit = env['KOS_PYTHON']?.trim()
  if (explicit) {
    return [{ command: explicit, args: [], source: 'KOS_PYTHON' }]
  }

  const candidates: InterpreterCandidate[] = []
  if (repoRoot !== null) {
    const venv = venvPython(repoRoot, platform)
    if (exists(venv)) {
      candidates.push({ command: venv, args: [], source: 'repository .venv' })
    }
  }
  if (platform === 'win32') {
    candidates.push({ command: 'py', args: ['-3.11'], source: 'py -3.11' })
  } else {
    candidates.push({ command: 'python3.11', args: [], source: 'python3.11' })
    candidates.push({ command: 'python3', args: [], source: 'python3' })
  }
  candidates.push({ command: 'python', args: [], source: 'python' })
  return candidates
}

/**
 * The Knowledge OS checkout the shell runs from, if any: the parent of the
 * desktop/ folder, recognized by its knowledge_os package and pyproject.toml.
 */
export function findRepoRoot(appPath: string, exists: (path: string) => boolean): string | null {
  const candidate = join(appPath, '..')
  const isCheckout =
    exists(join(candidate, 'pyproject.toml')) &&
    exists(join(candidate, 'knowledge_os', 'reader', '__init__.py'))
  return isCheckout ? candidate : null
}
