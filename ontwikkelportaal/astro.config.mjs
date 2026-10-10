import { unified } from '@astrojs/markdown-remark';
import { defineConfig, passthroughImageService } from 'astro/config';
import pagefind from 'astro-pagefind';
import { remarkPortal } from './src/lib/remark-portal.mjs';
import { rehypeCodeViewer } from './src/lib/rehype-code-viewer.mjs';

export default defineConfig({
  // Every page is <route>/index.html; nginx serves it without a redirect.
  trailingSlash: 'ignore',
  build: {
    format: 'directory',
    inlineStylesheets: 'never',
  },
  // Images from docs/ are copied as they are; no sharp in the build.
  image: {
    service: passthroughImageService(),
  },
  integrations: [
    // One index for the whole site, whatever a page declares as its language.
    pagefind({ indexConfig: { forceLanguage: 'nl' } }),
  ],
  markdown: {
    // nldd-code-viewer owns code blocks, so no highlighter at build time.
    syntaxHighlight: false,
    processor: unified({
      remarkPlugins: [remarkPortal],
      rehypePlugins: [rehypeCodeViewer],
      // Render the text as written: no curly quotes, no dashes made of hyphens.
      smartypants: false,
    }),
  },
  vite: {
    build: {
      // The CSP allows no inline script: every processed script becomes a file.
      assetsInlineLimit: 0,
    },
    ssr: {
      noExternal: ['@nldd/design-system'],
    },
  },
});
