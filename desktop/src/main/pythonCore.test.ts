import { delimiter } from 'path'
import { describe, expect, it } from 'vitest'
import { classifyEarlyExit, pythonEnvironment } from './pythonCore'

describe('classifyEarlyExit', () => {
  it('reports a workspace error printed by kos-read', () => {
    const result = classifyEarlyExit(
      'ERROR: workspace marker not found at D:\\x\\knowledge-os.toml\n',
      1
    )
    expect(result.error).toBe('invalid-workspace')
    expect(result.message).toContain('workspace marker not found')
    expect(result.retryPort).toBe(false)
  })

  it('retries with another port when the port was taken', () => {
    const output =
      "ERROR:    [Errno 10048] error while attempting to bind on address ('127.0.0.1', 5000)"
    expect(classifyEarlyExit(output, 1).retryPort).toBe(true)
    expect(classifyEarlyExit('OSError: [Errno 98] Address already in use', 1).retryPort).toBe(true)
  })

  it('falls back to a generic early exit with the output as detail', () => {
    const result = classifyEarlyExit('Traceback (most recent call last):\n  boom', 3)
    expect(result.error).toBe('early-exit')
    expect(result.message).toContain('exit code 3')
    expect(result.detail).toContain('boom')
  })
})

describe('pythonEnvironment', () => {
  it('puts the checkout first on PYTHONPATH and forces UTF-8', () => {
    const env = pythonEnvironment({ PYTHONPATH: 'existing', PATH: 'p' }, 'C:\\repo')
    expect(env['PYTHONPATH']).toBe(`C:\\repo${delimiter}existing`)
    expect(env['PYTHONIOENCODING']).toBe('utf-8')
    expect(env['PATH']).toBe('p')
  })

  it('leaves PYTHONPATH alone outside a checkout', () => {
    expect(pythonEnvironment({}, null)['PYTHONPATH']).toBeUndefined()
  })
})
