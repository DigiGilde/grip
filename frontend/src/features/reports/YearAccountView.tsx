import { DocumentLink } from '@/ui/Icon';
import { useQuery } from '@tanstack/react-query';
import { STATUS_COLORS, statusLabel } from '@/features/assignments/labels';
import { EmptyNotice, LoadError, Loading } from '@/ui/layout';
import { RouterLinks } from '@/layout/RouterLinks';
import { fetchYearAccount, reportKeys, yearAccountCsvUrl, type YearAccountRow } from './api';
import { KIND_LABELS, scopeNote } from './labels';
import { assignmentReportPath } from './paths';
import { formatEuro } from '@/lib/format';
import { Figures, MoneyCell, ReportBlock } from './ui';

const AMOUNT_COLUMNS = '125px 125px 125px 125px 110px 125px 135px 125px 135px 150px';

/** Whether the API sent amounts for this row at all. */
const hasAmounts = (row: YearAccountRow) => 'delivered_cents' in row;

function AmountCells({ row }: { row: YearAccountRow }) {
  if (!hasAmounts(row)) {
    return (
      <>
        {Array.from({ length: 10 }, (_, index) => (
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
      <MoneyCell cents={row.delivered_cents} />
      <MoneyCell
        cents={row.to_deliver_cents}
        {...((row.to_deliver_cents ?? 0) > 0 ? { note: 'Nog aan te leveren' } : {})}
      />
      <MoneyCell cents={row.invoiced_cents} />
      <MoneyCell
        cents={row.to_invoice_cents}
        {...((row.to_invoice_cents ?? 0) > 0 ? { note: 'Nog te factureren' } : {})}
      />
      <MoneyCell
        cents={row.difference_cents}
        {...(overAgreement ? { critical: true, note: 'Meer dan afgesproken' } : {})}
      />
    </>
  );
}

/** The year account: assignments received and carried out in a budget year. */
export function YearAccountView({ year, bare }: { year: string; bare?: boolean }) {
  const query = useQuery({
    queryKey: reportKeys.yearAccount(year),
    queryFn: () => fetchYearAccount(year),
  });
  if (query.isPending) return <Loading />;
  if (query.isError) return <LoadError error={query.error} retry={() => void query.refetch()} />;
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
      bare={bare}
      testId="year-account"
      title={`Jaarverantwoording ${account.year}`}
      note={scopeNote(
        account.scope,
        'Alle opdrachten die in dit jaar lopen. Van een opdracht over meerdere jaren tellen de maanden van dit jaar.',
        'De opdrachten waar je bij betrokken bent. Van een opdracht over meerdere jaren tellen de maanden van dit jaar.',
      )}
    >
      {totals && (
        <Figures
          label="Jaarverantwoording in het kort"
          figures={[
            {
              label: 'Afgesproken',
              value: formatEuro(totals.agreed_cents),
              detail: 'offertes met akkoord, het deel van dit jaar',
              quiet: totals.agreed_cents === 0,
            },
            {
              label: 'Gerealiseerd',
              value: formatEuro(totals.realised_cents),
              detail: `en ${formatEuro(totals.forecast_cents)} nog gepland`,
              quiet: totals.realised_cents === 0,
            },
            totals.to_deliver_cents > 0
              ? {
                  label: 'Nog aan te leveren',
                  value: formatEuro(totals.to_deliver_cents),
                  attention: 'Gerealiseerd, nog niet aangeleverd',
                  detail: `${formatEuro(totals.delivered_cents)} is aangeleverd`,
                }
              : {
                  label: 'Nog aan te leveren',
                  value: formatEuro(0),
                  detail: `${formatEuro(totals.delivered_cents)} is aangeleverd`,
                  quiet: true,
                },
            totals.to_invoice_cents > 0
              ? {
                  label: 'Nog te factureren',
                  value: formatEuro(totals.to_invoice_cents),
                  attention: 'Aangeleverd, geen factuur vastgelegd',
                  detail: `${formatEuro(totals.invoiced_cents)} is gefactureerd`,
                }
              : {
                  label: 'Nog te factureren',
                  value: formatEuro(0),
                  detail: `${formatEuro(totals.invoiced_cents)} is gefactureerd`,
                  quiet: true,
                },
          ]}
        />
      )}
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
                <nldd-text-cell text="Nog gepland" horizontal-alignment="right" />
                <nldd-text-cell text="Kosten" horizontal-alignment="right" />
                <nldd-text-cell text="Aangeleverd" horizontal-alignment="right" />
                <nldd-text-cell text="Nog aan te leveren" horizontal-alignment="right" />
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
              <MoneyCell cents={totals.delivered_cents} bold />
              <MoneyCell cents={totals.to_deliver_cents} bold />
              <MoneyCell cents={totals.invoiced_cents} bold />
              <MoneyCell cents={totals.to_invoice_cents} bold />
              <nldd-text-cell />
            </nldd-table-row>
          )}
        </nldd-table>
      </RouterLinks>
      <nldd-text size="sm" color="secondary">
        Een opdracht opent de rapportage van die opdracht. Aangeleverd is wat als factuurgegevens
        van afgesloten maanden naar de financiële administratie is gegaan. Gefactureerd is een
        factuur die in grip is vastgelegd als verstuurd; tot dat gebeurt telt niets als
        gefactureerd.
      </nldd-text>
      {totals && (
        <div>
          <DocumentLink
            kind="download"
            href={yearAccountCsvUrl(String(account.year))}
            text={`Download de jaarverantwoording ${account.year} als CSV`}
          />
        </div>
      )}
    </ReportBlock>
  );
}
