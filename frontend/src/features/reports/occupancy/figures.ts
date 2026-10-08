import { formatFte, formatPercent } from '@/lib/format';
import type { OccupancySummary } from '../api';
import { monthAbbreviation, monthName } from '../labels';
import type { Groups, ViewTarget } from './view';

export interface OccupancyTile {
  key: string;
  label: string;
  value: string;
  /** One sentence of context. */
  detail?: string;
  /** A tiny row of months, each with its figure. */
  months?: { label: string; value: string }[];
  /** Needs attention; the word says what is the matter. */
  attention?: string;
  /** Nothing to report: the tile steps back. */
  quiet?: boolean;
  /** The rows this figure counts. Absent when there is nothing to show. */
  target?: ViewTarget;
}

const people = (count: number) => `${count} ${count === 1 ? 'persoon' : 'mensen'}`;

/**
 * The answer before the table. Every tile that counts people leads to
 * exactly those people: `target` is the view of the table that shows them.
 */
export function occupancyTiles(
  summary: OccupancySummary,
  year: number,
  groups: Groups,
): OccupancyTile[] {
  const [now, ...ahead] = summary.window ?? [];
  const tiles: OccupancyTile[] = [
    {
      key: 'average',
      label: `Gemiddelde bezetting ${year}`,
      value: summary.average_pct === null ? 'Onbekend' : formatPercent(summary.average_pct),
      detail: `van ${people(summary.person_count).replace(' ', ' inzetbare ')}`,
      target: { show: 'iedereen' },
    },
  ];

  if (now) {
    const tentative = Number(now.tentative_fte);
    tiles.push({
      key: 'free',
      label: `Vrij in ${monthName(now.month)}`,
      value: `${formatFte(now.free_fte)} FTE`,
      months: ahead.map((month) => ({
        label: monthAbbreviation(month.month),
        value: formatFte(month.free_fte),
      })),
      ...(tentative > 0
        ? { detail: `Van de inzet nu is ${formatFte(now.tentative_fte)} FTE onder voorbehoud.` }
        : {}),
      quiet: Number(now.free_fte) === 0,
      ...(groups.vrij.length > 0 ? { target: { show: 'vrij' as const, sort: 'free' as const } } : {}),
    });
  }

  const overMonths = summary.over_months ?? [];
  tiles.push(
    summary.over_count > 0
      ? {
          key: 'over',
          label: 'Boven 100%',
          value: people(summary.over_count),
          attention: 'Te veel ingepland',
          detail: `in ${overMonths.map(monthAbbreviation).join(', ')}`,
          target: { show: 'boven-100', ...(overMonths[0] ? { month: overMonths[0] } : {}) },
        }
      : { key: 'over', label: 'Boven 100%', value: 'Niemand', quiet: true },
  );

  if (ahead.length > 0) {
    const first = ahead[0];
    const last = ahead[ahead.length - 1];
    const span =
      first && last ? `${monthAbbreviation(first.month)} t/m ${monthAbbreviation(last.month)}` : '';
    tiles.push(
      summary.idle_count > 0
        ? {
            key: 'idle',
            label: 'Zonder inzet de komende 3 maanden',
            value: people(summary.idle_count),
            attention: 'Geen inzet gepland',
            detail: span,
            target: { show: 'zonder-inzet' },
          }
        : {
            key: 'idle',
            label: 'Zonder inzet de komende 3 maanden',
            value: 'Niemand',
            detail: span,
            quiet: true,
          },
    );
  }
  return tiles;
}
