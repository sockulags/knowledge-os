// The in-app agent's past conversations (issue #100), kept on this computer
// in the app's user-data folder, one JSON file per conversation, in a folder
// per knowledge base. They are not records: nothing here is written to the
// knowledge base or synced. The reader UI owns what a conversation holds; this
// store only checks its shape, its size, and where it goes.

import { createHash } from 'crypto'
import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync
} from 'fs'
import { join, resolve } from 'path'

/** How many conversations a knowledge base keeps; the oldest go first. */
export const MAX_CONVERSATIONS = 200
/** The largest conversation file, in bytes. */
export const MAX_CONVERSATION_BYTES = 4 * 1024 * 1024
const ID_PATTERN = /^[a-z0-9][a-z0-9-]{7,63}$/

/** What the chat list shows about one conversation. */
export interface ConversationSummary {
  id: string
  title: string
  createdAt: string
  updatedAt: string
  providerId: string | null
  /** The page or project in view when it started, for the list. */
  about: string | null
}

export interface Conversation extends ConversationSummary {
  version: 1
  /** The panel's transcript, as the reader UI keeps it. */
  transcript: unknown[]
}

export class ConversationError extends Error {}

function text(value: unknown, name: string, limit: number): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new ConversationError(`${name} must be a non-empty string`)
  }
  return value.trim().slice(0, limit)
}

function optionalText(value: unknown, limit: number): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value.trim().slice(0, limit) : null
}

function checkId(id: unknown): string {
  if (typeof id !== 'string' || !ID_PATTERN.test(id)) {
    throw new ConversationError('not a conversation id')
  }
  return id
}

/** A conversation as the reader sent it, checked and normalised. */
export function parseConversation(value: unknown): Conversation {
  if (typeof value !== 'object' || value === null) {
    throw new ConversationError('a conversation must be an object')
  }
  const raw = value as Record<string, unknown>
  if (!Array.isArray(raw['transcript'])) {
    throw new ConversationError('transcript must be a list')
  }
  const date = (field: string): string => {
    const stamp = text(raw[field], field, 40)
    if (Number.isNaN(Date.parse(stamp))) throw new ConversationError(`${field} must be a date`)
    return stamp
  }
  return {
    version: 1,
    id: checkId(raw['id']),
    title: text(raw['title'], 'title', 200),
    createdAt: date('createdAt'),
    updatedAt: date('updatedAt'),
    providerId: optionalText(raw['providerId'], 64),
    about: optionalText(raw['about'], 200),
    transcript: raw['transcript']
  }
}

function summary(conversation: Conversation): ConversationSummary {
  const { id, title, createdAt, updatedAt, providerId, about } = conversation
  return { id, title, createdAt, updatedAt, providerId, about }
}

export class ConversationStore {
  constructor(private readonly root: string) {}

  /** The folder of one knowledge base's conversations (named by a hash of its path). */
  folder(workspaceRoot: string): string {
    const key = createHash('sha256').update(resolve(workspaceRoot)).digest('hex').slice(0, 16)
    return join(this.root, key)
  }

  private file(workspaceRoot: string, id: string): string {
    return join(this.folder(workspaceRoot), `${checkId(id)}.json`)
  }

  private readAll(workspaceRoot: string): Conversation[] {
    const folder = this.folder(workspaceRoot)
    if (!existsSync(folder)) return []
    const conversations: Conversation[] = []
    for (const name of readdirSync(folder)) {
      if (!name.endsWith('.json')) continue
      try {
        conversations.push(parseConversation(JSON.parse(readFileSync(join(folder, name), 'utf8'))))
      } catch {
        // A damaged file is left alone and not listed.
      }
    }
    return conversations.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  }

  /** Newest first. */
  list(workspaceRoot: string): ConversationSummary[] {
    return this.readAll(workspaceRoot).map(summary)
  }

  get(workspaceRoot: string, id: string): Conversation {
    const path = this.file(workspaceRoot, id)
    if (!existsSync(path)) throw new ConversationError('conversation not found')
    return parseConversation(JSON.parse(readFileSync(path, 'utf8')))
  }

  /** Write a conversation (create or replace), then keep only the newest MAX_CONVERSATIONS. */
  save(workspaceRoot: string, value: unknown): ConversationSummary {
    const conversation = parseConversation(value)
    const body = JSON.stringify(conversation)
    if (Buffer.byteLength(body) > MAX_CONVERSATION_BYTES) {
      throw new ConversationError('the conversation is too long to keep')
    }
    const folder = this.folder(workspaceRoot)
    mkdirSync(folder, { recursive: true })
    const path = this.file(workspaceRoot, conversation.id)
    const staging = `${path}.tmp`
    writeFileSync(staging, body, 'utf8')
    renameSync(staging, path)
    for (const old of this.readAll(workspaceRoot).slice(MAX_CONVERSATIONS)) {
      rmSync(this.file(workspaceRoot, old.id), { force: true })
    }
    return summary(conversation)
  }

  remove(workspaceRoot: string, id: string): void {
    rmSync(this.file(workspaceRoot, id), { force: true })
  }
}
