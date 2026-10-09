#!/usr/bin/env node
/**
 * Runs axe-core on every page, in a real (headless) browser.
 *
 * A machine finds a part of what WCAG asks: names, roles, contrast, structure.
 * What it cannot judge (focus order, what a screen reader hears, whether a
 * drawing has an equal alternative) is in docs/toegankelijkheid.md.
 *
 * Per route, reader, width and theme it reports the rules that fail, with the
 * elements. With --open it also opens what a page offers (sheets, the first
 * row menu, the account menu) and checks those while they are open.
 *
 * Usage (servers must be running; see `just check-a11y`):
 *   node scripts/check-a11y.mjs --base http://a11y.localhost:5183
 *     [--only /opdrachten] [--persons "Priya Product"] [--widths 1280,390]
 *     [--themes dark,light] [--open] [--json out.json] [--verbose]
 *
 * Use a host name of your own in --base: the person is chosen with the
 * development cookie, which must not land on the localhost you work in.
 * --open clicks buttons that open a form; nothing is submitted, but run it
 * against a database you can throw away.
 * Exit code 1 when a rule fails.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { chromium } from 'playwright-core';

const args = Object.fromEntries(
  process.argv.slice(2).flatMap((arg, i, all) => {
    if (!arg.startsWith('--')) return [];
    const next = all[i + 1];
    return [[arg.slice(2), next && !next.startsWith('--') ? next : true]];
  }),
);

const BASE = String(args.base ?? 'http://a11y.localhost:5183').replace(/\/$/, '');
const ONLY = typeof args.only === 'string' ? args.only : null;
const VERBOSE = Boolean(args.verbose);
const OPEN = Boolean(args.open);
const WIDTHS = String(args.widths ?? '1280,390')
  .split(',')
  .map(Number);
const THEMES = String(args.themes ?? 'dark,light').split(',');
const DEV_PERSON_COOKIE = 'grip_dev_person';
const SETTLE_MS = 6000;

/** WCAG 2.1 A and AA, plus the best practices that say something about structure. */
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'];

/** Buttons that open a form without changing anything until it is submitted. */
const OPENS_FORM =
  /^(nieuwe? |wijzig|voeg |leg .* vast$|stel .* in$|bied aan|schrijf|vraag om|zet iemand|details$)/i;

const require = createRequire(import.meta.url);
const AXE = require.resolve('axe-core/axe.min.js');
const src = path.resolve(import.meta.dirname, '../src');

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

/** Every route with real ids, as the default (managing) person sees them. */
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
  const template = ((await api('/api/form-templates')) ?? [])[0];
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
    ':templateId': template?.id,
  };
  const out = [];
  const skip = new Set([
    'assignmentFinance',
    'assignmentStaffing',
    'assignmentBudget',
    'assignmentQuote',
    'assignmentMonthClose',
    'ratesLegacy',
  ]);
  for (const [key, template_] of Object.entries(paths)) {
    if (skip.has(key)) continue;
    if (template_.includes(':assignmentId')) {
      for (const assignment of perPhase) {
        const base = template_.replace(':assignmentId', assignment.id);
        if (key === 'assignmentDetail') {
          for (const tab of assignmentTabs)
            out.push({
              name: `opdracht (${assignment.phase}) /${tab}`,
              url: tab ? `${base}/${tab}` : base,
            });
        } else {
          out.push({ name: `${key} (${assignment.phase})`, url: base });
        }
      }
    } else if (template_.includes(':topic')) {
      for (const topic of topics)
        out.push({ name: `rapportage /${topic}`, url: template_.replace(':topic', topic) });
    } else if (key === 'vacancyDetail' && vacancy) {
      const base = template_.replace(':vacancyId', vacancy.id);
      for (const tab of vacancyTabs)
        out.push({ name: `vacature /${tab}`, url: tab ? `${base}/${tab}` : base });
    } else {
      const params = template_.match(/:\w+/g) ?? [];
      if (params.some((param) => !fill[param])) continue;
      let url = template_;
      for (const param of params) url = url.replace(param, fill[param]);
      out.push({ name: template_, url });
    }
  }
  // A page that does not exist and one the reader may not open: the states.
  out.push({ name: 'niet gevonden', url: '/bestaat-niet' });
  out.push({
    name: 'opdracht die niet bestaat',
    url: '/opdrachten/00000000-0000-4000-8000-000000000000',
  });
  return ONLY ? out.filter((route) => route.url.startsWith(ONLY)) : out;
}

async function settle(page) {
  await page
    .waitForFunction(
      () =>
        !document.querySelector('[data-state="loading"]') &&
        !document.querySelector('nldd-inline-dialog[variant="loading"]'),
      { timeout: SETTLE_MS },
    )
    .catch(() => {});
  await page.waitForTimeout(350);
  // A colour that is still fading in is measured as a contrast it never rests in.
  await page
    .evaluate(() =>
      Promise.race([
        Promise.all(
          document
            .getAnimations()
            .filter((animation) => Number.isFinite(animation.effect?.getComputedTiming().endTime))
            .map((animation) => animation.finished.catch(() => {})),
        ),
        new Promise((resolve) => setTimeout(resolve, 1500)),
      ]),
    )
    .catch(() => {});
}

async function scan(page, context) {
  await page.addScriptTag({ path: AXE }).catch(() => {});
  const result = await page.evaluate(
    async ({ tags, context }) => {
      const outcome = await axe.run(context ?? document, {
        runOnly: { type: 'tag', values: tags },
        resultTypes: ['violations', 'incomplete'],
      });
      const brief = (list) =>
        list.map((violation) => ({
          id: violation.id,
          impact: violation.impact,
          help: violation.help,
          tags: violation.tags.filter((tag) => /^wcag\d|best-practice/.test(tag)),
          nodes: violation.nodes.map((node) => ({
            target: node.target.flat().join(' >>> '),
            html: node.html.slice(0, 200),
            summary: (node.failureSummary ?? '').replace(/\s+/g, ' ').slice(0, 260),
          })),
        }));
      return { violations: brief(outcome.violations), incomplete: brief(outcome.incomplete) };
    },
    { tags: TAGS, context },
  );
  return result;
}

/** Opens what the page offers, one thing at a time, and scans while it is open. */
async function scanOpened(page, record) {
  const candidates = await page.evaluate(
    (pattern) => {
      const re = new RegExp(pattern.source, pattern.flags);
      const visible = (el) => {
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      };
      const main = document.getElementById('inhoud') ?? document.body;
      return [...main.querySelectorAll('nldd-button')]
        .filter((el) => visible(el) && !el.hasAttribute('href') && !el.closest('nldd-sheet'))
        .map((el) => (el.getAttribute('text') ?? el.textContent ?? '').trim())
        .filter((text) => re.test(text))
        .slice(0, 3);
    },
    { source: OPENS_FORM.source, flags: OPENS_FORM.flags },
  );
  for (const text of [...new Set(candidates)]) {
    const button = page.locator(`#inhoud nldd-button[text="${text.replace(/"/g, '\\"')}"]`).first();
    if (!(await button.count())) continue;
    await button.click({ timeout: 2000 }).catch(() => {});
    await page.waitForTimeout(500);
    const opened = await page.evaluate(() => Boolean(document.querySelector('nldd-sheet[open]')));
    if (opened) {
      record(`formulier "${text}"`, await scan(page));
      await page.keyboard.press('Escape');
      await page.waitForTimeout(300);
      const still = await page.evaluate(() => Boolean(document.querySelector('nldd-sheet[open]')));
      if (still) {
        await page.reload({ waitUntil: 'domcontentloaded' });
        await settle(page);
      }
    }
  }
  // The first menu of a row, and the account menu in the bar.
  for (const [label, selector] of [
    ['rijmenu', '#inhoud nldd-icon-button[popup-type="menu"]'],
    ['accountmenu', 'nldd-toolbar-item[slot="end"] [data-account-menu]'],
  ]) {
    const trigger = page.locator(selector).first();
    if (!(await trigger.count())) continue;
    await trigger.click({ timeout: 2000 }).catch(() => {});
    await page.waitForTimeout(350);
    record(label, await scan(page));
    await page.keyboard.press('Escape');
    await page.waitForTimeout(200);
  }
}

async function main() {
  const everyone = (await api('/api/people')) ?? [];
  const wanted = typeof args.persons === 'string' ? args.persons.split(',') : null;
  const readers = [{ kind: 'beheerder (standaard)', id: null }];
  for (const candidate of everyone.filter((p) => p.is_active !== false)) {
    const status = await fetch(`${BASE}/api/auth/status`, {
      headers: { Cookie: `${DEV_PERSON_COOKIE}=${candidate.id}` },
    }).then((r) => r.json());
    const functions = status.functions ?? [];
    const relations = status.relations ?? [];
    if (wanted ? wanted.includes(candidate.name) : false) {
      readers.push({ kind: candidate.name, id: candidate.id });
    } else if (
      !wanted &&
      functions.length === 0 &&
      relations.includes('assignment_manager') &&
      !readers.some((r) => r.kind === 'eigenaar')
    ) {
      readers.push({ kind: 'eigenaar', id: candidate.id });
    } else if (
      !wanted &&
      functions.join() === 'tekenbevoegde' &&
      !readers.some((r) => r.kind === 'tekenbevoegde')
    ) {
      readers.push({ kind: 'tekenbevoegde', id: candidate.id });
    }
  }
  const list = await routes();
  const browser = await chromium.launch({ executablePath: browserPath(), headless: true });
  const findings = [];
  // What axe could not decide by itself (contrast over an image, for instance).
  const unsure = new Map();
  let scans = 0;
  const host = new URL(BASE).hostname;

  for (const reader of readers) {
    for (const width of WIDTHS) {
      for (const theme of THEMES) {
        const context = await browser.newContext({
          viewport: { width, height: 900 },
          colorScheme: theme === 'light' ? 'light' : 'dark',
          locale: 'nl-NL',
        });
        if (reader.id) {
          await context.addCookies([
            { name: DEV_PERSON_COOKIE, value: reader.id, domain: host, path: '/' },
          ]);
        }
        const page = await context.newPage();
        for (const route of list) {
          await page.goto(`${BASE}${route.url}`, { waitUntil: 'domcontentloaded' }).catch(() => {});
          await settle(page);
          const record = (state, outcome) => {
            scans += 1;
            for (const item of outcome.incomplete) {
              unsure.set(item.id, (unsure.get(item.id) ?? 0) + item.nodes.length);
            }
            for (const violation of outcome.violations) {
              // A skip link stands before every landmark by design, and axe
              // exempts one; it does not see that this one is, because the
              // link itself is inside the component's shadow root.
              if (violation.id === 'region') {
                violation.nodes = violation.nodes.filter(
                  (node) => node.target !== 'nldd-skip-link',
                );
                if (violation.nodes.length === 0) continue;
              }
              findings.push({
                rule: violation.id,
                impact: violation.impact,
                help: violation.help,
                tags: violation.tags,
                page: route.name,
                url: route.url,
                state,
                reader: reader.kind,
                width,
                theme,
                nodes: violation.nodes,
              });
            }
          };
          record('pagina', await scan(page));
          // Opening things once is enough: wide, dark, as who may act.
          if (OPEN && reader.id === null && width === WIDTHS[0] && theme === THEMES[0]) {
            await scanOpened(page, record);
          }
          if (VERBOSE) process.stderr.write(`${reader.kind} ${width} ${theme} ${route.name}\n`);
        }
        await context.close();
      }
    }
  }
  await browser.close();

  // One line per rule and page: the same element fails in every theme and width.
  const perRule = new Map();
  for (const finding of findings) {
    const entry = perRule.get(finding.rule) ?? {
      impact: finding.impact,
      help: finding.help,
      tags: finding.tags,
      pages: new Map(),
      nodes: 0,
    };
    const key = `${finding.page}${finding.state === 'pagina' ? '' : ` [${finding.state}]`}`;
    const where = entry.pages.get(key) ?? { variants: new Set(), targets: new Set() };
    where.variants.add(`${finding.reader}/${finding.width}/${finding.theme}`);
    for (const node of finding.nodes) where.targets.add(node.target);
    entry.pages.set(key, where);
    entry.nodes += finding.nodes.length;
    perRule.set(finding.rule, entry);
  }

  console.log(`\n${scans} metingen, ${list.length} routes, ${readers.length} lezers`);
  console.log(`${perRule.size} regels met bevindingen\n`);
  console.log("| Regel | Ernst | Pagina's | Elementen | Wat |");
  console.log('|---|---|---|---|---|');
  const sorted = [...perRule.entries()].sort((a, b) => b[1].pages.size - a[1].pages.size);
  for (const [rule, entry] of sorted) {
    console.log(
      `| ${rule} | ${entry.impact ?? ''} | ${entry.pages.size} | ${entry.nodes} | ${entry.help} |`,
    );
  }
  if (unsure.size > 0) {
    console.log('\nNiet te beslissen door de machine (met de hand nalopen):');
    for (const [rule, count] of unsure) console.log(`- ${rule}: ${count} elementen`);
  }
  if (VERBOSE || args.detail) {
    for (const [rule, entry] of sorted) {
      console.log(`\n## ${rule} (${entry.tags.join(', ')})`);
      for (const [pageName, where] of entry.pages) {
        console.log(`- ${pageName}: ${[...where.targets].slice(0, 4).join(' | ')}`);
      }
    }
  }
  if (typeof args.json === 'string') {
    writeFileSync(args.json, JSON.stringify(findings, null, 1));
  }
  process.exit(perRule.size > 0 ? 1 : 0);
}

await main();
