/** The vacancy list: what a row says about where a vacancy stands, and the order. */
import { daysSince, durationText } from '@/features/assignments/views';
import { formatDate } from '@/lib/format';
import type { VacancySummary } from './api';
import { STATUS_LABELS } from './labels';
import { STEP_NAMES, type StepAction } from './steps';

export type ListOrder = 'waiting' | 'newest' | 'function';

export const ORDER_OPTIONS: { value: ListOrder; label: string }[] = [
  { value: 'waiting', label: 'Wacht het langst' },
  { value: 'newest', label: 'Nieuwste eerst' },
  { value: 'function', label: 'Functie, A tot Z' },
];

/** From this many days on, a row says how long the vacancy has been waiting. */
const WAITING_WORTH_SAYING = 4;

export interface Standing {
  /** The step the vacancy is at, in the words of the step bar; '' when none is next. */
  step: string;
  /** What it waits on and for how long, or when it ended. */
  detail: string;
}

/** What the "Volgende stap" column says for a row. */
export function standingOf(vacancy: VacancySummary, now: Date = new Date()): Standing {
  const step = vacancy.step ? (STEP_NAMES[vacancy.step as StepAction] ?? '') : '';
  if (!step) {
    // Ended: nothing is next. Say when, never the status a second time.
    const ended = vacancy.step_since ? `Sinds ${formatDate(vacancy.step_since)}` : '';
    return { step: '', detail: vacancy.step === undefined ? '' : ended };
  }
  const days = daysSince(vacancy.step_since, now);
  const waiting =
    days !== null && days >= WAITING_WORTH_SAYING ? `al ${durationText(days)}` : '';
  return { step, detail: [vacancy.step_detail, waiting].filter(Boolean).join(', ') };
}

function waitingDays(vacancy: VacancySummary, now: Date): number {
  return daysSince(vacancy.step_since, now) ?? 0;
}

/**
 * The rows in the chosen order. "Wacht het langst" puts what needs someone
 * first, longest wait on top, and what has ended last; the list arrives
 * newest first, which is the tie-break everywhere.
 */
export function orderVacancies(
  vacancies: readonly VacancySummary[],
  order: ListOrder,
  now: Date = new Date(),
): VacancySummary[] {
  const rows = vacancies.map((vacancy, index) => ({ vacancy, index }));
  if (order === 'function') {
    rows.sort(
      (a, b) =>
        a.vacancy.function_title.localeCompare(b.vacancy.function_title, 'nl') || a.index - b.index,
    );
  } else if (order === 'waiting') {
    rows.sort((a, b) => {
      const aOpen = a.vacancy.step ? 0 : 1;
      const bOpen = b.vacancy.step ? 0 : 1;
      if (aOpen !== bOpen) return aOpen - bOpen;
      const wait = aOpen === 0 ? waitingDays(b.vacancy, now) - waitingDays(a.vacancy, now) : 0;
      return wait || a.index - b.index;
    });
  }
  return rows.map((row) => row.vacancy);
}

/** The status as a word; the color beside it never carries the meaning alone. */
export function statusWord(vacancy: VacancySummary): string {
  return STATUS_LABELS[vacancy.status];
}
