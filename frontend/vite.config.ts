import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import type { ProxyOptions } from "vite";

const LOCAL_API_ORIGIN = "http://127.0.0.1:8766";

function localApiProxy(): ProxyOptions {
  return {
    target: LOCAL_API_ORIGIN,
    changeOrigin: true,
    configure(proxy) {
      proxy.on("proxyReq", (request) => {
        // The browser and Vite are same-origin. Re-establish that invariant at
        // the loopback backend after the development proxy changes the Host.
        request.setHeader("Origin", LOCAL_API_ORIGIN);
      });
    },
  };
}

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
    proxy:
      mode === "real"
        ? {
            "/auth": localApiProxy(),
            "/health": localApiProxy(),
            "/v1": localApiProxy(),
          }
        : undefined,
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
  },
  build: {
    // Runtime resource discovery is package-owned. This generated directory is
    // ignored and rebuilt from the committed lockfile before staging.
    outDir: "../src/prompt_enhancer/_resources/dashboard",
    emptyOutDir: true,
  },
  test: {
    include: ["src/**/*.test.{ts,tsx}"],
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: true,
    coverage: {
      reporter: ["text", "html"],
    },
  },
}));
