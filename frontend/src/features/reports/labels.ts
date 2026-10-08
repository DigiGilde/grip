import type { Scope } from './api';

export const MONTH_NAMES = [
  'januari',
  'februari',
  'maart',
  'april',
  'mei',
  'juni',
  'juli',
  'augustus',
  'september',
  'oktober',
  'november',
  'december',
] as const;

export const MONTH_ABBREVIATIONS = [
  'jan',
  'feb',
  'mrt',
  'apr',
  'mei',
  'jun',
  'jul',
  'aug',
  'sep',
  'okt',
  'nov',
  'dec',
] as const;

/** The month number (1 to 12) of a `YYYY-MM` text; 0 when it is none. */
function monthNumber(month: string): number {
  const number = Number(month.slice(5, 7));
  return Number.isInteger(number) && number >= 1 && number <= 12 ? number : 0;
}

export function monthName(month: string): string {
  const number = monthNumber(month);
  return number ? `${MONTH_NAMES[number - 1]} ${month.slice(0, 4)}` : month;
}

export function monthAbbreviation(month: string): string {
  const number = monthNumber(month);
  return number ? (MONTH_ABBREVIATIONS[number - 1] ?? month) : month;
}

export const QUOTE_STATUS_LABELS: Record<string, string> = {
  issued: 'Gemaakt, wacht op akkoord',
  accepted: 'Akkoord',
  rejected: 'Afgewezen',
  superseded: 'Vervangen door een nieuwe offerte',
};

export const VACANCY_STATUS_LABELS: Record<string, string> = {
  draft: 'Vacature in concept',
  requested: 'Vacature aangevraagd',
  approved: 'Vacature goedgekeurd',
  open: 'Vacature open',
};

export const ACCEPTANCE_FORM_LABELS: Record<string, string> = {
  own_instance: 'in de eigen omgeving van de opdrachtgever',
  signing_link: 'via een tekenlink',
  uploaded_pdf: 'met een getekend document',
};

export const KIND_LABELS: Record<string, string> = {
  external: 'Extern',
  internal: 'Intern',
};

/** Says over what a total was taken, so nobody reads a part as the whole. */
export function scopeNote(scope: Scope, all: string, own: string): string {
  return scope === 'all' ? all : own;
}
