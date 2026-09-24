import { resolve } from 'path'
import { defineConfig } from 'electron-vite'

// Three pages, each with its own preload script: the start page, the
// Referat import window, and the Clone Knowledge Base window. Sandboxed
// preload scripts cannot load shared chunks, so the preload entries share
// no code.
export default defineConfig({
  main: {},
  preload: {
    build: {
      rollupOptions: {
        input: {
          index: resolve(__dirname, 'src/preload/index.ts'),
          referat: resolve(__dirname, 'src/preload/referat.ts'),
          clone: resolve(__dirname, 'src/preload/clone.ts')
        }
      }
    }
  },
  renderer: {
    build: {
      rollupOptions: {
        input: {
          index: resolve(__dirname, 'src/renderer/index.html'),
          referat: resolve(__dirname, 'src/renderer/referat.html'),
          clone: resolve(__dirname, 'src/renderer/clone.html')
        }
      }
    }
  }
})
