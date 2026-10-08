/** Dutch names for the codes the API uses. */

export const STATUS_LABELS: Record<string, string> = {
  draft: 'Concept',
  requested: 'Aangevraagd',
  quoted: 'Offerte uitgegeven',
  accepted: 'Akkoord',
  in_progress: 'In uitvoering',
  completed: 'Afgerond',
  accounted: 'Verantwoord',
  rejected: 'Afgewezen',
  cancelled: 'Geannuleerd',
};

/** What the button says that moves an assignment to a status. */
export const TRANSITION_LABELS: Record<string, string> = {
  draft: 'Terug naar concept',
  requested: 'Markeer als aangevraagd',
  quoted: 'Markeer offerte als uitgegeven',
  accepted: 'Markeer als akkoord',
  in_progress: 'Start uitvoering',
  completed: 'Rond af',
  accounted: 'Markeer als verantwoord',
  rejected: 'Markeer als afgewezen',
  cancelled: 'Annuleer opdracht',
};

export type BadgeColor = 'neutral' | 'success' | 'warning' | 'critical' | 'accent';

export const STATUS_COLORS: Record<string, BadgeColor> = {
  draft: 'neutral',
  requested: 'accent',
  quoted: 'accent',
  accepted: 'success',
  in_progress: 'success',
  completed: 'neutral',
  accounted: 'neutral',
  rejected: 'critical',
  cancelled: 'critical',
};

export const KIND_LABELS: Record<string, string> = {
  external: 'Externe opdracht',
  internal: 'Interne opdracht',
};

export const TRAFFIC_FORM_LABELS: Record<string, string> = {
  none: 'Geen verkeer met de opdrachtgever',
  document: 'Offerte als document',
  federated: 'Via grip van de opdrachtgever',
};

export const ROLE_LABELS: Record<string, string> = {
  owner: 'Eigenaar',
  manager: 'Manager',
};

export const LINE_KIND_LABELS: Record<string, string> = {
  personnel: 'Personeel',
  fixed: 'Vast bedrag',
};

export const RATE_CATEGORIES = ['A', 'B', 'C', 'D', 'E'] as const;

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}
