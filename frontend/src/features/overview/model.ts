/** What the start page shows, worked out from the overview response. */
import { FIGURE_LABELS } from '@/features/assignments/financeText';
import type { Phase } from '@/features/assignments/labels';
import { assignmentTabPath, type AssignmentTabKey } from '@/features/assignments/paths';
import { formatEuro, formatMonth } from '@/lib/format';
import { hasFigures, type Overview, type OverviewRow } from './api';

export type SortMode = 'attention' | 'name';

export const SORT_OPTIONS: readonly { value: SortMode; label: string }[] = [
  { value: 'attention', label: 'Aandacht eerst' },
  { value: 'name', label: 'Alfabetisch' },
];

export interface AttentionItem {
  key: string;
  assignment: string;
  text: string;
  href: string;
  /** An overrun is wrong now; the rest waits. */
  tone: 'critical' | 'info';
}

const TABS = new Set(['finance', 'monthClose', 'budget', 'staffing', 'quote', 'overview']);

/** Every attention point of every row, the most pressing first, each a link. */
export function attentionItems(rows: readonly OverviewRow[]): AttentionItem[] {
  return [...rows]
    .sort((a, b) => urgency(a) - urgency(b) || a.name.localeCompare(b.name, 'nl'))
    .flatMap((row) =>
      (row.attention ?? []).map((point) => ({
        key: `${row.assignment_id}-${point.kind}`,
        assignment: row.name,
        text: point.text,
        tone: point.kind === 'overrun' ? ('critical' as const) : ('info' as const),
        href: assignmentTabPath(
          row.assignment_id,
          (TABS.has(point.tab) ? point.tab : 'overview') as AssignmentTabKey,
        ),
      })),
    );
}

/** Lower is more pressing: an overrun, then any other point, then nothing. */
function urgency(row: OverviewRow): number {
  const points = row.attention ?? [];
  if (points.some((point) => point.kind === 'overrun')) return 0;
  return points.length > 0 ? 1 : 2;
}

export function sortRows(rows: readonly OverviewRow[], mode: SortMode): OverviewRow[] {
  const byName = (a: OverviewRow, b: OverviewRow) => a.name.localeCompare(b.name, 'nl');
  return [...rows].sort(
    mode === 'name' ? byName : (a, b) => urgency(a) - urgency(b) || byName(a, b),
  );
}

/** The rows of a phase that have something in the chosen year, and how many do not. */
export function rowsOfPhase(rows: readonly OverviewRow[], phase: Phase) {
  const inPhase = rows.filter((row) => row.phase === phase);
  const shown = inPhase.filter((row) => row.in_year !== false);
  return { shown, leftOut: inPhase.length - shown.length };
}

/**
 * The reference month when every row with amounts has the same one:
 * a string, null for "no month closed", undefined when the rows differ.
 */
export function sharedReference(rows: readonly OverviewRow[]): string | null | undefined {
  const months = new Set(
    rows.filter((row) => hasFigures(row.figures)).map((row) => row.reference_month ?? null),
  );
  if (months.size !== 1) return undefined;
  return [...months][0];
}

export interface StartTile {
  key: string;
  label: string;
  value: string;
  context: string;
  attention?: string;
}

/** The few figures of running work, and the pipeline apart. Empty without amounts. */
export function startTiles(
  overview: Overview,
  period: string,
  reference: string | null | undefined,
): StartTile[] {
  const active = overview.figures_active;
  if (!active) return [];
  const tiles: StartTile[] = [
    {
      key: 'expected',
      label: `${FIGURE_LABELS.expected} lopend werk, ${period}`,
      value: formatEuro(active.expected_total_cents),
      context: `van ${formatEuro(active.budgeted_cents)} begroot`,
      ...(active.overrun ? { attention: 'Boven de begroting' } : {}),
    },
    {
      key: 'realised',
      label: FIGURE_LABELS.realised,
      value: formatEuro(active.realised_total_cents),
      context: reference
        ? `t/m ${formatMonth(reference)}`
        : reference === null
          ? active.realised_cents === 0 && active.realised_total_cents !== 0
            ? 'alleen kosten; nog geen maand afgesloten'
            : 'nog geen maand afgesloten'
          : '',
    },
  ];
  if (overview.to_deliver_cents != null) {
    tiles.push({
      key: 'deliver',
      label: 'Nog aan te leveren',
      value: formatEuro(overview.to_deliver_cents),
      context:
        overview.to_invoice_cents != null && overview.to_invoice_cents !== 0
          ? `${formatEuro(overview.to_invoice_cents)} nog te factureren`
          : '',
    });
  }
  const pipeline = overview.figures_potential;
  if (pipeline && pipeline.expected_total_cents !== 0) {
    tiles.push({
      key: 'pipeline',
      label: 'Potentiële opdrachten',
      value: formatEuro(pipeline.expected_total_cents),
      context: 'telt niet mee in lopend werk',
    });
  }
  return tiles;
}
