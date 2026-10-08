import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams, useSearchParams } from 'react-router-dom';
import { errorMessage } from '@/api/client';
import { orUndef, useNlddEvent } from '@/components/nldd/events';
import { Button, TextInput } from '@/features/assignments/ui';
import { useAssignmentShell } from '@/features/assignments/shell';
import { formatDateTime } from '@/features/quotes/format';
import { DocumentLink, MenuAction } from '@/features/quotes/ui';
import { useInstance } from '@/layout/useInstance';
import { formatEuro, formatMonth, formatPercent } from '@/lib/format';
import { PageHeading } from '@/pages/PageHeading';
import { EmptyNotice, ErrorNotice, FormSheet, Loading, Quiet, Section, Stack } from '@/ui/layout';
import { BillingTotals, Invoices } from './BillingSection';
import {
  billingKey,
  closeMonth,
  createExport,
  exportCsvUrl,
  fetchBillingStatus,
  fetchExports,
  fetchMonth,
  fetchTimeline,
  monthKeys,
  normalisePercent,
  percentInput,
  reopenMonth,
  type BillingExport,
  type MonthBilling,
  type MonthDetail,
  type MonthLine,
  type MonthState,
} from './api';
import { billingStateRemark, billingStateText } from './billingText';
import { INVOICE_PARAM, MONTH_PARAM, monthsFromParam } from './paths';

function has(lines: MonthLine[], field: keyof MonthLine): boolean {
  return lines.some((line) => field in line);
}

function PercentCell({
  label,
  value,
  invalid,
  onChange,
}: {
  label: string;
  value: string;
  invalid: boolean;
  onChange: (value: string) => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useNlddEvent(ref, 'input', (event) => {
    const detail = (event as CustomEvent<{ value?: unknown }>).detail;
    const target = event.target as { value?: unknown } | null;
    onChange(String(detail?.value ?? target?.value ?? ''));
  });
  return (
    <nldd-cell>
      <nldd-text-field
        ref={ref}
        size="sm"
        width="96px"
        value={value}
        keyboard="decimal"
        accessible-label={label}
        invalid={orUndef(invalid)}
      />
    </nldd-cell>
  );
}

function MonthTable({
  detail,
  editable,
  edits,
  onEdit,
}: {
  detail: MonthDetail;
  editable: boolean;
  edits: Record<string, string>;
  onEdit: (allocationId: string, value: string) => void;
}) {
  const lines = detail.lines;
  const showPct = has(lines, 'planned_fte_pct');
  const showRate = has(lines, 'category');
  const showEstablished = showPct && (detail.closed || editable);
  const columns = [
    'minmax(160px,1.5fr)',
    'minmax(140px,1.2fr)',
    ...(showPct ? ['100px'] : []),
    ...(showEstablished ? ['130px'] : []),
    ...(showRate ? ['90px', 'minmax(110px,1fr)', 'minmax(110px,1fr)'] : []),
    ...(showRate && detail.closed ? ['minmax(110px,1fr)'] : []),
  ].join(' ');

  return (
    <nldd-table accessible-label={`Inzet in ${formatMonth(detail.month)}`} columns={columns}>
      <nldd-table-row slot="header">
        <nldd-text-cell text="Persoon" />
        <nldd-text-cell text="Rol" />
        {showPct ? <nldd-text-cell text="Gepland" horizontal-alignment="right" /> : null}
        {showEstablished ? (
          <nldd-text-cell text="Vastgesteld" horizontal-alignment="right" />
        ) : null}
        {showRate ? (
          <>
            <nldd-text-cell text="Categorie" />
            <nldd-text-cell text="Maandtarief" horizontal-alignment="right" />
            <nldd-text-cell text="Bedrag gepland" horizontal-alignment="right" />
          </>
        ) : null}
        {showRate && detail.closed ? (
          <nldd-text-cell text="Bedrag vastgesteld" horizontal-alignment="right" />
        ) : null}
      </nldd-table-row>
      {lines.map((line) => {
        const typed = edits[line.allocation_id];
        const value = typed ?? percentInput(line.planned_fte_pct);
        return (
          <nldd-table-row key={line.allocation_id}>
            <nldd-text-cell text={line.person_name} />
            <nldd-text-cell text={line.description} />
            {showPct ? (
              <nldd-text-cell
                text={formatPercent(line.planned_fte_pct)}
                horizontal-alignment="right"
              />
            ) : null}
            {showEstablished && editable ? (
              <PercentCell
                label={`Vastgesteld percentage van ${line.person_name}`}
                value={value}
                invalid={normalisePercent(value) === null}
                onChange={(next) => onEdit(line.allocation_id, next)}
              />
            ) : null}
            {showEstablished && !editable ? (
              <nldd-text-cell
                text={formatPercent(line.established_fte_pct)}
                horizontal-alignment="right"
              />
            ) : null}
            {showRate ? (
              <>
                <nldd-text-cell text={line.category ?? ''} />
                <nldd-text-cell
                  text={formatEuro(line.monthly_rate_cents)}
                  horizontal-alignment="right"
                />
                <nldd-text-cell
                  text={formatEuro(line.planned_amount_cents)}
                  horizontal-alignment="right"
                />
              </>
            ) : null}
            {showRate && detail.closed ? (
              <nldd-text-cell
                text={formatEuro(line.established_amount_cents)}
                horizontal-alignment="right"
              />
            ) : null}
          </nldd-table-row>
        );
      })}
    </nldd-table>
  );
}


/** The month's state in one word, as a label. */
function StateBadge({ state, billing }: { state: MonthState; billing: MonthBilling | undefined }) {
  if (billing?.state === 'invoiced') return <nldd-badge color="success" text="Gefactureerd" />;
  if (billing?.state === 'delivered') return <nldd-badge color="accent" text="Aangeleverd" />;
  if (state.closed) return <nldd-badge color="neutral" text="Afgesloten" />;
  if (state.closable) return <nldd-badge color="warning" text="Af te sluiten" />;
  return <nldd-badge color="neutral" text="Nog niet voorbij" />;
}

/** What happened to the month, in words. */
function stateLine(state: MonthState, billing: MonthBilling | undefined): string {
  if (billing && billing.state !== 'not_delivered') return billingStateText(billing);
  if (state.closed) {
    return `Afgesloten op ${formatDateTime(state.closed_at)}${state.closed_by_name ? ` door ${state.closed_by_name}` : ''}`;
  }
  return '';
}

interface MonthRowProps {
  state: MonthState;
  billing: MonthBilling | undefined;
  selected: boolean;
  mayClose: boolean;
  mayDeliver: boolean;
  mayRecord: boolean;
  csvUrl: string | null;
  busy: boolean;
  onShow: () => void;
  onDeliver: () => void;
  onRecord: () => void;
}

/**
 * One month in the timeline. It carries the next step of that month, and
 * only when there is one: close it, deliver its billing data, record the
 * invoice. A month that is not over has no action.
 */
function MonthRow({
  state,
  billing,
  selected,
  mayClose,
  mayDeliver,
  mayRecord,
  csvUrl,
  busy,
  onShow,
  onDeliver,
  onRecord,
}: MonthRowProps) {
  const name = formatMonth(state.month);
  const remark = billing ? billingStateRemark(billing) : null;
  const toClose = !state.closed && state.closable && mayClose && !selected;
  const toDeliver = state.closed && mayDeliver && (!billing || billing.state === 'not_delivered');
  const toRecord = billing?.state === 'delivered' && mayRecord;
  const amount = billing?.invoiced_cents ?? billing?.delivered_cents ?? billing?.deliverable_cents;
  return (
    <nldd-table-row {...(selected ? { 'aria-current': 'true' } : {})}>
      <nldd-text-cell
        text={name}
        {...(state.reopen_count > 0
          ? { 'supporting-text': `${state.reopen_count} keer heropend` }
          : {})}
      />
      <nldd-cell>
        <StateBadge state={state} billing={billing} />
      </nldd-cell>
      <nldd-text-cell
        text={stateLine(state, billing)}
        {...(remark ? { 'supporting-text': remark, color: 'warning' } : {})}
      />
      <nldd-text-cell
        text={amount === null || amount === undefined ? '' : formatEuro(amount)}
        horizontal-alignment="right"
      />
      <nldd-cell>
        <nldd-container layout="row" gap="8" vertical-alignment="center">
          {toClose ? (
            <Button size="sm" text="Sluit af" accessibleLabel={`Sluit ${name} af`} onClick={onShow} />
          ) : null}
          {toDeliver ? (
            <Button
              size="sm"
              text="Lever aan"
              accessibleLabel={`Lever de factuurgegevens van ${name} aan`}
              disabled={busy}
              onClick={onDeliver}
            />
          ) : null}
          {toRecord ? (
            <Button
              size="sm"
              text="Leg factuur vast"
              accessibleLabel={`Leg de factuur van ${name} vast`}
              onClick={onRecord}
            />
          ) : null}
          {state.closed && !selected ? (
            <nldd-icon-button icon="more" size="sm" text={`Meer over ${name}`}>
              <nldd-menu slot="popup" placement="bottom-end">
                <MenuAction text="Bekijk de inzet" onSelect={onShow} />
              </nldd-menu>
            </nldd-icon-button>
          ) : null}
          {csvUrl && selected ? <DocumentLink href={csvUrl} text="CSV" /> : null}
        </nldd-container>
      </nldd-cell>
    </nldd-table-row>
  );
}

/**
 * The monthly close of one assignment: establish the actual inzet per
 * month, deliver the billing data, record the invoice. The oldest month
 * that should be closed leads; each closed month carries its next step.
 */
export function MonthClosePage() {
  const { assignmentId = '' } = useParams();
  const shell = useAssignmentShell();
  const [searchParams, setSearchParams] = useSearchParams();
  const instance = useInstance();
  const queryClient = useQueryClient();

  const timeline = useQuery({
    queryKey: monthKeys.timeline(assignmentId),
    queryFn: () => fetchTimeline(assignmentId),
  });
  const started = timeline.data?.closing_started ?? false;
  const months = timeline.data?.months ?? [];
  const mayClose = timeline.data?.may_close ?? false;
  const due = months.filter((m) => !m.closed && m.closable);
  const requested = searchParams.get(MONTH_PARAM);
  // Without a choice: the oldest month that waits to be closed.
  const selected =
    months.find((m) => m.month === requested)?.month ??
    (mayClose ? due[0]?.month : undefined) ??
    null;

  const billing = useQuery({
    queryKey: billingKey(assignmentId),
    queryFn: () => fetchBillingStatus(assignmentId),
    enabled: started,
  });
  const detail = useQuery({
    queryKey: monthKeys.detail(assignmentId, selected ?? ''),
    queryFn: () => fetchMonth(assignmentId, selected ?? ''),
    enabled: started && selected !== null,
  });
  const exports = useQuery({
    queryKey: monthKeys.exports(assignmentId),
    queryFn: () => fetchExports(assignmentId),
    enabled: started,
  });

  const [edits, setEdits] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [reopening, setReopening] = useState(false);
  const [reason, setReason] = useState('');
  const [reopenError, setReopenError] = useState<string | null>(null);
  const [recordFor, setRecordFor] = useState<string[] | null>(null);
  // The address can ask to record an invoice for some months.
  const fromAddress = monthsFromParam(searchParams.get(INVOICE_PARAM));
  const recording = recordFor ?? (fromAddress.length > 0 ? fromAddress : null);

  const select = (month: string) => {
    setEdits({});
    setError(null);
    setSearchParams({ [MONTH_PARAM]: month }, { replace: true });
  };

  const run = useMutation({
    mutationFn: (action: () => Promise<unknown>) => action(),
    onSuccess: async () => {
      setEdits({});
      setError(null);
      setReopening(false);
      await queryClient.invalidateQueries({ queryKey: ['months', assignmentId] });
      await queryClient.invalidateQueries({ queryKey: ['assignments'] });
      await queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
    onError: (failure) => setError(errorMessage(failure)),
  });

  const data = detail.data;
  const status = billing.data;
  const billingOf = (month: string) => status?.months?.find((m) => m.month === month);
  const latestExport = (month: string): BillingExport | undefined =>
    exports.data?.exports.find((entry) => entry.month === month);
  const editable = Boolean(data && !data.closed && data.may_close);
  const anyClosed = months.some((m) => m.closed);
  const showBilling = Boolean(status?.billable && anyClosed && status.delivered_cents !== undefined);
  const mayDeliver = Boolean(status?.billable && mayClose);
  const name = timeline.data?.assignment_name;
  const title = name ? `Maandafsluiting ${name}` : 'Maandafsluiting';

  const close = () => {
    if (!data || !selected) return;
    const established: { allocation_id: string; fte_pct: string }[] = [];
    for (const line of data.lines) {
      const typed = edits[line.allocation_id];
      if (typed === undefined) continue;
      const pct = normalisePercent(typed);
      if (pct === null) {
        setError(
          `Het vastgestelde percentage van ${line.person_name} is geen getal tussen 0 en 100.`,
        );
        return;
      }
      if (Number(pct) !== Number(line.planned_fte_pct)) {
        established.push({ allocation_id: line.allocation_id, fte_pct: pct });
      }
    }
    run.mutate(() => closeMonth(assignmentId, selected, established));
  };

  const csvOf = (month: string): string | null => {
    const entry = latestExport(month);
    return entry && entry.lines.some((line) => 'amount_cents' in line)
      ? exportCsvUrl(entry.id)
      : null;
  };

  return (
    <>
      <nldd-simple-section>
        {/* Inside the tabs of an assignment the shell shows the name and the way back. */}
        {shell ? null : <PageHeading text={title} instanceName={instance?.name} />}
        <Stack gap="group">
          {timeline.isPending ? <Loading /> : null}
          {timeline.isError ? <ErrorNotice message={errorMessage(timeline.error)} /> : null}

          {timeline.data && !started ? (
            <EmptyNotice text="Maanden afsluiten kan zodra er een akkoord is" />
          ) : null}
          {timeline.data && started && months.length === 0 ? (
            <EmptyNotice
              text="Deze opdracht heeft nog geen maanden"
              supportingText="Geef de opdracht een periode of zet iemand in."
            />
          ) : null}

          {started && error ? <ErrorNotice message={error} /> : null}

          {started && selected && data ? (
            <Section
              title={
                data.closed ? `${formatMonth(selected)}` : `${formatMonth(selected)} afsluiten`
              }
              level={2}
            >
              {data.pricing_problem ? (
                <nldd-banner
                  variant="warning"
                  size="sm"
                  text="De bedragen van deze maand kunnen niet worden berekend"
                  supporting-text={data.pricing_problem}
                />
              ) : null}
              {data.lines.length > 0 ? (
                <MonthTable
                  detail={data}
                  editable={editable}
                  edits={edits}
                  onEdit={(id, value) => setEdits((current) => ({ ...current, [id]: value }))}
                />
              ) : (
                <EmptyNotice text="In deze maand is niemand ingezet" />
              )}
              {data.planned_total_cents !== undefined ? (
                <Quiet>
                  Gepland {formatEuro(data.planned_total_cents)}
                  {data.established_total_cents !== null &&
                  data.established_total_cents !== undefined
                    ? ` · vastgesteld ${formatEuro(data.established_total_cents)}`
                    : ''}
                  {data.closed
                    ? ` · afgesloten op ${formatDateTime(data.closed_at)}${data.closed_by_name ? ` door ${data.closed_by_name}` : ''}`
                    : ''}
                </Quiet>
              ) : null}
              {data.may_close || data.may_reopen ? (
                <nldd-button-group>
                  {data.may_close ? (
                    <Button
                      text={`Sluit ${formatMonth(selected)} af`}
                      appearance="primary"
                      loading={run.isPending && !reopening}
                      onClick={close}
                    />
                  ) : null}
                  {data.may_reopen ? (
                    <Button
                      text="Heropen"
                      accessibleLabel={`Heropen ${formatMonth(selected)}`}
                      onClick={() => {
                        setReopenError(null);
                        setReopening(true);
                      }}
                    />
                  ) : null}
                </nldd-button-group>
              ) : null}
              {data.history.some((record) => record.reopened_at) ? (
                <nldd-table
                  accessible-label="Eerdere afsluitingen van deze maand"
                  columns="minmax(160px,1fr) minmax(160px,1fr) minmax(200px,2fr)"
                >
                  <nldd-table-row slot="header">
                    <nldd-text-cell text="Afgesloten" />
                    <nldd-text-cell text="Heropend" />
                    <nldd-text-cell text="Reden" />
                  </nldd-table-row>
                  {data.history
                    .filter((record) => record.reopened_at)
                    .map((record) => (
                      <nldd-table-row key={record.closed_at}>
                        <nldd-text-cell
                          text={formatDateTime(record.closed_at)}
                          {...(record.closed_by_name
                            ? { 'supporting-text': record.closed_by_name }
                            : {})}
                        />
                        <nldd-text-cell
                          text={formatDateTime(record.reopened_at)}
                          {...(record.reopened_by_name
                            ? { 'supporting-text': record.reopened_by_name }
                            : {})}
                        />
                        <nldd-text-cell text={record.reopen_reason ?? ''} />
                      </nldd-table-row>
                    ))}
                </nldd-table>
              ) : null}
            </Section>
          ) : null}
          {started && selected && detail.isPending ? <Loading /> : null}
          {started && selected && detail.isError ? (
            <ErrorNotice message={errorMessage(detail.error)} />
          ) : null}

          {started && months.length > 0 ? (
            <Section title="Maanden" level={2}>
              <nldd-table
                accessible-label="Maanden van de opdracht"
                columns="minmax(130px,1fr) 150px minmax(240px,2.4fr) minmax(110px,1fr) minmax(170px,1.2fr)"
              >
                <nldd-table-row slot="header">
                  <nldd-text-cell text="Maand" />
                  <nldd-text-cell text="Stand" />
                  <nldd-text-cell text="Laatste stap" />
                  <nldd-text-cell text="Bedrag" horizontal-alignment="right" />
                  <nldd-text-cell text="Volgende stap" />
                </nldd-table-row>
                {months.map((state) => (
                  <MonthRow
                    key={state.month}
                    state={state}
                    billing={billingOf(state.month)}
                    selected={state.month === selected}
                    mayClose={mayClose}
                    mayDeliver={mayDeliver}
                    mayRecord={Boolean(status?.may_record_invoice)}
                    csvUrl={csvOf(state.month)}
                    busy={run.isPending}
                    onShow={() => select(state.month)}
                    onDeliver={() => run.mutate(() => createExport(assignmentId, state.month))}
                    onRecord={() => setRecordFor([state.month])}
                  />
                ))}
              </nldd-table>
              {showBilling && status ? <BillingTotals status={status} /> : null}
            </Section>
          ) : null}

          {started && status && status.delivered_cents !== undefined ? (
            <Invoices
              assignmentId={assignmentId}
              status={status}
              recordFor={recording}
              onRecordDone={() => {
                setRecordFor(null);
                if (fromAddress.length > 0) {
                  const next = new URLSearchParams(searchParams);
                  next.delete(INVOICE_PARAM);
                  setSearchParams(next, { replace: true });
                }
              }}
            />
          ) : null}
        </Stack>
      </nldd-simple-section>

      <FormSheet
        open={reopening}
        title="Maand heropenen"
        submitText="Heropen"
        busy={run.isPending && reopening}
        error={reopenError}
        onClose={() => setReopening(false)}
        onSubmit={() => {
          if (!selected) return;
          if (!reason.trim()) {
            setReopenError('Geef een reden voor het heropenen.');
            return;
          }
          run.mutate(() => reopenMonth(assignmentId, selected, reason.trim()), {
            onSuccess: () => setReason(''),
            onError: (failure) => setReopenError(errorMessage(failure)),
          });
        }}
      >
        <nldd-text>
          Na heropenen telt deze maand weer met de geplande inzet, tot de maand opnieuw wordt
          afgesloten. De eerdere afsluiting en de reden blijven bewaard.
        </nldd-text>
        <TextInput label="Reden" value={reason} onChange={setReason} required multiline />
      </FormSheet>
    </>
  );
}
