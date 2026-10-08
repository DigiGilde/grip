import type { CatalogueRole } from './api';

const ACCENTED = 'áàâäãåéèêëíìîïóòôöõúùûüçñ';
const PLAIN = 'aaaaaaeeeeiiiiooooouuuucn';

/** Lower case without accents and with single spaces, for comparing names. */
export function foldName(value: string): string {
  const lowered = value.trim().toLowerCase().replace(/\s+/g, ' ');
  let folded = '';
  for (const char of lowered) {
    const at = ACCENTED.indexOf(char);
    folded += at === -1 ? char : PLAIN[at];
  }
  return folded;
}

/**
 * The roles that fit what was typed: every word must occur in the name. A
 * name that starts with the query comes first, the rest stays alphabetical.
 */
export function matchRoles(roles: CatalogueRole[], typed: string): CatalogueRole[] {
  const query = foldName(typed);
  if (!query) return roles;
  const words = query.split(' ');
  const hits = roles.filter((role) => {
    const name = foldName(role.name);
    return words.every((word) => name.includes(word));
  });
  const rank = (role: CatalogueRole) => {
    const name = foldName(role.name);
    if (name === query) return 0;
    return name.startsWith(query) ? 1 : 2;
  };
  return [...hits].sort((a, b) => rank(a) - rank(b));
}

/** Whether a role with exactly this name is in the list, whatever the capitals. */
export function hasExactRole(roles: CatalogueRole[], typed: string): boolean {
  const query = foldName(typed);
  return roles.some((role) => foldName(role.name) === query);
}

export function sourceText(role: CatalogueRole): string {
  return role.source === 'wies' ? 'Wies' : 'Zelf toegevoegd';
}

export function usageText(count: number): string {
  if (count === 0) return 'Nergens in gebruik';
  return count === 1 ? '1 begrotingsregel' : `${count} begrotingsregels`;
}

const RESULT_LABELS: [string, string][] = [
  ['created', 'toegevoegd'],
  ['adopted', 'gekoppeld aan een bestaande rol'],
  ['renamed', 'hernoemd'],
  ['reactivated', 'weer ingeschakeld'],
  ['unchanged', 'ongewijzigd'],
  ['deactivated', 'uitgeschakeld omdat ze nog in gebruik zijn'],
  ['deleted', 'verwijderd'],
  ['conflicts', 'met een naam die al bestaat'],
];

/** The counts of a sync run as one readable line; zero counts are left out. */
export function roleSyncSummary(result: Record<string, number>): string {
  const parts = RESULT_LABELS.filter(([key]) => (result[key] ?? 0) > 0).map(
    ([key, label]) => `${result[key]} ${label}`,
  );
  return parts.length > 0 ? parts.join(', ') : 'Niets gewijzigd';
}
