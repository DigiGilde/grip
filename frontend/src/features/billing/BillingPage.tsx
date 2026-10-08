import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/api/client';
import { Button, SelectInput } from '@/features/assignments/ui';
import {
  billingAcrossKey,
  deliverBatch,
  fetchBillingAcross,
  type BillingOverview,
  type BillingPeriod,
} from '@/features/month-close/billingApi';
import { deliverPeriodPath, monthClosePath } from '@/features/month-close/paths';
import { PERIOD_STATE_TEXT, periodAmount, periodLine } from '@/features/month-close/periodText';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { formatEuro } from '@/lib/format';
import { EmptyNotice, ErrorNotice, FormSheet, Loading, Page, Stack } from '@/ui/layout';

interface Row {
  overview: BillingOverview;
  period: BillingPeriod;
}

/** What asks for an act comes first; within that, the oldest period. */
const ORDER: Record<BillingPeriod['state'], number> = {
  ready: 0,
  to_close: 1,
  delivered: 2,
  running: 3,
  invoiced: 4,
};

function rowsOf(assignments: BillingOverview[]): Row[] {
  const rows: Row[] = [];
  for (const overview of assignments) {
    for (const period of overview.periods) {
      if (period.state === 'invoiced' || period.state === 'running') continue;
      rows.push({ overview, period });
    }
  }
  return rows.sort(
    (a, b) =>
      ORDER[a.period.state] - ORDER[b.period.state] ||
      a.period.key.localeCompare(b.period.key) ||
      a.overview.assignment_name.localeCompare(b.overview.assignment_name),
  );
}

function complete(overview: BillingOverview): boolean {
  return (overview.terms.missing_details ?? []).length === 0;
}

function capital(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function link(row: Row): string {
  const { overview, period } = row;
  if (period.state === 'ready') return deliverPeriodPath(overview.assignment_id, period.key);
  const month = period.months.find((entry) => entry.state === 'to_close');
  if (month) return monthClosePath(overview.assignment_id, month.month);
  return deliverPeriodPath(overview.assignment_id, period.key).split('?')[0] ?? '';
}

function remark(row: Row): string {
  if (row.period.state === 'ready' && !complete(row.overview)) {
    return 'Het factuuradres ontbreekt nog';
  }
  return periodLine(row.period);
}

/**
 * Closing and billing over all the assignments someone manages. A manager
 * with ten assignments thinks per period, not per assignment: what is ready
 * goes to the financial administration in one go.
 */
export function BillingPage() {
  const instance = useInstance();
  const queryClient = useQueryClient();
  const containerRef = useRef<HTMLDivElement>(null);
  useRouterLinks(containerRef);
  const across = useQuery({ queryKey: billingAcrossKey, queryFn: fetchBillingAcross });
  const [asking, setAsking] = useState(false);
  const [via, setVia] = useState<'mail' | 'self'>('self');
  const [error, setError] = useState<string | null>(null);

  const rows = rowsOf(across.data?.assignments ?? []);
  const batch = rows.filter(
    (row) => row.period.state === 'ready' && row.overview.may_deliver && complete(row.overview),
  );
  const total = batch.reduce((sum, row) => sum + (row.period.to_deliver_cents ?? 0), 0);
  const canMail = Boolean(across.data?.can_mail);

  const deliver = useMutation({
    mutationFn: () =>
      deliverBatch(
        batch.map((row) => ({
          assignment_id: row.overview.assignment_id,
          period_key: row.period.key,
        })),
        canMail ? via : 'self',
      ),
    onSuccess: async () => {
      setAsking(false);
      await queryClient.invalidateQueries({ queryKey: ['billing'] });
      await queryClient.invalidateQueries({ queryKey: ['months'] });
      await queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
    onError: (failure) => setError(errorMessage(failure)),
  });

  const count = batch.length;
  const title =
    count === 0
      ? 'Er staat niets klaar om aan te leveren'
      : `${count} ${count === 1 ? 'periode is' : 'perioden zijn'} klaar: ${formatEuro(total)}`;
  return (
    <div ref={containerRef}>
      <Page title="Factureren" instanceName={instance?.name} spacing="sections">
        {across.isPending ? <Loading /> : null}
        {across.isError ? <ErrorNotice message={errorMessage(across.error)} /> : null}
        {across.data ? (
          <>
            <nldd-card background="tinted" accessible-label="Nu te doen">
              <nldd-container padding="24" gap="16">
                <nldd-title
                  size={2}
                  heading-level={2}
                  overline={count === 0 ? 'Niets te doen' : 'Nu te doen'}
                  text={title}
                  {...(count > 0
                    ? {
                        'supporting-text':
                          'Voor elke periode maakt grip een factuurverzoek voor de financiële administratie.',
                      }
                    : {})}
                />
                {count > 0 ? (
                  <nldd-button-group>
                    <Button
                      appearance="primary"
                      text={count === 1 ? 'Lever aan' : 'Lever alles aan'}
                      onClick={() => {
                        setError(null);
                        setVia(canMail ? 'mail' : 'self');
                        setAsking(true);
                      }}
                    />
                  </nldd-button-group>
                ) : null}
              </nldd-container>
            </nldd-card>

            {rows.length > 0 ? (
              <Stack gap="related">
                <nldd-title size={4} heading-level={2} text="Open perioden" />
                <nldd-table
                  accessible-label="Open perioden van alle opdrachten"
                  columns="minmax(200px,2fr) minmax(170px,1.4fr) 210px minmax(180px,2fr) minmax(120px,1fr)"
                  sm-columns="minmax(140px,1fr) minmax(100px,auto)"
                >
                  <nldd-table-row slot="header">
                    <nldd-text-cell text="Opdracht" />
                    <nldd-text-cell hide-below="md" text="Periode" />
                    <nldd-text-cell hide-below="md" text="Stand" />
                    <nldd-text-cell hide-below="md" text="Laatste stap" />
                    <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
                  </nldd-table-row>
                  {rows.map((row) => {
                    const amount = periodAmount(row.period);
                    const ready = row.period.state === 'ready';
                    return (
                      <nldd-table-row key={`${row.overview.assignment_id}-${row.period.key}`}>
                        <nldd-cell>
                          <nldd-link href={link(row)} text={row.overview.assignment_name} />
                        </nldd-cell>
                        <nldd-text-cell hide-below="md" text={capital(row.period.label)} />
                        <nldd-cell hide-below="md">
                          <nldd-badge
                            color={ready ? 'accent' : 'neutral'}
                            text={PERIOD_STATE_TEXT[row.period.state]}
                          />
                        </nldd-cell>
                        <nldd-text-cell
                          hide-below="md"
                          size="sm"
                          color={ready && !complete(row.overview) ? 'warning' : 'secondary'}
                          text={remark(row)}
                        />
                        <nldd-text-cell
                          horizontal-alignment="right"
                          text={amount ? `**${formatEuro(amount)}**` : ''}
                          hide-above="sm"
                          supporting-text={`${capital(row.period.label)} · ${PERIOD_STATE_TEXT[row.period.state].toLowerCase()}`}
                        />
                        <nldd-text-cell
                          hide-below="md"
                          horizontal-alignment="right"
                          text={amount ? `**${formatEuro(amount)}**` : ''}
                        />
                      </nldd-table-row>
                    );
                  })}
                </nldd-table>
              </Stack>
            ) : (
              <EmptyNotice text="Alle perioden die voorbij zijn, zijn afgesloten en gefactureerd" />
            )}
          </>
        ) : null}
      </Page>

      <FormSheet
        open={asking}
        title={count === 1 ? 'Lever aan' : `Lever ${count} perioden aan`}
        submitText={`Lever ${formatEuro(total)} aan`}
        busy={deliver.isPending}
        error={error}
        onClose={() => setAsking(false)}
        onSubmit={() => {
          setError(null);
          deliver.mutate();
        }}
      >
        <nldd-list accessible-label="Perioden die worden aangeleverd">
          {batch.map((row) => (
            <nldd-list-item key={`${row.overview.assignment_id}-${row.period.key}`}>
              <nldd-text-cell
                text={row.overview.assignment_name}
                supporting-text={capital(row.period.label)}
              />
              <nldd-text-cell
                width="fit-content"
                horizontal-alignment="right"
                text={formatEuro(row.period.to_deliver_cents)}
              />
            </nldd-list-item>
          ))}
        </nldd-list>
        {canMail ? (
          <SelectInput
            label="Hoe lever je aan"
            value={via}
            onChange={(value) => setVia(value === 'self' ? 'self' : 'mail')}
            options={[
              { value: 'mail', label: 'Mail de financiële administratie' },
              { value: 'self', label: 'Ik geef de factuurverzoeken zelf door' },
            ]}
          />
        ) : null}
      </FormSheet>
    </div>
  );
}
