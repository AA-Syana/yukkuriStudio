import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 開発中は /api をFastAPI(8000番)へ中継する
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
});
