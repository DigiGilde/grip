#!/usr/bin/env node
/**
 * Measures how fast the pages are for every kind of reader, against a budget.
 *
 * Per page and reader, in a real (headless) browser on a warm server:
 *
 *   usable     milliseconds from navigation until the page shows its content:
 *              nothing loading and no request to the API still running
 *   calls      the requests to the API the page makes on load
 *   slowest    the slowest of those, with its time
 *   sql        the most statements one request ran, and its time in the
 *              database (from the Server-Timing header of the development
 *              server; a dash when the server does not send it)
 *   kB         what the API sent for the page, as it went over the line
 *   long       milliseconds the main thread was blocked in tasks over 50 ms
 *   MB         the JavaScript heap after the page settled
 *
 * The budget (docs/snelheid.md): a page is usable within one second, no
 * request on load takes more than 300 ms, and no request runs more than
 * 50 statements.
 *
 * Usage (servers must be running; see `just check-speed`):
 *   node scripts/check-speed.mjs --base http://speed.localhost:5184
 *     [--only /inzet] [--readers beheerder,eigenaar] [--json out.json]
 *     [--calls] [--api]
 *
 * --calls lists every request per page; --api skips the browser pages and
 * only times the requests the pages were seen to make (needs an earlier
 * --json file to read them from: --api out.json).
 *
 * Use a host name of your own in --base: the reader is chosen with the
 * development cookie, which must not land on the localhost you work in.
 * Exit code 1 when something is over budget.
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { chromium } from 'playwright-core';

const args = Object.fromEntries(
  process.argv.slice(2).flatMap((arg, i, all) => {
    if (!arg.startsWith('--')) return [];
    const next = all[i + 1];
    return [[arg.slice(2), next && !next.startsWith('--') ? next : true]];
  }),
);

const BASE = String(args.base ?? 'http://speed.localhost:5184').replace(/\/$/, '');
const ONLY = typeof args.only === 'string' ? args.only : null;
const READERS = typeof args.readers === 'string' ? args.readers.split(',') : null;
const DEV_PERSON_COOKIE = 'grip_dev_person';

const BUDGET = { usableMs: 1000, callMs: 300, statements: 50 };
const SETTLE_MS = 30000;
const RETRY_BELOW_MS = 3000;
const QUIET_MS = 250;

const REPORT_TOPICS = [
  'omzet',
  'bezetting',
  'pijplijn',
  'kosten',
  'declarabiliteit',
  'open-rollen',
  'jaarverantwoording',
];
const ASSIGNMENT_TABS = ['', 'taken', 'financieel', 'bemensing', 'begroting', 'maandafsluiting'];

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

/** One reader of each kind, chosen by what the server says they are. */
async function readers() {
  const everyone = ((await api('/api/people')) ?? []).filter((p) => p.is_active !== false);
  if (everyone.length === 0)
    throw new Error(`Geen personen gevonden op ${BASE}; draaien de servers?`);
  const assignments = (await api('/api/assignments')) ?? [];
  const owned = new Map();
  for (const assignment of assignments) {
    const owner = everyone.find((p) => p.name === assignment.owner_name)?.id;
    if (owner) owned.set(owner, (owned.get(owner) ?? 0) + 1);
  }
  const reports = new Map();
  for (const person of everyone)
    if (person.manager_id)
      reports.set(person.manager_id, (reports.get(person.manager_id) ?? 0) + 1);

  const status = async (person) =>
    fetch(`${BASE}/api/auth/status`, {
      headers: { Cookie: `${DEV_PERSON_COOKIE}=${person.id}` },
    }).then((r) => r.json());
  const found = [];
  const take = (kind, person) => {
    if (person && !found.some((f) => f.id === person.id)) found.push({ kind, ...person });
  };
  const most = (counts) =>
    everyone.filter((p) => counts.has(p.id)).sort((a, b) => counts.get(b.id) - counts.get(a.id))[0];

  // The default person of development is the beheerder.
  const me = await fetch(`${BASE}/api/auth/status`).then((r) => r.json());
  take(
    'beheerder',
    everyone.find((p) => p.id === (me.person?.id ?? me.person_id)) ?? {
      id: null,
      name: 'beheerder',
    },
  );
  take('eigenaar', most(owned));
  take('leidinggevende', most(reports));
  let planner = null;
  let lezer = null;
  let member = null;
  for (const person of everyone) {
    if (planner && lezer && member) break;
    if (found.some((f) => f.id === person.id)) continue;
    const s = await status(person);
    const functions = s.functions ?? [];
    const relations = s.relations ?? [];
    if (!planner && functions.includes('planner')) planner = person;
    else if (!lezer && functions.join() === 'lezer') lezer = person;
    else if (!member && functions.length === 0 && relations.join() === 'team_member')
      member = person;
  }
  take('planner', planner);
  take('lezer', lezer);
  take('teamlid', member);
  return READERS ? found.filter((f) => READERS.includes(f.kind)) : found;
}

/** The pages a reader opens, with ids of things that reader can see. */
async function pages(reader) {
  const assignments = (await api('/api/assignments', reader.id)) ?? [];
  const running = assignments.find((a) => a.phase === 'active') ?? assignments[0];
  const vacancy = ((await api('/api/vacancies', reader.id)) ?? [])[0];
  const out = [
    ['Start', '/'],
    ['Taken', '/taken'],
    ['Wat is er gebeurd', '/wat-is-er-gebeurd'],
    ['Opdrachten', '/opdrachten'],
    ['Inzet', '/inzet'],
    ['Kosten', '/kosten'],
    ['Factureren', '/factureren'],
    ['Team', '/team'],
    ['Vacatures', '/vacatures'],
    ['Open rollen', '/vacatures/open-rollen'],
    ['Rapportage', '/rapportage'],
    ...REPORT_TOPICS.map((topic) => [`Rapportage ${topic}`, `/rapportage/${topic}`]),
    ['Tarieven', '/beheer/tarieven'],
    ['Activiteit', '/beheer/activiteit'],
  ];
  if (running)
    for (const tab of ASSIGNMENT_TABS)
      out.push([
        `Opdracht ${tab || 'overzicht'}`,
        `/opdrachten/${running.id}${tab ? `/${tab}` : ''}`,
      ]);
  if (vacancy) out.push(['Vacature', `/vacatures/${vacancy.id}`]);
  if (reader.id) out.push(['Persoon', `/team/${reader.id}`]);
  const list = out.map(([name, url]) => ({ name, url }));
  return ONLY ? list.filter((p) => p.url.startsWith(ONLY)) : list;
}

/** Runs in the page before anything else: adds up the long tasks. */
function watchLongTasks() {
  window.__longTaskMs = 0;
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) window.__longTaskMs += entry.duration;
    }).observe({ type: 'longtask', buffered: true });
  } catch {
    // A browser without long task timing reports zero.
  }
}

/** Runs in the page: is there content and is nothing loading. */
function settled() {
  const main = document.querySelector('main') ?? document.querySelector('#root');
  if (!main) return false;
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const loading = [...main.querySelectorAll('[data-state="loading"], [variant="loading"]')].some(
    visible,
  );
  return !loading && main.querySelectorAll('*').length > 3;
}

function serverTiming(header) {
  if (!header) return {};
  const sql = header.match(/sql;dur=([\d.]+);desc="(\d+)"/);
  const app = header.match(/app;dur=([\d.]+)/);
  return {
    sqlMs: sql ? Number(sql[1]) : undefined,
    statements: sql ? Number(sql[2]) : undefined,
    appMs: app ? Number(app[1]) : undefined,
  };
}

async function measure(page, url) {
  const calls = new Map();
  let running = 0;
  let lastChange = Date.now();
  const onRequest = (request) => {
    if (!new URL(request.url()).pathname.startsWith('/api/')) return;
    running += 1;
    lastChange = Date.now();
    calls.set(request, { started: Date.now() });
  };
  const onDone = async (request) => {
    const call = calls.get(request);
    if (!call || call.ms !== undefined) return;
    call.ms = Date.now() - call.started;
    running -= 1;
    lastChange = Date.now();
    const response = await request.response().catch(() => null);
    const target = new URL(request.url());
    call.method = request.method();
    call.path = target.pathname + target.search;
    call.status = response?.status() ?? 0;
    Object.assign(call, serverTiming(response?.headers()['server-timing']));
    const sizes = await request.sizes().catch(() => null);
    call.bytes = sizes ? sizes.responseBodySize : 0;
  };
  page.on('request', onRequest);
  page.on('requestfinished', onDone);
  page.on('requestfailed', onDone);

  const started = Date.now();
  await page.goto(`${BASE}${url}`, { waitUntil: 'commit', timeout: 30000 });
  let usable = null;
  while (Date.now() - started < SETTLE_MS) {
    const quiet = running === 0 && Date.now() - lastChange >= QUIET_MS;
    if (quiet && (await page.evaluate(settled).catch(() => false))) {
      // Usable from the moment the last request came back.
      usable = Math.max(lastChange, started) - started;
      if (running === 0 && Date.now() - lastChange >= QUIET_MS) break;
    }
    await page.waitForTimeout(50);
  }
  page.off('request', onRequest);
  page.off('requestfinished', onDone);
  page.off('requestfailed', onDone);
  await page.waitForTimeout(50);

  const longTaskMs = await page.evaluate(() => Math.round(window.__longTaskMs ?? 0)).catch(() => 0);
  const heap = await page.evaluate(() => performance.memory?.usedJSHeapSize ?? 0).catch(() => 0);
  const done = [...calls.values()].filter((c) => c.ms !== undefined);
  return {
    usableMs: usable,
    longTaskMs,
    heapMb: Math.round(heap / 1e5) / 10,
    calls: done.sort((a, b) => b.ms - a.ms),
  };
}

function summary(result) {
  const calls = result.calls;
  const slowest = calls[0];
  const heaviest = [...calls].sort((a, b) => (b.statements ?? 0) - (a.statements ?? 0))[0];
  const over = [];
  if (result.usableMs === null) over.push('komt niet tot rust');
  else if (result.usableMs > BUDGET.usableMs) over.push('pagina');
  if (slowest && slowest.ms > BUDGET.callMs) over.push('verzoek');
  if (heaviest && (heaviest.statements ?? 0) > BUDGET.statements) over.push('statements');
  return {
    usableMs: result.usableMs,
    calls: calls.length,
    slowestMs: slowest?.ms ?? 0,
    slowest: slowest ? slowest.path.split('?')[0] : '',
    statements: heaviest?.statements,
    statementsOf: heaviest ? heaviest.path.split('?')[0] : '',
    sqlMs: Math.round(Math.max(0, ...calls.map((c) => c.sqlMs ?? 0))),
    kb: Math.round(calls.reduce((sum, c) => sum + (c.bytes ?? 0), 0) / 1024),
    longTaskMs: result.longTaskMs,
    heapMb: result.heapMb,
    over,
  };
}

function shorten(path, width) {
  const plain = path.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, '{id}');
  return plain.length > width ? `${plain.slice(0, width - 1)}…` : plain.padEnd(width);
}

function printTable(rows) {
  console.log(
    `${'pagina'.padEnd(28)}${'lezer'.padEnd(16)}${'bruikbaar'.padStart(10)}${'calls'.padStart(6)}` +
      `${'traagste'.padStart(9)}${'sql'.padStart(6)}${'kB'.padStart(7)}${'lang'.padStart(6)}${'MB'.padStart(6)}  traagste verzoek`,
  );
  for (const row of rows) {
    const s = row.summary;
    console.log(
      `${row.name.slice(0, 27).padEnd(28)}${row.kind.padEnd(16)}` +
        `${(s.usableMs === null ? '-' : `${s.usableMs} ms`).padStart(10)}${String(s.calls).padStart(6)}` +
        `${`${s.slowestMs} ms`.padStart(9)}${String(s.statements ?? '-').padStart(6)}` +
        `${String(s.kb).padStart(7)}${String(s.longTaskMs).padStart(6)}${String(s.heapMb).padStart(6)}` +
        `  ${shorten(s.slowest, 44)}${s.over.length ? ` OVER: ${s.over.join(', ')}` : ''}`,
    );
    if (args.calls)
      for (const call of row.calls)
        console.log(
          `    ${String(call.ms).padStart(5)} ms ${String(call.statements ?? '-').padStart(4)} st ` +
            `${String(Math.round((call.bytes ?? 0) / 1024)).padStart(5)} kB ${call.status} ${shorten(call.path, 80)}`,
        );
  }
}

/** Times the requests an earlier run saw, without a browser. */
async function apiOnly(file) {
  const earlier = JSON.parse(readFileSync(file, 'utf8'));
  const seen = new Map();
  for (const row of earlier.rows)
    for (const call of row.calls)
      if (call.method === 'GET') seen.set(`${row.readerId ?? ''} ${call.path}`, { row, call });
  const out = [];
  for (const { row, call } of seen.values()) {
    const times = [];
    let timing = {};
    let bytes = 0;
    for (let i = 0; i < 3; i += 1) {
      const started = performance.now();
      const response = await fetch(`${BASE}${call.path}`, {
        headers: row.readerId ? { Cookie: `${DEV_PERSON_COOKIE}=${row.readerId}` } : {},
      });
      bytes = (await response.arrayBuffer()).byteLength;
      times.push(performance.now() - started);
      timing = serverTiming(response.headers.get('server-timing'));
    }
    out.push({
      kind: row.kind,
      path: call.path,
      ms: Math.round(Math.min(...times)),
      bytes,
      ...timing,
    });
  }
  out.sort((a, b) => b.ms - a.ms);
  for (const call of out)
    console.log(
      `${String(call.ms).padStart(6)} ms ${String(call.statements ?? '-').padStart(5)} st ` +
        `${String(Math.round(call.sqlMs ?? 0)).padStart(5)} ms sql ${String(Math.round(call.bytes / 1024)).padStart(6)} kB ` +
        `${call.kind.padEnd(15)} ${shorten(call.path, 90)}`,
    );
  if (typeof args.json === 'string')
    writeFileSync(args.json, JSON.stringify({ api: out }, null, 2));
  return out.some((c) => c.ms > BUDGET.callMs || (c.statements ?? 0) > BUDGET.statements);
}

async function main() {
  if (typeof args.api === 'string') {
    process.exitCode = (await apiOnly(args.api)) ? 1 : 0;
    return;
  }
  const who = await readers();
  const browser = await chromium.launch({
    executablePath: browserPath(),
    headless: true,
    args: ['--enable-precise-memory-info'],
  });
  const rows = [];
  for (const reader of who) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    if (reader.id)
      await context.addCookies([{ name: DEV_PERSON_COOKIE, value: reader.id, url: BASE }]);
    await context.addInitScript(watchLongTasks);
    const page = await context.newPage();
    for (const target of await pages(reader)) {
      // Twice: the first visit warms the server and the browser, the second
      // counts. A page that takes seconds is not measured again: it is over
      // budget either way.
      let result = await measure(page, target.url);
      if (result.usableMs !== null && result.usableMs < RETRY_BELOW_MS)
        result = await measure(page, target.url);
      rows.push({
        ...target,
        kind: reader.kind,
        readerId: reader.id,
        ...result,
        summary: summary(result),
      });
      const s = rows.at(-1).summary;
      process.stderr.write(
        `${reader.kind} ${target.url.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, '{id}')}: ` +
          `${s.usableMs ?? '-'} ms, traagste ${s.slowestMs} ms\n`,
      );
    }
    await context.close();
  }
  await browser.close();

  printTable(rows);
  const over = rows.filter((row) => row.summary.over.length > 0);
  console.log(
    `\n${rows.length} metingen, ${over.length} boven het budget ` +
      `(pagina ${BUDGET.usableMs} ms, verzoek ${BUDGET.callMs} ms, ${BUDGET.statements} statements).`,
  );
  if (typeof args.json === 'string')
    writeFileSync(args.json, JSON.stringify({ base: BASE, budget: BUDGET, rows }, null, 2));
  process.exitCode = over.length > 0 ? 1 : 0;
}

main().catch((error) => {
  console.error(error.message ?? error);
  process.exitCode = 2;
});
