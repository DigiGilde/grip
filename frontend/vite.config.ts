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
  build: {
    rolldownOptions: {
      output: {
        // The design system and the React stack change far less often than
        // our own code. In their own chunks they stay cached across deploys,
        // and no single file dominates the first load.
        codeSplitting: {
          groups: [
            { name: 'design-system', test: /node_modules[\\/](@nldd|lit|lit-html|lit-element|@lit)[\\/]/, priority: 20 },
            { name: 'vendor', test: /node_modules[\\/]/, priority: 10 },
          ],
        },
      },
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
