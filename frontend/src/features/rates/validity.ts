import { formatDate } from '@/lib/format';
import type { CardStatus, RateCard } from './api';

/** "geldig van 1 jan 2026 t/m 30 jun 2026" or "geldig vanaf 1 jul 2026". */
export function validityText(validFrom: string, validTo: string | null): string {
  return validTo
    ? `geldig van ${formatDate(validFrom)} t/m ${formatDate(validTo)}`
    : `geldig vanaf ${formatDate(validFrom)}`;
}

/** Where a card stands in time, seen from a day. */
export type Moment = 'now' | 'coming' | 'past' | 'draft';

export function momentOf(
  card: Pick<RateCard, 'status' | 'valid_from' | 'valid_to'>,
  day: string,
): Moment {
  if (card.status === 'draft') return 'draft';
  if (card.valid_from > day) return 'coming';
  if (card.valid_to !== null && card.valid_to < day) return 'past';
  return 'now';
}

export const MOMENT_LABELS: Record<Moment, string> = {
  now: 'Geldt nu',
  coming: 'Komt eraan',
  past: 'Voorbij',
  draft: 'Concept',
};

export const MOMENT_COLORS: Record<Moment, 'accent' | 'neutral' | 'warning'> = {
  now: 'accent',
  coming: 'neutral',
  past: 'neutral',
  draft: 'warning',
};

/** The label of a card's place in time, with "gesloten" where that applies. */
export function momentLabel(moment: Moment, status: CardStatus): string {
  return status === 'closed' ? `${MOMENT_LABELS[moment]}, gesloten` : MOMENT_LABELS[moment];
}

/** The first day of next year, as the proposed start of a new card. Any date is as valid. */
export function firstDayOfNextYear(today: string): string {
  return `${Number(today.slice(0, 4)) + 1}-01-01`;
}

/** Today as an ISO date in local time. */
export function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

/** The day before an ISO date. */
export function dayBefore(iso: string): string {
  const date = new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

/**
 * Until when a card starting on a date can hold: the day before the next
 * card that prices starts, or open-ended (null) when nothing follows.
 */
export function latestEnd(
  validFrom: string,
  cards: Pick<RateCard, 'status' | 'valid_from'>[],
): string | null {
  const next = cards
    .filter((card) => card.status !== 'draft' && card.valid_from > validFrom)
    .map((card) => card.valid_from)
    .sort()[0];
  return next ? dayBefore(next) : null;
}
