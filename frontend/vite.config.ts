/// <reference types="vitest/config" />
// Dashboard — context/02 §2. Em desenvolvimento, `npm run dev` serve em :5173 e
// repassa /api (REST e WebSocket) ao backend do compose; o navegador vê uma
// origem só, como verá atrás do nginx. Em produção, o build estático é servido
// pelo nginx do compose, com HTTPS (context/02 §6).
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const ALVO_API = process.env.VITE_PROXY_ALVO ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: ALVO_API, changeOrigin: true, ws: true },
    },
  },
  build: {
    // Leaflet e Recharts num pacote só passam dos 500 kB. É um painel de
    // estação fixa (context/00 §8, sem versão mobile), aberto uma vez por
    // turno: dividir o pacote não compra nada.
    chunkSizeWarningLimit: 1200,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/testes/preparar.ts"],
    css: false,
  },
});
