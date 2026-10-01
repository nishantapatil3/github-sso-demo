import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

// Proxy auth + API to the backend so UI and API share one origin (cookie session).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/auth": { target: backend, changeOrigin: false },
      "/api": { target: backend, changeOrigin: false },
    },
  },
});
