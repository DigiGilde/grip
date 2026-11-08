import { useNavigate } from 'react-router-dom';
import {
  NOTHING_PLANNED_TEXT,
  nothingPlanned,
  varianceWord,
} from '@/features/assignments/financeText';
import { assignmentPath } from '@/features/assignments/paths';
import { hasFigures, type Figures, type OverviewRow } from '@/features/overview/api';
import { MoneyCell, NumberCell } from '@/features/reports/ui';
import { formatEuro, formatMonth, formatPercent } from '@/lib/format';
import { IconCell } from '@/ui/Icon';
import { NameLine } from '@/ui/layout';
import { OpenRow, ROW_ACTIONS_COLUMN } from '@/ui/RowActions';

function varianceNote(figures: Figures): string {
  const word = varianceWord(figures).toLowerCase();
  return figures.variance_pct === null ? word : `${formatPercent(figures.variance_pct)}, ${word}`;
}

function VarianceCell({ figures, bold }: { figures: Figures; bold?: boolean }) {
  if (nothingPlanned(figures)) return <NumberCell text={NOTHING_PLANNED_TEXT} muted />;
  return (
    <MoneyCell
      cents={Math.abs(figures.variance_cents)}
      bold={bold}
      note={varianceNote(figures)}
      {...(figures.overrun ? { critical: true } : {})}
    />
  );
}

function AmountCells({ figures, bold }: { figures: Figures; bold?: boolean }) {
  const used = figures.realised_pct === null ? '' : formatPercent(figures.realised_pct);
  return (
    <>
      <MoneyCell cents={figures.budgeted_cents} bold={bold} hideBelow="md" />
      <MoneyCell cents={figures.expected_total_cents} bold={bold} />
      <VarianceCell figures={figures} bold={bold} />
      <NumberCell
        text={bold && used ? `**${used}**` : used}
        hideBelow="md"
        {...(bold && used ? { note: `${formatEuro(figures.realised_total_cents)} gerealiseerd` } : {})}
      />
    </>
  );
}

/** How far the amounts of a row are real, when the rows differ in that. */
function standText(row: OverviewRow): string {
  return row.reference_month
    ? `Stand t/m ${formatMonth(row.reference_month)}`
    : 'Nog geen maand afgesloten';
}

function detailOf(row: OverviewRow, perRow: boolean): string | undefined {
  if (row.pricing_error) return row.pricing_error;
  return [row.client_name, perRow ? standText(row) : null].filter(Boolean).join(' · ') || undefined;
}

/**
 * Running work per assignment, with every amount of the rule in one row and
 * the total under it. The name opens the landing of the assignment.
 */
export function AssignmentsSheet({
  rows,
  total,
  label,
  perRowStand,
}: {
  rows: readonly OverviewRow[];
  total: Figures | undefined;
  label: string;
  /** The rows differ in how far they are closed: each says so itself. */
  perRowStand: boolean;
}) {
  const navigate = useNavigate();
  return (
    <nldd-table
      accessible-label={label}
      columns={`minmax(260px,2fr) 140px 150px 170px 110px ${ROW_ACTIONS_COLUMN}`}
      sm-columns={`minmax(0,1fr) 92px 100px`}
      data-testid="assignments-sheet"
    >
      <nldd-table-row slot="header">
        <nldd-text-cell text="Opdracht" />
        <nldd-text-cell text="Begroot" horizontal-alignment="right" hide-below="md" />
        <nldd-text-cell text="Verwacht totaal" horizontal-alignment="right" />
        <nldd-text-cell text="Afwijking" horizontal-alignment="right" />
        <nldd-text-cell text="Uitputting" horizontal-alignment="right" hide-below="md" />
        <nldd-cell hide-below="md">
          <span className="grip-visually-hidden">Acties</span>
        </nldd-cell>
      </nldd-table-row>
      {rows.map((row) => (
        <OpenRow key={row.assignment_id} onOpen={() => navigate(assignmentPath(row.assignment_id))}>
          <nldd-cell row-header>
            <NameLine detail={detailOf(row, perRowStand)}>
              <nldd-link size="md" href={assignmentPath(row.assignment_id)} text={row.name} />
            </NameLine>
          </nldd-cell>
          {hasFigures(row.figures) ? (
            <AmountCells figures={row.figures} />
          ) : (
            <>
              <NumberCell text="Niet berekend" muted hideBelow="md" />
              <nldd-text-cell />
              <nldd-text-cell />
              <nldd-text-cell hide-below="md" />
            </>
          )}
          <IconCell concept="open" hide-below="md" />
        </OpenRow>
      ))}
      {total && (
        <nldd-table-row>
          <nldd-text-cell text="**Samen**" />
          <AmountCells figures={total} bold />
          <nldd-cell hide-below="md" />
        </nldd-table-row>
      )}
    </nldd-table>
  );
}
