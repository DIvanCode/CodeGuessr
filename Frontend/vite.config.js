import { defineConfig } from "vite";

const proxy = { "/api": process.env.API_TARGET ?? "http://127.0.0.1:8000" };

export default defineConfig({
  esbuild: { jsx: "automatic" },
  server: { proxy },
  preview: { proxy },
});
