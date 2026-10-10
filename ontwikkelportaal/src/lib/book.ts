import { getCollection, getEntry } from 'astro:content';
import { ACCESS_LABELS, ORGANISATIONS, PREFIX, type Organisation } from './site';

export interface BookPersona {
  code: string;
  naam: string;
  rol: string;
  organisatie: Organisation;
  eenheid: string;
  instances: string[];
  grips: string;
  search: string;
}

/** The personas in the order of the chain, then by code. */
export async function bookPersonas(): Promise<BookPersona[]> {
  const entries = await getCollection('personas');
  return entries
    .map((e) => e.data)
    .sort(
      (a, b) =>
        ORGANISATIONS.indexOf(a.organisatie) - ORGANISATIONS.indexOf(b.organisatie) ||
        a.code.localeCompare(b.code),
    )
    .map((p) => ({
      code: p.code,
      naam: p.naam,
      rol: p.rol,
      organisatie: p.organisatie,
      eenheid: p.eenheid,
      instances: p.grips.map((g) => g.instantie),
      grips: p.grips.length
        ? p.grips
            .map((g) =>
              g.toegang === 'account' ? g.instantie : `${g.instantie} (${ACCESS_LABELS[g.toegang].toLowerCase()})`,
            )
            .join('; ')
        : 'geen',
      search: `${p.code} ${p.naam} ${p.rol} ${p.organisatie} ${p.eenheid}`.toLowerCase(),
    }));
}

/** The grip instances any persona uses, in the order of the chain. */
export function bookInstances(personas: BookPersona[]): string[] {
  const used = new Set(personas.flatMap((p) => p.instances));
  const known = ORGANISATIONS.filter((o) => used.has(o));
  const other = [...used].filter((i) => !(ORGANISATIONS as readonly string[]).includes(i)).sort();
  return [...known, ...other];
}

/** The attributes the sidebar filter reads on a list item or a table row. */
export const filterData = (p: BookPersona) => ({
  'data-persona': p.code,
  'data-org': p.organisatie,
  'data-instances': p.instances.join('|'),
  'data-search': p.search,
});

/** The prefix of an organisation as used in ?organisatie=. */
export const orgParam = (org: Organisation) => PREFIX[org].toLowerCase();

const GENERATED_SECTION = 'alle-personas';

/**
 * The README of the Personaboek without its own table of all personas: the
 * overview generates that one from the front matter of the persona files.
 */
export async function aboutBookHtml(): Promise<string> {
  const intro = await getEntry('intros', 'personas/README');
  const html = intro?.rendered?.html;
  if (!html) throw new Error('docs/personas/README.md ontbreekt of is niet gerenderd');
  const [head, ...sections] = html.split(/(?=<h2 )/);
  const kept = sections.filter((s) => !s.startsWith(`<h2 id="${GENERATED_SECTION}"`));
  if (kept.length !== sections.length - 1) {
    throw new Error(`docs/personas/README.md: de sectie "${GENERATED_SECTION}" ontbreekt`);
  }
  return [head, ...kept].join('');
}
