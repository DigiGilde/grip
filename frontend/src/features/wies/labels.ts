import type { PersonProposal, ProposalAction } from './api';

export const ACTION_LABELS: Record<ProposalAction, string> = {
  add: 'Toevoegen',
  deactivate: 'Deactiveren',
  reactivate: 'Opnieuw activeren',
  rename: 'Naam wijzigen',
};

/** In the order a beheerder reads them: who comes in first, who leaves last. */
export const ACTION_ORDER: ProposalAction[] = ['add', 'reactivate', 'rename', 'deactivate'];

export const GROUP_HEADINGS: Record<ProposalAction, string> = {
  add: 'Toevoegen aan grip',
  reactivate: 'Opnieuw activeren',
  rename: 'Naam wijzigen',
  deactivate: 'Deactiveren in grip',
};

/** What the change does, in one line under the name. */
export function describe(proposal: PersonProposal): string {
  const parts = [proposal.email];
  if (proposal.action === 'rename' && proposal.current_name) {
    parts.push(`heet nu ${proposal.current_name}`);
  }
  if (proposal.suborganization) parts.push(proposal.suborganization);
  if (proposal.skills && proposal.skills.length > 0) parts.push(proposal.skills.join(', '));
  return parts.join(' · ');
}
