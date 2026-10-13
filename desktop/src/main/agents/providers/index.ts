// Every provider the app offers, in the order it offers them. Adding one is a
// new module here that implements AgentProvider and passes the conformance
// suite (see desktop/README.md, "In-app agents").

import type { AgentProvider } from '../contract'
import { claudeProvider } from './claude'
import { codexProvider } from './codex'

export const PROVIDERS: readonly AgentProvider[] = [claudeProvider, codexProvider]

export function findProvider(id: string): AgentProvider | null {
  return PROVIDERS.find((provider) => provider.id === id) ?? null
}
