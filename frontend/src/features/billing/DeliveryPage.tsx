import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import {
  deliveryDocumentUrl,
  fetchDelivery,
  type DeliveryLine,
} from '@/features/month-close/billingApi';
import { DETAIL_LABELS } from '@/features/month-close/periodText';
import { useInstance } from '@/layout/useInstance';
import { formatDate, formatEuro, formatPercent } from '@/lib/format';
import { ActionBar } from '@/ui/ActionBar';
import { ErrorNotice, Facts, Loading, Page, Section } from '@/ui/layout';

const ADDRESS = ['organisation', 'attention_of', 'address', 'postcode_city', 'reference'] as const;

function Lines({ lines }: { lines: DeliveryLine[] }) {
  const named = lines.some((line) => line.person_name);
  return (
    <nldd-table
      accessible-label="Specificatie"
      columns={`minmax(120px,1fr) minmax(160px,2fr) ${named ? 'minmax(140px,1.5fr) ' : ''}90px minmax(110px,1fr) minmax(110px,1fr)`}
    >
      <nldd-table-row slot="header">
        <nldd-text-cell text="Maand" />
        <nldd-text-cell text="Omschrijving" />
        {named ? <nldd-text-cell text="Naam" /> : null}
        <nldd-text-cell text="Inzet" horizontal-alignment="right" />
        <nldd-text-cell text="Maandtarief" horizontal-alignment="right" />
        <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
      </nldd-table-row>
      {lines.map((line, index) => (
        <nldd-table-row key={`${line.month}-${line.description}-${index}`}>
          <nldd-text-cell text={line.month_label} />
          <nldd-text-cell text={line.description} />
          {named ? <nldd-text-cell text={line.person_name} /> : null}
          <nldd-text-cell text={formatPercent(line.fte_pct)} horizontal-alignment="right" />
          <nldd-text-cell text={formatEuro(line.monthly_rate_cents)} horizontal-alignment="right" />
          <nldd-text-cell text={formatEuro(line.amount_cents)} horizontal-alignment="right" />
        </nldd-table-row>
      ))}
    </nldd-table>
  );
}

/**
 * One delivery, as the financial administration opens it from the mail:
 * what to invoice, to whom, and the document that says it.
 */
export function DeliveryPage() {
  const { deliveryId = '' } = useParams();
  const instance = useInstance();
  const delivery = useQuery({
    queryKey: ['billing', 'delivery', deliveryId],
    queryFn: () => fetchDelivery(deliveryId),
  });
  const data = delivery.data;
  return (
    <Page
      title={data ? `Factuurverzoek ${data.reference}` : 'Factuurverzoek'}
      instanceName={instance?.name}
      spacing="sections"
    >
      {delivery.isPending ? <Loading /> : null}
      {delivery.isError ? <ErrorNotice message={errorMessage(delivery.error)} /> : null}
      {data ? (
        <>
          <nldd-card background="tinted" accessible-label="Te factureren">
            <nldd-container padding="24">
              <nldd-title
                size={2}
                heading-level={2}
                overline={`Te factureren over ${data.period_label}`}
                text={formatEuro(data.total_cents)}
                supporting-text={`${data.assignment_name}${data.client_name ? ` voor ${data.client_name}` : ''} · aangeleverd op ${formatDate(data.delivered_at)}${data.delivered_by_name ? ` door ${data.delivered_by_name}` : ''}`}
              />
            </nldd-container>
          </nldd-card>
          {data.has_document ? (
            <ActionBar
              label="Het factuurverzoek"
              actions={[
                {
                  text: 'Bekijk factuurverzoek (pdf)',
                  href: deliveryDocumentUrl(data.id),
                  kind: 'elsewhere',
                  primary: true,
                },
              ]}
            />
          ) : null}
          <Section title="Factuur aan">
            <Facts
              label="Factuur aan"
              facts={ADDRESS.filter((key) => data.details[key]).map((key) => ({
                label: DETAIL_LABELS[key],
                value: data.details[key],
              }))}
            />
          </Section>
          <Section title="Specificatie">
            <Lines lines={data.lines} />
          </Section>
        </>
      ) : null}
    </Page>
  );
}
