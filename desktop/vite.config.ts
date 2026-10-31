import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The Tauri shell is a fixed host; dev server settings per Tauri conventions.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    target: "es2021",
  },
});
