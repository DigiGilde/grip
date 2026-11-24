// Search over the Pagefind index with the design system's own controls:
// Pagefind finds and ranks, the page draws the field, the filters and the list.

import { loadPagefind, NO_INDEX, resultRow } from './pagefind';

const MAX_RESULTS = 30;

const field = document.getElementById('zoekveld') as (HTMLElement & { value?: string }) | null;
const list = document.getElementById('zoekresultaten');
const state = document.getElementById('zoeken-stand');
const rows = [...document.querySelectorAll<HTMLElement>('#zoeken [data-filter]')];
const selected = new Set<HTMLElement>();

let term = new URLSearchParams(location.search).get('q') ?? '';
let timer = 0;
let latest = 0;

/** Every group is passed, ticked or not: Pagefind only counts the groups it is given. */
function chosen(): Record<string, { any: string[] }> {
  const filters: Record<string, { any: string[] }> = {};
  for (const row of rows) filters[row.dataset.filter!] ??= { any: [] };
  for (const row of selected) filters[row.dataset.filter!].any.push(row.dataset.value!);
  return filters;
}

function showCounts(counts: Record<string, Record<string, number>>) {
  for (const row of rows) {
    const cell = row.querySelector('[data-count]');
    const value = counts[row.dataset.filter!]?.[row.dataset.value!] ?? 0;
    cell?.setAttribute('text', String(value));
  }
}

async function run() {
  const request = ++latest;
  const index = await loadPagefind();
  if (!index) {
    if (state) state.textContent = NO_INDEX;
    return;
  }
  if (!list || !state) return;
  const filters = chosen();
  const ticked = Object.keys(filters).filter((key) => filters[key].any.length > 0);
  if (!term && !ticked.length) {
    list.replaceChildren();
    state.textContent = '';
    showCounts(await index.filters());
    return;
  }
  const response = await index.search(term || null, { filters });
  if (!response || request !== latest) return;
  const data = await Promise.all(response.results.slice(0, MAX_RESULTS).map((r) => r.data()));
  if (request !== latest) return;
  // A group with a ticked value shows its counts without its own choice, so
  // ticking one value does not zero the others; the rest follow the choice.
  const counts = { ...response.filters };
  for (const key of ticked) counts[key] = response.totalFilters?.[key] ?? counts[key];
  showCounts(counts);
  list.replaceChildren(...data.map(resultRow));
  const total = response.results.length;
  const subject = term ? ` voor ‘${term}’` : '';
  if (total === 0) state.textContent = `Niets gevonden${subject}.`;
  else if (total > MAX_RESULTS) state.textContent = `De eerste ${MAX_RESULTS} van ${total} resultaten${subject}.`;
  else state.textContent = `${total} ${total === 1 ? 'resultaat' : 'resultaten'}${subject}.`;
}

function remember() {
  const url = new URL(location.href);
  if (term) url.searchParams.set('q', term);
  else url.searchParams.delete('q');
  history.replaceState(null, '', url);
}

field?.addEventListener('input', (event) => {
  const value = (event as CustomEvent<{ value?: string }>).detail?.value ?? field.value ?? '';
  term = String(value).trim();
  remember();
  window.clearTimeout(timer);
  timer = window.setTimeout(run, 200);
});

for (const item of rows) {
  item.addEventListener('change', (event) => {
    const checked = Boolean((event as CustomEvent<{ checked?: boolean }>).detail?.checked);
    if (checked) selected.add(item);
    else selected.delete(item);
    item.querySelector('nldd-checkbox')?.toggleAttribute('checked', checked);
    void run();
  });
}

if (field && term) field.setAttribute('value', term);
void run();
