import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { STATUS_COLORS, statusLabel } from '@/features/assignments/labels';
import { EmptyNotice, ErrorNotice, Loading } from '@/features/assignments/ui';
import { RouterLinks } from '@/layout/RouterLinks';
import { fetchYearAccount, reportKeys, yearAccountCsvUrl, type YearAccountRow } from './api';
import { KIND_LABELS, scopeNote } from './labels';
import { assignmentReportPath } from './paths';
import { MoneyCell, ReportBlock } from './ui';

const AMOUNT_COLUMNS = '130px 130px 130px 130px 130px 130px 140px 140px';

/** Whether the API sent amounts for this row at all. */
const hasAmounts = (row: YearAccountRow) => 'billed_cents' in row;

function AmountCells({ row }: { row: YearAccountRow }) {
  if (!hasAmounts(row)) {
    return (
      <>
        {Array.from({ length: 8 }, (_, index) => (
          <nldd-text-cell key={index} />
        ))}
      </>
    );
  }
  const overAgreement = typeof row.difference_cents === 'number' && row.difference_cents < 0;
  return (
    <>
      <MoneyCell
        cents={row.agreed_cents}
        {...(row.agreed_cents === null ? { note: 'Geen akkoord' } : {})}
      />
      <MoneyCell
        cents={row.budgeted_cents}
        {...(row.pricing_error ? { note: row.pricing_error } : {})}
      />
      <MoneyCell cents={row.realised_cents} />
      <MoneyCell cents={row.forecast_cents} />
      <MoneyCell cents={row.costs_cents} />
      <MoneyCell cents={row.billed_cents} />
      <MoneyCell cents={row.to_bill_cents} />
      <MoneyCell
        cents={row.difference_cents}
        {...(overAgreement ? { critical: true, note: 'Meer dan afgesproken' } : {})}
      />
    </>
  );
}

/** The year account: assignments received and carried out in a budget year. */
export function YearAccountView({ year }: { year: string }) {
  const query = useQuery({
    queryKey: reportKeys.yearAccount(year),
    queryFn: () => fetchYearAccount(year),
  });
  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorNotice message={errorMessage(query.error)} />;
  const account = query.data;
  const rows = account.rows ?? [];
  if (rows.length === 0) {
    return (
      <EmptyNotice
        text={`Er zijn geen opdrachten in ${account.year}`}
        supportingText="Je ziet hier de opdrachten waar je bij betrokken bent en die in dit jaar lopen."
      />
    );
  }
  const totals = account.totals;
  const showAmounts = rows.some(hasAmounts);
  return (
    <ReportBlock
      testId="year-account"
      title={`Jaarverantwoording ${account.year}`}
      note={scopeNote(
        account.scope,
        'Alle opdrachten die in dit jaar lopen. Van een opdracht over meerdere jaren tellen de maanden van dit jaar.',
        'De opdrachten waar je bij betrokken bent. Van een opdracht over meerdere jaren tellen de maanden van dit jaar.',
      )}
    >
      <RouterLinks>
        <nldd-table
          accessible-label={`Jaarverantwoording ${account.year}`}
          columns={`minmax(220px,2fr) minmax(170px,1fr) 100px 170px${showAmounts ? ` ${AMOUNT_COLUMNS}` : ''}`}
        >
          <nldd-table-row slot="header">
            <nldd-text-cell text="Opdracht" />
            <nldd-text-cell text="Opdrachtgever" />
            <nldd-text-cell text="Soort" />
            <nldd-text-cell text="Status" />
            {showAmounts && (
              <>
                <nldd-text-cell text="Afgesproken" horizontal-alignment="right" />
                <nldd-text-cell text="Begroot" horizontal-alignment="right" />
                <nldd-text-cell text="Gerealiseerd" horizontal-alignment="right" />
                <nldd-text-cell text="Prognose" horizontal-alignment="right" />
                <nldd-text-cell text="Kosten" horizontal-alignment="right" />
                <nldd-text-cell text="Gefactureerd" horizontal-alignment="right" />
                <nldd-text-cell text="Nog te factureren" horizontal-alignment="right" />
                <nldd-text-cell text="Afgesproken min gerealiseerd" horizontal-alignment="right" />
              </>
            )}
          </nldd-table-row>
          {rows.map((row) => (
            <nldd-table-row key={row.assignment_id}>
              <nldd-cell>
                <nldd-link href={assignmentReportPath(row.assignment_id)} text={row.name} />
              </nldd-cell>
              <nldd-text-cell text={row.client_name ?? ''} />
              <nldd-text-cell text={KIND_LABELS[row.kind] ?? row.kind} />
              <nldd-cell>
                <nldd-badge
                  color={STATUS_COLORS[row.status] ?? 'neutral'}
                  text={statusLabel(row.status)}
                />
              </nldd-cell>
              {showAmounts && <AmountCells row={row} />}
            </nldd-table-row>
          ))}
          {showAmounts && totals && (
            <nldd-table-row>
              <nldd-text-cell text="**Totaal**" />
              <nldd-text-cell />
              <nldd-text-cell />
              <nldd-text-cell />
              <MoneyCell cents={totals.agreed_cents} bold />
              <MoneyCell cents={totals.budgeted_cents} bold />
              <MoneyCell cents={totals.realised_cents} bold />
              <MoneyCell cents={totals.forecast_cents} bold />
              <MoneyCell cents={totals.costs_cents} bold />
              <MoneyCell cents={totals.billed_cents} bold />
              <MoneyCell cents={totals.to_bill_cents} bold />
              <nldd-text-cell />
            </nldd-table-row>
          )}
        </nldd-table>
      </RouterLinks>
      <nldd-text size="sm" color="secondary">
        Een opdracht opent de rapportage van die opdracht. Gefactureerd is wat in factuurgegevens
        van afgesloten maanden is vastgelegd.
      </nldd-text>
      {totals && (
        <div>
          <nldd-link
            href={yearAccountCsvUrl(String(account.year))}
            text={`Download de jaarverantwoording ${account.year} als CSV`}
            size="md"
          />
        </div>
      )}
    </ReportBlock>
  );
}
