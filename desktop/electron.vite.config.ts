import { resolve } from 'path'
import { defineConfig } from 'electron-vite'

// Two pages, each with its own preload script: the start page and the
// Referat import window. Sandboxed preload scripts cannot load shared
// chunks, so the two preload entries share no code.
export default defineConfig({
  main: {},
  preload: {
    build: {
      rollupOptions: {
        input: {
          index: resolve(__dirname, 'src/preload/index.ts'),
          referat: resolve(__dirname, 'src/preload/referat.ts')
        }
      }
    }
  },
  renderer: {
    build: {
      rollupOptions: {
        input: {
          index: resolve(__dirname, 'src/renderer/index.html'),
          referat: resolve(__dirname, 'src/renderer/referat.html')
        }
      }
    }
  }
})
