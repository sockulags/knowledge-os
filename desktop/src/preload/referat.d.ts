import type { ReferatApi } from '../shared/referat'

declare global {
  interface Window {
    referat: ReferatApi
  }
}
