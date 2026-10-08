import { formatEuro } from '@/lib/format';
import type { Totals } from './api';
import { hasAmounts } from './api';

export const TOTALS_COLUMNS = '130px 130px 130px 130px 150px';

export function TotalsHeaderCells() {
  return (
    <>
      <nldd-text-cell text="Begroot" horizontal-alignment="right" />
      <nldd-text-cell text="Gerealiseerd" horizontal-alignment="right" />
      <nldd-text-cell text="Prognose" horizontal-alignment="right" />
      <nldd-text-cell text="Kosten" horizontal-alignment="right" />
      <nldd-text-cell text="Beschikbaar" horizontal-alignment="right" />
    </>
  );
}

/**
 * Budgeted, realised, forecast, costs and available. An overrun is said in
 * words as well as colour, so it does not depend on seeing red.
 */
export function TotalsCells({
  totals,
  error,
  bold,
}: {
  totals: Totals | null | undefined;
  error?: string | null;
  bold?: boolean;
}) {
  if (!hasAmounts(totals)) {
    return (
      <>
        <nldd-text-cell
          text={error ? 'Niet berekend' : ''}
          {...(error ? { 'supporting-text': error } : {})}
          color="secondary"
        />
        <nldd-text-cell />
        <nldd-text-cell />
        <nldd-text-cell />
        <nldd-text-cell />
      </>
    );
  }
  const money = (cents: number) => (bold ? `**${formatEuro(cents)}**` : formatEuro(cents));
  return (
    <>
      <nldd-text-cell text={money(totals.budgeted_cents)} horizontal-alignment="right" />
      <nldd-text-cell text={money(totals.realised_cents)} horizontal-alignment="right" />
      <nldd-text-cell text={money(totals.forecast_cents)} horizontal-alignment="right" />
      <nldd-text-cell text={money(totals.coverage_cents)} horizontal-alignment="right" />
      <nldd-text-cell
        text={money(totals.available_cents)}
        horizontal-alignment="right"
        {...(totals.overrun ? { color: 'critical', 'supporting-text': 'Overschrijding' } : {})}
      />
    </>
  );
}
