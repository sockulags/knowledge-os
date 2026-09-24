import type { CloneApi } from '../shared/clone'

declare global {
  interface Window {
    kosClone: CloneApi
  }
}
