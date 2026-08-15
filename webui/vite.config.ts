import path from "node:path";

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const daemonTarget = process.env.LITEYUKI_WEBUI_PROXY_TARGET;

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  server: daemonTarget
    ? {
      proxy: {
        "/api": {
          target: daemonTarget,
          changeOrigin: true,
          configure(proxy) {
            proxy.on("proxyReq", (request) => request.setHeader("origin", daemonTarget));
          },
        },
      },
    }
    : undefined,
});
