import { formatEuro, formatPercent } from '@/lib/format';
import type { Figures } from './financeApi';
import { FIGURE_LABELS, costsSplitText, varianceText, varianceWord } from './financeText';

export const FIGURE_COLUMNS = '120px 125px 125px 120px 135px 150px 105px';

export function FigureHeaderCells() {
  return (
    <>
      <nldd-text-cell text={FIGURE_LABELS.budgeted} horizontal-alignment="right" />
      <nldd-text-cell text={FIGURE_LABELS.realised} horizontal-alignment="right" />
      <nldd-text-cell text={FIGURE_LABELS.planned} horizontal-alignment="right" />
      <nldd-text-cell text={FIGURE_LABELS.costs} horizontal-alignment="right" />
      <nldd-text-cell text={FIGURE_LABELS.expected} horizontal-alignment="right" />
      <nldd-text-cell text={FIGURE_LABELS.variance} horizontal-alignment="right" />
      <nldd-text-cell text={FIGURE_LABELS.realisedPct} horizontal-alignment="right" />
    </>
  );
}

/** The seven figures of a line or a total, as the service computed them. */
export function FigureCells({
  figures,
  error,
  bold,
}: {
  figures: Figures | null | undefined;
  error?: string | null;
  bold?: boolean;
}) {
  if (!figures) {
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
        <nldd-text-cell />
        <nldd-text-cell />
      </>
    );
  }
  const mark = (text: string) => (bold ? `**${text}**` : text);
  const costs = costsSplitText(figures);
  return (
    <>
      <nldd-text-cell text={mark(formatEuro(figures.budgeted_cents))} horizontal-alignment="right" />
      <nldd-text-cell text={mark(formatEuro(figures.realised_cents))} horizontal-alignment="right" />
      <nldd-text-cell text={mark(formatEuro(figures.planned_cents))} horizontal-alignment="right" />
      <nldd-text-cell
        text={mark(formatEuro(figures.costs_cents))}
        {...(costs ? { 'supporting-text': costs } : {})}
        horizontal-alignment="right"
      />
      <nldd-text-cell
        text={mark(formatEuro(figures.expected_total_cents))}
        horizontal-alignment="right"
      />
      <nldd-text-cell
        text={mark(varianceText(figures))}
        supporting-text={varianceWord(figures)}
        horizontal-alignment="right"
        {...(figures.overrun ? { color: 'critical' } : {})}
      />
      <nldd-text-cell
        text={mark(figures.realised_pct === null ? '' : formatPercent(figures.realised_pct))}
        horizontal-alignment="right"
      />
    </>
  );
}
