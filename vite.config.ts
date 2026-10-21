import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  root: "apps/judge-godmode-console",
  // No data: URIs: the server CSP blocks inline fonts (font-src falls back to 'self').
  build: { outDir: "../../dist", emptyOutDir: true, assetsInlineLimit: 0 },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8080",
      "/health": "http://127.0.0.1:8080",
    },
  },
});
