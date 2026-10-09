/** The words and the order of the cost screens, in one place so both say the same. */
import { formatEuro, formatMonth, formatPercent } from '@/lib/format';
import { PATHS } from '@/paths';
import type { CostItem, InvoiceLine } from './api';

/**
 * The fixed money words, as they read for a cost: what an assignment calls
 * "Gerealiseerd" is an invoice that has come in, and "Nog gepland" is an
 * invoice that is still expected.
 */
export const COST_LABELS = {
  budgeted: 'Begroot',
  received: 'Ontvangen',
  expected: 'Nog verwacht',
  forecast: 'Verwacht totaal',
  variance: 'Afwijking',
  covered: 'Gedekt',
  uncovered: 'Ongedekt',
} as const;

/** The variance in words, never by colour alone. */
export function varianceWord(item: Pick<CostItem, 'variance_cents'>): string {
  if (item.variance_cents < 0) return 'Overschrijding';
  if (item.variance_cents > 0) return 'Ruimte';
  return 'Precies begroot';
}

/** The words searched for, in the address. */
export const SEARCH_PARAM = 'zoek';
export const YEAR_PARAM = 'jaar';
export const ALL_YEARS = 'alle';

/** The choice of the year filter: the whole duration, or one of three years. */
export function yearOptions(now: Date = new Date()) {
  const year = now.getFullYear();
  return [
    { value: ALL_YEARS, label: 'Hele looptijd' },
    ...[year - 1, year, year + 1].map((value) => ({ value: String(value), label: String(value) })),
  ];
}

/** The year in the address; null for the whole duration or anything else. */
export function parseYear(value: string | null): number | null {
  return value !== null && /^\d{4}$/.test(value) ? Number(value) : null;
}

/** The page of one cost item, carrying the year the list was filtered on. */
export function costItemPath(id: string, year: number | null = null): string {
  const path = PATHS.costItem.replace(':costItemId', id);
  return year === null ? path : `${path}?${YEAR_PARAM}=${year}`;
}

export function costsPath(year: number | null = null): string {
  return year === null ? PATHS.costs : `${PATHS.costs}?${YEAR_PARAM}=${year}`;
}

/** What an invoice is called: its reference, else its description. */
export function lineLabel(line: Pick<InvoiceLine, 'reference' | 'description' | 'kind'>): string {
  return (
    line.reference ?? line.description ?? (line.kind === 'actual' ? 'Factuur' : 'Verwachte factuur')
  );
}

/** The quiet line under an invoice: its month, and its description when the name is the reference. */
export function lineDetail(line: InvoiceLine): string {
  return [line.period ? formatMonth(line.period) : '', line.reference ? line.description : null]
    .filter(Boolean)
    .join(' · ');
}

/** Invoices in the order of time; one without a period comes last. */
export function inTimeOrder(lines: readonly InvoiceLine[]): InvoiceLine[] {
  return [...lines].sort((a, b) => {
    if (a.period === b.period) return 0;
    if (a.period === null) return 1;
    if (b.period === null) return -1;
    return a.period < b.period ? -1 : 1;
  });
}

/** A received invoice of which the invoice itself is not attached. */
export function lacksDocument(line: InvoiceLine): boolean {
  return line.kind === 'actual' && line.attachments.length === 0;
}

export function attachmentCount(count: number): string {
  return count === 1 ? '1 bijlage' : `${count} bijlagen`;
}

/**
 * What asks for attention on a cost item, most pressing first: money nobody
 * pays for, an overrun, and a received invoice without its document.
 */
export function attentionPoints(item: CostItem): string[] {
  const points: string[] = [];
  if (item.uncovered_cents === null) points.push('Dekking boven 100%');
  else if (item.uncovered_cents > 0) points.push(`${formatEuro(item.uncovered_cents)} ongedekt`);
  if (item.variance_cents < 0) points.push('Overschrijding');
  const missing = item.invoice_lines.filter(lacksDocument).length;
  if (missing === 1) points.push('1 factuur zonder bijlage');
  else if (missing > 1) points.push(`${missing} facturen zonder bijlage`);
  return points;
}

/** "80% gedekt", or what to say when the shares do not add up. */
export function coverageText(item: CostItem): string {
  return item.covered_cents === null
    ? `${formatPercent(item.pct_total)} vastgelegd`
    : `${formatPercent(item.pct_total)} gedekt`;
}

/**
 * Who can change a cost item, for a reader who cannot. An item no budget
 * covers is managed by whoever made it and the beheerder; otherwise by the
 * managers of the assignments that cover it.
 */
export function whoCanEdit(item: CostItem): string {
  const covered = item.coverages.length > 0 || Number(item.hidden_coverage_pct) > 0;
  return covered
    ? 'Je kunt deze kostenpost bekijken. Wijzigen kan een manager van een opdracht die de kostenpost dekt, of de beheerder.'
    : 'Je kunt deze kostenpost bekijken. Wijzigen kan de beheerder, of wie de kostenpost heeft aangemaakt.';
}

/** The action that adds a share: the first one, or what is left after the others. */
export function addCoverageText(item: CostItem): string {
  const covered = item.coverages.length > 0 || Number(item.hidden_coverage_pct) > 0;
  return covered ? 'Verdeel het restant' : 'Leg dekking vast';
}

/** The step of the ramp for the nth covering budget line; past four they share the last. */
export function coverageStep(index: number): string {
  return String(Math.min(index, 3) + 1);
}

/** "20.00" as someone types it: "20"; "12.50" as "12,5". */
export function pctToInput(pct: string | null | undefined): string {
  if (!pct) return '';
  return pct
    .replace(/(\.\d*?)0+$/, '$1')
    .replace(/\.$/, '')
    .replace('.', ',');
}
