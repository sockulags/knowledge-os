import { mkdtempSync, readdirSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, describe, expect, it } from 'vitest'
import { ConversationError, ConversationStore, MAX_CONVERSATIONS } from './conversations'

const folders: string[] = []
afterEach(() => {
  while (folders.length > 0) rmSync(folders.pop()!, { recursive: true, force: true })
})

function store(): ConversationStore {
  const root = mkdtempSync(join(tmpdir(), 'kos-conversations-'))
  folders.push(root)
  return new ConversationStore(root)
}

function conversation(
  id: string,
  updatedAt: string,
  extra: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id,
    title: `Conversation ${id}`,
    createdAt: '2026-09-28T10:00:00.000Z',
    updatedAt,
    providerId: 'claude',
    about: 'Retry policy',
    transcript: [{ kind: 'user', id: 1, text: 'Hi', mode: 'ask' }],
    ...extra
  }
}

describe('ConversationStore', () => {
  it('keeps conversations per knowledge base, newest first', () => {
    const conversations = store()
    conversations.save('/kb/one', conversation('aaaaaaaa-1', '2026-09-28T10:00:00.000Z'))
    conversations.save('/kb/one', conversation('bbbbbbbb-2', '2026-09-28T11:00:00.000Z'))
    conversations.save('/kb/two', conversation('cccccccc-3', '2026-09-28T12:00:00.000Z'))
    expect(conversations.list('/kb/one').map((item) => item.id)).toEqual([
      'bbbbbbbb-2',
      'aaaaaaaa-1'
    ])
    expect(conversations.list('/kb/two').map((item) => item.id)).toEqual(['cccccccc-3'])
    expect(conversations.list('/kb/one')[0]).toEqual({
      id: 'bbbbbbbb-2',
      title: 'Conversation bbbbbbbb-2',
      createdAt: '2026-09-28T10:00:00.000Z',
      updatedAt: '2026-09-28T11:00:00.000Z',
      providerId: 'claude',
      about: 'Retry policy'
    })
    expect(conversations.get('/kb/one', 'aaaaaaaa-1').transcript).toHaveLength(1)
  })

  it('replaces a conversation saved again, and deletes one', () => {
    const conversations = store()
    conversations.save('/kb', conversation('aaaaaaaa-1', '2026-09-28T10:00:00.000Z'))
    conversations.save(
      '/kb',
      conversation('aaaaaaaa-1', '2026-09-28T10:05:00.000Z', { title: 'Renamed' })
    )
    expect(conversations.list('/kb')).toMatchObject([{ id: 'aaaaaaaa-1', title: 'Renamed' }])
    conversations.remove('/kb', 'aaaaaaaa-1')
    expect(conversations.list('/kb')).toEqual([])
    expect(() => conversations.get('/kb', 'aaaaaaaa-1')).toThrow(ConversationError)
  })

  it('refuses ids that could leave its folder, and malformed conversations', () => {
    const conversations = store()
    for (const id of ['../../evil-file', 'short', 'UPPERCASE-ID', 'a/b/c/d/e/f', '']) {
      expect(() => conversations.save('/kb', conversation(id, '2026-09-28T10:00:00.000Z'))).toThrow(
        ConversationError
      )
      expect(() => conversations.remove('/kb', id)).toThrow(ConversationError)
    }
    expect(() => conversations.save('/kb', conversation('aaaaaaaa-1', 'not a date'))).toThrow(
      'updatedAt must be a date'
    )
    expect(() =>
      conversations.save(
        '/kb',
        conversation('aaaaaaaa-1', '2026-09-28T10:00:00.000Z', { transcript: 'x' })
      )
    ).toThrow('transcript must be a list')
    expect(() =>
      conversations.save(
        '/kb',
        conversation('aaaaaaaa-1', '2026-09-28T10:00:00.000Z', {
          transcript: ['x'.repeat(5 * 1024 * 1024)]
        })
      )
    ).toThrow('too long')
  })

  it('keeps only the newest conversations and skips damaged files', () => {
    const conversations = store()
    for (let index = 0; index < MAX_CONVERSATIONS + 3; index++) {
      const stamp = new Date(Date.UTC(2026, 8, 1, 0, index)).toISOString()
      conversations.save(
        '/kb',
        conversation(`conversation-${String(index).padStart(4, '0')}`, stamp)
      )
    }
    const listed = conversations.list('/kb')
    expect(listed).toHaveLength(MAX_CONVERSATIONS)
    expect(listed.at(-1)?.id).toBe('conversation-0003')
    writeFileSync(join(conversations.folder('/kb'), 'broken-file-1.json'), '{not json')
    expect(conversations.list('/kb')).toHaveLength(MAX_CONVERSATIONS)
    expect(readdirSync(conversations.folder('/kb')).some((name) => name.endsWith('.tmp'))).toBe(
      false
    )
  })
})
