// @ts-check
import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

// Regla de Oro (plan_replication.md): SPA estática de una sola página, CSS inline
// (evita rutas /_astro/ rotas en ShinyApps.io). En dev, /api se proxea al gateway.
export default defineConfig({
  output: "static",
  build: { inlineStylesheets: "always" },
  vite: {
    plugins: [tailwindcss()],
    server: {
      proxy: {
        "/api": { target: "http://localhost:8000", changeOrigin: true },
        "/shiny": { target: "http://localhost:8000", changeOrigin: true, ws: true },
      },
    },
  },
});
