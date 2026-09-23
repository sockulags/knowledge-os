import { spawnSync } from 'child_process'
import {
  existsSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync
} from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  currentUserSid,
  removeRuntimeFile,
  runtimeFilePath,
  writeRuntimeFile,
  type RuntimeInfo
} from './runtimeFile'

const info: RuntimeInfo = {
  port: 51234,
  writeToken: 'secret-token',
  workspaceRoot: 'D:\\notes\\my-kb',
  workspaceName: 'my-kb',
  appVersion: '0.2.0',
  corePid: 4242
}

describe('runtime file for agents', () => {
  let dir: string
  let file: string

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'kos-runtime-'))
    file = runtimeFilePath(join(dir, 'userData'))
  })

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true })
  })

  it('writes the fields kos mcp reads, in the user-data folder', () => {
    const now = new Date('2026-09-23T20:00:00Z')
    writeRuntimeFile(file, info, { restrict: () => undefined, now })
    expect(file).toBe(join(dir, 'userData', 'runtime.json'))
    expect(JSON.parse(readFileSync(file, 'utf-8'))).toEqual({
      version: 1,
      app_version: '0.2.0',
      port: 51234,
      url: 'http://127.0.0.1:51234',
      write_token: 'secret-token',
      workspace: { root: 'D:\\notes\\my-kb', name: 'my-kb' },
      core_pid: 4242,
      shell_pid: process.pid,
      written_at: '2026-09-23T20:00:00.000Z'
    })
    expect(readdirSync(join(dir, 'userData'))).toEqual(['runtime.json'])
  })

  it('rewrites the file for the next knowledge base', () => {
    writeRuntimeFile(file, info, { restrict: () => undefined })
    writeRuntimeFile(
      file,
      { ...info, workspaceName: 'other', corePid: 5151 },
      { restrict: () => undefined }
    )
    const written = JSON.parse(readFileSync(file, 'utf-8'))
    expect(written.workspace.name).toBe('other')
    expect(written.core_pid).toBe(5151)
  })

  it('restricts access before the file becomes visible and writes nothing if that fails', () => {
    const restricted: string[] = []
    writeRuntimeFile(file, info, {
      platform: 'win32',
      restrict: (path) => {
        restricted.push(path)
        expect(existsSync(file)).toBe(false)
      }
    })
    expect(restricted).toHaveLength(1)
    expect(restricted[0]).not.toBe(file)

    rmSync(file)
    expect(() =>
      writeRuntimeFile(file, info, {
        platform: 'win32',
        restrict: () => {
          throw new Error('no ACL')
        }
      })
    ).toThrow('no ACL')
    expect(readdirSync(join(dir, 'userData'))).toEqual([])
  })

  it.runIf(process.platform === 'win32')(
    'grants access on Windows to the current user only, without inherited entries',
    () => {
      writeRuntimeFile(file, info)
      const acl = spawnSync('icacls', [file], { encoding: 'utf-8', windowsHide: true }).stdout
      const entries = acl
        .split(/\r?\n/)
        .map((line) => line.replace(file, '').trim())
        .filter((line) => line !== '' && !line.startsWith('Successfully'))
      expect(entries).toHaveLength(1)
      expect(entries[0]).toMatch(/:\(F\)$/)
      expect(entries[0]).not.toMatch(/\(I\)/)
      const sid = spawnSync('icacls', [file, '/save', join(dir, 'acl.txt')], { windowsHide: true })
      expect(sid.status).toBe(0)
      const saved = readFileSync(join(dir, 'acl.txt'), 'utf16le')
      expect(saved).toContain(currentUserSid())
      expect(saved).not.toMatch(/;;;(BA|SY|WD|AU|BU)\)/)
    }
  )

  it.runIf(process.platform !== 'win32')('is readable by the owner only elsewhere', () => {
    writeRuntimeFile(file, info)
    expect(statSync(file).mode & 0o777).toBe(0o600)
  })

  it('removes the file only while it still describes this core', () => {
    writeRuntimeFile(file, info, { restrict: () => undefined })
    expect(removeRuntimeFile(file, 9999)).toBe(false)
    expect(existsSync(file)).toBe(true)
    expect(removeRuntimeFile(file, info.corePid)).toBe(true)
    expect(existsSync(file)).toBe(false)
    expect(removeRuntimeFile(file, info.corePid)).toBe(false)
  })

  it('removes a damaged file', () => {
    writeRuntimeFile(file, info, { restrict: () => undefined })
    writeFileSync(file, '{"core_pid": 42', 'utf-8')
    expect(removeRuntimeFile(file, info.corePid)).toBe(true)
    expect(existsSync(file)).toBe(false)
  })
})
