/**
 * The two names on every screen: the product and the organisation.
 *
 * grip is the product and is the same everywhere. An instance belongs to an
 * organisation, whose name is a setting. Older settings wrote the two as one
 * string ("Grip Voorbeeldgilde (voorbeeld)"); this module takes that apart so
 * the screens can show each where it belongs.
 */

/** The product, in running text and as word mark. Always lower case. */
export const PRODUCT_NAME = 'grip';

/** What grip is, in one sentence. The same sentence everywhere. */
export const PRODUCT_SENTENCE = 'Grip op opdrachten, van offerte tot verantwoording.';

export interface InstanceNames {
  /** The organisation that runs this instance; empty when not known yet. */
  organisation: string;
  /** A note about the environment, such as "voorbeeld"; absent in production. */
  environment?: string;
}

/**
 * Splits the instance name into the organisation and a note on the
 * environment. A leading "Grip" is the product and is dropped; a trailing
 * note in brackets says something about the environment, not about the
 * organisation.
 */
export function instanceNames(name: string | null | undefined): InstanceNames {
  let rest = (name ?? '').trim();
  let environment: string | undefined;
  const note = rest.match(/\s*\(([^()]+)\)$/);
  if (note?.[1]) {
    environment = note[1].trim();
    rest = rest.slice(0, note.index).trim();
  }
  rest = rest.replace(/^grip\b[\s:,-]*/i, '').trim();
  return environment ? { organisation: rest, environment } : { organisation: rest };
}

/**
 * The title of a browser tab: the page first, because that is what differs
 * between tabs, then whose grip it is, then the product.
 */
export function documentTitle(page: string, instanceName?: string | null): string {
  const { organisation } = instanceNames(instanceName);
  return [page, organisation, PRODUCT_NAME].filter(Boolean).join(' · ');
}
