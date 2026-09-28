import { resolve } from 'path'
import { defineConfig } from 'electron-vite'

// Three pages, each with its own preload script: the start page, the
// Referat import window, and the Clone Knowledge Base window. Sandboxed
// preload scripts cannot load shared chunks, so the preload entries share
// no code.
export default defineConfig({
  main: {
    build: {
      // Bundled into the main process rather than loaded from node_modules at
      // run time: the ACP SDK imports zod, which it declares only as a peer
      // dependency, so the packaged app would not contain it (0.8.0 did not
      // start). scripts/check-packaged.mjs guards every run-time dependency.
      externalizeDeps: { exclude: ['@agentclientprotocol/sdk'] }
    }
  },
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
