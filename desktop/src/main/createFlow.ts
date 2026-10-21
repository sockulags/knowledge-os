// Creating a knowledge base from the start page or the File menu, kept apart
// from Electron so it is unit-testable. Finding Python and running `kos init`
// can take many seconds, so the start page says a knowledge base is being
// created before either begins, and goes back to the error screen when it fails.

import type { CoreFailure, InitResult } from './pythonCore'

export interface CreateSteps {
  /** Leave what the window shows and say the knowledge base in `folder` is being created. Resolves to a token for `isCurrent`. */
  showCreating: (folder: string) => Promise<number>
  /** False once something else (another open or create) has taken over the window. */
  isCurrent: (token: number) => boolean
  /** The Python interpreter, or null after it has shown why there is none. */
  python: () => Promise<string | null>
  init: (executable: string, folder: string) => Promise<InitResult>
  open: (root: string) => Promise<void>
  fail: (failure: CoreFailure) => void
}

export async function createKnowledgeBase(folder: string, steps: CreateSteps): Promise<void> {
  const token = await steps.showCreating(folder)
  const executable = await steps.python()
  if (executable === null || !steps.isCurrent(token)) return
  const result = await steps.init(executable, folder)
  if (!steps.isCurrent(token)) return
  if (!result.ok) {
    steps.fail(result.failure)
    return
  }
  await steps.open(result.root)
}
