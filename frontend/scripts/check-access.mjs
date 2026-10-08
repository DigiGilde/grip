#!/usr/bin/env node
/**
 * Opens every page as every kind of reader and checks what a reader without
 * the right gets to see.
 *
 * The server decides access; this checks that the screen tells the truth about
 * it. Per route and person, in a real (headless) browser:
 *
 *   settled   the page comes to rest: no "Bezig met laden" left when the
 *             requests are done
 *   state     what it rests in: content, empty, no-access, not-found,
 *             unreachable, failed (the `data-state` of `@/ui/layout`)
 *   refused   a request the server refused (403, 404) that the page does not
 *             explain with a no-access or not-found state
 *   action    a button that changes something, shown to a reader the server
 *             would refuse (read from the permissions the API itself returns)
 *   leak      an amount, scale or rate on the page of a reader who may not
 *             read money
 *
 * Usage (servers must be running; see `just check-access`):
 *   node scripts/check-access.mjs --base http://access.localhost:5183
 *     [--persons "Lars Lezer,Daan Developer"] [--only /opdrachten]
 *     [--json out.json] [--shots dir] [--verbose]
 *
 * Use a host name of your own in --base: the person is chosen with the
 * development cookie, which must not land on the localhost you work in.
 * Exit code 1 when there are findings.
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright-core';

const args = Object.fromEntries(
  process.argv.slice(2).flatMap((arg, i, all) => {
    if (!arg.startsWith('--')) return [];
    const next = all[i + 1];
    return [[arg.slice(2), next && !next.startsWith('--') ? next : true]];
  }),
);

const BASE = String(args.base ?? 'http://access.localhost:5183').replace(/\/$/, '');
const ONLY = typeof args.only === 'string' ? args.only : null;
const VERBOSE = Boolean(args.verbose);
const SHOTS = typeof args.shots === 'string' ? args.shots : null;
const DEV_PERSON_COOKIE = 'grip_dev_person';
const SETTLE_MS = 6000;

/**
 * The readers, by what they are. The first example person that fits each kind
 * is used; a kind nobody fits is skipped and named in the output.
 */
const KINDS = [
  { kind: 'beheerder', fits: (p) => p.functions.includes('beheerder') },
  {
    kind: 'eigenaar',
    fits: (p) => p.functions.length === 0 && p.relations.includes('assignment_manager'),
  },
  {
    kind: 'planner en manager',
    fits: (p) => p.functions.includes('planner') && p.relations.includes('assignment_manager'),
  },
  {
    kind: 'alleen planner',
    fits: (p) => p.functions.join() === 'planner' && p.relations.length === 0,
  },
  { kind: 'lezer', fits: (p) => p.functions.join() === 'lezer' },
  {
    kind: 'teamlid',
    fits: (p) => p.functions.length === 0 && p.relations.join() === 'team_member',
  },
  { kind: 'aanvrager', fits: (p) => p.functions.join() === 'aanvrager' },
  { kind: 'zonder rechten', fits: (p) => p.functions.length === 0 && p.relations.length === 0 },
];

/** Who may read amounts anywhere; for the others an amount on a page is a leak. */
const READS_MONEY = new Set(['beheerder', 'eigenaar', 'planner en manager', 'lezer']);
/** Who never changes anything outside their own account. */
const ONLY_READS = new Set(['lezer', 'teamlid', 'zonder rechten']);

/** Requests a page may make to find out what is there; a refusal of these is an answer, not a fault. */
const PROBES = [
  /\/api\/tasks\/bar/,
  /\/api\/updates/,
  /\/api\/push\//,
  /\/api\/auth\//,
  // Whether the reader may see someone's declarability is answered by asking.
  /\/api\/kpi\//,
];

/** Buttons that change nothing: they show, fetch, copy or go somewhere. */
const HARMLESS =
  /^(details$|toon|bekijk|download|kopieer|eerdere|latere|probeer opnieuw|ga naar|terug|naar |zoek|vandaag|meer|sluit$|annuleer|installeer|zet meldingen|leg een passkey|log uit|uitloggen)/i;
/** Pages about the reader's own account: acting there is theirs to do. */
const OWN_PAGES = [/^\/beveiliging/, /^\/meldingen/, /^\/bewijs-controleren/, /^\/tekenen/];

// An amount or a rate category. The scale of a vacancy is public (it is on
// the published vacancy), so a scale counts only outside the vacancy pages.
const MONEY = /€\s?\d|\bcategorie [A-E]\b/i;
const SCALE = /\bschaal \d/i;

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
    'login',
    'noAccess',
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
              assignmentId: assignment.id,
            });
        } else {
          out.push({
            name: `${key} (${assignment.phase})`,
            url: base,
            assignmentId: assignment.id,
          });
        }
      }
    } else if (template_.includes(':topic')) {
      for (const topic of topics)
        out.push({ name: `rapportage /${topic}`, url: template_.replace(':topic', topic) });
    } else if (key === 'vacancyDetail' && vacancy) {
      const base = template_.replace(':vacancyId', vacancy.id);
      for (const tab of vacancyTabs)
        out.push({
          name: `vacature /${tab}`,
          url: tab ? `${base}/${tab}` : base,
          vacancyId: vacancy.id,
        });
    } else {
      const params = template_.match(/:\w+/g) ?? [];
      if (params.some((param) => !fill[param])) continue;
      let url = template_;
      for (const param of params) url = url.replace(param, fill[param]);
      out.push({
        name: template_,
        url,
        ...(template_.includes(':vacancyId') ? { vacancyId: vacancy.id } : {}),
        ...(template_.includes(':personId') ? { personId: person.id } : {}),
      });
    }
  }
  return ONLY ? out.filter((route) => route.url.startsWith(ONLY)) : out;
}

/** Runs in the page: what it rests in and what it offers. */
function inspect(readerName) {
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return false;
    const style = getComputedStyle(el);
    return style.display !== 'none' && style.visibility !== 'hidden';
  };
  // Closed sheets and dialogs keep their content in the page; it is not shown.
  const hidden = (el) =>
    Boolean(
      el.closest('nldd-sheet:not([open]), nldd-modal:not([open]), nldd-modal-dialog:not([open])'),
    );
  const main = document.querySelector('main') ?? document.body;
  const all = [...main.querySelectorAll('*')].filter((el) => !hidden(el));

  const states = [
    ...new Set(all.filter((el) => el.dataset?.state && visible(el)).map((el) => el.dataset.state)),
  ];
  const loading =
    states.includes('loading') ||
    all.some((el) => el.getAttribute('variant') === 'loading' && visible(el));

  // The bar of the application (navigation, account) is not the page; a
  // button that is a link goes somewhere and changes nothing.
  const inBar = (el) =>
    Boolean(el.closest('nldd-toolbar, nldd-toolbar-item, nldd-menu-bar, [slot^="toolbar"]'));
  const buttons = all
    .filter(
      (el) => el.tagName === 'NLDD-BUTTON' && visible(el) && !inBar(el) && !el.hasAttribute('href'),
    )
    .map((el) => (el.getAttribute('text') ?? el.textContent ?? '').trim())
    .filter(Boolean);

  // Everything a person can read: text nodes and the text the design system
  // components carry in attributes.
  // A reader may see their own scale and rate: a row that names the reader is theirs.
  const ownRow = (el) => {
    const row = el.closest('nldd-table-row, nldd-list-item, tr');
    if (!row || !readerName) return false;
    return [...row.querySelectorAll('*')].some((cell) =>
      (cell.getAttribute('text') ?? cell.textContent ?? '').includes(readerName),
    );
  };
  const pieces = [];
  for (const el of all) {
    if (!visible(el) || inBar(el) || ownRow(el)) continue;
    for (const name of ['text', 'supporting-text', 'overline', 'value', 'label']) {
      const value = el.getAttribute(name);
      if (value) pieces.push(value);
    }
    for (const node of el.childNodes)
      if (node.nodeType === Node.TEXT_NODE && node.textContent.trim())
        pieces.push(node.textContent.trim());
  }
  const blocks = all.filter((el) => visible(el)).length;
  return { states, loading, buttons, text: pieces.join(' \n '), blocks, title: document.title };
}

function stateOf(found) {
  for (const state of ['no-access', 'not-found', 'unreachable', 'failed']) {
    if (found.states.includes(state)) return state;
  }
  if (found.states.includes('empty')) return found.blocksWithoutState ? 'content' : 'empty';
  return 'content';
}

async function mayActOn(route, person) {
  if (OWN_PAGES.some((own) => own.test(route.url))) return true;
  if (route.assignmentId) {
    const detail = await api(`/api/assignments/${route.assignmentId}`, person.id);
    return Boolean(
      detail &&
      Object.entries(detail.permissions ?? {}).some(([k, v]) => v && !k.startsWith('read_')),
    );
  }
  if (route.vacancyId) {
    const detail = await api(`/api/vacancies/${route.vacancyId}`, person.id);
    return Boolean(detail && Object.values(detail.permissions ?? {}).some(Boolean));
  }
  if (route.personId) return route.personId === person.id || !ONLY_READS.has(person.kind);
  if (route.url.startsWith('/aanvragen'))
    return person.kind === 'aanvrager' || !ONLY_READS.has(person.kind);
  return !ONLY_READS.has(person.kind) &&
    person.kind !== 'aanvrager' &&
    person.kind !== 'alleen planner'
    ? true
    : person.kind === 'alleen planner' &&
        /^\/(inzet|vacatures|team|taken|opdrachten$)/.test(route.url);
}

async function main() {
  const everyone = (await api('/api/people')) ?? [];
  const wanted = typeof args.persons === 'string' ? args.persons.split(',') : null;
  const persons = [];
  const missing = [];
  const described = [];
  for (const candidate of everyone.filter((p) => p.is_active !== false)) {
    const status = await fetch(`${BASE}/api/auth/status`, {
      headers: { Cookie: `${DEV_PERSON_COOKIE}=${candidate.id}` },
    }).then((r) => r.json());
    described.push({
      id: candidate.id,
      name: candidate.name,
      functions: status.functions ?? [],
      relations: status.relations ?? [],
    });
  }
  if (wanted) {
    for (const name of wanted) {
      const person = described.find((p) => p.name === name);
      if (!person) missing.push(name);
      else persons.push({ ...person, kind: KINDS.find((k) => k.fits(person))?.kind ?? 'anders' });
    }
  } else {
    for (const { kind, fits } of KINDS) {
      const person = described.find(fits);
      if (person) persons.push({ ...person, kind });
      else missing.push(kind);
    }
  }
  if (persons.length === 0)
    throw new Error(`Geen voorbeeldpersoon gevonden op ${BASE}; draaien de servers?`);
  const list = await routes();
  if (SHOTS) mkdirSync(SHOTS, { recursive: true });

  const browser = await chromium.launch({ executablePath: browserPath(), headless: true });
  const results = [];
  for (const person of persons) {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 1200 },
      colorScheme: 'dark',
    });
    await context.addCookies([{ name: DEV_PERSON_COOKIE, value: person.id, url: BASE }]);
    const page = await context.newPage();
    let refused = [];
    page.on('response', (response) => {
      const url = new URL(response.url());
      if (!url.pathname.startsWith('/api/')) return;
      if (response.request().method() !== 'GET') return;
      if (response.status() === 403 || response.status() === 404)
        refused.push(`${response.status()} ${url.pathname}`);
    });
    for (const route of list) {
      refused = [];
      const result = { person: person.name, kind: person.kind, ...route, findings: [] };
      try {
        await page.goto(`${BASE}${route.url}`, { waitUntil: 'networkidle', timeout: 30000 });
        const started = Date.now();
        let found = await page.evaluate(inspect, person.name);
        while (found.loading && Date.now() - started < SETTLE_MS) {
          await page.waitForTimeout(250);
          found = await page.evaluate(inspect, person.name);
        }
        if (found.blocks === 0) throw new Error('lege pagina: de applicatie toont niets');
        result.state = stateOf(found);
        if (found.loading)
          result.findings.push({
            kind: 'settled',
            what: `nog "Bezig met laden" na ${SETTLE_MS / 1000} s`,
          });

        const unexplained = refused.filter((line) => !PROBES.some((probe) => probe.test(line)));
        if (unexplained.length > 0 && !['no-access', 'not-found'].includes(result.state))
          result.findings.push({
            kind: 'refused',
            what: [...new Set(unexplained)].slice(0, 3).join(', '),
          });

        if (!(await mayActOn(route, person))) {
          const actions = found.buttons.filter((text) => !HARMLESS.test(text));
          if (actions.length > 0)
            result.findings.push({
              kind: 'action',
              what: [...new Set(actions)].slice(0, 5).join(' | '),
            });
        }

        const ownPage =
          route.personId === person.id || OWN_PAGES.some((own) => own.test(route.url));
        const clientPage = route.url.startsWith('/aanvragen') && person.kind === 'aanvrager';
        if (!READS_MONEY.has(person.kind) && !ownPage && !clientPage) {
          const hit =
            found.text.match(MONEY) ??
            (route.url.startsWith('/vacatures') ? null : found.text.match(SCALE));
          if (hit) {
            const at = found.text.indexOf(hit[0]);
            result.findings.push({
              kind: 'leak',
              what: found.text.slice(Math.max(0, at - 40), at + 40).replace(/\s+/g, ' '),
            });
          }
        }
        if (SHOTS && (result.findings.length > 0 || args.all)) {
          const file = `${route.name.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '')}-${person.kind.replace(/\s+/g, '-')}.png`;
          await page.screenshot({ path: path.join(SHOTS, file) });
        }
      } catch (error) {
        result.state = 'error';
        result.findings.push({ kind: 'error', what: String(error).slice(0, 120) });
      }
      results.push(result);
    }
    await context.close();
  }
  await browser.close();

  const kinds = ['settled', 'refused', 'action', 'leak', 'error'];
  console.log(`\n${list.length} adressen, ${persons.length} lezers, ${results.length} pagina's\n`);
  console.log(
    ['lezer'.padEnd(34), 'inhoud', 'leeg', 'geen toegang', 'niet gevonden', ...kinds].join('  '),
  );
  for (const person of persons) {
    const own = results.filter((r) => r.person === person.name);
    const n = (state) => String(own.filter((r) => r.state === state).length);
    const f = (kind) => String(own.filter((r) => r.findings.some((x) => x.kind === kind)).length);
    console.log(
      [
        `${person.name} (${person.kind})`.padEnd(34),
        n('content').padStart(6),
        n('empty').padStart(4),
        n('no-access').padStart(12),
        n('not-found').padStart(13),
        ...kinds.map((kind) => f(kind).padStart(kind.length)),
      ].join('  '),
    );
  }
  if (missing.length > 0) console.log(`\nNiet gevonden, dus niet nagelopen: ${missing.join(', ')}`);
  const withFindings = results.filter((r) => r.findings.length > 0);
  if (withFindings.length > 0) console.log('');
  for (const result of withFindings) {
    if (!VERBOSE && withFindings.length > 60 && withFindings.indexOf(result) >= 60) break;
    for (const finding of result.findings)
      console.log(
        `${finding.kind.padEnd(8)} ${result.kind.padEnd(18)} ${result.url}\n         ${finding.what}`,
      );
  }
  if (typeof args.json === 'string') writeFileSync(args.json, JSON.stringify(results, null, 2));
  console.log(
    `\n${results.length - withFindings.length} van ${results.length} pagina's zonder bevinding`,
  );
  process.exit(withFindings.length > 0 ? 1 : 0);
}

await main();
