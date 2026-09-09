import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The SPA is served by Vite in development. All `/api` calls are proxied to the
// FastAPI backend so the browser never talks to a hard-coded origin.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    // Allow the arena preview host (and localhost / any e2b.app host) so the
    // SPA loads in the user's browser.
    allowedHosts: [".e2b.app", "localhost", "127.0.0.1"],
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
      // Parity with the nginx container: the API page links to the
      // interactive OpenAPI docs, so dev should serve them from the backend too.
      "/docs": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
      "/openapi.json": {
        target: process.env.VITE_API_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
