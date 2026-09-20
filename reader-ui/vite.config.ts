import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Builds into knowledge_os/reader/static/app/, which is committed so
// `pip install -e ".[reader]"` and `kos-read` work with no Node toolchain
// installed (see reader-ui/README.md). `npm run dev` proxies /api to the
// Python server, which must be started separately (kos-read defaults to
// port 8800).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/",
  build: {
    outDir: "../knowledge_os/reader/static/app",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8800",
    },
  },
});
