import { formatFte, formatPercent } from '@/lib/format';
import type { OccupancySummary } from '../api';
import { monthAbbreviation, monthName } from '../labels';
import type { Figure } from '../ui';

const fte = (value: string | undefined) => `${formatFte(value ?? '0')} FTE`;

/** The answer before the table: four figures over the rows of the block. */
export function occupancyFigures(summary: OccupancySummary, year: number): Figure[] {
  const [now, ...ahead] = summary.window ?? [];
  const people = summary.person_count === 1 ? 'persoon' : 'mensen';
  const overMonths = (summary.over_months ?? []).map(monthAbbreviation).join(', ');
  const figures: Figure[] = [
    {
      label: `Gemiddelde bezetting ${year}`,
      value: summary.average_pct === null ? 'Onbekend' : formatPercent(summary.average_pct),
      detail: `van ${summary.person_count} inzetbare ${people}`,
    },
  ];
  if (now) {
    const tentative = Number(now.tentative_fte) > 0;
    figures.push({
      label: `Vrij in ${monthName(now.month)}`,
      value: fte(now.free_fte),
      detail:
        ahead.map((month) => `${monthAbbreviation(month.month)} ${formatFte(month.free_fte)}`).join(', ') +
        (tentative ? `. Nu ${fte(now.tentative_fte)} onder voorbehoud ingepland.` : ''),
      quiet: Number(now.free_fte) === 0,
    });
  }
  figures.push(
    summary.over_count > 0
      ? {
          label: 'Boven 100%',
          value: `${summary.over_count} ${summary.over_count === 1 ? 'persoon' : 'mensen'}`,
          attention: 'Te veel ingepland',
          detail: `in ${overMonths}`,
        }
      : { label: 'Boven 100%', value: 'Niemand', quiet: true },
  );
  if (ahead.length > 0) {
    const first = ahead[0];
    const last = ahead[ahead.length - 1];
    const span = first && last ? `${monthAbbreviation(first.month)} t/m ${monthAbbreviation(last.month)}` : '';
    figures.push(
      summary.idle_count > 0
        ? {
            label: 'Zonder inzet de komende 3 maanden',
            value: `${summary.idle_count} ${summary.idle_count === 1 ? 'persoon' : 'mensen'}`,
            attention: 'Geen inzet gepland',
            detail: span,
          }
        : {
            label: 'Zonder inzet de komende 3 maanden',
            value: 'Niemand',
            detail: span,
            quiet: true,
          },
    );
  }
  return figures;
}
