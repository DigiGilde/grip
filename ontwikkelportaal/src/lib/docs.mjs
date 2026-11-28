// Where the Markdown lives and which page each file becomes. Shared by the
// content collections, the remark plugin and the pages, so a link and the
// page it points at cannot disagree.
import { existsSync, readFileSync, statSync } from 'node:fs';
import { join, posix, relative, resolve, sep } from 'node:path';

// The npm scripts run in ontwikkelportaal/; the Markdown sits next to it. Resolved from
// the working directory because the build bundles this module elsewhere.
export const DOCS_ROOT = resolve(process.cwd(), '../docs');

export const ROUTES = {
  start: '/',
  docs: '/documentatie/',
  adr: '/besluiten/',
  book: '/personaboek/',
  bookAbout: '/personaboek/over/',
  search: '/zoeken/',
};

const ADR_FILE = /^adr\/(\d{4}-[^/]+)\.md$/;
const PERSONA_FILE = /^personas\/([A-Z]+-[A-Z]+)\.md$/;

/** Path of a file or directory relative to docs/, posix style. */
export function docsRelative(absolute) {
  const rel = relative(DOCS_ROOT, absolute);
  if (rel.startsWith('..') || rel.includes(`..${sep}`)) return null;
  return rel.split(sep).join('/');
}

function isDirectory(absolute) {
  try {
    return statSync(absolute).isDirectory();
  } catch {
    return false;
  }
}

/**
 * The route of a docs/ path (relative, posix), or null when the site has no
 * page for it. Directories map to their README.
 */
export function routeFor(rel, absolute) {
  let path = rel.replace(/\/$/, '');
  if (path === 'personas' && absolute && isDirectory(absolute)) return ROUTES.book;
  if (absolute && isDirectory(absolute)) {
    if (!existsSync(join(absolute, 'README.md'))) return null;
    path = path ? `${path}/README.md` : 'README.md';
  }
  if (path === 'README.md') return ROUTES.docs;
  if (path === 'adr/README.md') return ROUTES.adr;
  if (path === 'personas/README.md') return ROUTES.bookAbout;
  const adr = ADR_FILE.exec(path);
  if (adr) return `${ROUTES.adr}${adr[1]}/`;
  const persona = PERSONA_FILE.exec(path);
  if (persona) return `${ROUTES.book}${persona[1]}/`;
  if (/^[^/]+\.md$/.test(path) || /^hierarchie\/[^/]+\.md$/.test(path)) {
    return `${ROUTES.docs}${path.replace(/\.md$/, '')}/`;
  }
  return null;
}

/** The text of the first level-one heading of a Markdown file. */
export function firstHeading(text) {
  const match = /^# (.+)$/m.exec(text);
  return match ? match[1].trim() : '';
}

const STATUS_LINE = /^Status:\s*(.+)$/m;
const STATUS_PARTS = /^([^(.]+?)\s*(?:\((\d{4}-\d{2}-\d{2})\))?\s*(?:\.\s*(.*))?$/;

/** What a decision record says about itself: number, title, status, date. */
export function adrMeta(filePath) {
  const text = readFileSync(filePath, 'utf8');
  const name = posix.basename(filePath.split(sep).join('/'));
  const heading = /^(\d{4})\s+(.+)$/.exec(firstHeading(text));
  const statusLine = STATUS_LINE.exec(text);
  const parts = statusLine ? STATUS_PARTS.exec(statusLine[1].trim()) : null;
  const meta = {
    number: name.slice(0, 4),
    headingNumber: heading?.[1],
    title: heading?.[2],
    status: parts?.[1]?.trim(),
  };
  if (parts?.[2]) meta.date = parts[2];
  return meta;
}
