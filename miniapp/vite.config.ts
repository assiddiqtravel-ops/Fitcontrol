import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The Mini App talks to the backend at VITE_API_BASE (default /api/v1 via proxy
// in dev). Set VITE_API_BASE to the full backend URL in production builds.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
