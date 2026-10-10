// Turns the Markdown in docs/ into page content for the portal:
// - the first level-one heading goes (the page renders its own title);
// - in a decision record the "Status:" line goes (the page shows it as a tag);
// - raw HTML is shown as text;
// - a link to another document becomes a link to its page, fragment kept;
//   a link to anything else in or outside the repository becomes plain text;
// - an image outside docs/ becomes its alt text;
// - in docs/adr/README.md the index table goes and what follows it is handed
//   to the page separately, so the page can put the filterable list between.
import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import GithubSlugger from 'github-slugger';
import { toHtml } from 'hast-util-to-html';
import { toHast } from 'mdast-util-to-hast';
import { SKIP, visit } from 'unist-util-visit';
import { ROUTES, docsRelative, routeFor } from './docs.mjs';

const EXTERNAL = /^(https?:|mailto:)/i;
const SCHEME = /^[a-z][a-z0-9+.-]*:/i;
const STATUS_PREFIX = /^Status:\s*[^(.]*(?:\(\d{4}-\d{2}-\d{2}\))?\s*\.?\s*/;

function text(node) {
  if (node.value !== undefined) return String(node.value);
  return (node.children ?? []).map(text).join('');
}

function splitHref(url) {
  const hash = url.indexOf('#');
  return hash === -1 ? [url, ''] : [url.slice(0, hash), url.slice(hash + 1)];
}

function linkTarget(url, fileDir) {
  if (EXTERNAL.test(url) || url.startsWith('#')) return url;
  if (SCHEME.test(url) || url.startsWith('/')) return null;
  const [path, fragment] = splitHref(url);
  let decoded;
  try {
    decoded = decodeURI(path);
  } catch {
    return null;
  }
  const absolute = resolve(fileDir, decoded);
  const rel = docsRelative(absolute);
  if (rel === null) return null;
  const route = routeFor(rel, absolute);
  if (!route) return null;
  // The table of all personas is generated on the overview, not on the page about the book.
  if (route === ROUTES.bookAbout && fragment === 'alle-personas') return ROUTES.book;
  return fragment ? `${route}#${fragment}` : route;
}

function removeFirstTitle(tree) {
  const index = tree.children.findIndex((n) => n.type === 'heading' && n.depth === 1);
  if (index !== -1) tree.children.splice(index, 1);
}

function removeStatusLine(tree) {
  const index = tree.children.findIndex(
    (n) => n.type === 'paragraph' && text(n).startsWith('Status:'),
  );
  if (index === -1) return;
  const paragraph = tree.children[index];
  const first = paragraph.children[0];
  if (first?.type === 'text') first.value = first.value.replace(STATUS_PREFIX, '');
  if (!text(paragraph).trim()) tree.children.splice(index, 1);
}

function splitAdrIndex(tree, file) {
  const index = tree.children.findIndex(
    (n) => n.type === 'table' && text(n.children[0]?.children[0] ?? {}).trim() === 'Nr',
  );
  if (index === -1) throw new Error('docs/adr/README.md: de tabel met besluiten ontbreekt');
  const tail = tree.children.splice(index);
  tail.shift();
  const slugger = new GithubSlugger();
  const hast = toHast({ type: 'root', children: tail });
  visit(hast, 'element', (node) => {
    if (/^h[1-6]$/.test(node.tagName)) node.properties.id = slugger.slug(text(node));
  });
  file.data.astro ??= {};
  file.data.astro.frontmatter ??= {};
  file.data.astro.frontmatter.tailHtml = toHtml(hast);
}

export function remarkPortal() {
  return (tree, file) => {
    if (!file.path) return;
    const rel = docsRelative(file.path);
    if (rel === null) return;
    const fileDir = dirname(file.path);

    visit(tree, 'html', (node, index, parent) => {
      parent.children[index] = { type: 'text', value: node.value };
    });

    removeFirstTitle(tree);
    if (/^adr\/\d{4}-/.test(rel)) removeStatusLine(tree);

    visit(tree, (node, index, parent) => {
      if (node.type === 'link' || node.type === 'definition') {
        const target = linkTarget(node.url, fileDir);
        if (target !== null) {
          node.url = target;
        } else if (node.type === 'link') {
          parent.children.splice(index, 1, ...node.children);
          return [SKIP, index];
        }
      } else if (node.type === 'image' && !EXTERNAL.test(node.url)) {
        const absolute = resolve(fileDir, decodeURI(splitHref(node.url)[0]));
        if (docsRelative(absolute) === null || !existsSync(absolute)) {
          parent.children[index] = { type: 'text', value: node.alt ?? '' };
        }
      }
      return undefined;
    });

    if (rel === 'adr/README.md') splitAdrIndex(tree, file);
  };
}
