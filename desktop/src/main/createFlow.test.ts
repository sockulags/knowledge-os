import { describe, expect, it, vi } from 'vitest'
import { createKnowledgeBase, type CreateSteps } from './createFlow'
import type { InitResult } from './pythonCore'

function steps(overrides: Partial<CreateSteps> = {}): CreateSteps & { log: string[] } {
  const log: string[] = []
  return {
    log,
    showCreating: vi.fn(async (folder: string) => {
      log.push(`creating ${folder}`)
      return 1
    }),
    isCurrent: () => true,
    python: vi.fn(async () => {
      log.push('python')
      return 'python.exe'
    }),
    init: vi.fn(async (_executable: string, folder: string): Promise<InitResult> => {
      log.push('init')
      return { ok: true, root: folder }
    }),
    open: vi.fn(async (root: string) => {
      log.push(`open ${root}`)
    }),
    fail: vi.fn((failure) => {
      log.push(`fail ${failure.message}`)
    }),
    ...overrides
  }
}

describe('createKnowledgeBase', () => {
  it('shows that it is creating before looking for Python or running kos init', async () => {
    const flow = steps()
    await createKnowledgeBase('C:/kb', flow)
    expect(flow.log).toEqual(['creating C:/kb', 'python', 'init', 'open C:/kb'])
  })

  it('shows the creating state at once, while Python is still being found', async () => {
    let finishPython: (executable: string | null) => void = () => undefined
    const flow = steps({ python: () => new Promise((resolve) => (finishPython = resolve)) })
    const done = createKnowledgeBase('C:/kb', flow)
    await Promise.resolve()
    expect(flow.showCreating).toHaveBeenCalledWith('C:/kb')
    expect(flow.init).not.toHaveBeenCalled()
    finishPython(null)
    await done
    expect(flow.init).not.toHaveBeenCalled()
  })

  it('reports a failed kos init instead of opening anything', async () => {
    const failure = { error: 'create-failed' as const, message: 'not empty', detail: '' }
    const flow = steps({ init: async () => ({ ok: false, failure }) })
    await createKnowledgeBase('C:/kb', flow)
    expect(flow.fail).toHaveBeenCalledWith(failure)
    expect(flow.open).not.toHaveBeenCalled()
  })

  it('stops when another open took over the window meanwhile', async () => {
    const flow = steps({ isCurrent: () => false })
    await createKnowledgeBase('C:/kb', flow)
    expect(flow.init).not.toHaveBeenCalled()
    expect(flow.open).not.toHaveBeenCalled()
  })
})
