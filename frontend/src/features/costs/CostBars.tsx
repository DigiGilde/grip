import { formatEuro, formatPercent } from '@/lib/format';
import '@/features/reports/reports.css';
import type { CostItem, Coverage } from './api';
import { COST_LABELS, coverageStep } from './costText';
import './costs.css';

function coverageTitle(coverage: Coverage): string {
  return `${coverage.assignment_name}, ${coverage.budget_line_description}: ${formatPercent(coverage.pct)}, ${formatEuro(coverage.amount_cents)}`;
}

/** The mark that goes with a word that asks for attention. */
function AttentionMark() {
  return (
    <span className="grip-mark" aria-hidden="true">
      !
    </span>
  );
}

/**
 * What is expected against the budget: one bar for the expected total, split
 * into what has come in and what is still expected, with the budget as a
 * line through it. The bar is as long as the larger of the two, so a bar
 * that passes the line is an overrun. Every value is also text under the bar.
 */
export function ForecastBar({ item }: { item: CostItem }) {
  const longest = Math.max(item.budgeted_cents, item.forecast_cents);
  const room = Math.max(item.variance_cents, 0);
  const markAt = item.budgeted_cents > 0 ? (item.budgeted_cents / longest) * 100 : null;
  const side = markAt !== null && markAt > 50 ? 'before' : 'after';
  const summary = [
    `${COST_LABELS.received} ${formatEuro(item.actual_cents)}`,
    `${COST_LABELS.expected.toLowerCase()} ${formatEuro(item.estimate_cents)}`,
    `${COST_LABELS.budgeted.toLowerCase()} ${formatEuro(item.budgeted_cents)}`,
  ].join(', ');

  return (
    <figure className="cost-bar cost-chart">
      <figcaption className="cost-bar__head">
        Facturen
        {markAt !== null && (
          <span
            className="cost-bar__mark-label"
            data-side={side}
            style={{ left: `${markAt}%` }}
            aria-hidden="true"
          >
            {COST_LABELS.budgeted}
          </span>
        )}
      </figcaption>
      <div className="cost-bar__plot">
        <div className="cost-bar__track" role="img" aria-label={summary}>
          {item.actual_cents > 0 && (
            <span
              className="cost-seg"
              data-kind="received"
              style={{ flexGrow: item.actual_cents }}
              title={`${COST_LABELS.received}: ${formatEuro(item.actual_cents)}`}
            />
          )}
          {item.estimate_cents > 0 && (
            <span
              className="cost-seg"
              data-kind="expected"
              style={{ flexGrow: item.estimate_cents }}
              title={`${COST_LABELS.expected}: ${formatEuro(item.estimate_cents)}`}
            />
          )}
          {(room > 0 || item.forecast_cents === 0) && (
            <span className="cost-seg" data-kind="room" style={{ flexGrow: room || 1 }} />
          )}
        </div>
        {markAt !== null && (
          <span className="cost-bar__mark" data-side={side} style={{ left: `${markAt}%` }} />
        )}
      </div>
      <ul className="cost-legend">
        <li>
          <span className="cost-swatch cost-seg" data-kind="received" aria-hidden="true" />
          {COST_LABELS.received} <strong>{formatEuro(item.actual_cents)}</strong>
        </li>
        <li>
          <span className="cost-swatch cost-seg" data-kind="expected" aria-hidden="true" />
          {COST_LABELS.expected} <strong>{formatEuro(item.estimate_cents)}</strong>
        </li>
      </ul>
    </figure>
  );
}

interface CoverageSegmentsProps {
  item: CostItem;
  /** Whether a segment says what it is on hover; the small bar in a list does not. */
  titles?: boolean;
}

/** The shares of the expected total, one segment per payer and one for nobody. */
function CoverageSegments({ item, titles }: CoverageSegmentsProps) {
  const hidden = Number(item.hidden_coverage_pct);
  const uncovered = Number(item.uncovered_pct ?? 0);
  // Nothing is expected yet, so there is nothing to divide.
  if (item.forecast_cents === 0) {
    return <span className="cost-seg" data-kind="room" style={{ flexGrow: 1 }} />;
  }
  return (
    <>
      {item.coverages.map((coverage, index) => (
        <span
          key={coverage.budget_line_id}
          className="cost-seg"
          data-step={coverageStep(index)}
          style={{ flexGrow: Number(coverage.pct) }}
          {...(titles ? { title: coverageTitle(coverage) } : {})}
        />
      ))}
      {hidden > 0 && (
        <span
          className="cost-seg"
          data-kind="hidden"
          style={{ flexGrow: hidden }}
          {...(titles
            ? {
                title: `Opdrachten die je niet kunt inzien: ${formatPercent(item.hidden_coverage_pct)}`,
              }
            : {})}
        />
      )}
      {uncovered > 0 && (
        <span
          className="cost-seg"
          data-kind="uncovered"
          style={{ flexGrow: uncovered }}
          {...(titles
            ? {
                title: `${COST_LABELS.uncovered}: ${formatPercent(item.uncovered_pct)}, ${formatEuro(item.uncovered_cents)}`,
              }
            : {})}
        />
      )}
    </>
  );
}

/** "Gedekt € 12.000 (80%), ongedekt € 3.000 (20%)", for a screen reader. */
function coverageSummary(item: CostItem): string {
  if (item.covered_cents === null) {
    return `De dekking komt op ${formatPercent(item.pct_total)}, meer dan het verwacht totaal`;
  }
  const covered = `${COST_LABELS.covered} ${formatEuro(item.covered_cents)} (${formatPercent(item.pct_total)})`;
  return item.uncovered_cents
    ? `${covered}, ${COST_LABELS.uncovered.toLowerCase()} ${formatEuro(item.uncovered_cents)} (${formatPercent(item.uncovered_pct)})`
    : covered;
}

/**
 * Who pays: the expected total divided over the budget lines that cover it,
 * and what nobody pays for as a part of its own. The table under "Dekking"
 * holds the same shares by name.
 */
export function CoverageBar({ item }: { item: CostItem }) {
  return (
    <figure className="cost-bar cost-chart">
      <figcaption className="cost-bar__head">Dekking</figcaption>
      <div className="cost-bar__plot">
        <div className="cost-bar__track" role="img" aria-label={coverageSummary(item)}>
          <CoverageSegments item={item} titles />
        </div>
      </div>
      <ul className="cost-legend">
        {item.covered_cents === null ? (
          <li className="cost-legend__attention">
            <AttentionMark />
            Dekking boven 100% <strong>{formatPercent(item.pct_total)}</strong>
          </li>
        ) : (
          <>
            <li>
              <span className="cost-swatch cost-seg" data-step="2" aria-hidden="true" />
              {COST_LABELS.covered}{' '}
              <strong>
                {formatEuro(item.covered_cents)} ({formatPercent(item.pct_total)})
              </strong>
            </li>
            {item.uncovered_cents !== null && item.uncovered_cents > 0 && (
              <li className="cost-legend__attention">
                <span className="cost-swatch cost-seg" data-kind="uncovered" aria-hidden="true" />
                {COST_LABELS.uncovered}{' '}
                <strong>
                  {formatEuro(item.uncovered_cents)}
                  {item.uncovered_pct ? ` (${formatPercent(item.uncovered_pct)})` : ''}
                </strong>
              </li>
            )}
          </>
        )}
      </ul>
    </figure>
  );
}

/** The coverage of one cost item as a small bar, for a row in the list. */
export function CoverageMiniBar({ item }: { item: CostItem }) {
  return (
    <span className="cost-mini cost-chart" role="img" aria-label={coverageSummary(item)}>
      <CoverageSegments item={item} />
    </span>
  );
}
