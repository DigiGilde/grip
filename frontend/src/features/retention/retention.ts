/**
 * The retention periods of the instance, as the beheerder reads and sets
 * them (ADR 0057). They are instance settings; the server checks every value.
 */

export const SETTING_ASSIGNMENT = 'retention.assignment';
export const SETTING_PROPOSE_CLOSE = 'dossier.propose_close_after_days';
export const SETTING_CLOSE_AFTER_PROPOSAL = 'dossier.close_after_proposal_days';
export const SETTING_EVENTS = 'events.retention_days';
export const SETTING_READS = 'events.read_retention_days';
export const SETTING_REQUEST_FORMS = 'vacancy.request_form_retention_days';

export const MAX_YEARS = 100;
/** A hundred years, as the server allows. */
export const MAX_DAYS = 36500;

/** What happens to an assignment once its dossier is closed. Null: nothing is set. */
export type CaseRule = { outcome: 'destroy'; years: number } | { outcome: 'keep' } | null;

export type CaseChoice = 'destroy' | 'keep' | 'none';

export const CASE_CHOICES: readonly { value: CaseChoice; label: string }[] = [
  { value: 'destroy', label: 'Vernietigen na een aantal jaren' },
  { value: 'keep', label: 'Blijvend bewaren' },
  { value: 'none', label: 'Nog niet bepaald: niets vernietigen' },
];

export function caseRuleOf(value: unknown): CaseRule {
  if (typeof value !== 'object' || value === null) return null;
  const rule = value as { outcome?: unknown; years?: unknown };
  if (rule.outcome === 'keep') return { outcome: 'keep' };
  if (rule.outcome === 'destroy' && typeof rule.years === 'number') {
    return { outcome: 'destroy', years: rule.years };
  }
  return null;
}

export function choiceOf(rule: CaseRule): CaseChoice {
  return rule === null ? 'none' : rule.outcome;
}

function years(count: number): string {
  return count === 1 ? '1 jaar' : `${count} jaar`;
}

function days(count: number): string {
  return count === 1 ? '1 dag' : `${count} dagen`;
}

export function caseRuleText(rule: CaseRule): string {
  if (rule === null) return 'Nog niet bepaald: niets wordt vernietigd';
  if (rule.outcome === 'keep') return 'Blijvend bewaren';
  return `Vernietigen na ${years(rule.years)}`;
}

export function proposeCloseText(value: unknown): string {
  return typeof value === 'number' ? `Na ${days(value)} zonder wijziging` : 'Nooit';
}

export function closeAfterProposalText(value: unknown): string {
  return typeof value === 'number' ? `${days(value)} na die taak` : 'Nooit';
}

export function eventsText(value: unknown): string {
  return typeof value === 'number' && value > 0 ? `Gewist na ${days(value)}` : 'Nooit gewist';
}

const VACANCY_ENDED = 'de vacature is vervuld, ingetrokken of afgewezen';

export function requestFormsText(value: unknown): string {
  return typeof value === 'number' && value > 0
    ? `Verwijderd ${days(value)} nadat ${VACANCY_ENDED}`
    : `Verwijderd bij de eerstvolgende nachtelijke ronde nadat ${VACANCY_ENDED}`;
}

/** A whole number as typed, or null when it is not one within the bounds. */
export function wholeNumber(input: string, min: number, max?: number): number | null {
  const text = input.trim();
  if (!/^\d+$/.test(text)) return null;
  const value = Number(text);
  if (value < min || (max !== undefined && value > max)) return null;
  return value;
}

/** The text of a setting in a field: empty for nothing. */
export function inputOf(value: unknown): string {
  return typeof value === 'number' ? String(value) : '';
}
