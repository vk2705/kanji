import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// `base` deliberately has no default here — it differs per deployment target
// (srv.alteon.help, the shared dev box, needs '/kanji/'; kanji.alteon.help, the
// dedicated prod VM, needs '/') and is always passed explicitly via the
// `npm run build:dev` / `build:prod` scripts in package.json. See
// DEPLOY_README.md and deploy/nginx/README.md for which to use where.
export default defineConfig({
  plugins: [react()],
})
