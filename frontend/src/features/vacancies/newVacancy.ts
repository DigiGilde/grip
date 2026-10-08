/** The words of the "Nieuwe vacature" sheet: which roles are offered and what a type means. */
import { formatDate, formatFte } from '@/lib/format';
import type { FilledRole, UnfilledRole, VacancyType } from './api';

export const KNOWN_CANDIDATE = new Set<VacancyType>(['beoogd', 'gerede']);
export const FILLED_GROUP = 'Ingevulde rollen';

const tentativeText = (role: { tentative?: boolean }) =>
  role.tentative ? ', onder voorbehoud' : '';

export function roleLabel(role: UnfilledRole): string {
  return `${role.assignment_name}: ${role.role ?? role.description} (${formatFte(role.unfilled_fte)} fte open${tentativeText(role)})`;
}

/** "Opdracht: Adviseur (ingevuld door Naam t/m 31 dec 2026)"; without names for who may not see them. */
export function filledRoleLabel(role: FilledRole): string {
  const by = (role.filled_by ?? [])
    .map((filler) => `${filler.person_name} t/m ${formatDate(filler.until)}`)
    .join(', ');
  return `${role.assignment_name}: ${role.role ?? role.description} (${by ? `ingevuld door ${by}` : 'ingevuld'}${tentativeText(role)})`;
}

/** What the chosen type means for the procedure, in one line; empty when nothing special. */
export function typeConsequence(type: VacancyType): string {
  return KNOWN_CANDIDATE.has(type) ? 'Wordt niet opengesteld: de kandidaat is bekend.' : '';
}

/** "Ingevuld door Naam t/m 31 dec 2026. Een vacature start de vervanging of opvolging." */
export function filledHint(role: FilledRole): string {
  const by = (role.filled_by ?? [])
    .map((filler) => `${filler.person_name} t/m ${formatDate(filler.until)}`)
    .join(', ');
  return `${by ? `Ingevuld door ${by}` : 'Deze rol is ingevuld'}. Een vacature start de vervanging of opvolging.`;
}
