import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Component and hook tests (`src/**/*.test.tsx`) in a simulated DOM. The
// pure `src/**/*.test.ts` tests use Node's own runner and stay out of here.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.tsx"],
  },
});
