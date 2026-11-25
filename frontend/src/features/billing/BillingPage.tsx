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
import { periodAmount, periodLine, periodStateText } from '@/features/month-close/periodText';
import { fetchOverview, overviewKeys } from '@/features/overview/api';
import { fetchSteering, reportKeys } from '@/features/reports/api';
import { currentReportYear } from '@/features/reports/years';
import { useInstance } from '@/layout/useInstance';
import { useRouterLinks } from '@/layout/useRouterLinks';
import { formatEuro } from '@/lib/format';
import { PATHS } from '@/paths';
import {
  EmptyNotice,
  FormSheet,
  LoadError,
  Loading,
  NoAccess,
  Page,
  Quiet,
  Stack,
} from '@/ui/layout';

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

/** A period someone has begun on: a month closed, or more than closing left to do. */
function started(row: Row): boolean {
  return (
    row.period.state !== 'to_close' || row.period.months.some((month) => month.state === 'closed')
  );
}

function complete(overview: BillingOverview): boolean {
  return (overview.terms.missing_details ?? []).length === 0;
}

function capital(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** The request a delivered period went out with, when the reader may open it. */
function deliveryLink({ period }: Row): string | null {
  const delivery = (period.deliveries ?? []).at(-1);
  if (!delivery?.may_open) return null;
  return PATHS.billingDelivery.replace(':deliveryId', delivery.id);
}

function link(row: Row): string {
  const { overview, period } = row;
  if (period.state === 'ready') return deliverPeriodPath(overview.assignment_id, period.key);
  const request = deliveryLink(row);
  if (request) return request;
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
  const thisYear = currentReportYear();
  // The same figure as the row on Geld; billing itself has no year.
  const open = useQuery({
    queryKey: overviewKeys.list(thisYear),
    queryFn: () => fetchOverview(thisYear),
    select: (overview) => overview.to_deliver_cents ?? 0,
  });
  const scope = useQuery({
    queryKey: reportKeys.steering(thisYear),
    queryFn: () => fetchSteering(thisYear),
    select: (steering) => steering.turnover?.scope,
  });
  const [asking, setAsking] = useState(false);
  const [via, setVia] = useState<'mail' | 'self'>('self');
  const [error, setError] = useState<string | null>(null);

  const all = rowsOf(across.data?.assignments ?? []);
  // What is under way is listed; periods nobody began on are one quiet line.
  const rows = all.filter(started);
  const untouched = all.length - rows.length;
  const nearest = rows.find((row) => row.period.state === 'to_close');
  const batch = rows.filter(
    (row) => row.period.state === 'ready' && row.overview.may_deliver && complete(row.overview),
  );
  const total = across.data?.ready_cents ?? 0;
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
  // Closed and ready, but the client's invoice address is not known yet.
  const held = rows.filter(
    (row) => row.period.state === 'ready' && row.overview.may_deliver && !complete(row.overview),
  ).length;
  // A naverrekening is a difference on a period delivered before, not a
  // period that is ready: it is named as what it is.
  // Ready, but for someone else to deliver: the reader watches here.
  const forOthers = rows.filter(
    (row) => row.period.state === 'ready' && !row.overview.may_deliver,
  ).length;
  const corrections = batch.filter((row) => row.period.correction).length;
  const toDeliver = open.data ?? 0;
  // What is realised but not ready yet: its period still has months to close.
  const notReady =
    toDeliver === 0 || held > 0 || forOthers > 0
      ? null
      : count === 0
        ? `De ${formatEuro(toDeliver)} die nog aan te leveren is, zit in perioden die nog niet helemaal zijn afgesloten.`
        : toDeliver > total
          ? `In totaal is ${formatEuro(toDeliver)} nog aan te leveren. De rest zit in perioden die nog niet helemaal zijn afgesloten.`
          : null;
  const title =
    count === 0
      ? 'Er staat nu niets klaar om aan te leveren'
      : corrections === count
        ? `${count} ${count === 1 ? 'naverrekening' : 'naverrekeningen'} aan te leveren: ${formatEuro(total)}`
        : corrections > 0
          ? `${count} perioden aan te leveren, waarvan ${corrections} als naverrekening: ${formatEuro(total)}`
          : `${count} ${count === 1 ? 'periode is' : 'perioden zijn'} klaar: ${formatEuro(total)}`;
  return (
    <div ref={containerRef}>
      <Page
        kind="list"
        title="Factureren"
        {...(scope.data
          ? {
              lead: `Wat er nu openstaat op ${scope.data === 'own' ? 'jouw' : 'alle'} opdrachten, over alle jaren.`,
            }
          : {})}
        instanceName={instance?.name}
        back={{ href: PATHS.money, text: 'Terug naar Geld' }}
        spacing="sections"
      >
        {across.isPending ? <Loading /> : null}
        {across.isError ? (
          <LoadError error={across.error} retry={() => void across.refetch()} />
        ) : null}
        {across.data && across.data.reads_money === false ? (
          <NoAccess who="Factureren is voor wie de bedragen van een opdracht mag zien: de eigenaar, een manager, de beheerder of een lezer." />
        ) : null}
        {across.data && across.data.reads_money !== false ? (
          <>
            {count > 0 ? (
              <Stack gap="related">
                <nldd-card background="tinted" accessible-label="Nu te doen">
                  <nldd-container padding="24" gap="16">
                    <nldd-title
                      size="display-2"
                      heading-level={2}
                      overline="Nu te doen"
                      text={title}
                    />
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
                  </nldd-container>
                </nldd-card>
                {notReady ? <Quiet>{notReady}</Quiet> : null}
              </Stack>
            ) : (
              <Stack gap="tight">
                <nldd-text>
                  <p>
                    {held === 0
                      ? forOthers === 0
                        ? `${title}.`
                        : forOthers === 1
                          ? '1 periode is klaar om aan te leveren. Dat doet de eigenaar of een manager van de opdracht.'
                          : `${forOthers} perioden zijn klaar om aan te leveren. Dat doet de eigenaar of een manager van de opdracht.`
                      : held === 1
                        ? '1 periode is afgesloten, maar het factuuradres ontbreekt nog.'
                        : `${held} perioden zijn afgesloten, maar het factuuradres ontbreekt nog.`}
                  </p>
                </nldd-text>
                {notReady ? <Quiet>{notReady}</Quiet> : null}
                {nearest && held === 0 && forOthers === 0 ? (
                  <Quiet>
                    Het dichtst bij: {nearest.overview.assignment_name}, {nearest.period.label},{' '}
                    {periodLine(nearest.period)}.
                  </Quiet>
                ) : null}
              </Stack>
            )}

            {rows.length > 0 ? (
              <Stack gap="related">
                <nldd-title size="display-4" heading-level={2} text="Perioden die lopen" />
                <nldd-table
                  accessible-label="Open perioden van alle opdrachten"
                  columns="minmax(220px,1.2fr) minmax(220px,1.4fr) 120px"
                  sm-columns="minmax(140px,1fr) minmax(100px,auto)"
                >
                  <nldd-table-row slot="header">
                    <nldd-text-cell text="Opdracht" />
                    <nldd-text-cell hide-below="md" text="Stand" />
                    <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
                  </nldd-table-row>
                  {rows.map((row) => {
                    const amount = periodAmount(row.period);
                    const ready = row.period.state === 'ready';
                    return (
                      <nldd-table-row key={`${row.overview.assignment_id}-${row.period.key}`}>
                        <nldd-cell row-header>
                          <nldd-container gap="4">
                            <nldd-link href={link(row)} text={row.overview.assignment_name} />
                            <Quiet>{capital(row.period.label)}</Quiet>
                          </nldd-container>
                        </nldd-cell>
                        <nldd-cell hide-below="md">
                          <nldd-container gap="4">
                            {row.period.state === 'to_close' ? null : (
                              <div>
                                <nldd-badge
                                  color={ready ? 'accent' : 'neutral'}
                                  text={periodStateText(row.period)}
                                />
                              </div>
                            )}
                            <nldd-text
                              size="sm"
                              color={ready && !complete(row.overview) ? 'warning' : 'secondary'}
                            >
                              <span>{remark(row)}</span>
                            </nldd-text>
                          </nldd-container>
                        </nldd-cell>
                        <nldd-text-cell
                          horizontal-alignment="right"
                          text={amount ? `**${formatEuro(amount)}**` : ''}
                          hide-above="sm"
                          supporting-text={periodStateText(row.period)}
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
            ) : null}
            {untouched > 0 ? (
              <Quiet>
                {untouched === 1
                  ? 'Van 1 periode die voorbij is, is nog geen maand afgesloten.'
                  : `Van ${untouched} perioden die voorbij zijn, is nog geen maand afgesloten.`}
              </Quiet>
            ) : null}
            {all.length === 0 ? (
              <EmptyNotice text="Alle perioden die voorbij zijn, zijn afgesloten en gefactureerd" />
            ) : null}
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
