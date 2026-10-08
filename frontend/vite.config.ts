import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The ".ts" extension is needed by Vite's native config loader.
import { API_PREFIX, stripApiPrefix } from "./src/proxy.ts";

// The FastAPI backend started with `uvicorn app.main:app --reload`.
const BACKEND_URL = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // A dev proxy instead of CORS: the browser only talks to the Vite server
    // (same origin), and Vite forwards /api/... calls to the backend.
    proxy: {
      [API_PREFIX + "/"]: {
        target: BACKEND_URL,
        changeOrigin: true,
        rewrite: stripApiPrefix,
      },
    },
  },
  test: {
    // jsdom gives tests a fake browser (document, window, XMLHttpRequest).
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
  },
});
