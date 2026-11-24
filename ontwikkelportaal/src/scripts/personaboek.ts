// Narrows the personas in the sidebar, and the table on the overview, by a
// search term, organisation and grip instance. Each element to filter carries
// data-org, data-instances (separated by |) and data-search.
const field = document.getElementById('personaboek-zoeken') as (HTMLElement & { value?: string }) | null;
const count = document.getElementById('personaboek-aantal');
const options = [...document.querySelectorAll<HTMLElement>('#personaboek-filter [data-filter]')];
const items = [...document.querySelectorAll<HTMLElement>('[data-persona]')];
const total = new Set(items.map((i) => i.dataset.persona)).size;

let term = '';
const chosen: Record<string, Set<string>> = { org: new Set(), instance: new Set() };

function matches(item: HTMLElement): boolean {
  if (term && !(item.dataset.search ?? '').includes(term)) return false;
  if (chosen.org.size && !chosen.org.has(item.dataset.org ?? '')) return false;
  if (chosen.instance.size) {
    const own = (item.dataset.instances ?? '').split('|');
    if (!own.some((i) => chosen.instance.has(i))) return false;
  }
  return true;
}

function apply() {
  const shown = new Set<string | undefined>();
  for (const item of items) {
    const visible = matches(item);
    item.hidden = !visible;
    if (visible) shown.add(item.dataset.persona);
  }
  if (count) {
    count.textContent = shown.size === total ? `${total} persona’s` : `${shown.size} van ${total} persona’s`;
  }
}

function tick(option: HTMLElement, checked: boolean) {
  const group = chosen[option.dataset.filter!];
  if (checked) group.add(option.dataset.value!);
  else group.delete(option.dataset.value!);
  option.toggleAttribute('checked', checked);
  option.querySelector('nldd-checkbox')?.toggleAttribute('checked', checked);
}

field?.addEventListener('input', (event) => {
  const value = (event as CustomEvent<{ value?: string }>).detail?.value ?? field.value ?? '';
  term = String(value).trim().toLowerCase();
  apply();
});

for (const option of options) {
  option.addEventListener('change', (event) => {
    tick(option, Boolean((event as CustomEvent<{ checked?: boolean }>).detail?.checked));
    apply();
  });
}

// A link such as /personaboek/?organisatie=prg opens the overview filtered.
const params = new URLSearchParams(location.search);
for (const [name, key] of [['organisatie', 'org'], ['instantie', 'instance']] as const) {
  for (const wanted of params.getAll(name)) {
    const option = options.find(
      (o) => o.dataset.filter === key && (o.dataset.param === wanted.toLowerCase() || o.dataset.value === wanted),
    );
    if (option) tick(option, true);
  }
}
apply();
