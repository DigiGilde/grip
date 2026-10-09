/** The three views of the list of assignments. */
import type { Phase } from './labels';
import { todayIso } from '@/lib/today';

export const VIEW_PARAM = 'weergave';
/** The words searched for, in the address. */
export const SEARCH_PARAM = 'zoek';

export const VIEWS: readonly { phase: Phase; slug: string }[] = [
  { phase: 'potential', slug: 'pijplijn' },
  { phase: 'active', slug: 'lopend' },
  { phase: 'closed', slug: 'afgesloten' },
];

export const DEFAULT_PHASE: Phase = 'active';

/** The phase a `weergave` value in the address stands for; running work by default. */
export function phaseOfView(value: string | null): Phase {
  return VIEWS.find((view) => view.slug === value)?.phase ?? DEFAULT_PHASE;
}

/**
 * The address of a view. The words searched for travel along, so the counts
 * on the tabs and the list behind them are about the same search; the page
 * does not, because every view starts at its first.
 */
export function viewHref(path: string, phase: Phase, search = ''): string {
  const slug = VIEWS.find((view) => view.phase === phase)?.slug;
  const params = new URLSearchParams();
  if (phase !== DEFAULT_PHASE && slug) params.set(VIEW_PARAM, slug);
  if (search) params.set(SEARCH_PARAM, search);
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

/** Whole days between an ISO date and today; null without a date. */
export function daysSince(iso: string | null | undefined, now: Date = new Date()): number | null {
  if (!iso) return null;
  // Both as calendar days of the instance, so the count turns at its midnight.
  const then = Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(then)) return null;
  const today = Date.parse(`${todayIso(now)}T00:00:00Z`);
  return Math.max(0, Math.round((today - then) / 86_400_000));
}

/** "vandaag", "1 dag", "12 dagen", "5 weken", "4 maanden". */
export function durationText(days: number | null): string {
  if (days === null) return '';
  if (days === 0) return 'vandaag';
  if (days === 1) return '1 dag';
  if (days < 21) return `${days} dagen`;
  if (days < 84) return `${Math.round(days / 7)} weken`;
  return `${Math.round(days / 30)} maanden`;
}
