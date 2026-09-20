import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  // Prod (kanji.alteon.help, dedicated Oracle VM) serves the SPA from '/' —
  // only the backend API keeps a '/kanji/api/' prefix (see deploy/nginx/kanji.conf
  // and frontend/src/api.js). The old shared srv.alteon.help box needed '/kanji/'
  // for the whole app, but that box is dev-only now (see CHANGELOG.md 1.1).
  base: '/',
  plugins: [react()],
})
