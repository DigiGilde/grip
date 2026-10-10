// Checks the built site in dist/ and exits non-zero on any problem:
// - every internal link and asset resolves, and every #fragment exists;
// - no link points at a .md file;
// - no inline script and no inline event handler (the CSP allows neither);
// - the top bar has no section items; every page but the start page has a back
//   button to an existing page and breadcrumbs ending in itself;
// - every document is in exactly one chapter, and every chapter has a page;
// - every page has the search window and a Zoeken item that works without script;
// - every nldd-* element used is defined by an import in src/nldd-components.js;
// - every persona and every decision has a page, and the search index exists;
// - every page has grip's icons, written by `just brand`;
// - no en or em dash and no local path in the output.
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { CHAPTERS, chapterDocs } from '../src/lib/chapters.mjs';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const DIST = join(ROOT, 'dist');
const DOCS = join(ROOT, '..', 'docs');
const ELEMENT_SLOTS = new Set([
  'header', 'sidebar', 'footer', 'global', 'utility', 'breadcrumbs', 'legal-bar', 'start', 'end',
  'actions', 'no-results', 'empty', 'left', 'right',
]);
const START = join(DIST, 'index.html');
const GRIP_ICONS = ['/favicon.ico', '/favicon.svg', '/apple-touch-icon.png'];

const problems = [];
const problem = (file, message) => problems.push(`${relative(DIST, file) || file}: ${message}`);

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path, out);
    else out.push(path);
  }
  return out;
}

if (!existsSync(DIST)) {
  console.error('dist/ ontbreekt: draai eerst npm run build');
  process.exit(1);
}

const files = walk(DIST);
const pages = files.filter((f) => f.endsWith('.html'));
const html = new Map(pages.map((f) => [f, readFileSync(f, 'utf8')]));
const ids = new Map([...html].map(([f, text]) => [f, new Set([...text.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]))]));

function targetFile(url, from) {
  const path = decodeURIComponent(url);
  const absolute = path.startsWith('/') ? join(DIST, path) : join(dirname(from), path);
  if (existsSync(absolute) && statSync(absolute).isFile()) return absolute;
  const index = join(absolute, 'index.html');
  return existsSync(index) ? index : null;
}

const decode = (s) => s.replace(/&amp;/g, '&').replace(/&#39;/g, "'").replace(/&quot;/g, '"');

for (const [file, text] of html) {
  // A moved page: only a redirect to a page that is checked itself.
  if (/<meta http-equiv="refresh"/.test(text)) {
    const to = /url=([^"]+)"/.exec(text)?.[1];
    if (!to || !targetFile(decode(to).split('?')[0], file)) problem(file, `doorverwijzing naar niets: ${to}`);
    continue;
  }

  // Links and assets.
  for (const m of text.matchAll(/\s(?:href|src)="([^"]*)"/g)) {
    const ref = decode(m[1]);
    if (/^(https?:|mailto:)/.test(ref)) continue;
    if (/^[a-z][a-z0-9+.-]*:/i.test(ref)) {
      problem(file, `onverwacht schema in ${ref}`);
      continue;
    }
    const [withQuery, fragment] = ref.split('#');
    const path = withQuery.split('?')[0];
    if (/\.md$/i.test(path)) problem(file, `link naar Markdown: ${ref}`);
    const target = path ? targetFile(path, file) : file;
    if (!target) {
      problem(file, `verwijst naar niets: ${ref}`);
    } else if (fragment && target.endsWith('.html') && !ids.get(target)?.has(decodeURIComponent(fragment))) {
      problem(file, `anker ontbreekt: ${ref}`);
    }
  }

  // Scripts the policy would block.
  for (const m of text.matchAll(/<script\b([^>]*)>/g)) {
    if (!/\ssrc=/.test(m[1])) problem(file, 'inline script');
  }
  if (/<[a-z][^>]*\son[a-z]+=/i.test(text)) problem(file, 'inline event handler');

  // The search window is on every page; the Zoeken item still leads to the search page without script.
  if (!/<nldd-window[^>]*\sid="zoekvenster"/.test(text) || !/id="zoekvenster-veld"/.test(text)) problem(file, 'zoekvenster ontbreekt');
  if (!/<nldd-menu-bar-item[^>]*\sid="zoeken-knop"[^>]*\shref="\/zoeken\/"/.test(text)) problem(file, 'Zoeken in de bovenbalk wijst niet naar /zoeken/');

  // Navigation: the website title leads home, a deeper page goes up with the back button.
  if (/<nldd-menu-bar slot="global"/.test(text)) problem(file, 'bovenbalk heeft onderdelen');
  const bar = /<nldd-top-navigation-bar\b([^>]*)>/.exec(text)?.[1] ?? '';
  const back = /\sback-href="([^"]*)"/.exec(bar)?.[1];
  if (file === START) {
    if (back !== undefined) problem(file, 'de start heeft een terugknop');
    if (/<nldd-breadcrumbs\b/.test(text)) problem(file, 'de start heeft een kruimelpad');
  } else {
    if (!back) problem(file, 'terugknop ontbreekt');
    else if (!targetFile(decode(back).split('?')[0], file)) problem(file, `terugknop wijst naar niets: ${back}`);
    if (!/\sback-text="[^"]+"/.test(bar)) problem(file, 'terugknop zonder tekst');
    const crumbs = /<nldd-breadcrumbs\b[^>]*>([\s\S]*?)<\/nldd-breadcrumbs>/.exec(text)?.[1] ?? '';
    const items = [...crumbs.matchAll(/<nldd-breadcrumbs-item\b([^>]*)>/g)].map((m) => m[1]);
    if (items.length < 2) problem(file, 'kruimelpad ontbreekt');
    else if (!/\scurrent\b/.test(items[items.length - 1])) problem(file, 'kruimelpad eindigt niet bij de pagina zelf');
  }

  // A named slot of a layout that leaked into the HTML lands in no slot of the
  // element around it, and so is never shown.
  for (const m of text.matchAll(/\sslot="([^"]+)"/g)) {
    if (!ELEMENT_SLOTS.has(m[1])) problem(file, `slot="${m[1]}" bestaat bij geen nldd-element`);
  }

  // The tab and home screen show grip's mark, never the design system's own icon.
  const icons = [...text.matchAll(/<link rel="(?:icon|apple-touch-icon)"[^>]*\shref="([^"]*)"/g)].map((m) => m[1]);
  if (icons.join(' ') !== GRIP_ICONS.join(' ')) problem(file, `pictogrammen ${icons.join(', ') || 'ontbreken'}`);

  if (/[\u2013\u2014]/.test(text)) problem(file, 'en of em dash');
  if (/\/Users\/|\/home\/[a-z]/.test(text)) problem(file, 'lokaal pad');
  const bodies = (text.match(/data-pagefind-body/g) ?? []).length;
  if (bodies > 1) problem(file, `${bodies} keer data-pagefind-body`);
}

// Every nldd-* element is defined by an imported entry point.
const require = createRequire(join(ROOT, 'package.json'));
const registry = readFileSync(join(ROOT, 'src', 'nldd-components.js'), 'utf8');
const defined = new Set();
for (const m of registry.matchAll(/import '(@nldd\/design-system\/[^']+)'/g)) {
  const source = readFileSync(require.resolve(m[1]), 'utf8');
  for (const d of source.matchAll(/(?:customElements\.define|customElement)\(\s*'(nldd-[a-z-]+)'/g)) defined.add(d[1]);
}
const used = new Map();
for (const [file, text] of html) {
  for (const m of text.matchAll(/<(nldd-[a-z-]+)/g)) used.set(m[1], file);
}
for (const file of walk(join(ROOT, 'src', 'scripts'))) {
  for (const m of readFileSync(file, 'utf8').matchAll(/(?:createElement|element)\('(nldd-[a-z-]+)'/g)) used.set(m[1], file);
}
for (const [tag, file] of used) {
  if (!defined.has(tag)) problem(file, `${tag} wordt niet geregistreerd in src/nldd-components.js`);
}

// A page per persona and per decision, and a search index.
for (const name of readdirSync(join(DOCS, 'personas'))) {
  const code = /^([A-Z]+-[A-Z]+)\.md$/.exec(name)?.[1];
  if (code && !existsSync(join(DIST, 'personaboek', code, 'index.html'))) problems.push(`persona ${code} heeft geen pagina`);
}
for (const name of readdirSync(join(DOCS, 'adr'))) {
  const slug = /^(\d{4}-.+)\.md$/.exec(name)?.[1];
  if (slug && !existsSync(join(DIST, 'besluiten', slug, 'index.html'))) problems.push(`besluit ${slug} heeft geen pagina`);
}
// Every document in exactly one chapter, and a page per chapter.
const docIds = [
  ...readdirSync(DOCS).filter((n) => n.endsWith('.md') && n !== 'README.md').map((n) => n.slice(0, -3)),
  ...readdirSync(join(DOCS, 'hierarchie')).filter((n) => n.endsWith('.md')).map((n) => `hierarchie/${n.slice(0, -3)}`),
];
for (const id of docIds) {
  const count = CHAPTERS.filter((c) => chapterDocs(c).includes(id)).length;
  if (count !== 1) problems.push(`docs/${id}.md staat in ${count} hoofdstukken`);
}
for (const c of CHAPTERS) {
  for (const id of chapterDocs(c)) {
    if (!docIds.includes(id)) problems.push(`hoofdstuk ${c.slug} noemt docs/${id}.md, dat niet bestaat`);
  }
  if (docIds.includes(c.slug)) problems.push(`hoofdstuk ${c.slug} valt samen met docs/${c.slug}.md`);
  if (!existsSync(join(DIST, 'documentatie', c.slug, 'index.html'))) problems.push(`hoofdstuk ${c.slug} heeft geen pagina`);
}
for (const asset of ['pagefind/pagefind.js', 'pagefind/pagefind-entry.json']) {
  if (!existsSync(join(DIST, asset))) problems.push(`zoekindex: ${asset} ontbreekt`);
}

if (problems.length) {
  console.error(problems.join('\n'));
  console.error(`\n${problems.length} problemen in ${pages.length} pagina's`);
  process.exit(1);
}
console.log(`check: ${pages.length} pagina's, ${used.size} soorten nldd-elementen, geen problemen`);
