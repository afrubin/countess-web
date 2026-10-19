import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

// `npm run dev` serves the page with hot reload and passes /api to a running countess_web:
//   COUNTESS_WEB_TOKEN=dev countess_web --port 8642 --no-browser
//   COUNTESS_WEB_PORT=8642 npm run dev        then open http://localhost:5173/?token=dev
// The page sends the token itself; the proxy adds nothing, so it gives no other site a way in.
const backend = `http://127.0.0.1:${process.env.COUNTESS_WEB_PORT ?? '8642'}`

export default defineConfig({
  plugins: [vue()],
  // Relative asset paths, so the page works under a proxy's path prefix (Open OnDemand's /rnode/...).
  base: './',
  build: {
    outDir: '../src/countess_web/static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': {
        target: backend,
        ws: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
  },
})
