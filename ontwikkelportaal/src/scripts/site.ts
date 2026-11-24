import '../nldd-components.js';

interface Instance {
  naam: string;
  rol: string;
  omschrijving: string;
  url: string;
}

const text = (value: unknown) => (typeof value === 'string' ? value.trim() : '');

/** An instance from config.json, or null when it lacks a name or an http(s) address. */
function parseInstance(raw: unknown): Instance | null {
  if (!raw || typeof raw !== 'object') return null;
  const entry = raw as Record<string, unknown>;
  const naam = text(entry.naam);
  let url: URL;
  try {
    url = new URL(text(entry.url));
  } catch {
    return null;
  }
  if (!naam || (url.protocol !== 'http:' && url.protocol !== 'https:')) return null;
  return {
    naam,
    rol: text(entry.rol),
    omschrijving: text(entry.omschrijving),
    url: url.href,
  };
}

function element(tag: string, attributes: Record<string, string> = {}, ...children: Node[]): HTMLElement {
  const el = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) el.setAttribute(name, value);
  el.append(...children);
  return el;
}

function instanceCard(instance: Instance): HTMLElement {
  const title = element('nldd-title', { size: '5', 'heading-level': '3', text: instance.naam });
  if (instance.rol) title.setAttribute('supporting-text', instance.rol);
  const card = element(
    'nldd-card',
    { 'accessible-label': instance.naam },
    element('nldd-container', { slot: 'header', padding: '16', 'padding-bottom': '0' }, title),
  );
  if (instance.omschrijving) {
    const paragraph = element('p');
    paragraph.textContent = instance.omschrijving;
    card.append(element('nldd-container', { padding: '16' }, element('nldd-rich-text', {}, paragraph)));
  }
  card.append(
    element(
      'nldd-container',
      { slot: 'footer', padding: '16', 'padding-top': '0' },
      element('nldd-button', { appearance: 'secondary', href: instance.url, text: `Open ${instance.naam}` }),
    ),
  );
  return card;
}

// The instances are not in the pages: the container writes config.json at
// start from ONTWIKKELPORTAAL_INSTANCES, so one image serves every environment.
async function showInstances() {
  const section = document.getElementById('demo');
  const list = document.getElementById('demo-instanties');
  if (!section || !list) return;
  let configured: unknown;
  try {
    const response = await fetch('/config.json', { cache: 'no-cache' });
    if (!response.ok) return;
    configured = (await response.json())?.instances;
  } catch {
    return;
  }
  if (!Array.isArray(configured)) return;
  const instances = configured.map(parseInstance).filter((i): i is Instance => i !== null);
  if (!instances.length) return;
  list.replaceChildren(...instances.map(instanceCard));
  section.hidden = false;
}

function wireSidebarTriggers() {
  document.querySelectorAll('.sidebar-trigger nldd-button').forEach((button) => {
    button.addEventListener('click', () => {
      const section = button.closest('nldd-sidebar-section') as (HTMLElement & { show?: () => void }) | null;
      section?.show?.();
    });
  });
}

wireSidebarTriggers();
void showInstances();
