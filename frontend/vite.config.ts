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
            // The text editor of the design system brings CodeMirror, about
            // as many bytes as our own code. Only the pages that write text
            // need it, and `ui/TextEditor` imports it on demand. It is left
            // out of both groups, so it lands in the chunk of that import
            // and is fetched then, not with every first page.
            {
              name: 'design-system',
              test: /node_modules[\\/](lit|lit-html|lit-element|@lit|@nldd[\\/](?!design-system[\\/]dist[\\/](components[\\/]inputs[\\/]text-editor|utilities[\\/]codemirror)[\\/]))[\\/]?/,
              priority: 20,
            },
            {
              name: 'vendor',
              test: /node_modules[\\/](?!(@codemirror|@lezer|@marijn|style-mod|w3c-keyname|crelt|@nldd)[\\/])/,
              priority: 10,
            },
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
