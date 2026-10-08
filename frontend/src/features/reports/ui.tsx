import type { ReactNode } from 'react';
import { SectionHeading } from '@/ui/layout';
import { formatEuro } from '@/lib/format';
import type { Totals } from './api';
import { hasAmounts } from './api';
import './reports.css';

// Tests leave the nldd-* elements unregistered on purpose, so they read the
// light DOM this app is responsible for.
if (import.meta.env.MODE !== 'test') void import('./register');

/** A block of a report: a heading, a line that says what it covers, and its content. */
export function ReportBlock({
  title,
  note,
  children,
  testId,
  bare,
}: {
  title: string;
  note?: string;
  children: ReactNode;
  testId?: string;
  /** The page heading already names the block: leave the heading out. */
  bare?: boolean;
}) {
  return (
    <section data-testid={testId} aria-label={title}>
      <nldd-container gap="16">
        <nldd-container gap="4">
          {!bare && <SectionHeading text={title} />}
          {note && (
            <nldd-text size="sm" color="secondary">
              {note}
            </nldd-text>
          )}
        </nldd-container>
        {children}
      </nldd-container>
    </section>
  );
}

export interface Figure {
  label: string;
  value: string;
  /** A line under the value: what it is made of, or over which period. */
  detail?: string;
  /** Needs attention; the word says what is the matter. */
  attention?: string;
  /** Nothing to report (a zero, or not applicable): the figure steps back. */
  quiet?: boolean;
}

/**
 * The conclusion of a block, before its detail: a few figures a reader can
 * take in without reading a table. A figure that needs attention says so
 * with a mark and a word, not with colour alone.
 */
export function Figures({ figures, label }: { figures: Figure[]; label: string }) {
  return (
    <dl className="grip-figures" aria-label={label}>
      {figures.map((figure) => (
        <div
          key={figure.label}
          className={[
            'grip-figure',
            figure.attention ? 'grip-figure--attention' : '',
            figure.quiet ? 'grip-figure--quiet' : '',
          ]
            .filter(Boolean)
            .join(' ')}
        >
          <dt>{figure.label}</dt>
          <dd className="grip-figure__value">{figure.value}</dd>
          {figure.attention && (
            <dd className="grip-figure__flag">
              <span className="grip-mark" aria-hidden="true">
                !
              </span>
              {figure.attention}
            </dd>
          )}
          {figure.detail && <dd className="grip-figure__detail">{figure.detail}</dd>}
        </div>
      ))}
    </dl>
  );
}

/**
 * An amount in a table, right aligned. Empty when the API sent none; a zero
 * is muted, so the amounts that matter stand out.
 */
export function MoneyCell({
  cents,
  bold,
  note,
  critical,
}: {
  cents: number | null | undefined;
  bold?: boolean;
  note?: string;
  critical?: boolean;
}) {
  const text = formatEuro(cents);
  const zero = cents === 0;
  return (
    <nldd-text-cell
      text={bold && text && !zero ? `**${text}**` : text}
      horizontal-alignment="right"
      {...(note ? { 'supporting-text': note } : {})}
      {...(critical ? { color: 'critical' } : zero ? { color: 'secondary' } : {})}
    />
  );
}

export function NumberCell({
  text,
  note,
  muted,
}: {
  text: string;
  note?: string;
  muted?: boolean;
}) {
  return (
    <nldd-text-cell
      text={text}
      horizontal-alignment="right"
      {...(note ? { 'supporting-text': note } : {})}
      {...(muted ? { color: 'secondary' } : {})}
    />
  );
}

export const TOTALS_COLUMNS = '120px 120px 120px 110px 130px 140px';

export function TotalsHeaderCells() {
  return (
    <>
      <nldd-text-cell text="Begroot" horizontal-alignment="right" />
      <nldd-text-cell text="Gerealiseerd" horizontal-alignment="right" />
      <nldd-text-cell text="Nog gepland" horizontal-alignment="right" />
      <nldd-text-cell text="Kosten" horizontal-alignment="right" />
      <nldd-text-cell text="Verwacht totaal" horizontal-alignment="right" />
      <nldd-text-cell text="Afwijking" horizontal-alignment="right" />
    </>
  );
}

/**
 * The amounts in the words of the assignment pages: begroot, gerealiseerd,
 * nog gepland, kosten, verwacht totaal and afwijking (begroot min verwacht
 * totaal). An overrun is said in words.
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
        <nldd-text-cell />
      </>
    );
  }
  return (
    <>
      <MoneyCell cents={totals.budgeted_cents} bold={bold} />
      <MoneyCell cents={totals.realised_cents} bold={bold} />
      <MoneyCell cents={totals.forecast_cents} bold={bold} />
      <MoneyCell cents={totals.coverage_cents} bold={bold} />
      <MoneyCell cents={totals.used_cents} bold={bold} />
      <MoneyCell
        cents={totals.available_cents}
        bold={bold}
        {...(totals.overrun ? { critical: true, note: 'Overschrijding' } : {})}
      />
    </>
  );
}

/** Something secondary: there for who wants it, out of the way for who does not. */
export function Disclosure({ summary, children }: { summary: string; children: ReactNode }) {
  return (
    <details className="grip-disclosure">
      <summary>{summary}</summary>
      {children}
    </details>
  );
}
