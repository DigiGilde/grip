/** The words that go with the figures, in one place so every screen says the same. */
import { formatEuro, formatMonth, formatPercent } from '@/lib/format';
import type { Figures, Signal } from './financeApi';

export const FIGURE_LABELS = {
  budgeted: 'Begroot',
  realised: 'Gerealiseerd',
  planned: 'Nog gepland',
  costs: 'Kosten',
  expected: 'Verwacht totaal',
  variance: 'Afwijking',
  realisedPct: 'Uitputting',
} as const;

/** "Stand t/m februari 2026 (laatst afgesloten maand)". */
export function referenceText(referenceMonth: string | null | undefined): string {
  return referenceMonth
    ? `Stand t/m ${formatMonth(referenceMonth)} (laatst afgesloten maand)`
    : 'Er is nog geen maand afgesloten. Alle bedragen komen uit de planning.';
}

/** The variance in words: room or overrun, never by colour alone. */
export function varianceWord(figures: Pick<Figures, 'variance_cents'>): string {
  if (figures.variance_cents < 0) return 'Overschrijding';
  if (figures.variance_cents > 0) return 'Ruimte';
  return 'Geen ruimte';
}

/** "€ 1.200 (4,5%)", with the sign of the amount. */
export function varianceText(figures: Pick<Figures, 'variance_cents' | 'variance_pct'>): string {
  const amount = formatEuro(figures.variance_cents);
  return figures.variance_pct === null ? amount : `${amount} (${formatPercent(figures.variance_pct)})`;
}

/** How the costs split, e.g. "€ 3.000 gerealiseerd, € 1.500 ingeschat". */
export function costsSplitText(
  figures: Pick<Figures, 'costs_realised_cents' | 'costs_forecast_cents' | 'costs_cents'>,
): string {
  if (figures.costs_cents === 0) return '';
  return `${formatEuro(figures.costs_realised_cents)} gerealiseerd, ${formatEuro(figures.costs_forecast_cents)} ingeschat`;
}

export interface SignalText {
  variant: 'critical' | 'warning' | 'neutral';
  text: string;
}

export function signalText(signal: Signal, thresholdPct: string): SignalText {
  const pct = signal.pct === null ? '' : ` (${formatPercent(signal.pct)})`;
  switch (signal.kind) {
    case 'overrun':
      return {
        variant: 'critical',
        text: `Overschrijding op ${signal.description}: ${formatEuro(signal.amount_cents)}${pct} boven de begroting`,
      };
    case 'free_room':
      return {
        variant: 'neutral',
        text: `Vrije ruimte op ${signal.description}: ${formatEuro(signal.amount_cents)}${pct}, boven de drempel van ${formatPercent(thresholdPct)}`,
      };
    case 'rate_mismatch':
      return {
        variant: 'warning',
        text:
          signal.count === 1
            ? 'Van 1 persoon wordt de inzet in een andere categorie geprijsd dan de begrotingsregel aanneemt'
            : `Van ${signal.count} personen wordt de inzet in een andere categorie geprijsd dan de begrotingsregel aanneemt`,
      };
    case 'months_not_closed': {
      const first = signal.months[0];
      const last = signal.months.at(-1);
      const range =
        first && last && first !== last
          ? `${formatMonth(first)} t/m ${formatMonth(last)}`
          : formatMonth(first);
      return {
        variant: 'warning',
        text:
          signal.count === 1
            ? `De maand ${range} is voorbij en nog niet afgesloten`
            : `${signal.count} maanden zijn voorbij en nog niet afgesloten (${range})`,
      };
    }
    case 'not_priced':
      return {
        variant: 'critical',
        text: `${signal.count === 1 ? '1 regel kon' : `${signal.count} regels konden`} niet worden berekend. ${signal.description ?? ''}`.trim(),
      };
    default:
      return { variant: 'neutral', text: signal.description ?? signal.kind };
  }
}
