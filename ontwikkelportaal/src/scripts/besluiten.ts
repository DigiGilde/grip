// Narrows the list of decisions by number or title and by status.
const field = document.getElementById('besluiten-zoeken') as (HTMLElement & { value?: string }) | null;
const control = document.getElementById('besluiten-status') as (HTMLElement & { value?: string }) | null;
const count = document.getElementById('besluiten-aantal');
const rows = [...document.querySelectorAll<HTMLElement>('#besluiten nldd-list-item[data-status]')];

let term = '';
let status = '';

function apply() {
  let shown = 0;
  for (const row of rows) {
    const visible =
      (!term || (row.dataset.search ?? '').includes(term)) && (!status || row.dataset.status === status);
    row.hidden = !visible;
    if (visible) shown += 1;
  }
  if (count) count.textContent = shown === rows.length ? `${rows.length} besluiten` : `${shown} van ${rows.length} besluiten`;
}

field?.addEventListener('input', (event) => {
  const value = (event as CustomEvent<{ value?: string }>).detail?.value ?? field.value ?? '';
  term = String(value).trim().toLowerCase();
  apply();
});

control?.addEventListener('change', (event) => {
  const value = (event as CustomEvent<{ value?: string }>).detail?.value ?? control.value ?? '';
  status = String(value);
  apply();
});
