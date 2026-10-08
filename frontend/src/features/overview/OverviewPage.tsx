import { useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { assignmentPath } from '@/features/assignments/paths';
import { STATUS_COLORS, statusLabel } from '@/features/assignments/labels';
import { EmptyNotice, ErrorNotice, Loading } from '@/features/assignments/ui';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { PageHeading } from '@/pages/PageHeading';
import { fetchOverview, hasAmounts, overviewKeys } from './api';
import { TOTALS_COLUMNS, TotalsCells, TotalsHeaderCells } from './TotalsCells';
import { YearFilter } from './YearFilter';
import { currentYearChoice, periodLabel } from './years';

/** Stand van zaken: budgeted, used and available per assignment. */
export function OverviewPage() {
  const instance = useInstance();
  const [year, setYear] = useState(currentYearChoice);
  const tableRef = useRef<HTMLDivElement>(null);
  useRouterLinks(tableRef);

  const query = useQuery({ queryKey: overviewKeys.list(year), queryFn: () => fetchOverview(year) });
  const rows = query.data?.rows ?? [];
  const showAmounts = hasAmounts(query.data?.totals);

  return (
    <nldd-simple-section>
      <PageHeading text="Stand van zaken" instanceName={instance?.name} />
      <nldd-container gap="16">
        <div>
          <YearFilter value={year} onChange={setYear} />
        </div>
        {query.isPending && <Loading />}
        {query.isError && <ErrorNotice message={errorMessage(query.error)} />}
        {query.isSuccess && rows.length === 0 && (
          <EmptyNotice
            text="Er zijn geen opdrachten om te tonen"
            supportingText="Je ziet hier de opdrachten waar je bij betrokken bent."
          />
        )}
        {rows.length > 0 && (
          <div ref={tableRef}>
            <nldd-table
              accessible-label={`Stand van zaken over ${periodLabel(year)}`}
              columns={`minmax(220px,2fr) 170px${showAmounts ? ` ${TOTALS_COLUMNS}` : ' minmax(160px,1fr)'}`}
            >
              <nldd-table-row slot="header">
                <nldd-text-cell text="Opdracht" />
                <nldd-text-cell text="Status" />
                {showAmounts ? <TotalsHeaderCells /> : <nldd-text-cell text="Opdrachtgever" />}
              </nldd-table-row>
              {rows.map((row) => (
                <nldd-table-row key={row.assignment_id}>
                  <nldd-cell>
                    <nldd-link href={assignmentPath(row.assignment_id)} text={row.name} />
                  </nldd-cell>
                  <nldd-cell>
                    <nldd-badge
                      color={STATUS_COLORS[row.status] ?? 'neutral'}
                      text={statusLabel(row.status)}
                    />
                  </nldd-cell>
                  {showAmounts ? (
                    <TotalsCells totals={row.totals} error={row.pricing_error} />
                  ) : (
                    <nldd-text-cell text={row.client_name ?? ''} />
                  )}
                </nldd-table-row>
              ))}
              {showAmounts && (
                <nldd-table-row>
                  <nldd-text-cell text="**Totaal**" />
                  <nldd-text-cell />
                  <TotalsCells totals={query.data?.totals} bold />
                </nldd-table-row>
              )}
            </nldd-table>
          </div>
        )}
      </nldd-container>
    </nldd-simple-section>
  );
}
