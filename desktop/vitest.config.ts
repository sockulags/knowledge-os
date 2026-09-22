import { defineConfig } from 'vitest/config'

// Unit tests run in plain Node. The modules under test import only Node
// built-ins, never the 'electron' runtime, so they need no mocking.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    globals: false
  }
})
