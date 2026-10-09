import { formatMonth } from '@/lib/format';
import type { AllocationLoad } from './api';

const pct = (value: string) => `${Number(value).toLocaleString('nl-NL')}%`;

/**
 * "Lot Lid komt boven 100% in maart 2026 (150%) en april 2026 (150%)", or
 * null when the inzet fits. The figures are the server's.
 */
export function overLoadText(load: AllocationLoad | undefined): string | null {
  const months = load?.over_months ?? [];
  if (months.length === 0) return null;
  const parts = months.map((item) => `${formatMonth(item.month)} (${pct(item.new_pct)})`);
  // A long period reads as its first months and a count.
  const shown = parts.slice(0, 4);
  const rest = parts.length - shown.length;
  const list =
    shown.length === 1
      ? shown[0]
      : `${shown.slice(0, -1).join(', ')}${rest > 0 ? ', ' : ' en '}${shown.at(-1)}`;
  const more = rest > 0 ? ` en nog ${rest} ${rest === 1 ? 'maand' : 'maanden'}` : '';
  return `${load?.person_name || 'Deze persoon'} komt boven 100% in ${list}${more}`;
}
