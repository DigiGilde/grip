import path from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    port: 5183,
    strictPort: true,
    proxy: {
      // Same origin in development as in production (nginx proxies /api there),
      // so the session and CSRF cookies need no cross-site handling.
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8010',
        changeOrigin: false,
      },
    },
  },
});
