/** Dutch names for the codes the API uses. */

export const STATUS_LABELS: Record<string, string> = {
  draft: 'In voorbereiding',
  requested: 'Aangevraagd',
  quoted: 'Offerte uitgegeven',
  verbally_agreed: 'Mondeling akkoord',
  accepted: 'Akkoord',
  in_progress: 'In uitvoering',
  completed: 'Afgerond',
  accounted: 'Verantwoord',
  rejected: 'Afgewezen',
  cancelled: 'Geannuleerd',
};

/** What the button says that moves an assignment to a status. */
export const TRANSITION_LABELS: Record<string, string> = {
  draft: 'Terug naar in voorbereiding',
  requested: 'Markeer als aangevraagd',
  quoted: 'Markeer offerte als uitgegeven',
  verbally_agreed: 'Leg mondeling akkoord vast',
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
  verbally_agreed: 'accent',
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

export type Phase = 'potential' | 'active' | 'closed';

/** The three views of the list of assignments. */
export const PHASE_VIEW_LABELS: Record<Phase, string> = {
  potential: 'Pijplijn',
  active: 'Lopend',
  closed: 'Afgesloten',
};

/** What the phase is called next to amounts, where pipeline must not read as work. */
export const PHASE_LABELS: Record<Phase, string> = {
  potential: 'Potentiële opdrachten',
  active: 'Lopende opdrachten',
  closed: 'Afgesloten opdrachten',
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

const RELATION_TEXT: Record<string, string> = {
  owner: 'Je bent eigenaar van deze opdracht.',
  manager: 'Je bent manager van deze opdracht.',
  member: 'Je werkt aan deze opdracht.',
};

/** One quiet line saying why the reader sees this assignment; empty when there is nothing to say. */
export function relationText(relations: readonly string[] | undefined): string {
  if (!relations?.length) return '';
  if (relations.includes('owner') && relations.includes('manager')) {
    return 'Je bent eigenaar en manager van deze opdracht.';
  }
  return RELATION_TEXT[relations[0] ?? ''] ?? '';
}
