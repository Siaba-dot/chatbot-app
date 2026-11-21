import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vystymui: API veikia http://127.0.0.1:8000 (uvicorn api.server:app)
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": process.env.API_URL || "http://127.0.0.1:8000" } },
});
