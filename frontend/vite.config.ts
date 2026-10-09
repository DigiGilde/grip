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
            // What the shell, the start page and the tasks render: the part
            // of the design system every first page needs. Every other
            // component stays out of the groups, so it lands with the pages
            // that use it and is fetched on the way there (the date picker
            // with a form, the text editor with a page that writes text).
            // A component the shell starts to use and that is not listed
            // here still works: it then travels with our own code.
            {
              name: 'design-system',
              test: new RegExp(
                'node_modules[\\\\/](' +
                  'lit|lit-html|lit-element|@lit|@floating-ui|' +
                  '@nldd[\\\\/]design-system[\\\\/]dist[\\\\/](' +
                  'utilities[\\\\/](?!codemirror)|' +
                  'components[\\\\/](' +
                  'actions[\\\\/](button|button-group|icon-button|menu|toolbar)|' +
                  'content[\\\\/](avatar|avatar-group|icon|identity|keyboard-shortcut|title|tooltip)|' +
                  'layout[\\\\/](app-view|container|page|page-sections|popover|split-views)|' +
                  'lists-and-tables[\\\\/](cells|list|list-item)|' +
                  'navigation[\\\\/](menu-bar|menu-bar-item|skip-link|tab-bar)|' +
                  'status-and-feedback[\\\\/](activity-indicator|badge|banner|inline-dialog)' +
                  ')[\\\\/]))',
              ),
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
