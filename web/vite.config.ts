import path from "path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  // Backend'e (FastAPI) dev sırasında proxy — /api istekleri 8000'e gider.
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
})
