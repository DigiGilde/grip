import { formatEuro, formatFte, formatPeriod } from '@/lib/format';
import type { QuoteContent, QuoteLine } from './api';
import { scaleText } from './format';
import './register';

function rateText(line: QuoteLine): string {
  const rates = line.monthly_rates ?? [];
  if (rates.length === 0) return '';
  const distinct = new Set(rates.map((rate) => rate.monthly_rate_cents));
  if (distinct.size === 1) return formatEuro(rates[0]?.monthly_rate_cents);
  return rates.map((rate) => `${rate.year}: ${formatEuro(rate.monthly_rate_cents)}`).join(', ');
}

function periodText(line: QuoteLine): string {
  if (line.kind === 'fixed') return line.year ? String(line.year) : '';
  return formatPeriod(line.start_date, line.end_date);
}

/**
 * The lines of a quote with subtotals per year and the total. Used for the
 * preview, for an issued quote and for what a signer sees, so all three show
 * the same columns in the same order.
 */
export function QuoteContentTable({ content, label }: { content: QuoteContent; label: string }) {
  const showSubtotals = content.subtotals_per_year.length > 1;
  return (
    <nldd-table
      accessible-label={label}
      columns="minmax(180px,2fr) 70px minmax(170px,1.4fr) minmax(150px,1.2fr) minmax(120px,1fr) minmax(120px,1fr)"
    >
      <nldd-table-row slot="header">
        <nldd-text-cell text="Omschrijving" />
        <nldd-text-cell text="FTE" horizontal-alignment="right" />
        <nldd-text-cell text="Periode" />
        <nldd-text-cell text="Schaal" />
        <nldd-text-cell text="Maandtarief" horizontal-alignment="right" />
        <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
      </nldd-table-row>
      {content.lines.map((line) => (
        <nldd-table-row key={line.position}>
          <nldd-text-cell
            text={line.description}
            {...(line.role && line.role !== line.description
              ? { 'supporting-text': line.role }
              : {})}
          />
          <nldd-text-cell
            text={line.kind === 'personnel' ? formatFte(line.fte) : ''}
            horizontal-alignment="right"
          />
          <nldd-text-cell text={periodText(line)} />
          <nldd-text-cell text={line.kind === 'personnel' ? scaleText(line) : ''} />
          <nldd-text-cell text={rateText(line)} horizontal-alignment="right" />
          <nldd-text-cell text={formatEuro(line.amount_cents)} horizontal-alignment="right" />
        </nldd-table-row>
      ))}
      {showSubtotals
        ? content.subtotals_per_year.map((subtotal) => (
            <nldd-table-row key={`subtotal-${subtotal.year}`}>
              <nldd-text-cell text={`Subtotaal ${subtotal.year}`} />
              <nldd-text-cell text="" />
              <nldd-text-cell text="" />
              <nldd-text-cell text="" />
              <nldd-text-cell text="" />
              <nldd-text-cell
                text={formatEuro(subtotal.amount_cents)}
                horizontal-alignment="right"
              />
            </nldd-table-row>
          ))
        : null}
      <nldd-table-row>
        <nldd-title-cell text="Totaal" />
        <nldd-text-cell text="" />
        <nldd-text-cell text="" />
        <nldd-text-cell text="" />
        <nldd-text-cell text="" />
        <nldd-text-cell
          text={formatEuro(content.total_cents)}
          horizontal-alignment="right"
        />
      </nldd-table-row>
    </nldd-table>
  );
}
