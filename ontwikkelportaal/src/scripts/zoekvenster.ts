// The search window: Cmd+K or Ctrl+K, or the Zoeken item in the top bar, opens it on any page.
// On the search page itself both just focus that page's field.
import { loadPagefind, NO_INDEX, resultRow } from './pagefind';

const MAX_RESULTS = 8;

type Field = HTMLElement & { value?: string; focus: () => void };
type Windowed = HTMLElement & { open: boolean; show: () => void; hide: () => void };

const dialog = document.getElementById('zoekvenster') as Windowed | null;
const field = document.getElementById('zoekvenster-veld') as Field | null;
const list = document.getElementById('zoekvenster-resultaten');
const state = document.getElementById('zoekvenster-stand');
const more = document.getElementById('zoekvenster-meer');
const trigger = document.getElementById('zoeken-knop');
const pageField = document.getElementById('zoekveld') as Field | null;
const searchPath = trigger?.getAttribute('href') ?? '/zoeken/';

let opener: HTMLElement | null = null;
let timer = 0;
let latest = 0;

function show(message: string, hasResults: boolean, term = '') {
  if (state) state.textContent = message;
  if (more) {
    more.hidden = !term;
    more.setAttribute('href', `${searchPath}?q=${encodeURIComponent(term)}`);
  }
  if (!hasResults) list?.replaceChildren();
}

async function run() {
  const request = ++latest;
  const term = (field?.value ?? '').trim();
  if (!term) {
    show('', false);
    return;
  }
  const index = await loadPagefind();
  if (!index) {
    show(NO_INDEX, false);
    return;
  }
  const response = await index.search(term);
  if (!response || request !== latest) return;
  const data = await Promise.all(response.results.slice(0, MAX_RESULTS).map((r) => r.data()));
  if (request !== latest || !list) return;
  list.replaceChildren(...data.map(resultRow));
  const total = response.results.length;
  const message =
    total === 0
      ? 'Geen resultaten'
      : total > MAX_RESULTS
        ? `De eerste ${MAX_RESULTS} van ${total} resultaten`
        : `${total} ${total === 1 ? 'resultaat' : 'resultaten'}`;
  show(message, total > 0, term);
}

function open() {
  if (pageField) {
    pageField.focus();
    return;
  }
  if (!dialog) return;
  const active = document.activeElement;
  opener = active instanceof HTMLElement && active !== document.body ? active : trigger;
  dialog.show();
  field?.focus();
  void loadPagefind();
}

function toggle() {
  if (dialog?.open) dialog.hide();
  else open();
}

dialog?.addEventListener('close', () => {
  if (opener?.isConnected) opener.focus();
  opener = null;
});

field?.addEventListener('input', () => {
  window.clearTimeout(timer);
  timer = window.setTimeout(run, 200);
});

dialog?.addEventListener('keydown', (event) => {
  const items = [...(list?.querySelectorAll<HTMLElement>('nldd-list-item') ?? [])];
  if (event.target === field) {
    if (event.key === 'ArrowDown' && items.length) {
      event.preventDefault();
      items[0].focus();
    } else if (event.key === 'Enter' && items.length) {
      event.preventDefault();
      location.assign(items[0].getAttribute('href')!);
    }
  } else if (event.key === 'ArrowUp' && event.target === items[0]) {
    event.preventDefault();
    field?.focus();
  }
});

trigger?.addEventListener('click', (event) => {
  event.preventDefault();
  open();
});

// Cmd+K is global, also inside a text field: the same as on the regelrecht site.
document.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    toggle();
  }
});
