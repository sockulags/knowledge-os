// A scripted ACP agent for the conformance suite (conformance.ts). It speaks
// ACP over stdio like a real adapter and records what the client sent it.
//
// Environment:
//   MOCK_RECORD=<file>     append one JSON line per request it receives
//   MOCK_AUTH=required     refuse session/new with ACP's auth-required error
//   MOCK_LOAD=1            advertise session/load
//
// A prompt's text is a command:
//   echo <text>    stream <text> as the agent's message
//   tool           report a tool call that completes
//   permission     ask for permission, then say which option came back
//   wait           keep the turn open until it is cancelled
//   crash          exit at once, mid-turn

// Plain JavaScript run by Node, so it has no return types to declare.
/* eslint-disable @typescript-eslint/explicit-function-return-type */

import { appendFileSync } from 'node:fs'
import { Readable, Writable } from 'node:stream'
import {
  AgentSideConnection,
  PROTOCOL_VERSION,
  RequestError,
  ndJsonStream
} from '@agentclientprotocol/sdk'

function record(method, params) {
  if (process.env.MOCK_RECORD) {
    appendFileSync(
      process.env.MOCK_RECORD,
      JSON.stringify({ method, params, env: pickEnv() }) + '\n'
    )
  }
}

function pickEnv() {
  const names = [
    'CLAUDE_CODE_EXECUTABLE',
    'CODEX_PATH',
    'INITIAL_AGENT_MODE',
    'ELECTRON_RUN_AS_NODE',
    'MOCK_MARKER'
  ]
  return Object.fromEntries(
    names.filter((name) => process.env[name] !== undefined).map((name) => [name, process.env[name]])
  )
}

let sessions = 0
const waiting = new Map()

const connection = new AgentSideConnection(
  (client) => ({
    async initialize(params) {
      record('initialize', params)
      return {
        protocolVersion: PROTOCOL_VERSION,
        agentCapabilities: { loadSession: process.env.MOCK_LOAD === '1' },
        agentInfo: { name: 'mock-agent', version: '1.0.0' },
        authMethods: [{ id: 'mock-login', name: 'Log in', description: 'Run the login command' }]
      }
    },
    async newSession(params) {
      record('session/new', params)
      if (process.env.MOCK_AUTH === 'required') throw RequestError.authRequired()
      sessions += 1
      return { sessionId: `mock-session-${sessions}` }
    },
    async loadSession(params) {
      record('session/load', params)
      return {}
    },
    async authenticate(params) {
      record('authenticate', params)
      return {}
    },
    async cancel(params) {
      record('session/cancel', params)
      waiting.get(params.sessionId)?.()
    },
    async prompt(params) {
      record('session/prompt', params)
      const text = params.prompt.map((block) => (block.type === 'text' ? block.text : '')).join('')
      const say = (message) =>
        client.sessionUpdate({
          sessionId: params.sessionId,
          update: { sessionUpdate: 'agent_message_chunk', content: { type: 'text', text: message } }
        })
      if (text.startsWith('echo ')) {
        await say(text.slice(5))
        return { stopReason: 'end_turn' }
      }
      if (text === 'tool') {
        await client.sessionUpdate({
          sessionId: params.sessionId,
          update: {
            sessionUpdate: 'tool_call',
            toolCallId: 'call-1',
            title: 'search',
            kind: 'search',
            status: 'in_progress',
            rawInput: { query: 'retry' }
          }
        })
        await client.sessionUpdate({
          sessionId: params.sessionId,
          update: {
            sessionUpdate: 'tool_call_update',
            toolCallId: 'call-1',
            status: 'completed',
            rawOutput: '{"results":[]}'
          }
        })
        return { stopReason: 'end_turn' }
      }
      // `permission [TITLE]`: ask to use a tool, `write_note` unless named.
      if (text === 'permission' || text.startsWith('permission ')) {
        const title = text.split(' ')[1] ?? 'write_note'
        const answer = await client.requestPermission({
          sessionId: params.sessionId,
          toolCall: { toolCallId: 'call-2', title, status: 'pending' },
          options: [
            { optionId: 'allow', name: 'Allow', kind: 'allow_once' },
            { optionId: 'reject', name: 'Reject', kind: 'reject_once' }
          ]
        })
        await say(
          answer.outcome.outcome === 'selected'
            ? `chose ${answer.outcome.optionId}`
            : 'chose nothing'
        )
        return { stopReason: 'end_turn' }
      }
      if (text === 'wait') {
        await new Promise((resolve) => waiting.set(params.sessionId, resolve))
        return { stopReason: 'cancelled' }
      }
      if (text === 'crash') {
        process.exit(3)
      }
      // A sign-in that expired mid-session, as Claude Code reports it.
      if (text === 'expired') {
        await say('Failed to authenticate: OAuth session expired and could not be refreshed')
        throw RequestError.internalError(
          undefined,
          'Failed to authenticate: OAuth session expired and could not be refreshed'
        )
      }
      if (text === 'fail') {
        throw RequestError.internalError(undefined, 'Something else went wrong')
      }
      await say(`unknown command: ${text}`)
      return { stopReason: 'end_turn' }
    }
  }),
  ndJsonStream(Writable.toWeb(process.stdout), Readable.toWeb(process.stdin))
)

void connection
