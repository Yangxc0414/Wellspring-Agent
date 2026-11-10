import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Read through globalThis so the config keeps typechecking without @types/node.
const nodeEnv = (
  globalThis as unknown as { process?: { env?: Record<string, string | undefined> } }
).process?.env;

export default defineConfig(({ mode }) => ({
  base: "./",
  define: {
    __STATIC_ONLY__: JSON.stringify(mode === "static")
  },
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        // A server-side concern, so it gets its own variable: `VITE_RUNTIME_URL` is read by the
        // browser and must stay empty in dev, otherwise the page calls the runtime cross-origin
        // and the proxy is bypassed.
        target: nodeEnv?.RUNTIME_PROXY_URL || "http://127.0.0.1:8787",
        changeOrigin: true
      }
    }
  },
  build: {
    target: "es2020",
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/react") || id.includes("node_modules/scheduler")) {
            return "react-vendor";
          }
          if (id.includes("node_modules/zustand")) {
            return "state-vendor";
          }
          return undefined;
        }
      }
    }
  }
}));
