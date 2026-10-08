import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { ErrorNotice, Loading, SectionHeading } from '@/features/assignments/ui';
import { formatEuro, formatFte, formatPercent, formatPeriod } from '@/lib/format';
import { fetchAssignmentOverview, hasAmounts, overviewKeys, type LineOverview } from './api';
import { TOTALS_COLUMNS, TotalsCells, TotalsHeaderCells } from './TotalsCells';
import { YearFilter } from './YearFilter';
import { currentYearChoice, periodLabel } from './years';

function lineSummary(line: LineOverview): string {
  const parts = [
    line.role,
    line.fte ? `${formatFte(line.fte)} FTE` : '',
    line.rate_category ? `categorie ${line.rate_category}` : '',
    formatPeriod(line.start_date, line.end_date),
  ];
  return parts.filter(Boolean).join(', ');
}

function Team({ line }: { line: LineOverview }) {
  if (line.team.length === 0) return null;
  const showTime = line.team.some((member) => member.fte_pct !== undefined);
  const showAmount = line.team.some((member) => 'amount_cents' in member);
  return (
    <nldd-table
      accessible-label={`Team op ${line.description}`}
      columns={`minmax(180px,2fr)${showTime ? ' minmax(200px,1.5fr) 110px' : ''}${showAmount ? ' 140px' : ''}`}
    >
      <nldd-table-row slot="header">
        <nldd-text-cell text="Team" />
        {showTime && <nldd-text-cell text="Periode" />}
        {showTime && <nldd-text-cell text="Inzet" horizontal-alignment="right" />}
        {showAmount && <nldd-text-cell text="Bedrag" horizontal-alignment="right" />}
      </nldd-table-row>
      {line.team.map((member) => (
        <nldd-table-row key={member.allocation_id}>
          <nldd-text-cell
            text={member.person_name}
            {...(member.category_mismatch
              ? { 'supporting-text': 'Declareert in een andere categorie dan de regel aanneemt' }
              : {})}
          />
          {showTime && (
            <nldd-text-cell text={formatPeriod(member.start_date, member.end_date)} />
          )}
          {showTime && (
            <nldd-text-cell text={formatPercent(member.fte_pct)} horizontal-alignment="right" />
          )}
          {showAmount && (
            <nldd-text-cell
              text={
                'amount_cents' in member
                  ? member.amount_cents == null
                    ? 'Niet berekend'
                    : formatEuro(member.amount_cents)
                  : ''
              }
              {...(member.pricing_error ? { 'supporting-text': member.pricing_error } : {})}
              horizontal-alignment="right"
            />
          )}
        </nldd-table-row>
      ))}
    </nldd-table>
  );
}

function Costs({ line }: { line: LineOverview }) {
  const costs = line.costs ?? [];
  if (costs.length === 0) return null;
  return (
    <nldd-table accessible-label={`Kosten op ${line.description}`} columns="minmax(220px,2fr) 110px 140px">
      <nldd-table-row slot="header">
        <nldd-text-cell text="Kostenpost" />
        <nldd-text-cell text="Dekking" horizontal-alignment="right" />
        <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
      </nldd-table-row>
      {costs.map((cost) => (
        <nldd-table-row key={cost.cost_item_id}>
          <nldd-text-cell text={cost.description} />
          <nldd-text-cell text={formatPercent(cost.pct)} horizontal-alignment="right" />
          <nldd-text-cell
            text={cost.amount_cents == null ? 'Niet berekend' : formatEuro(cost.amount_cents)}
            horizontal-alignment="right"
          />
        </nldd-table-row>
      ))}
    </nldd-table>
  );
}

/** The budget lines of one assignment, and per line the team and the costs. */
export function AssignmentOverviewSection({ assignmentId }: { assignmentId: string }) {
  const [year, setYear] = useState(currentYearChoice);
  const query = useQuery({
    queryKey: overviewKeys.assignment(assignmentId, year),
    queryFn: () => fetchAssignmentOverview(assignmentId, year),
  });
  const overview = query.data;
  const lines = overview?.lines ?? [];
  const showAmounts = lines.some((line) => hasAmounts(line.totals) || line.pricing_error);

  return (
    <nldd-container gap="12">
      <SectionHeading text="Stand van zaken" />
      <div>
        <YearFilter value={year} onChange={setYear} />
      </div>
      {query.isPending && <Loading />}
      {query.isError && <ErrorNotice message={errorMessage(query.error)} />}
      {overview?.pricing_error && (
        <nldd-banner
          variant="warning"
          size="sm"
          text="Niet alle bedragen konden worden berekend."
          supporting-text={overview.pricing_error}
        />
      )}
      {showAmounts && (
        <nldd-table
          accessible-label={`Stand per begrotingsregel over ${periodLabel(year)}`}
          columns={`minmax(220px,2fr) ${TOTALS_COLUMNS}`}
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Begrotingsregel" />
            <TotalsHeaderCells />
          </nldd-table-row>
          {lines.map((line) => (
            <nldd-table-row key={line.budget_line_id}>
              <nldd-text-cell text={line.description} supporting-text={lineSummary(line)} />
              <TotalsCells totals={line.totals} error={line.pricing_error} />
            </nldd-table-row>
          ))}
          {hasAmounts(overview?.totals) && (
            <nldd-table-row>
              <nldd-text-cell text="**Totaal**" />
              <TotalsCells totals={overview?.totals} bold />
            </nldd-table-row>
          )}
        </nldd-table>
      )}
      {lines
        .filter((line) => line.team.length > 0 || (line.costs ?? []).length > 0)
        .map((line) => (
          <nldd-container key={line.budget_line_id} gap="8">
            <SectionHeading text={line.description} level={3} />
            <Team line={line} />
            <Costs line={line} />
          </nldd-container>
        ))}
    </nldd-container>
  );
}
