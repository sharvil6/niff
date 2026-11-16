import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  server: {
    // `npm run dev` serves the page; API calls go to uvicorn on port 8000.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
