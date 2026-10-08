/** The three views of the list of assignments. */
import type { AssignmentSummary } from './api';
import type { Phase } from './labels';
import { todayIso } from '@/lib/today';

export const VIEW_PARAM = 'weergave';

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

export function viewHref(path: string, phase: Phase): string {
  const slug = VIEWS.find((view) => view.phase === phase)?.slug;
  return phase === DEFAULT_PHASE || !slug ? path : `${path}?${VIEW_PARAM}=${slug}`;
}

export function countByPhase(items: readonly AssignmentSummary[]): Record<Phase, number> {
  const counts: Record<Phase, number> = { potential: 0, active: 0, closed: 0 };
  for (const item of items) counts[item.phase] += 1;
  return counts;
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
