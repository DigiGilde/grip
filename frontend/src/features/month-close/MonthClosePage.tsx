import { Fragment, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams, useSearchParams } from 'react-router-dom';
import { useNlddEvent } from '@/components/nldd/events';
import { Button } from '@/features/assignments/ui';
import { useAssignmentShell } from '@/features/assignments/shell';
import { formatDate, formatEuro } from '@/lib/format';
import { useInstance } from '@/layout/useInstance';
import { PageHeading } from '@/pages/PageHeading';
import { OpenRow, RowActions, ROW_ACTIONS_COLUMN, type RowAction } from '@/ui/RowActions';
import { EmptyNotice, LoadError, Loading, Quiet, Stack } from '@/ui/layout';
import { Invoices } from './BillingSection';
import { billingKey, fetchBillingStatus } from './api';
import {
  billingOverviewKey,
  deliveryCsvUrl,
  deliveryDocumentUrl,
  fetchBillingOverview,
  type BillingOverview,
  type BillingPeriod,
  type PeriodMonth,
} from './billingApi';
import { DeliverSheet, PeriodInvoiceSheet, TermsSheet } from './BillingSheets';
import { MonthSheet } from './MonthSheet';
import { INVOICE_PARAM, MONTH_PARAM, PERIOD_PARAM, monthsFromParam } from './paths';
import {
  PERIOD_STATE_COLOR,
  periodStateText,
  RHYTHM_TEXT,
  periodAmount,
  periodLine,
  periodName,
  stepAction,
  stepLine,
  stepTitle,
} from './periodText';

const COLUMNS = `minmax(200px,2fr) 210px minmax(180px,2fr) minmax(120px,1fr) ${ROW_ACTIONS_COLUMN}`;
const NARROW_COLUMNS = `minmax(140px,1fr) minmax(100px,auto) ${ROW_ACTIONS_COLUMN}`;

function euro(cents: number | null | undefined): string {
  return cents === null || cents === undefined ? '' : formatEuro(cents);
}

/** Where a month stands, as words in its own row. */
function monthLine(month: PeriodMonth): string {
  if (month.state === 'closed') {
    const who = month.closed_by_name ? ` door ${month.closed_by_name}` : '';
    const correction = (month.correction_cents ?? 0) !== 0 ? ' · gewijzigd na de aanlevering' : '';
    return `Afgesloten op ${formatDate(month.closed_at)}${who}${correction}`;
  }
  if (month.state === 'to_close') return 'Af te sluiten';
  if (month.state === 'running') return 'Loopt nog';
  return '';
}

interface NowProps {
  overview: BillingOverview;
  onAct: () => void;
}

/**
 * The work of the step the head of the assignment names. It is the first
 * thing on the tab and carries the only accent: its button. With nothing due it says so, and
 * names when the next thing comes.
 */
function Now({ overview, onAct }: NowProps) {
  const step = overview.next_step;
  const may =
    (step.kind === 'close_month' && overview.may_close) ||
    (step.kind === 'deliver' && overview.may_deliver) ||
    (step.kind === 'record_invoice' && overview.may_record_invoice);
  const waiting = step.kind !== 'none' && !may;
  if (waiting) {
    // Someone who cannot act gets no call to act: what is open, and who can.
    const period = step.period_label ? periodName(step.period_label, true) : 'De periode';
    const month = step.month_label ?? 'de maand';
    const open =
      step.kind === 'close_month'
        ? `${month.charAt(0).toUpperCase()}${month.slice(1)} is nog niet afgesloten.`
        : step.kind === 'deliver'
          ? `${period} is afgesloten en nog niet aangeleverd.`
          : `${period} is aangeleverd; de factuur is nog niet vastgelegd.`;
    return (
      <div data-waiting>
        <Stack gap="tight">
          <nldd-text>{open}</nldd-text>
          <Quiet>Dit kan de eigenaar of een manager van de opdracht.</Quiet>
        </Stack>
      </div>
    );
  }
  return (
    <nldd-card
      background="tinted"
      accessible-label={step.kind === 'none' ? 'Stand' : stepTitle(step)}
    >
      <nldd-container padding="24" gap="16">
        {/* The head of the assignment says what to do now; this is the work. */}
        <nldd-title
          size={3}
          heading-level={2}
          text={stepTitle(step)}
          supporting-text={stepLine(step, overview)}
        />
        {may ? (
          <nldd-button-group>
            <Button appearance="primary" text={stepAction(step)} onClick={onAct} />
          </nldd-button-group>
        ) : null}
      </nldd-container>
    </nldd-card>
  );
}

/** Three small figures over the whole assignment; one that says nothing is left out. */
function Figures({ overview }: { overview: BillingOverview }) {
  const figures = [
    { label: 'Afgesloten', cents: overview.closed_cents },
    { label: 'Aangeleverd', cents: overview.delivered_cents },
    { label: 'Gefactureerd', cents: overview.invoiced_cents },
  ].filter((figure) => figure.cents);
  if (figures.length === 0) return null;
  return (
    <nldd-text size="sm" color="secondary">
      {figures.map((figure, index) => (
        <Fragment key={figure.label}>
          {index > 0 ? ' · ' : ''}
          {figure.label} <strong>{euro(figure.cents)}</strong>
        </Fragment>
      ))}
    </nldd-text>
  );
}

/** A link in a sentence that acts in place instead of leaving the page. */
function InlineAction({ text, onAct }: { text: string; onAct: () => void }) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'click', (event) => {
    event.preventDefault();
    onAct();
  });
  return <nldd-link ref={ref} href="#" text={text} size="sm" />;
}

interface PeriodRowsProps {
  overview: BillingOverview;
  period: BillingPeriod;
  /** The period the one thing to do now is in: the only row that stands out. */
  isNext: boolean;
  expanded: boolean;
  onToggle: () => void;
  onMonth: (month: string) => void;
  onDeliver: () => void;
  onInvoice: () => void;
}

/**
 * A billing period as one line to scan: which period, where it stands, the
 * last step and the amount. Its months are detail and show on demand. A
 * period of one month is the month itself and opens it.
 */
function PeriodRows({
  overview,
  period,
  isNext,
  expanded,
  onToggle,
  onMonth,
  onDeliver,
  onInvoice,
}: PeriodRowsProps) {
  const single = period.months.length === 1 && overview.terms.rhythm === 'month';
  const delivery = (period.deliveries ?? []).at(-1);
  const actions: RowAction[] = [];
  if (period.state === 'ready' && overview.may_deliver && overview.billable) {
    actions.push({ text: 'Lever aan', onSelect: onDeliver });
  }
  if (period.awaits_invoice && overview.may_record_invoice) {
    actions.push({ text: 'Leg factuur vast', onSelect: onInvoice });
  }
  if (delivery?.has_document) {
    actions.push({ text: 'Bekijk factuurverzoek (pdf)', href: deliveryDocumentUrl(delivery.id) });
    actions.push({ text: 'Download als bestand (csv)', href: deliveryCsvUrl(delivery.id) });
  }
  const amount = periodAmount(period);
  const done = period.state === 'invoiced';
  const open = single ? () => onMonth(period.months[0]?.month ?? '') : onToggle;
  return (
    <>
      <OpenRow onOpen={open}>
        <nldd-text-cell
          text={`**${period.label.charAt(0).toUpperCase()}${period.label.slice(1)}**`}
          {...(period.months.length > 1 ? { 'supporting-text': period.span } : {})}
          {...(done ? { color: 'secondary' } : {})}
        />
        <nldd-cell hide-below="md">
          <nldd-badge
            color={isNext ? PERIOD_STATE_COLOR[period.state] : 'neutral'}
            text={periodStateText(period)}
          />
        </nldd-cell>
        <nldd-text-cell hide-below="md" size="sm" color="secondary" text={periodLine(period)} />
        <nldd-text-cell
          horizontal-alignment="right"
          text={amount ? `**${euro(amount)}**` : ''}
          {...(done ? { color: 'secondary' } : {})}
          hide-above="sm"
          supporting-text={periodStateText(period)}
        />
        <nldd-text-cell
          hide-below="md"
          horizontal-alignment="right"
          text={amount ? `**${euro(amount)}**` : ''}
          {...(done ? { color: 'secondary' } : {})}
        />
        <RowActions name={period.label} actions={actions} />
      </OpenRow>
      {expanded && !single
        ? period.months.map((month) => (
            <OpenRow key={month.month} onOpen={() => onMonth(month.month)}>
              <nldd-cell>
                <nldd-container padding-left="24">
                  <nldd-text size="sm" color="secondary">
                    {month.label}
                  </nldd-text>
                </nldd-container>
              </nldd-cell>
              <nldd-cell hide-below="md" />
              <nldd-text-cell hide-below="md" size="sm" color="secondary" text={monthLine(month)} />
              <nldd-text-cell
                size="sm"
                color="secondary"
                horizontal-alignment="right"
                text={euro(month.amount_cents)}
              />
              <nldd-cell />
            </OpenRow>
          ))
        : null}
    </>
  );
}

/**
 * Closing and billing of one assignment. Two acts with their own rhythm:
 * a month is settled soon after it ends; a billing period, a month or a
 * quarter by the agreement, goes to the financial administration once all
 * its months are settled. The tab leads with the one thing to do now, shows
 * the periods as the course, and keeps months and people for on demand.
 */
export function MonthClosePage() {
  const { assignmentId = '' } = useParams();
  const shell = useAssignmentShell();
  const instance = useInstance();
  const [searchParams, setSearchParams] = useSearchParams();

  const overview = useQuery({
    queryKey: billingOverviewKey(assignmentId),
    queryFn: () => fetchBillingOverview(assignmentId),
  });
  const data = overview.data;
  const started = data?.closing_started ?? false;
  const status = useQuery({
    queryKey: billingKey(assignmentId),
    queryFn: () => fetchBillingStatus(assignmentId),
    enabled: started,
  });

  const [toggled, setToggled] = useState<Record<string, boolean>>({});
  const [delivering, setDelivering] = useState<string | null>(null);
  const [invoicing, setInvoicing] = useState<string | null>(null);
  const [terms, setTerms] = useState(false);
  const [correcting, setCorrecting] = useState<string[] | null>(null);

  const setParam = (name: string, value: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (value === null) next.delete(name);
    else next.set(name, value);
    setSearchParams(next, { replace: true });
  };
  const month = searchParams.get(MONTH_PARAM);
  // An address can ask for a step: a period to deliver, months to invoice.
  const periodFromAddress = searchParams.get(PERIOD_PARAM);
  const invoiceMonths = monthsFromParam(searchParams.get(INVOICE_PARAM));

  const periods = data?.periods ?? [];
  const step = data?.next_step;
  const find = (key: string | null) => periods.find((period) => period.key === key) ?? null;
  const periodOfMonth = (wanted: string | null | undefined) =>
    periods.find((period) => period.months.some((entry) => entry.month === wanted)) ?? null;
  // Open by default: only the period the next step is in.
  const current =
    step?.period_key ?? periodOfMonth(step?.month)?.key ?? periods.at(-1)?.key ?? null;
  const isExpanded = (key: string) => toggled[key] ?? key === current;

  const act = () => {
    if (!step) return;
    if (step.kind === 'close_month' && step.month) setParam(MONTH_PARAM, step.month);
    if (step.kind === 'deliver') setDelivering(step.period_key);
    if (step.kind === 'record_invoice') setInvoicing(step.period_key);
  };

  const invoiceFromAddress = periodOfMonth(invoiceMonths[0])?.key ?? null;
  const deliverKey =
    delivering ?? (periodFromAddress && data?.may_deliver ? periodFromAddress : null);
  const deliverTarget = find(deliverKey);
  const invoiceTarget = find(invoicing ?? invoiceFromAddress);
  const title = data
    ? `Afsluiten en factureren ${data.assignment_name}`
    : 'Afsluiten en factureren';
  const invoices = status.data?.invoices ?? [];
  const client = data?.terms.details?.organisation ?? data?.client_name;

  return (
    <>
      <nldd-simple-section>
        {/* Inside the tabs of an assignment the shell shows the name and the way back. */}
        {shell ? null : <PageHeading text={title} instanceName={instance?.name} />}
        {overview.isPending ? <Loading /> : null}
        {overview.isError ? (
          <LoadError error={overview.error} retry={() => void overview.refetch()} />
        ) : null}
        {data && !started ? (
          <EmptyNotice text="Maanden afsluiten kan zodra er een akkoord is" />
        ) : null}
        {data && started && periods.length === 0 && data.upcoming_count === 0 ? (
          <EmptyNotice
            text="Deze opdracht heeft nog geen maanden"
            supportingText="Geef de opdracht een periode of zet iemand in."
          />
        ) : null}

        {data && started && (periods.length > 0 || data.upcoming_count > 0) ? (
          <Stack gap="section">
            <Now overview={data} onAct={act} />

            <Stack gap="related">
              <Stack gap="tight">
                <nldd-title size={4} heading-level={2} text="Perioden" />
                <Figures overview={data} />
              </Stack>
              {periods.length > 0 ? (
                <nldd-table
                  accessible-label="Perioden van de opdracht"
                  columns={COLUMNS}
                  sm-columns={NARROW_COLUMNS}
                >
                  <nldd-table-row slot="header">
                    <nldd-text-cell text="Periode" />
                    <nldd-text-cell hide-below="md" text="Stand" />
                    <nldd-text-cell hide-below="md" text="Laatste stap" />
                    <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
                    <nldd-cell />
                  </nldd-table-row>
                  {periods.map((period) => (
                    <Fragment key={period.key}>
                      <PeriodRows
                        overview={data}
                        period={period}
                        isNext={period.key === current && data.next_step.kind !== 'none'}
                        expanded={isExpanded(period.key)}
                        onToggle={() =>
                          setToggled((now) => ({ ...now, [period.key]: !isExpanded(period.key) }))
                        }
                        onMonth={(wanted) => setParam(MONTH_PARAM, wanted)}
                        onDeliver={() => setDelivering(period.key)}
                        onInvoice={() => setInvoicing(period.key)}
                      />
                    </Fragment>
                  ))}
                </nldd-table>
              ) : null}
              <nldd-text size="sm" color="secondary">
                {[
                  data.upcoming_count > 0
                    ? `Nog ${data.upcoming_count} ${
                        data.terms.rhythm === 'quarter'
                          ? data.upcoming_count === 1
                            ? 'kwartaal'
                            : 'kwartalen'
                          : data.upcoming_count === 1
                            ? 'maand'
                            : 'maanden'
                      } te gaan, t/m ${data.upcoming_until ?? ''}`
                    : null,
                  `Factureren ${RHYTHM_TEXT[data.terms.rhythm]}`,
                  client && data.terms.details ? `factuur aan ${client}` : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
                {data.may_edit_terms ? (
                  <>
                    {' · '}
                    <InlineAction text="Wijzig factuurafspraken" onAct={() => setTerms(true)} />
                  </>
                ) : null}
              </nldd-text>
            </Stack>

            {status.data && invoices.length > 0 ? (
              <Invoices
                assignmentId={assignmentId}
                status={status.data}
                recordFor={correcting}
                onRecordDone={() => setCorrecting(null)}
              />
            ) : null}
          </Stack>
        ) : null}
      </nldd-simple-section>

      <MonthSheet
        assignmentId={assignmentId}
        month={started ? month : null}
        onClose={() => setParam(MONTH_PARAM, null)}
      />
      {data ? (
        <>
          <DeliverSheet
            overview={data}
            period={deliverTarget?.state === 'ready' ? deliverTarget : null}
            onClose={() => {
              setDelivering(null);
              if (periodFromAddress) setParam(PERIOD_PARAM, null);
            }}
          />
          <PeriodInvoiceSheet
            overview={data}
            period={invoiceTarget?.awaits_invoice && data.may_record_invoice ? invoiceTarget : null}
            onClose={() => {
              setInvoicing(null);
              if (invoiceMonths.length > 0) setParam(INVOICE_PARAM, null);
            }}
          />
          <TermsSheet overview={data} open={terms} onClose={() => setTerms(false)} />
        </>
      ) : null}
    </>
  );
}
