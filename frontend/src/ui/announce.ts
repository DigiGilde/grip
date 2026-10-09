/**
 * Says something to a screen reader without moving focus.
 *
 * A sighted reader sees a sheet close and the page change; a screen reader
 * hears only the button focus returns to. One polite live region for the
 * whole application carries what happened, in a few words. It is made on
 * first use and stays in the document: a region that appears together with
 * its text is not read out.
 */
import './hidden.css';

const REGION_ID = 'grip-announcer';
let clearing: number | undefined;

function region(): HTMLElement {
  const existing = document.getElementById(REGION_ID);
  if (existing) return existing;
  const created = document.createElement('div');
  created.id = REGION_ID;
  created.className = 'grip-visually-hidden';
  created.setAttribute('role', 'status');
  created.setAttribute('aria-live', 'polite');
  created.setAttribute('aria-atomic', 'true');
  document.body.append(created);
  return created;
}

/** Makes the region ahead of the first message, so that message is heard too. */
export function prepareAnnouncer(): void {
  region();
}

export function announce(message: string): void {
  const target = region();
  // The same words twice in a row are a change too: empty first.
  target.textContent = '';
  window.setTimeout(() => {
    target.textContent = message;
  }, 50);
  // Said once; it should not be found again by someone reading the page later.
  window.clearTimeout(clearing);
  clearing = window.setTimeout(() => {
    target.textContent = '';
  }, 8000);
}
