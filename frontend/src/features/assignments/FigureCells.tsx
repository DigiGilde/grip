import { formatEuro, formatPercent } from '@/lib/format';
import type { Figures } from './financeApi';
import { FIGURE_LABELS, costsSplitText, nothingPlanned, varianceWord } from './financeText';

/** The table's cell is too narrow for the sentence of the landing. */
const NOTHING_PLANNED_IN_TABLE = 'Niets gepland';

export const FIGURE_COLUMNS =
  'minmax(92px,1fr) minmax(130px,1.1fr) minmax(100px,1fr) minmax(130px,1.2fr) minmax(120px,1fr) minmax(140px,1.2fr) minmax(92px,.8fr)';

export function FigureHeaderCells() {
  return (
    <>
      <nldd-text-cell text={FIGURE_LABELS.budgeted} horizontal-alignment="right" />
      <nldd-text-cell text={FIGURE_LABELS.realisedEffort} horizontal-alignment="right" />
      <nldd-text-cell text={FIGURE_LABELS.planned} horizontal-alignment="right" />
      <nldd-text-cell text={FIGURE_LABELS.costs} horizontal-alignment="right" />
      <nldd-text-cell text={FIGURE_LABELS.expected} horizontal-alignment="right" />
      <nldd-text-cell text={FIGURE_LABELS.variance} horizontal-alignment="right" />
      <nldd-text-cell text={FIGURE_LABELS.realisedPct} horizontal-alignment="right" />
    </>
  );
}

/** The share and the word under the amount: "27,8%, ruimte". */
function varianceNote(figures: Pick<Figures, 'variance_cents' | 'variance_pct'>): string {
  const word = varianceWord(figures);
  return figures.variance_pct === null
    ? word
    : `${formatPercent(figures.variance_pct)}, ${word.toLowerCase()}`;
}

/** The seven figures of a line or a total, as the service computed them. */
export function FigureCells({
  figures,
  error,
  bold,
  withoutPlan,
  showRealisedTotal,
}: {
  figures: Figures | null | undefined;
  error?: string | null;
  bold?: boolean;
  /** Say "Niets gepland" when nothing is planned: for a personnel line and the total. */
  withoutPlan?: boolean;
  /** Say under Uitputting which amount the share is of: the total row. */
  showRealisedTotal?: boolean;
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
  const unplanned = withoutPlan === true && nothingPlanned(figures);
  return (
    <>
      <nldd-text-cell
        text={mark(formatEuro(figures.budgeted_cents))}
        horizontal-alignment="right"
      />
      <nldd-text-cell
        text={mark(formatEuro(figures.realised_cents))}
        horizontal-alignment="right"
      />
      <nldd-text-cell text={mark(formatEuro(figures.planned_cents))} horizontal-alignment="right" />
      <nldd-text-cell
        text={mark(formatEuro(figures.costs_cents))}
        {...(costs ? { 'supporting-text': costs } : {})}
        horizontal-alignment="right"
      />
      {unplanned ? (
        <>
          <nldd-text-cell text={NOTHING_PLANNED_IN_TABLE} horizontal-alignment="right" />
          <nldd-text-cell />
        </>
      ) : (
        <>
          <nldd-text-cell
            text={mark(formatEuro(figures.expected_total_cents))}
            horizontal-alignment="right"
          />
          <nldd-text-cell
            text={mark(formatEuro(figures.variance_cents))}
            supporting-text={varianceNote(figures)}
            horizontal-alignment="right"
            {...(figures.overrun ? { color: 'critical' } : {})}
          />
        </>
      )}
      <nldd-text-cell
        text={mark(figures.realised_pct === null ? '' : formatPercent(figures.realised_pct))}
        {...(showRealisedTotal && figures.realised_pct !== null
          ? {
              'supporting-text': `${formatEuro(figures.realised_total_cents)} ${FIGURE_LABELS.realised.toLowerCase()}`,
            }
          : {})}
        horizontal-alignment="right"
      />
    </>
  );
}
