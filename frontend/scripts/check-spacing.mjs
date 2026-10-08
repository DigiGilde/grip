#!/usr/bin/env node
/**
 * Measures the spacing of every page in a real (headless) browser.
 *
 * docs/ontwerp.md says what a finished screen looks like: one left edge, gaps
 * from one scale, controls of one height in a row. A test without a browser
 * cannot see that, and a hidden browser tab measures wrong. This script loads
 * each route as each example person at two widths and reports, per page:
 *
 *   collapsed   an element without a height whose content is drawn anyway
 *   overlap     two blocks under each other that overlap
 *   touching    two different blocks under each other with no space between
 *   off-scale   a gap that is not a step of the scale
 *   edge        a block that starts left of or right of its siblings
 *   height      controls in one row with different heights
 *   tight       text closer than 8 to the edge of the box it sits in
 *   overflow    the page scrolls sideways
 *   clipped     text cut off by its box
 *
 * Usage (servers must be running; see `just check-spacing`):
 *   node scripts/check-spacing.mjs --base http://spacing.localhost:5231
 *     [--persons "Bente Beheer,Lotte Leiding"] [--widths 1280,390]
 *     [--only /beheer] [--json out.json] [--verbose]
 *
 * Exit code 1 when there are findings, so it can guard a change.
 */
import { readFileSync, writeFileSync, existsSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import { chromium } from 'playwright-core';

const args = Object.fromEntries(
  process.argv.slice(2).flatMap((arg, i, all) => {
    if (!arg.startsWith('--')) return [];
    const next = all[i + 1];
    return [[arg.slice(2), next && !next.startsWith('--') ? next : true]];
  }),
);

const BASE = String(args.base ?? 'http://spacing.localhost:5183').replace(/\/$/, '');
const PERSONS = String(args.persons ?? 'Bente Beheer,Lotte Leiding').split(',');
const WIDTHS = String(args.widths ?? '1280,390')
  .split(',')
  .map(Number);
const ONLY = typeof args.only === 'string' ? args.only : null;
const VERBOSE = Boolean(args.verbose);
const DEV_PERSON_COOKIE = 'grip_dev_person';

const src = path.resolve(import.meta.dirname, '../src');

/** `key: 'value'` pairs of an object literal in a source file, so routes cannot drift. */
function literal(file, name) {
  const text = readFileSync(path.join(src, file), 'utf8');
  const start = text.indexOf(`${name} = {`);
  const body = text.slice(start, text.indexOf('}', start));
  return Object.fromEntries(
    [...body.matchAll(/^\s*'?([\w-]+)'?:\s*(?:'([^']*)'|\{)/gm)].map((m) => [m[1], m[2] ?? '']),
  );
}

function browserPath() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const cache = path.join(homedir(), 'Library/Caches/ms-playwright');
  if (existsSync(cache)) {
    const shells = readdirSync(cache)
      .filter((name) => name.startsWith('chromium_headless_shell-'))
      .sort()
      .reverse();
    for (const shell of shells) {
      const dir = path.join(cache, shell);
      const found = readdirSync(dir, { recursive: true }).find((file) =>
        /(^|\/)(headless_shell|chrome-headless-shell)$/.test(String(file)),
      );
      if (found) return path.join(dir, String(found));
    }
  }
  const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  return existsSync(chrome) ? chrome : undefined;
}

async function api(pathname, personId) {
  const response = await fetch(`${BASE}${pathname}`, {
    headers: personId ? { Cookie: `${DEV_PERSON_COOKIE}=${personId}` } : {},
  });
  if (!response.ok) return null;
  const body = await response.json();
  return Array.isArray(body) ? body : (body.items ?? body);
}

/** Every route with real ids from the example data. */
async function routes() {
  const paths = literal('paths.ts', 'PATHS');
  const assignmentTabs = Object.values(
    literal('features/assignments/paths.ts', 'ASSIGNMENT_TAB_SEGMENTS'),
  );
  const vacancyTabs = Object.values(literal('features/vacancies/paths.ts', 'VACANCY_TAB_SEGMENTS'));
  const topics = Object.keys(literal('features/reports/topics.ts', 'TOPICS'));

  const assignments = (await api('/api/assignments')) ?? [];
  const perPhase = [...new Map(assignments.map((a) => [a.phase, a])).values()];
  const vacancy = ((await api('/api/vacancies')) ?? [])[0];
  const person = ((await api('/api/people')) ?? []).find((p) => p.is_active !== false);
  const cost = ((await api('/api/costs')) ?? [])[0];
  let quote = null;
  for (const assignment of assignments) {
    const quotes = await api(`/api/assignments/${assignment.id}/quotes`);
    const list = Array.isArray(quotes) ? quotes : (quotes?.quotes ?? []);
    if (list.length > 0) {
      quote = list[0];
      break;
    }
  }

  const fill = {
    ':vacancyId': vacancy?.id,
    ':personId': person?.id,
    ':costItemId': cost?.id,
    ':quoteId': quote?.id,
  };
  const out = [];
  const skipKeys = new Set([
    'assignmentFinance',
    'assignmentStaffing',
    'assignmentBudget',
    'assignmentQuote',
    'assignmentMonthClose',
    'ratesLegacy',
    'login',
  ]);
  for (const [key, template] of Object.entries(paths)) {
    if (skipKeys.has(key)) continue;
    if (template.includes(':assignmentId')) {
      for (const assignment of perPhase) {
        const base = template.replace(':assignmentId', assignment.id);
        if (key === 'assignmentDetail') {
          for (const tab of assignmentTabs) {
            out.push({
              name: `opdracht (${assignment.phase}) /${tab}`,
              url: tab ? `${base}/${tab}` : base,
            });
          }
        } else {
          out.push({ name: `${key} (${assignment.phase})`, url: base });
        }
      }
    } else if (template.includes(':topic')) {
      for (const topic of topics)
        out.push({ name: `rapportage /${topic}`, url: template.replace(':topic', topic) });
    } else if (key === 'vacancyDetail' && vacancy) {
      const base = template.replace(':vacancyId', vacancy.id);
      for (const tab of vacancyTabs)
        out.push({ name: `vacature /${tab}`, url: tab ? `${base}/${tab}` : base });
    } else {
      const param = template.match(/:\w+/)?.[0];
      if (param && !fill[param]) continue;
      out.push({ name: template, url: param ? template.replace(param, fill[param]) : template });
    }
  }
  return ONLY ? out.filter((route) => route.url.startsWith(ONLY)) : out;
}

/** Runs in the page. Returns the findings for what is on screen. */
function measure() {
  const SCALE = new Set([4, 8, 16, 20, 24, 32, 48]);
  // Composed by the design system: their inside is not ours to space.
  const LEAF = new Set(
    (
      'nldd-table nldd-list nldd-toolbar nldd-tab-bar nldd-step-bar nldd-title nldd-button nldd-banner ' +
      'nldd-inline-dialog nldd-dropdown nldd-text-field nldd-number-field nldd-date-field nldd-search-field ' +
      'nldd-multiline-text-field nldd-checkbox nldd-radio-group nldd-switch nldd-menu nldd-menu-button ' +
      'nldd-icon-button nldd-segmented-control nldd-tag nldd-badge nldd-link nldd-text nldd-rich-text ' +
      'nldd-breadcrumbs nldd-form-field nldd-icon svg table ul ol p'
    ).split(' '),
  );
  const CONTROLS =
    'nldd-button, nldd-dropdown, nldd-text-field, nldd-number-field, nldd-date-field, nldd-search-field, ' +
    'nldd-icon-button, nldd-menu-button, nldd-segmented-control';
  const findings = [];
  const round = (n) => Math.round(n);

  const describe = (el) => {
    if (el.nodeType === Node.TEXT_NODE) return `"${el.textContent.trim().slice(0, 32)}"`;
    const tag = el.tagName.toLowerCase();
    const text = (el.getAttribute('text') || el.textContent || '')
      .trim()
      .replace(/\s+/g, ' ')
      .slice(0, 32);
    return text ? `${tag} "${text}"` : tag;
  };

  const box = (node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      if (!node.textContent.trim()) return null;
      const range = document.createRange();
      range.selectNodeContents(node);
      const rect = range.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 ? rect : null;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return null;
    const style = getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden') return null;
    if (style.position === 'fixed' || style.position === 'absolute') return null;
    const rect = node.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) return rect;
    // A host without a height whose content is drawn anyway (a table cell
    // used outside a row, for instance): the content overflows the host and
    // lands on whatever comes next. Measure what is drawn.
    const drawn = ink(node);
    if (drawn) {
      findings.push({ kind: 'collapsed', gap: Math.round(drawn.height), where: describe(node) });
      return drawn;
    }
    return null;
  };

  /** The union of what an element's descendants draw, through shadow roots. */
  const ink = (el) => {
    let top = Infinity;
    let left = Infinity;
    let bottom = -Infinity;
    let right = -Infinity;
    const visit = (root) => {
      for (const child of root.querySelectorAll('*')) {
        if (child.shadowRoot) visit(child.shadowRoot);
        const hasText = [...child.childNodes].some(
          (n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim(),
        );
        if (!hasText) continue;
        const style = getComputedStyle(child);
        if (style.display === 'none' || style.visibility === 'hidden') continue;
        const r = child.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        top = Math.min(top, r.top);
        left = Math.min(left, r.left);
        bottom = Math.max(bottom, r.bottom);
        right = Math.max(right, r.right);
      }
    };
    if (el.shadowRoot) visit(el.shadowRoot);
    visit(el);
    if (top === Infinity) return null;
    return { top, left, bottom, right, width: right - left, height: bottom - top };
  };

  /** Children that take part in the layout; a box-less wrapper gives its own children. */
  const parts = (el) => {
    const out = [];
    for (const child of el.childNodes) {
      if (child.nodeType === Node.ELEMENT_NODE) {
        if (child.hasAttribute('slot') && el.tagName === 'NLDD-SIMPLE-SECTION') continue;
        const style = getComputedStyle(child);
        if (style.display === 'contents') {
          out.push(...parts(child));
          continue;
        }
        if (style.display.startsWith('inline') && !child.tagName.includes('-')) {
          // Inline text flow: the parent is one block of text.
          return [];
        }
      }
      const rect = box(child);
      if (rect) out.push({ node: child, rect });
    }
    return out;
  };

  const sameRow = (a, b) => {
    const overlap = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    const apart = a.right <= b.left + 1 || b.right <= a.left + 1;
    return apart && overlap > 0.5 * Math.min(a.height, b.height);
  };

  const walk = (el, depth) => {
    if (el.nodeType !== Node.ELEMENT_NODE) return;
    if (LEAF.has(el.tagName.toLowerCase())) return;
    const items = parts(el);
    if (items.length === 0) return;

    const sorted = [...items].sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);
    // Group into rows.
    const rows = [];
    for (const item of sorted) {
      const row = rows.at(-1);
      if (row && row.some((other) => sameRow(other.rect, item.rect))) row.push(item);
      else rows.push([item]);
    }
    const rowBox = (row) => ({
      top: Math.min(...row.map((i) => i.rect.top)),
      bottom: Math.max(...row.map((i) => i.rect.bottom)),
      left: Math.min(...row.map((i) => i.rect.left)),
    });

    for (let i = 1; i < rows.length; i += 1) {
      const above = rowBox(rows[i - 1]);
      const below = rowBox(rows[i]);
      const gap = round(below.top - above.bottom);
      const pair = `${describe(rows[i - 1][0].node)} | ${describe(rows[i][0].node)}`;
      if (gap < -1) findings.push({ kind: 'overlap', gap, where: pair });
      else if (gap <= 1) findings.push({ kind: 'touching', gap, where: pair });
      else if (![...SCALE].some((step) => Math.abs(step - gap) <= 1)) {
        findings.push({ kind: 'off-scale', gap, where: pair });
      }
    }

    // One left edge for the blocks of a stack, near the top of the page tree.
    if (rows.length > 1 && depth <= 3) {
      const lefts = rows.map((row) => round(rowBox(row).left));
      const edge = Math.min(...lefts);
      rows.forEach((row, i) => {
        const style =
          row[0].node.nodeType === Node.ELEMENT_NODE ? getComputedStyle(row[0].node) : null;
        const centred =
          style && (style.textAlign === 'center' || style.marginLeft === style.marginRight);
        if (lefts[i] - edge > 1 && !(centred && lefts[i] - edge > 40)) {
          findings.push({ kind: 'edge', gap: lefts[i] - edge, where: describe(row[0].node) });
        }
      });
    }

    for (const row of rows) {
      if (row.length > 1) {
        const controls = row
          .flatMap((item) =>
            item.node.nodeType !== Node.ELEMENT_NODE
              ? []
              : item.node.matches(CONTROLS)
                ? [item.node]
                : [...item.node.querySelectorAll(CONTROLS)],
          )
          .map((control) => ({ control, rect: control.getBoundingClientRect() }))
          .filter(
            ({ rect }) => rect.height > 0 && row.some((item) => sameRow(item.rect, rect) || true),
          );
        const first = controls[0];
        const inLine = controls.filter(
          ({ rect }) =>
            first &&
            Math.abs(rect.top + rect.height / 2 - (first.rect.top + first.rect.height / 2)) < 12,
        );
        const heights = [...new Set(inLine.map(({ rect }) => round(rect.height)))];
        if (heights.length > 1) {
          findings.push({
            kind: 'height',
            gap: Math.max(...heights) - Math.min(...heights),
            where: `${heights.join('/')} in ${describe(el)}`,
          });
        }
      }
    }

    // Text against the edge of a box of our own making.
    const style = getComputedStyle(el);
    const boxed =
      !el.tagName.includes('-') &&
      (parseFloat(style.borderTopWidth) > 0 ||
        (style.backgroundColor !== 'rgba(0, 0, 0, 0)' && style.backgroundColor !== 'transparent'));
    if (boxed) {
      const own = el.getBoundingClientRect();
      for (const item of items) {
        const inset = Math.min(
          item.rect.left - own.left,
          own.right - item.rect.right,
          item.rect.top - own.top,
          own.bottom - item.rect.bottom,
        );
        if (inset < 7) findings.push({ kind: 'tight', gap: round(inset), where: describe(el) });
      }
    }

    for (const item of items) walk(item.node, depth + 1);
  };

  const roots = [...document.querySelectorAll('nldd-simple-section')].filter(
    (section) => !section.parentElement?.closest('nldd-simple-section'),
  );
  const main = document.querySelector('#inhoud, main');
  for (const root of roots.length > 0 ? roots : main ? [main] : []) walk(root, 0);

  // Sideways scroll, on the document and on the scroller the shell uses.
  const deep = (root, visit) => {
    for (const el of root.querySelectorAll('*')) {
      visit(el);
      if (el.shadowRoot) deep(el.shadowRoot, visit);
    }
  };
  const doc = document.scrollingElement;
  if (doc.scrollWidth > window.innerWidth + 1) {
    findings.push({
      kind: 'overflow',
      gap: doc.scrollWidth - window.innerWidth,
      where: 'document',
    });
  }
  deep(document, (el) => {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const style = getComputedStyle(el);
    const scrolls = style.overflowX === 'auto' || style.overflowX === 'scroll';
    if (
      scrolls &&
      el.scrollWidth > el.clientWidth + 1 &&
      rect.height > 200 &&
      rect.width > window.innerWidth * 0.6
    ) {
      findings.push({
        kind: 'overflow',
        gap: el.scrollWidth - el.clientWidth,
        where: describe(el),
      });
    }
    const hides = style.overflowX === 'hidden' || style.overflowX === 'clip';
    const hasText = [...el.childNodes].some(
      (n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim(),
    );
    if (
      hides &&
      hasText &&
      style.textOverflow !== 'ellipsis' &&
      el.scrollWidth > el.clientWidth + 1
    ) {
      findings.push({ kind: 'clipped', gap: el.scrollWidth - el.clientWidth, where: describe(el) });
    }
    if (hasText && rect.right > window.innerWidth + 1 && rect.left < window.innerWidth) {
      findings.push({
        kind: 'clipped',
        gap: round(rect.right - window.innerWidth),
        where: describe(el),
      });
    }
  });

  const title = document.querySelector('#page-heading')?.textContent?.trim() ?? document.title;
  return { title, findings, blocks: roots.length };
}

const KINDS = [
  'collapsed',
  'overlap',
  'touching',
  'off-scale',
  'edge',
  'height',
  'tight',
  'overflow',
  'clipped',
];

async function main() {
  const people = (await api('/api/people')) ?? [];
  const persons = PERSONS.map((name) => people.find((p) => p.name === name.trim())).filter(Boolean);
  if (persons.length === 0)
    throw new Error(`No example person found at ${BASE}; are the servers running?`);
  const list = await routes();

  const browser = await chromium.launch({ executablePath: browserPath(), headless: true });
  const results = [];
  for (const person of persons) {
    for (const width of WIDTHS) {
      const context = await browser.newContext({
        viewport: { width, height: 900 },
        colorScheme: 'dark',
      });
      await context.addCookies([{ name: DEV_PERSON_COOKIE, value: person.id, url: BASE }]);
      const page = await context.newPage();
      for (const route of list) {
        try {
          await page.goto(`${BASE}${route.url}`, { waitUntil: 'networkidle', timeout: 30000 });
          await page.waitForFunction(
            () => !document.querySelector('nldd-inline-dialog[variant="loading"]'),
            null,
            {
              timeout: 10000,
            },
          );
          await page.waitForTimeout(250);
          const measured = await page.evaluate(measure);
          results.push({ person: person.name, width, ...route, ...measured });
        } catch (error) {
          results.push({
            person: person.name,
            width,
            ...route,
            title: '',
            findings: [],
            error: String(error).slice(0, 120),
          });
        }
      }
      await context.close();
    }
  }
  await browser.close();

  const count = (result) =>
    Object.fromEntries(
      KINDS.map((kind) => [kind, result.findings.filter((f) => f.kind === kind).length]),
    );
  const weight = (result) => {
    const c = count(result);
    return (
      c.collapsed * 100 +
      c.overlap * 100 +
      c.touching * 20 +
      c.overflow * 20 +
      c.clipped * 10 +
      c.height * 5 +
      c.tight * 5 +
      c.edge * 3 +
      c['off-scale']
    );
  };
  results.sort((a, b) => weight(b) - weight(a));

  const totals = Object.fromEntries(KINDS.map((kind) => [kind, 0]));
  const pad = (text, n) => String(text).padEnd(n).slice(0, n);
  console.log(
    `${pad('pagina', 44)} ${pad('persoon', 14)} ${pad('br.', 5)} ${KINDS.map((k) => pad(k, 9)).join(' ')}`,
  );
  for (const result of results) {
    const c = count(result);
    for (const kind of KINDS) totals[kind] += c[kind];
    const any = result.findings.length > 0 || result.error;
    if (!any && !VERBOSE) continue;
    console.log(
      `${pad(result.name, 44)} ${pad(result.person, 14)} ${pad(result.width, 5)} ${KINDS.map((k) => pad(c[k] || '', 9)).join(' ')}${result.error ? ` FOUT ${result.error}` : ''}`,
    );
    if (VERBOSE)
      for (const f of result.findings)
        console.log(`    ${pad(f.kind, 10)} ${pad(f.gap, 5)} ${f.where}`);
  }
  const clean = results.filter((r) => r.findings.length === 0 && !r.error).length;
  console.log(
    `\n${results.length} metingen, ${clean} zonder bevinding. Totaal: ${KINDS.map((k) => `${k} ${totals[k]}`).join(', ')}`,
  );
  if (typeof args.json === 'string') writeFileSync(args.json, JSON.stringify(results, null, 2));
  process.exit(results.some((r) => r.findings.length > 0) ? 1 : 0);
}

await main();
