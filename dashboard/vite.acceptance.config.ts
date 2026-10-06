import { defineConfig } from 'vite'
import base from './vite.config.ts'

export default defineConfig({ ...base, server: { host: '127.0.0.1', port: 4273, strictPort: true,
  proxy: { '/api': { target: 'http://127.0.0.1:4274', changeOrigin: false } } } })
