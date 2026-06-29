import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Backend address for the dev proxy. Override with VITE_BACKEND if needed.
const backend = process.env.VITE_BACKEND ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/ws": { target: backend, ws: true, changeOrigin: true },
    },
  },
});
