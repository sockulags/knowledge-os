// The local API of the running core, as the Referat plugin uses it. Every
// write is `POST /api/records` with the per-process token from
// `GET /api/session`; the plugin never touches the knowledge base's files.
// Requests come from the main process, so they carry no Origin header and
// pass the core's loopback and origin checks like the reader's own.

import type { CommitInfo, CreateOutcome, KosApi, RecordInfo } from './importer'

export interface ProjectInfo {
  id: string
  title: string
}

interface NavResponse {
  projects?: { id: string; title: string }[]
  record_index?: { id: string; kind: string; project: string | null }[]
}

export class KosClient implements KosApi {
  private token: string | null = null
  private readonly base: string

  constructor(baseUrl: string) {
    this.base = baseUrl.replace(/\/+$/, '')
  }

  private async getJson<T>(path: string): Promise<{ status: number; body: T | null }> {
    const response = await fetch(`${this.base}${path}`, { headers: { Accept: 'application/json' } })
    const body = (await response.json().catch(() => null)) as T | null
    return { status: response.status, body }
  }

  private async nav(): Promise<NavResponse> {
    const { status, body } = await this.getJson<NavResponse>('/api/nav')
    if (status !== 200 || body === null) throw new Error(`The knowledge base answered ${status}.`)
    return body
  }

  async projects(): Promise<ProjectInfo[]> {
    return (await this.nav()).projects?.map(({ id, title }) => ({ id, title })) ?? []
  }

  /** The project a record belongs to, or null. */
  async projectOfRecord(id: string): Promise<string | null> {
    const entry = (await this.nav()).record_index?.find(
      (item) => item.id === id && item.kind !== 'skill' && item.kind !== 'doc'
    )
    return entry?.project ?? null
  }

  async recordIds(): Promise<string[]> {
    return ((await this.nav()).record_index ?? [])
      .filter((item) => item.kind !== 'skill' && item.kind !== 'doc')
      .map((item) => item.id)
  }

  async search(query: string): Promise<string[]> {
    const { status, body } = await this.getJson<{ results?: { id: string }[] }>(
      `/api/search?q=${encodeURIComponent(query)}`
    )
    if (status !== 200 || body === null) return []
    return (body.results ?? []).map((result) => result.id)
  }

  async record(id: string): Promise<RecordInfo | null> {
    const { status, body } = await this.getJson<{
      id: string
      title: string
      is_decision: boolean
      technical_details?: { provenance?: { kind: string; reference: string }[] }
    }>(`/api/records/${encodeURIComponent(id)}`)
    if (status !== 200 || body === null) return null
    return {
      id: body.id,
      title: body.title,
      isDecision: body.is_decision,
      provenance: body.technical_details?.provenance ?? []
    }
  }

  private async writeToken(): Promise<string> {
    if (this.token !== null) return this.token
    const { status, body } = await this.getJson<{ write_token?: string }>('/api/session')
    if (status !== 200 || typeof body?.write_token !== 'string') {
      throw new Error('The knowledge base did not hand out a write token.')
    }
    this.token = body.write_token
    return this.token
  }

  async createRecord(payload: {
    metadata: Record<string, unknown>
    body: string
    project_path?: string
  }): Promise<CreateOutcome> {
    let response: Response
    try {
      response = await fetch(`${this.base}/api/records`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'X-KOS-Write-Token': await this.writeToken()
        },
        body: JSON.stringify(payload)
      })
    } catch (error) {
      return {
        ok: false,
        status: 0,
        error: 'unreachable',
        detail: `The knowledge base could not be reached: ${error instanceof Error ? error.message : String(error)}`
      }
    }
    const body = (await response.json().catch(() => null)) as Record<string, unknown> | null
    if (response.status === 201 && body !== null && typeof body['id'] === 'string') {
      const commit = (body['commit'] as CommitInfo | undefined) ?? null
      return { ok: true, id: body['id'], commit }
    }
    const issues = Array.isArray(body?.['issues'])
      ? (body['issues'] as { path?: string; message?: string }[])
          .map((issue) => issue.message ?? '')
          .filter((message) => message !== '')
      : []
    const detail = [typeof body?.['detail'] === 'string' ? body['detail'] : '', ...issues]
      .filter((part) => part !== '')
      .join(' ')
    return {
      ok: false,
      status: response.status,
      error: typeof body?.['error'] === 'string' ? body['error'] : `http_${response.status}`,
      detail: detail || `The knowledge base answered ${response.status}.`
    }
  }
}
