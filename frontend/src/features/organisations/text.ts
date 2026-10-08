import type { Organisation } from './api';

/** What the picker shows for an organisation: its label and abbreviation. */
export function organisationText(organisation: Organisation): string {
  return organisation.abbreviation
    ? `${organisation.label} (${organisation.abbreviation})`
    : organisation.label;
}

/**
 * Where the organisation sits: everything above it, top first. Empty for an
 * organisation at the top. This is what tells two equal names apart.
 */
export function organisationPlace(organisation: Organisation): string {
  return organisation.path.slice(0, -1).join(' > ');
}

/** The second line under an organisation in a list. */
export function organisationDetails(organisation: Organisation): string {
  const place = organisationPlace(organisation);
  if (organisation.source === 'manual') {
    return place ? `${place} · zelf toegevoegd` : 'Zelf toegevoegd';
  }
  return place || (organisation.main_type ?? '');
}

const RESULT_LABELS: [string, string][] = [
  ['created', 'toegevoegd'],
  ['updated', 'bijgewerkt'],
  ['unchanged', 'ongewijzigd'],
  ['adopted', 'zelf toegevoegd en nu uit het register'],
  ['closed', 'afgesloten'],
  ['deleted', 'verwijderd'],
  ['skipped_ended', 'al opgeheven en niet toegevoegd'],
  ['excluded', 'uitgesloten'],
];

/** The counts of a sync run as one readable line; zero counts are left out. */
export function syncSummary(result: Record<string, number>): string {
  const parts = RESULT_LABELS.filter(([key]) => (result[key] ?? 0) > 0).map(
    ([key, label]) => `${result[key]} ${label}`,
  );
  return parts.length > 0 ? parts.join(', ') : 'Niets gewijzigd';
}
