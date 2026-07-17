import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  // Relative asset paths so the built renderer works from file:// inside
  // the packaged app (absolute "/assets/..." 404s and white-screens).
  base: "./",
  plugins: [vue()],
  server: {
    host: "127.0.0.1",
    port: 5173
  }
});

